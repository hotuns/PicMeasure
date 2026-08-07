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
}

export interface SessionResponse {
  session_id: string;
  mode: AppMode;
  images: Record<string, { width: number; height: number }>;
  ball_candidates: BallCandidate[] | { left: BallCandidate[]; right: BallCandidate[] };
  known_ball_diameter: number;
  unit: "cm" | "mm";
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
  points: Point[];
  rightPoints: Point[];
  points3d: Point3D[];
  diameters: DiameterResult[];
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
