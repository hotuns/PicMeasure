#!/bin/sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT_DIR"

uv run pyinstaller \
  --noconfirm \
  --clean \
  --onedir \
  --name PicMeasure \
  --add-data "src/picmeasure/web_static:picmeasure/web_static" \
  --collect-all uvicorn \
  --collect-all pydantic \
  --collect-all cv2 \
  --hidden-import picmeasure.web \
  src/picmeasure/launcher.py

cp -f stereo.toml dist/PicMeasure/stereo.toml
if [ -f config.toml ]; then cp -f config.toml dist/PicMeasure/config.toml; fi
if [ -f remote_config.json ]; then cp -f remote_config.json dist/PicMeasure/remote_config.json; fi
cp -f scripts/launch_bundle.command dist/PicMeasure/"启动 PicMeasure.command"
chmod +x dist/PicMeasure/"启动 PicMeasure.command"

printf '%s\n' "已生成: $ROOT_DIR/dist/PicMeasure"
