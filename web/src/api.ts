import type { BranchResult, MeasureMode, Point, PointPreview, RemoteCapture, RemoteCaptureResponse, SavedAnnotationRecord, SeriesPoint, SessionResponse, StereoCalibrationResult } from "./types";

async function checked<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(body.detail || "请求失败");
  }
  if (response.status === 204 || response.headers.get("content-length") === "0") {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export async function createMonocular(image: File): Promise<SessionResponse> {
  const body = new FormData();
  body.append("image", image);
  return checked(await fetch("/api/sessions/monocular", { method: "POST", body }));
}

export async function createStereo(
  left: File,
  right: File,
  calibration?: File,
): Promise<SessionResponse> {
  const body = new FormData();
  body.append("left", left);
  body.append("right", right);
  if (calibration) body.append("calibration", calibration);
  return checked(await fetch("/api/sessions/stereo", { method: "POST", body }));
}

export async function calibrateStereo(
  leftImages: File[],
  rightImages: File[],
  settings: { columns: number; rows: number; squareSize: number; unit: "mm" | "cm"; baseline?: number },
): Promise<StereoCalibrationResult> {
  const body = new FormData();
  leftImages.forEach((file) => body.append("left_images", file));
  rightImages.forEach((file) => body.append("right_images", file));
  body.append("columns", String(settings.columns));
  body.append("rows", String(settings.rows));
  body.append("square_size", String(settings.squareSize));
  body.append("unit", settings.unit);
  if (settings.baseline !== undefined) body.append("baseline", String(settings.baseline));
  return checked(await fetch("/api/calibration/stereo", { method: "POST", body }));
}

export async function snapPoint(input: {
  sessionId: string;
  point: Point;
  mode: MeasureMode;
  previous?: Point;
  snapping: boolean;
}): Promise<PointPreview> {
  return checked(
    await fetch("/api/points/snap", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: input.sessionId,
        point: input.point,
        mode: input.mode,
        previous: input.previous ?? null,
        snapping: input.snapping,
      }),
    }),
  );
}

export async function stereoPoint(input: {
  sessionId: string;
  point: Point;
  mode: MeasureMode;
  previous?: Point;
  snapping: boolean;
  manualRight?: Point;
}): Promise<PointPreview> {
  return checked(
    await fetch("/api/points/stereo", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: input.sessionId,
        point: input.point,
        mode: input.mode,
        previous: input.previous ?? null,
        snapping: input.snapping,
        manual_right: input.manualRight ?? null,
      }),
    }),
  );
}

export function imageUrl(sessionId: string, view: string): string {
  return `/api/sessions/${sessionId}/images/${view}`;
}

export async function listRemoteCaptures(deviceId = 3331, startDate?: string, endDate?: string): Promise<RemoteCaptureResponse> {
  const query = new URLSearchParams({ limit: "30" });
  if (startDate) query.set("start_date", startDate);
  if (endDate) query.set("end_date", endDate);
  return checked(await fetch(`/api/remote/devices/${deviceId}/captures?${query}`));
}

export function remoteImageUrl(deviceId: number, path: string): string {
  return `/api/remote/devices/${deviceId}/image?path=${encodeURIComponent(path)}`;
}

export async function createRemoteStereo(capture: RemoteCapture, calibration?: File): Promise<SessionResponse> {
  const body = new FormData();
  body.append("device_id", String(capture.device_id));
  body.append("capture_id", capture.id);
  body.append("captured_at", capture.captured_at);
  body.append("left_path", capture.images.key3.path);
  body.append("right_path", capture.images.key2.path);
  if (calibration) body.append("calibration", calibration);
  return checked(await fetch("/api/sessions/remote-stereo", {
    method: "POST",
    body,
  }));
}

export async function createRemoteMonocular(capture: RemoteCapture, imageKey: string): Promise<SessionResponse> {
  const image = capture.images[imageKey];
  if (!image) throw new Error(`${imageKey} 图片不存在`);
  const body = new FormData();
  body.append("device_id", String(capture.device_id));
  body.append("capture_id", capture.id);
  body.append("captured_at", capture.captured_at);
  body.append("image_key", imageKey);
  body.append("image_path", image.path);
  return checked(await fetch("/api/sessions/remote-monocular", { method: "POST", body }));
}

export async function saveAnnotation(input: {
  sessionId: string;
  capturedAt?: string;
  branches: BranchResult[] | Record<string, unknown>[];
  calibration: Record<string, unknown>;
}): Promise<{ saved: boolean; path: string }> {
  return checked(await fetch("/api/annotations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: input.sessionId, captured_at: input.capturedAt, branches: input.branches, calibration: input.calibration }),
  }));
}

export async function saveAnnotationImage(sessionId: string, image: Blob): Promise<{ saved: boolean; path: string }> {
  const body = new FormData();
  body.append("image", image, "annotated.png");
  return checked(await fetch(`/api/annotations/${sessionId}/image`, { method: "POST", body }));
}

export function deviceExportUrl(deviceId = 3331): string {
  return `/api/exports/device/${deviceId}`;
}

export async function loadSeries(deviceId = 3331): Promise<{ device_id: number; series: Record<string, SeriesPoint[]> }> {
  return checked(await fetch(`/api/annotations/series?device_id=${deviceId}`));
}

export async function listSavedAnnotations(deviceId = 3331): Promise<{ device_id: number; records: SavedAnnotationRecord[] }> {
  return checked(await fetch(`/api/annotations/device/${deviceId}`));
}

export async function deleteSavedAnnotation(deviceId: number, filename: string): Promise<void> {
  await checked(await fetch(`/api/annotations/device/${deviceId}/${encodeURIComponent(filename)}`, { method: "DELETE" }));
}

export async function reopenSavedAnnotation(deviceId: number, filename: string): Promise<SessionResponse> {
  return checked(await fetch(`/api/sessions/from-annotation/${deviceId}/${encodeURIComponent(filename)}`, { method: "POST" }));
}
