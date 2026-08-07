import type { MeasureMode, Point, PointPreview, SessionResponse, StereoCalibrationResult } from "./types";

async function checked<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(body.detail || "请求失败");
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
): Promise<SessionResponse> {
  const body = new FormData();
  body.append("left", left);
  body.append("right", right);
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
