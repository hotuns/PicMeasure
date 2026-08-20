export type Point = [number, number];
export type Point3D = [number, number, number];
export type AppMode = "monocular" | "stereo";
export type Workflow = AppMode | "calibration";
export type MeasureMode = "length" | "diameter";
export type ViewName = "primary" | "left" | "right";

export interface BallCandidate {
  center: Point;
  radius: number;
  score: number;
  circularity: number;
  edge_support: number;
  mask_fill: number;
  area_ratio: number;
  pixels_per_unit: number;
  method: string;
  saved_at?: string;
  image_key?: string;
}

export interface SessionResponse {
  session_id: string;
  mode: AppMode;
  images: Record<string, { width: number; height: number }>;
  ball_candidates: BallCandidate[] | { left: BallCandidate[]; right: BallCandidate[] };
  known_ball_diameter: number;
  unit: "cm" | "mm";
  source?: RemoteSource;
  saved_calibration?: BallCandidate | null;
  existing_branches?: BranchResult[];
  alignment?: {
    source: "features" | "configured";
    matches: number;
    inliers: number;
    median_vertical_error_px: number;
    p90_vertical_error_px: number;
  };
}

export interface PointPreview {
  raw: Point;
  candidate: Point;
  snapped: boolean;
  score: number;
  right?: Point;
  point_3d?: Point3D;
  match_score?: number;
  manual?: boolean;
}

export interface DiameterResult {
  sectionId: number;
  leftEdges: [Point, Point];
  rightEdges?: [Point, Point];
  points3d?: [Point3D, Point3D];
  pixels: number;
  value: number;
}

export interface BranchResult {
  id: number;
  key: string;
  points: Point[];
  rightPoints: Point[];
  points3d: Point3D[];
  diameters: DiameterResult[];
}

export interface RemoteImageRecord {
  record_id: number;
  table: string;
  key: string;
  path: string;
  timestamp: string;
  measurement: MeasurementStatus;
}

export interface MeasurementStatus {
  measured: boolean;
  saved_at?: string;
  branch_count?: number;
  path?: string;
}

export interface RemoteCapture {
  id: string;
  device_id: number;
  captured_at: string;
  images: Record<string, RemoteImageRecord>;
  stereo_ready: boolean;
  stereo_measurement: MeasurementStatus;
}

export interface RemoteCaptureResponse {
  device: { id: number; name: string; status: string };
  captures: RemoteCapture[];
}

export interface RemoteStereoSource {
  kind: "remote";
  device_id: number;
  capture_id: string;
  captured_at: string;
  left: { key: "key3"; path: string };
  right: { key: "key2"; path: string };
}

export interface RemoteMonocularSource {
  kind: "remote";
  device_id: number;
  capture_id: string;
  captured_at: string;
  image: { key: string; path: string };
}

export type RemoteSource = RemoteStereoSource | RemoteMonocularSource;

export interface SeriesPoint {
  timestamp: string;
  value: number;
  unit: string;
  capture_id?: string;
  annotation_id?: string;
  target?: string;
  image_url?: string | null;
}

export interface SavedAnnotationRecord {
  id: string;
  captured_at?: string;
  saved_at?: string;
  mode?: string;
  target: string;
  measurements: Array<{ key?: string; value?: number; unit?: string }>;
  image_url?: string | null;
}

export interface CameraCalibrationResult {
  camera_matrix: number[][];
  distortion_coefficients: number[];
  rms_error: number;
}

export interface CalibrationQualityResult {
  valid_pairs: number;
  total_pairs: number;
  stereo_rms_error: number;
  rectified_median_vertical_error_px: number;
  rectified_p90_vertical_error_px: number;
}

export interface StereoCalibrationResult {
  toml: string;
  accepted_indices: number[];
  rejected_indices: number[];
  image_size: Point;
  unit: "cm" | "mm";
  baseline: number;
  rotation: number[][];
  translation: number[];
  left: CameraCalibrationResult;
  right: CameraCalibrationResult;
  quality: CalibrationQualityResult;
}
