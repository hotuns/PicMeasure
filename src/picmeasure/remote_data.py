"""Read device image records from THCPN and download their OSS objects."""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from urllib.request import urlopen

import pymysql
from pymysql.cursors import DictCursor

TABLE_NAME = re.compile(r"^device_data_\d+$")
CONFIG_FILENAME = "remote_config.json"


@dataclass(frozen=True)
class RemoteSettings:
    """Connection settings for the existing THCPN store."""

    host: str
    port: int
    user: str
    password: str
    database: str
    oss_base_url: str


def load_remote_settings() -> RemoteSettings:
    """Load settings from the project or packaged executable directory."""
    application_dir = (
        Path(sys.executable).resolve().parent
        if getattr(sys, "frozen", False)
        else Path.cwd()
    )
    config_path = Path(
        os.environ.get("PICMEASURE_REMOTE_CONFIG", application_dir / CONFIG_FILENAME)
    )
    raw: dict[str, Any] = {}
    if config_path.is_file():
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    source = raw.get("thcpn", raw.get("source", {}))
    return RemoteSettings(
        host=os.environ.get("PICMEASURE_DB_HOST", source.get("host", "")),
        port=int(os.environ.get("PICMEASURE_DB_PORT", source.get("port", 3306))),
        user=os.environ.get("PICMEASURE_DB_USER", source.get("user", "")),
        password=os.environ.get("PICMEASURE_DB_PASSWORD", source.get("password", "")),
        database=os.environ.get(
            "PICMEASURE_DB_NAME", source.get("database", source.get("db", "thcpn"))
        ),
        oss_base_url=os.environ.get(
            "PICMEASURE_OSS_BASE_URL", raw.get("oss_base_url", raw.get("oss", {}).get("base_url", ""))
        ).rstrip("/")
        + "/",
    )


def _connect(settings: RemoteSettings) -> pymysql.Connection:
    if not all((settings.host, settings.user, settings.database, settings.oss_base_url)):
        raise RuntimeError(
            f"远程数据配置不完整，请在程序目录配置 {CONFIG_FILENAME}"
        )
    return pymysql.connect(
        host=settings.host,
        port=settings.port,
        user=settings.user,
        password=settings.password,
        database=settings.database,
        charset="utf8mb4",
        cursorclass=DictCursor,
        connect_timeout=8,
        read_timeout=15,
    )


def _image_item(row: dict[str, Any], table: str) -> dict[str, Any] | None:
    data = row.get("data")
    if isinstance(data, str):
        data = json.loads(data)
    if not isinstance(data, dict):
        return None
    for key, entry in data.items():
        path = entry.get("value") if isinstance(entry, dict) else entry
        if isinstance(path, str) and path.lower().endswith((".jpg", ".jpeg", ".png")):
            ts = row["ts"]
            return {
                "record_id": int(row["id"]),
                "table": table,
                "key": key,
                "path": path,
                "timestamp": ts.isoformat(sep=" ") if isinstance(ts, datetime) else str(ts),
            }
    return None


def list_capture_groups(
    device_id: int,
    limit: int = 30,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """Return image capture rounds for one device, optionally within a date range."""
    range_start = (
        datetime.combine(datetime.fromisoformat(start_date).date(), time.min)
        if start_date
        else None
    )
    range_end = (
        datetime.combine(datetime.fromisoformat(end_date).date() + timedelta(days=1), time.min)
        if end_date
        else None
    )
    settings = load_remote_settings()
    with _connect(settings) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT id, name, status FROM devices WHERE id=%s", (device_id,))
        device = cursor.fetchone()
        if device is None:
            raise ValueError(f"设备 {device_id} 不存在")
        cursor.execute(
            "SELECT tb_name FROM device_data_index ORDER BY end_at DESC, id DESC"
        )
        tables = [row["tb_name"] for row in cursor.fetchall()]
        records: list[dict[str, Any]] = []
        target = max(80, limit * 8)
        for table in tables:
            if not TABLE_NAME.fullmatch(table):
                continue
            if range_start is not None and range_end is not None:
                cursor.execute(
                    f"SELECT id, data, ts FROM `{table}` "
                    "WHERE device_id=%s AND type='image' AND ts >= %s AND ts < %s "
                    "ORDER BY ts DESC, id DESC",
                    (device_id, range_start, range_end),
                )
            else:
                cursor.execute(
                    f"SELECT id, data, ts FROM `{table}` "
                    "WHERE device_id=%s AND type='image' ORDER BY ts DESC, id DESC LIMIT %s",
                    (device_id, target),
                )
            records.extend(
                item
                for row in cursor.fetchall()
                if (item := _image_item(row, table)) is not None
            )
            if range_start is None and len(records) >= target:
                break

    records.sort(key=lambda item: item["timestamp"])
    groups: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    for item in records:
        item_time = datetime.fromisoformat(item["timestamp"])
        repeated = any(existing["key"] == item["key"] for existing in current)
        gap = (
            (item_time - datetime.fromisoformat(current[-1]["timestamp"])).total_seconds()
            if current
            else 0
        )
        if current and (repeated or gap > 90):
            groups.append(_capture_group(device_id, current))
            current = []
        current.append(item)
    if current:
        groups.append(_capture_group(device_id, current))
    groups.reverse()
    return {
        "device": {"id": int(device["id"]), "name": device["name"], "status": device["status"]},
        "captures": groups if range_start is not None else groups[:limit],
    }


def _capture_group(device_id: int, records: list[dict[str, Any]]) -> dict[str, Any]:
    images = {record["key"]: record for record in records}
    anchor = records[0]
    return {
        "id": f"{device_id}-{anchor['table']}-{anchor['record_id']}",
        "device_id": device_id,
        "captured_at": anchor["timestamp"],
        "images": images,
        "stereo_ready": "key2" in images and "key3" in images,
    }


def download_remote_image(device_id: int, path: str) -> bytes:
    """Download one image while keeping a device scoped object path."""
    normalized = "/" + path.lstrip("/")
    if not normalized.startswith(f"/{device_id}/"):
        raise ValueError("图片路径与设备不匹配")
    settings = load_remote_settings()
    with urlopen(urljoin(settings.oss_base_url, normalized.lstrip("/")), timeout=30) as response:
        return response.read()
