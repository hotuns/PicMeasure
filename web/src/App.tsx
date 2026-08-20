import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Check,
  Camera,
  ChartNoAxesCombined,
  ChevronLeft,
  ChevronRight,
  CircleDot,
  Database,
  Download,
  Eye,
  EyeOff,
  Hand,
  ImagePlus,
  Info,
  Maximize2,
  MousePointer2,
  Plus,
  RefreshCw,
  Ruler,
  Save,
  ScanLine,
  Settings2,
  Trash2,
  Undo2,
  Upload,
  X,
  XCircle,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import Konva from "konva";
import { Circle, Image as KonvaImage, Layer, Line, Stage, Text } from "react-konva";
import { calibrateStereo, createMonocular, createRemoteMonocular, createRemoteStereo, createStereo, deleteSavedAnnotation, deviceExportUrl, imageUrl, listRemoteCaptures, listSavedAnnotations, loadSeries, remoteImageUrl, reopenSavedAnnotation, saveAnnotation, saveAnnotationImage, snapPoint, stereoPoint } from "./api";
import type {
  AppMode,
  BallCandidate,
  BranchResult,
  DiameterResult,
  MeasureMode,
  Point,
  Point3D,
  PointPreview,
  RemoteCapture,
  RemoteCaptureResponse,
  SavedAnnotationRecord,
  SeriesPoint,
  SessionResponse,
  StereoCalibrationResult,
  ViewName,
  Workflow,
} from "./types";

type ToastKind = "success" | "error" | "info";

interface ToastState {
  kind: ToastKind;
  text: string;
}

function useHtmlImage(src: string | null): HTMLImageElement | null {
  const [image, setImage] = useState<HTMLImageElement | null>(null);
  useEffect(() => {
    if (!src) {
      setImage(null);
      return;
    }
    const next = new window.Image();
    next.onload = () => setImage(next);
    next.src = src;
    return () => {
      next.onload = null;
    };
  }, [src]);
  return image;
}

function distance2d(a: Point, b: Point): number {
  return Math.hypot(b[0] - a[0], b[1] - a[1]);
}

function distance3d(a: Point3D, b: Point3D): number {
  return Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2]);
}

function polylineLength(points: Point[] | Point3D[]): number {
  let total = 0;
  for (let index = 1; index < points.length; index += 1) {
    const a = points[index - 1];
    const b = points[index];
    total += a.length === 3 ? distance3d(a as Point3D, b as Point3D) : distance2d(a as Point, b as Point);
  }
  return total;
}

function download(name: string, content: string, type = "application/json"): void {
  const anchor = document.createElement("a");
  anchor.href = URL.createObjectURL(new Blob([content], { type }));
  anchor.download = name;
  anchor.click();
  URL.revokeObjectURL(anchor.href);
}

function ScoreBar({ label, value }: { label: string; value: number }) {
  const width = Math.round(Math.min(1, Math.max(0, value)) * 100);
  return (
    <div className="score-bar">
      <span>{label}</span>
      <div><i style={{ width: `${width}%` }} /></div>
      <strong>{value.toFixed(2)}</strong>
    </div>
  );
}

function FileDrop({
  label,
  hint,
  accept,
  multiple,
  required,
  selected,
  onFiles,
}: {
  label: string;
  hint?: string;
  accept: string;
  multiple?: boolean;
  required?: boolean;
  selected?: string;
  onFiles: (files: File[]) => void;
}) {
  const [drag, setDrag] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  return (
    <div
      className={`dropzone${drag ? " drag" : ""}${selected ? " filled" : ""}`}
      onClick={() => inputRef.current?.click()}
      onDragOver={(event) => {
        event.preventDefault();
        setDrag(true);
      }}
      onDragLeave={() => setDrag(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDrag(false);
        const files = Array.from(event.dataTransfer.files ?? []);
        if (files.length) onFiles(files);
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        multiple={multiple}
        hidden
        onChange={(event) => {
          const files = Array.from(event.currentTarget.files ?? []);
          if (files.length) onFiles(files);
          event.currentTarget.value = "";
        }}
      />
      <div className="dropzone-icon"><Upload size={16} /></div>
      <div className="dropzone-copy">
        <strong>{label}{required && <em>必选</em>}</strong>
        <span>{selected ?? hint ?? "点击选择或拖入文件"}</span>
      </div>
      {selected ? <Check size={15} className="dropzone-check" /> : <ChevronRight size={15} className="dropzone-arrow" />}
    </div>
  );
}

function UploadScreen({
  onReady,
  onCalibrated,
}: {
  onReady: (session: SessionResponse, names: string[]) => void;
  onCalibrated: (result: StereoCalibrationResult) => void;
}) {
  const [mode, setMode] = useState<Workflow>("monocular");
  const [files, setFiles] = useState<Record<string, File | undefined>>({});
  const [calibrationFiles, setCalibrationFiles] = useState<{ left: File[]; right: File[] }>({ left: [], right: [] });
  const [board, setBoard] = useState({ columns: 9, rows: 6, squareSize: 20, unit: "mm" as "mm" | "cm", baseline: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async () => {
    setBusy(true);
    setError("");
    try {
      if (mode === "monocular") {
        if (!files.primary) throw new Error("请选择一张待测图像");
        onReady(await createMonocular(files.primary), [files.primary.name]);
      } else if (mode === "stereo") {
        if (!files.left || !files.right) {
          throw new Error("请选择左右图");
        }
        onReady(await createStereo(files.left, files.right, files.calibration), [files.left.name, files.right.name]);
      } else {
        if (calibrationFiles.left.length !== calibrationFiles.right.length) {
          throw new Error("左右标定图数量必须一致，并按相同顺序配对");
        }
        if (calibrationFiles.left.length < 6) throw new Error("至少需要 6 组有效标定图，建议拍摄 15–30 组");
        const baseline = board.baseline.trim() === "" ? undefined : Number(board.baseline);
        if (baseline !== undefined && (!Number.isFinite(baseline) || baseline <= 0)) {
          throw new Error("双目基线必须是大于 0 的数字");
        }
        onCalibrated(await calibrateStereo(calibrationFiles.left, calibrationFiles.right, { ...board, baseline }));
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法创建测量会话");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="setup-shell">
      <section className="setup-panel">
        <div className="product-mark"><ScanLine size={24} /><span>PicMeasure</span></div>
        <h1>图像测量工作台</h1>
        <p className="setup-intro">选择测量方式并导入图像。文件可以点击选择，也可以直接拖入。</p>
        <div className="segmented wide" aria-label="测量方式">
          <button className={mode === "monocular" ? "active" : ""} onClick={() => setMode("monocular")}>单目测量</button>
          <button className={mode === "stereo" ? "active" : ""} onClick={() => setMode("stereo")}>双目测量</button>
          <button className={mode === "calibration" ? "active" : ""} onClick={() => setMode("calibration")}>双目标定</button>
        </div>
        <div className="step-rule"><b>1</b>导入图像</div>
        <div className="file-stack">
          {mode === "monocular" ? (
            <FileDrop
              label="测量图像"
              hint="单张 JPG / PNG，需包含参考球"
              accept="image/*"
              required
              selected={files.primary?.name}
              onFiles={(list) => setFiles((current) => ({ ...current, primary: list[0] }))}
            />
          ) : mode === "stereo" ? (
            <>
              <FileDrop
                label="左相机图像"
                hint="校正后的左图"
                accept="image/*"
                required
                selected={files.left?.name}
                onFiles={(list) => setFiles((current) => ({ ...current, left: list[0] }))}
              />
              <FileDrop
                label="右相机图像"
                hint="校正后的右图"
                accept="image/*"
                required
                selected={files.right?.name}
                onFiles={(list) => setFiles((current) => ({ ...current, right: list[0] }))}
              />
              <FileDrop
                label="标定文件（可选）"
                hint="默认使用项目根目录 stereo.toml"
                accept=".toml,application/toml,text/plain"
                selected={files.calibration?.name}
                onFiles={(list) => setFiles((current) => ({ ...current, calibration: list[0] }))}
              />
              <p className="settings-hint">不选择时使用项目根目录 stereo.toml；这里选择的文件只用于本次会话。</p>
            </>
          ) : (
            <>
              <FileDrop
                label="左相机图集"
                hint="多张棋盘格图像，按拍摄顺序与右图配对"
                accept="image/*"
                multiple
                required
                selected={calibrationFiles.left.length ? `${calibrationFiles.left.length} 张` : undefined}
                onFiles={(list) => setCalibrationFiles((current) => ({ ...current, left: list }))}
              />
              <FileDrop
                label="右相机图集"
                hint="多张棋盘格图像，顺序必须与左图一一对应"
                accept="image/*"
                multiple
                required
                selected={calibrationFiles.right.length ? `${calibrationFiles.right.length} 张` : undefined}
                onFiles={(list) => setCalibrationFiles((current) => ({ ...current, right: list }))}
              />
            </>
          )}
        </div>
        {mode === "calibration" && (
          <div className="calibration-settings">
            <p className="settings-note">使用同步拍摄的棋盘格图像，建议 15–30 组。行列数填写棋盘内部角点数。</p>
            <div className="field-grid">
              <label><span>角点列数</span><input type="number" min="3" value={board.columns} onChange={(event) => setBoard({ ...board, columns: Number(event.target.value) })} /></label>
              <label><span>角点行数</span><input type="number" min="3" value={board.rows} onChange={(event) => setBoard({ ...board, rows: Number(event.target.value) })} /></label>
              <label><span>方格边长</span><input type="number" min="0.001" step="any" value={board.squareSize} onChange={(event) => setBoard({ ...board, squareSize: Number(event.target.value) })} /></label>
              <label><span>单位</span><select value={board.unit} onChange={(event) => setBoard({ ...board, unit: event.target.value as "mm" | "cm" })}><option value="mm">mm</option><option value="cm">cm</option></select></label>
              <label className="field-wide"><span>双目基线（可选）</span><input type="number" min="0.001" step="any" placeholder="例如 155" value={board.baseline} onChange={(event) => setBoard({ ...board, baseline: event.target.value })} /></label>
            </div>
            <p className="settings-hint">基线指两相机光心（传感器）之间的实际距离，不是外壳间距；填写后标定结果会按该尺度重新缩放。</p>
          </div>
        )}
        {error && <div className="error-box"><XCircle size={15} /><span>{error}</span></div>}
        <button className="primary-command" onClick={submit} disabled={busy}>
          {mode === "calibration" ? <Camera size={18} /> : <ImagePlus size={18} />}
          {busy ? (mode === "calibration" ? "正在检测角点并计算" : "正在准备图像") : (mode === "calibration" ? "开始标定" : "打开工作台")}
        </button>
      </section>
    </main>
  );
}

function CalibrationResult({ result, onClose }: { result: StereoCalibrationResult; onClose: () => void }) {
  const quality = result.quality;
  const rejected = result.rejected_indices.map((index) => index + 1);
  return (
    <main className="setup-shell">
      <section className="setup-panel result-panel">
        <div className="product-mark"><Camera size={24} /><span>双目标定完成</span></div>
        <h1>{quality.valid_pairs} / {quality.total_pairs} 组有效</h1>
        <div className="calibration-metrics">
          <div><span>左相机重投影误差</span><strong>{result.left.rms_error.toFixed(3)} px</strong></div>
          <div><span>右相机重投影误差</span><strong>{result.right.rms_error.toFixed(3)} px</strong></div>
          <div><span>双目 RMS</span><strong>{quality.stereo_rms_error.toFixed(3)} px</strong></div>
          <div><span>校正后垂直误差 P50 / P90</span><strong>{quality.rectified_median_vertical_error_px.toFixed(3)} / {quality.rectified_p90_vertical_error_px.toFixed(3)} px</strong></div>
          <div><span>基线</span><strong>{result.baseline.toFixed(3)} {result.unit}</strong></div>
          <div><span>标定分辨率</span><strong>{result.image_size[0]} × {result.image_size[1]}</strong></div>
        </div>
        {rejected.length > 0 && <p className="warning-line">未检测到完整棋盘角点的组：{rejected.join("、")}</p>}
        <p className="settings-hint">下载 stereo.toml 后，在“双目测量”中导入它和左右图即可开始测量。</p>
        <button className="primary-command" onClick={() => download("stereo.toml", result.toml, "application/toml")}><Download size={18} />下载 stereo.toml</button>
        <button className="text-command result-back" onClick={onClose}>返回并重新标定</button>
      </section>
    </main>
  );
}

function ConfirmBar({
  preview,
  diameterFirst,
  pendingManualLeft,
  sessionMode,
  monoScale,
  unit,
  onConfirm,
  onCancel,
}: {
  preview: PointPreview | null;
  diameterFirst: PointPreview | null;
  pendingManualLeft: PointPreview | null;
  sessionMode: AppMode;
  monoScale?: number;
  unit: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  let title = "";
  let detail = "";
  let showActions = false;
  if (pendingManualLeft) {
    title = "手动匹配：等待右图对应点";
    detail = `左图已锁定 (${pendingManualLeft.candidate[0]}, ${pendingManualLeft.candidate[1]})，点击右图对应位置`;
  } else if (diameterFirst && !preview) {
    title = "直径第一侧边缘已锁定";
    detail = `(${diameterFirst.candidate[0]}, ${diameterFirst.candidate[1]})，点击枝条另一侧边缘`;
  } else if (preview) {
    title = preview.snapped ? "候选点已吸附" : "未找到可靠边缘，使用原位置";
    const distance = diameterFirst
      ? (sessionMode === "stereo" && diameterFirst.point_3d && preview.point_3d
          ? distance3d(diameterFirst.point_3d, preview.point_3d)
          : distance2d(diameterFirst.candidate, preview.candidate) / (monoScale ?? 1))
      : null;
    detail = `原始 (${preview.raw[0]}, ${preview.raw[1]}) → 目标 (${preview.candidate[0]}, ${preview.candidate[1]})${distance !== null ? ` · 距离 ${distance.toFixed(2)} ${unit}` : ""}`;
    showActions = true;
  }
  if (!title) return null;
  return (
    <div className="confirm-bar">
      <div className="confirm-copy">
        <strong>{title}</strong>
        <span>{detail}</span>
      </div>
      {showActions && (
        <div className="confirm-actions">
          <button className="command quiet" onClick={onCancel}><X size={15} />取消<kbd>Esc</kbd></button>
          <button className="command" onClick={onConfirm}><Check size={15} />确认<kbd>Enter</kbd></button>
        </div>
      )}
    </div>
  );
}

interface WorkbenchProps {
  session: SessionResponse;
  names: string[];
  onClose: () => void;
  onSaveNext?: () => Promise<void>;
  onSaved?: () => void;
  nextMeasurementLabel?: string;
  onSkipNext?: () => Promise<void>;
}

function Workbench({ session, names, onClose, onSaveNext, onSaved, nextMeasurementLabel, onSkipNext }: WorkbenchProps) {
  const [measureMode, setMeasureMode] = useState<MeasureMode>("length");
  const [view, setView] = useState<ViewName>(session.mode === "stereo" ? "left" : "primary");
  const [tool, setTool] = useState<"select" | "pan">("select");
  const [spacePan, setSpacePan] = useState(false);
  const [snapping, setSnapping] = useState(true);
  const [overlays, setOverlays] = useState(true);
  const [manualMatch, setManualMatch] = useState(false);
  const [pendingManualLeft, setPendingManualLeft] = useState<PointPreview | null>(null);
  const [preview, setPreview] = useState<PointPreview | null>(null);
  const [diameterFirst, setDiameterFirst] = useState<PointPreview | null>(null);
  const [branches, setBranches] = useState<BranchResult[]>(() => session.existing_branches?.length
    ? session.existing_branches.map((branch, index) => ({
      ...branch,
      id: branch.id ?? index + 1,
      points: branch.points ?? [],
      rightPoints: branch.rightPoints ?? [],
      points3d: branch.points3d ?? [],
      diameters: branch.diameters ?? [],
    }))
    : [{ id: 1, key: "树枝", points: [], rightPoints: [], points3d: [], diameters: [] }]);
  const [candidateIndex, setCandidateIndex] = useState(0);
  const [confirmedBalls, setConfirmedBalls] = useState<Partial<Record<ViewName, BallCandidate>>>(
    session.mode === "monocular" && session.saved_calibration
      ? { primary: session.saved_calibration }
      : {},
  );
  const [calibrationSkipped, setCalibrationSkipped] = useState(false);
  const [manualBall, setManualBall] = useState(false);
  const [manualBallPoints, setManualBallPoints] = useState<Point[]>([]);
  const [message, setMessage] = useState(
    session.mode === "monocular"
      ? session.saved_calibration
        ? `已应用 ${session.saved_calibration.image_key ?? "当前相机"} 的固定参考球标定`
        : "请确认参考球后开始测量"
      : "点击左图开始选点，右图可调整匹配位置",
  );
  const [error, setError] = useState("");
  const [toast, setToast] = useState<ToastState | null>(null);
  const [hoverPoint, setHoverPoint] = useState<Point | null>(null);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [stageSize, setStageSize] = useState({ width: 900, height: 650 });
  const [stageTransform, setStageTransform] = useState({ x: 0, y: 0, scale: 1 });
  const canvasHost = useRef<HTMLDivElement>(null);
  const stageRef = useRef<Konva.Stage>(null);
  const rightStageRef = useRef<Konva.Stage>(null);

  const leftImage = useHtmlImage(
    imageUrl(session.session_id, session.mode === "stereo" ? "left" : "primary"),
  );
  const rightImage = useHtmlImage(
    session.mode === "stereo" ? imageUrl(session.session_id, "right") : null,
  );
  const currentBranch = branches[branches.length - 1];
  const leftMeta = session.images[session.mode === "stereo" ? "left" : "primary"];
  const rightMeta = session.images.right;
  const imageMeta = session.images[view] ?? session.images.primary ?? session.images.left;
  const candidates = useMemo(() => {
    if (Array.isArray(session.ball_candidates)) return session.ball_candidates;
    return session.ball_candidates[view === "right" ? "right" : "left"] ?? [];
  }, [session.ball_candidates, view]);
  const currentCandidate = candidates[candidateIndex % Math.max(candidates.length, 1)];
  const monoScale = confirmedBalls.primary?.pixels_per_unit;
  const calibrationReady = session.mode === "stereo" || Boolean(monoScale) || calibrationSkipped;
  const panning = tool === "pan" || spacePan;
  const visibleBranches = branches.filter((branch) => branch.points.length || branch.diameters.length);
  const diameterCount = visibleBranches.reduce((total, branch) => total + branch.diameters.length, 0);
  const hasMeasurements = branches.some((branch) => branch.points.length > 0 || branch.diameters.length > 0);
  const canUndo = Boolean(preview || diameterFirst || pendingManualLeft || hasMeasurements);

  const notify = useCallback((text: string, kind: ToastKind = "info") => {
    setToast({ text, kind });
  }, []);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 2800);
    return () => window.clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    const host = canvasHost.current;
    if (!host) return;
    const observer = new ResizeObserver(([entry]) => {
      setStageSize({ width: entry.contentRect.width, height: entry.contentRect.height });
    });
    observer.observe(host);
    return () => observer.disconnect();
  }, []);

  const paneWidth = session.mode === "stereo"
    ? Math.max(1, (stageSize.width - 8) / 2)
    : stageSize.width;

  const fitImage = useCallback(() => {
    if (!leftMeta) return;
    const scale = Math.min(paneWidth / leftMeta.width, stageSize.height / leftMeta.height) * 0.94;
    setStageTransform({
      scale,
      x: (paneWidth - leftMeta.width * scale) / 2,
      y: (stageSize.height - leftMeta.height * scale) / 2,
    });
  }, [leftMeta, paneWidth, stageSize.height]);

  const zoomBy = useCallback((factor: number) => {
    setStageTransform((current) => {
      const scale = Math.max(0.05, Math.min(20, current.scale * factor));
      const cx = paneWidth / 2;
      const cy = stageSize.height / 2;
      const imageX = (cx - current.x) / current.scale;
      const imageY = (cy - current.y) / current.scale;
      return { scale, x: cx - imageX * scale, y: cy - imageY * scale };
    });
  }, [paneWidth, stageSize.height]);

  useEffect(() => fitImage(), [fitImage]);
  useEffect(() => setCandidateIndex(0), [view]);

  const imagePoint = (side: "left" | "right" | "primary"): Point | null => {
    const stage = side === "right" ? rightStageRef.current : stageRef.current;
    const pointer = stage?.getPointerPosition();
    const meta = side === "right" ? rightMeta : leftMeta;
    if (!stage || !pointer || !meta) return null;
    const x = Math.round((pointer.x - stage.x()) / stage.scaleX());
    const y = Math.round((pointer.y - stage.y()) / stage.scaleY());
    if (x < 0 || y < 0 || x >= meta.width || y >= meta.height) return null;
    return [x, y];
  };

  const requestPreview = async (point: Point, manualRight?: Point, snapOverride = snapping) => {
    setError("");
    try {
      const previous = currentBranch.points.at(-1);
      const next = session.mode === "stereo"
        ? await stereoPoint({
            sessionId: session.session_id,
            point,
            mode: measureMode,
            previous,
            snapping: snapOverride,
            manualRight,
          })
        : await snapPoint({
            sessionId: session.session_id,
            point,
            mode: measureMode,
            previous,
            snapping: snapOverride,
          });
      setPreview(next);
      setMessage(next.snapped ? "已吸附，按 Enter 确认" : "未找到可靠边缘，按 Enter 使用原位置");
      return true;
    } catch (reason) {
      const detail = reason instanceof Error ? reason.message : "选点失败";
      setError(detail);
      notify(detail, "error");
      setMessage("自动匹配失败，可开启手动匹配");
      return false;
    }
  };

  const handleCanvasClick = async (side: "left" | "right" | "primary") => {
    if (tool === "pan" || spacePan) return;
    const point = imagePoint(side);
    if (!point) return;
    const activeView: ViewName = session.mode === "stereo"
      ? (side === "right" ? "right" : "left")
      : "primary";
    setView(activeView);

    if (manualBall) {
      const points = [...manualBallPoints, point];
      if (points.length === 2) {
        const radius = distance2d(points[0], points[1]);
        const manual: BallCandidate = {
          center: points[0], radius, score: 1, circularity: 1, edge_support: 1,
          mask_fill: 1, area_ratio: 1, method: "manual",
          pixels_per_unit: (2 * radius) / session.known_ball_diameter,
        };
        setConfirmedBalls((current) => ({ ...current, [activeView]: manual }));
        setManualBall(false);
        setManualBallPoints([]);
        notify("手动参考球已确认", "success");
        setMessage("手动参考球已确认，可以开始测量");
      } else {
        setManualBallPoints(points);
        setMessage("请点击参考球圆周边缘");
      }
      return;
    }

    if (!calibrationReady) {
      notify("请先确认参考球再开始测量", "info");
      setMessage("请先确认参考球");
      return;
    }

    // After automatic correspondence, a click on the right image replaces
    // only the right endpoint and immediately re-triangulates the preview.
    if (session.mode === "stereo" && side === "right" && preview && !manualMatch) {
      const updated = await requestPreview(preview.candidate, point, false);
      if (updated) {
        setMessage("右图位置已更新，按 Enter 确认；可再次点击调整");
        notify("右图位置已更新", "success");
      }
      return;
    }

    if (session.mode === "stereo" && manualMatch) {
      if (side !== "right") {
        const snapped = await snapPoint({
          sessionId: session.session_id, point, mode: measureMode,
          previous: currentBranch.points.at(-1), snapping,
        });
        setPendingManualLeft(snapped);
        setMessage("请在右图点击对应位置");
      } else if (pendingManualLeft) {
        await requestPreview(pendingManualLeft.candidate, point);
        setPendingManualLeft(null);
      }
      return;
    }
    if (session.mode === "stereo" && side === "right") return;
    await requestPreview(point);
  };

  const confirmPreview = useCallback(() => {
    if (!preview) return;
    const isSecondDiameter = measureMode === "diameter" && Boolean(diameterFirst);
    setBranches((current) => {
      const next = structuredClone(current) as BranchResult[];
      const branch = next[next.length - 1];
      if (measureMode === "length") {
        branch.points.push(preview.candidate);
        if (preview.right) branch.rightPoints.push(preview.right);
        if (preview.point_3d) branch.points3d.push(preview.point_3d);
      } else if (!diameterFirst) {
        setDiameterFirst(preview);
      } else {
        const pixelDistance = distance2d(diameterFirst.candidate, preview.candidate);
        const value = session.mode === "stereo" && diameterFirst.point_3d && preview.point_3d
          ? distance3d(diameterFirst.point_3d, preview.point_3d)
          : pixelDistance / (monoScale ?? 1);
        const result: DiameterResult = {
          sectionId: branch.diameters.length + 1,
          leftEdges: [diameterFirst.candidate, preview.candidate],
          rightEdges: diameterFirst.right && preview.right ? [diameterFirst.right, preview.right] : undefined,
          points3d: diameterFirst.point_3d && preview.point_3d ? [diameterFirst.point_3d, preview.point_3d] : undefined,
          pixels: pixelDistance,
          value,
        };
        branch.diameters.push(result);
      }
      return next;
    });
    setPreview(null);
    if (measureMode === "length") {
      setMessage("长度点已确认，继续点击下一点");
      notify("长度点已确认", "success");
    } else if (isSecondDiameter) {
      setDiameterFirst(null);
      setMessage("直径截面已完成");
      notify("直径截面已完成", "success");
    } else {
      setMessage("第一侧边缘已锁定，请点击另一侧");
    }
  }, [preview, measureMode, diameterFirst, session.mode, monoScale, notify]);

  const cancelPending = useCallback(() => {
    setPreview(null);
    setDiameterFirst(null);
    setPendingManualLeft(null);
  }, []);

  const undo = useCallback(() => {
    if (preview) {
      setPreview(null);
      return;
    }
    if (diameterFirst) {
      setDiameterFirst(null);
      return;
    }
    if (pendingManualLeft) {
      setPendingManualLeft(null);
      return;
    }
    setBranches((current) => {
      const next = structuredClone(current) as BranchResult[];
      const branch = next[next.length - 1];
      if (measureMode === "diameter" && branch.diameters.length) branch.diameters.pop();
      else if (branch.points.length) {
        branch.points.pop(); branch.rightPoints.pop(); branch.points3d.pop();
      } else if (next.length > 1) next.pop();
      return next;
    });
    notify("已撤销上一步", "info");
  }, [preview, diameterFirst, pendingManualLeft, measureMode, notify]);

  const clearMeasurements = useCallback(() => {
    const exists = branches.some((branch) => branch.points.length > 0 || branch.diameters.length > 0);
    if (exists && !window.confirm("清除全部已有测量？此操作无法撤销。")) return;
    setBranches([{ id: 1, key: "树枝", points: [], rightPoints: [], points3d: [], diameters: [] }]);
    cancelPending();
    setSelectedKey(null);
    setMessage("已清除全部测量");
    notify("已清除全部测量", "success");
  }, [branches, cancelPending, notify]);

  const removeDiameter = (branchId: number, sectionId: number) => {
    setBranches((current) => current.map((branch) => {
      if (branch.id !== branchId) return branch;
      const rest = branch.diameters.filter((diameter) => diameter.sectionId !== sectionId);
      return { ...branch, diameters: rest.map((diameter, index) => ({ ...diameter, sectionId: index + 1 })) };
    }));
    notify("直径记录已删除", "success");
  };

  const removeBranch = (branchId: number) => {
    if (branches.length === 1) {
      clearMeasurements();
      return;
    }
    setBranches((current) => current.filter((branch) => branch.id !== branchId));
    cancelPending();
    setSelectedKey(null);
    notify("分支已删除", "success");
  };

  const setMeasureModeSafe = (next: MeasureMode) => {
    setMeasureMode(next);
    cancelPending();
  };

  useEffect(() => {
    const keyboard = (event: KeyboardEvent) => {
      if (event.code === "Space") {
        event.preventDefault();
        if (!event.repeat) setSpacePan(true);
      } else if (event.key === "Enter") confirmPreview();
      else if (event.key.toLowerCase() === "u") undo();
      else if (event.key.toLowerCase() === "a") setSnapping((value) => !value);
      else if (event.key.toLowerCase() === "v") setOverlays((value) => !value);
      else if (event.key.toLowerCase() === "d") setMeasureModeSafe(measureMode === "length" ? "diameter" : "length");
      else if (event.key === "Escape") {
        if (preview) setPreview(null);
        else if (diameterFirst) setDiameterFirst(null);
        else if (pendingManualLeft) setPendingManualLeft(null);
        else if (manualBall) {
          setManualBall(false);
          setManualBallPoints([]);
        }
      } else if (event.key === "+" || event.key === "=") zoomBy(1.25);
      else if (event.key === "-") zoomBy(1 / 1.25);
      else if (preview && ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) {
        event.preventDefault();
        const step = event.shiftKey ? 5 : 1;
        const dx = event.key === "ArrowLeft" ? -step : event.key === "ArrowRight" ? step : 0;
        const dy = event.key === "ArrowUp" ? -step : event.key === "ArrowDown" ? step : 0;
        setPreview((current) => current ? {
          ...current,
          candidate: [current.candidate[0] + dx, current.candidate[1] + dy],
          right: current.right ? [current.right[0] + dx, current.right[1] + dy] : undefined,
          snapped: false,
        } : null);
      }
    };
    const keyboardUp = (event: KeyboardEvent) => {
      if (event.code === "Space") {
        event.preventDefault();
        setSpacePan(false);
      }
    };
    const windowBlur = () => setSpacePan(false);
    window.addEventListener("keydown", keyboard);
    window.addEventListener("keyup", keyboardUp);
    window.addEventListener("blur", windowBlur);
    return () => {
      window.removeEventListener("keydown", keyboard);
      window.removeEventListener("keyup", keyboardUp);
      window.removeEventListener("blur", windowBlur);
    };
  }, [confirmPreview, undo, preview, diameterFirst, pendingManualLeft, manualBall, measureMode, zoomBy]);

  const confirmBall = () => {
    if (!currentCandidate) return;
    setConfirmedBalls((current) => ({ ...current, [view]: currentCandidate }));
    setMessage(`参考球已确认：${currentCandidate.pixels_per_unit.toFixed(2)} px/${session.unit}`);
    notify("参考球已确认", "success");
    if (session.mode === "stereo" && view === "left" && !confirmedBalls.right) setView("right");
  };

  const resetBall = (side: ViewName) => {
    setConfirmedBalls((current) => {
      const next = { ...current };
      delete next[side];
      return next;
    });
    setManualBall(false);
    setManualBallPoints([]);
  };

  const newBranch = () => {
    setBranches((current) => [...current, {
      id: current.length + 1, key: `叶片${current.length}`, points: [], rightPoints: [], points3d: [], diameters: [],
    }]);
    cancelPending();
    notify("已新建分支", "info");
  };

  const branchPayload = () => visibleBranches.map((branch) => ({
    ...branch,
    branch_id: branch.id,
    vertices: branch.points,
    vertices_right: branch.rightPoints,
    vertices_3d: branch.points3d,
    length_units: session.mode === "stereo"
      ? polylineLength(branch.points3d)
      : polylineLength(branch.points) / (monoScale ?? 1),
    diameter_measurements: branch.diameters,
    unit: session.unit,
  }));

  const saveLocal = async (continueNext = false) => {
    try {
      const result = await saveAnnotation({
        sessionId: session.session_id,
        capturedAt: session.source?.captured_at,
        branches: branchPayload(),
        calibration: confirmedBalls,
      });
      const annotated = await renderAnnotatedBlob();
      if (annotated) await saveAnnotationImage(session.session_id, annotated);
      notify(`测量数据和标注图已保存：${result.path}`, "success");
      onSaved?.();
      if (continueNext && onSaveNext) await onSaveNext();
    } catch (reason) {
      notify(reason instanceof Error ? reason.message : "保存失败", "error");
    }
  };

  const exportResult = () => {
    const payload = {
      schema_version: 2,
      mode: session.mode,
      images: session.mode === "monocular" ? { primary: names[0] } : { left: names[0], right: names[1] },
      unit: session.unit,
      calibration: confirmedBalls,
      branches: branchPayload(),
    };
    download("picmeasure_result.json", JSON.stringify(payload, null, 2));
    notify("测量结果已导出", "success");
  };

  const renderAnnotatedBlob = async (): Promise<Blob | null> => {
    const leftStage = stageRef.current;
    if (!leftStage) return null;
    const load = (src: string) => new Promise<HTMLImageElement>((resolve, reject) => {
      const image = new window.Image(); image.onload = () => resolve(image); image.onerror = reject; image.src = src;
    });
    const leftExport = await load(leftStage.toDataURL({ pixelRatio: 2 }));
    const rightExport = session.mode === "stereo" && rightStageRef.current
      ? await load(rightStageRef.current.toDataURL({ pixelRatio: 2 }))
      : null;
    const imageWidth = leftExport.width + (rightExport?.width ?? 0);
    const imageHeight = Math.max(leftExport.height, rightExport?.height ?? 0);
    const rows = Math.max(1, visibleBranches.length);
    const legendHeight = 46 + rows * 34;
    const canvas = document.createElement("canvas");
    canvas.width = imageWidth;
    canvas.height = imageHeight + legendHeight;
    const context = canvas.getContext("2d");
    if (!context) return null;
    context.fillStyle = "#111312"; context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(leftExport, 0, 0);
    if (rightExport) context.drawImage(rightExport, leftExport.width, 0);
    context.fillStyle = "#171918"; context.fillRect(0, imageHeight, canvas.width, legendHeight);
    context.fillStyle = "#35c98b"; context.font = "600 22px sans-serif";
    context.fillText(`PicMeasure · ${names.join(" / ")}`, 24, imageHeight + 30);
    visibleBranches.forEach((branch, index) => {
      const length = session.mode === "stereo" ? polylineLength(branch.points3d) : polylineLength(branch.points) / (monoScale ?? 1);
      const diameterText = branch.diameters.length ? ` · 直径 ${branch.diameters.map((item) => item.value.toFixed(2)).join(", ")} ${session.unit}` : "";
      context.fillStyle = "#e8ece9"; context.font = "20px sans-serif";
      context.fillText(`${branch.key || `分支${branch.id}`}：长度 ${length.toFixed(2)} ${session.unit}${diameterText}`, 24, imageHeight + 64 + index * 34);
    });
    return new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
  };

  const exportCanvas = async () => {
    const blob = await renderAnnotatedBlob();
    if (!blob) return;
    const uri = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = uri; anchor.download = "picmeasure_annotated.png"; anchor.click();
    URL.revokeObjectURL(uri);
    notify("带 key 和测量值的标注图已导出", "success");
  };

  const wheel = (event: Konva.KonvaEventObject<WheelEvent>) => {
    event.evt.preventDefault();
    const stage = event.target.getStage();
    const pointer = stage?.getPointerPosition();
    if (!stage || !pointer) return;
    const oldScale = stage.scaleX();
    const nextScale = Math.max(0.05, Math.min(12, event.evt.deltaY > 0 ? oldScale / 1.12 : oldScale * 1.12));
    const imagePosition = { x: (pointer.x - stage.x()) / oldScale, y: (pointer.y - stage.y()) / oldScale };
    setStageTransform({
      scale: nextScale,
      x: pointer.x - imagePosition.x * nextScale,
      y: pointer.y - imagePosition.y * nextScale,
    });
  };

  const branchColor = (index: number) => ["#35c98b", "#5ea2ff", "#f2b84b", "#e879b5"][index % 4];

  const crosshair = (point: Point, color: string, key: string, size = 6) => [
    <Line key={`${key}-h`} points={[point[0] - size / stageTransform.scale, point[1], point[0] + size / stageTransform.scale, point[1]]} stroke={color} strokeWidth={1 / stageTransform.scale} />,
    <Line key={`${key}-v`} points={[point[0], point[1] - size / stageTransform.scale, point[0], point[1] + size / stageTransform.scale]} stroke={color} strokeWidth={1 / stageTransform.scale} />,
    <Circle key={`${key}-dot`} x={point[0]} y={point[1]} radius={1.5 / stageTransform.scale} fill={color} />,
  ];

  const candidatesForSide = (side: "left" | "right" | "primary") => {
    if (Array.isArray(session.ball_candidates)) return side === "primary" ? session.ball_candidates : [];
    return side === "right" ? session.ball_candidates.right : session.ball_candidates.left;
  };

  const renderStage = (side: "left" | "right" | "primary") => {
    const isRight = side === "right";
    const meta = isRight ? rightMeta : leftMeta;
    const image = isRight ? rightImage : leftImage;
    if (!meta) return null;
    const activeView: ViewName = isRight ? "right" : session.mode === "stereo" ? "left" : "primary";
    const sideCandidates = candidatesForSide(side);
    const sideRef = isRight ? rightStageRef : stageRef;
    return (
      <div className="stereo-pane" key={side}>
        {session.mode === "stereo" && <div className="stereo-pane-label">{isRight ? "右图" : "左图"}</div>}
        <Stage
          ref={sideRef}
          width={paneWidth}
          height={stageSize.height}
          x={stageTransform.x}
          y={stageTransform.y}
          scaleX={stageTransform.scale}
          scaleY={stageTransform.scale}
          draggable={panning}
          onDragEnd={(event) => setStageTransform((current) => ({ ...current, x: event.target.x(), y: event.target.y() }))}
          onWheel={wheel}
          onClick={() => handleCanvasClick(side)}
          onMouseMove={() => setHoverPoint(imagePoint(side))}
          onMouseLeave={() => setHoverPoint(null)}
        >
          <Layer>
            {image && <KonvaImage image={image} width={meta.width} height={meta.height} />}
            {session.mode === "monocular" && overlays && !confirmedBalls[activeView] && !calibrationSkipped && !manualBall && sideCandidates.map((candidate, index) => (
              <Circle key={`${side}-${candidate.center[0]}-${candidate.center[1]}`} x={candidate.center[0]} y={candidate.center[1]} radius={candidate.radius} stroke={index === candidateIndex ? "#36e0b4" : "#ffd15c"} strokeWidth={(index === candidateIndex ? 2 : 1) / stageTransform.scale} opacity={index === candidateIndex ? 1 : 0.48} />
            ))}
            {session.mode === "monocular" && overlays && !confirmedBalls[activeView] && !calibrationSkipped && !manualBall && sideCandidates.map((candidate, index) => (
              <Text key={`${side}-label-${index}`} x={candidate.center[0] - candidate.radius} y={candidate.center[1] - candidate.radius - 15 / stageTransform.scale} text={`${index + 1}`} fontSize={11 / stageTransform.scale} fill={index === candidateIndex ? "#36e0b4" : "#ffd15c"} />
            ))}
            {overlays && activeView === view && manualBallPoints.map((point, index) => <Circle key={`manual-${index}`} x={point[0]} y={point[1]} radius={5 / stageTransform.scale} stroke="#36e0b4" strokeWidth={1.5 / stageTransform.scale} />)}
            {overlays && branches.map((branch, index) => {
              const points = isRight ? branch.rightPoints : branch.points;
              const selectedBranch = selectedKey === `l-${branch.id}`;
              return (
                <>
                  {points.length > 1 && (
                    <Line key={`line-${side}-${branch.id}`} points={points.flat()} stroke={selectedBranch ? "#ffffff" : branchColor(index)} strokeWidth={(selectedBranch ? 2.5 : 1.5) / stageTransform.scale} opacity={0.85} />
                  )}
                  {points.flatMap((point, pointIndex) => crosshair(point, selectedBranch ? "#ffffff" : branchColor(index), `${side}-${branch.id}-${pointIndex}`, 5))}
                  {branch.diameters.map((diameter) => {
                    const edges = isRight ? diameter.rightEdges : diameter.leftEdges;
                    const selectedDiameter = selectedKey === `d-${branch.id}-${diameter.sectionId}`;
                    return edges ? (
                      <Line key={`${side}-d-${branch.id}-${diameter.sectionId}`} points={edges.flat()} stroke={selectedDiameter ? "#ffffff" : branchColor(index)} strokeWidth={(selectedDiameter ? 2.5 : 1.5) / stageTransform.scale} />
                    ) : null;
                  })}
                </>
              );
            })}
            {overlays && diameterFirst && (isRight ? diameterFirst.right : !isRight) && crosshair(isRight ? diameterFirst.right! : diameterFirst.candidate, "#58e6c0", `${side}-diameter-first`, 7)}
            {overlays && pendingManualLeft && !isRight && (
              crosshair(pendingManualLeft.candidate, "#ffd15c", `${side}-pending`, 7)
            )}
            {overlays && preview && (
              isRight ? preview.right && crosshair(preview.right, "#36e0b4", `${side}-preview`, 7) : (
                <>
                  <Line points={[...preview.raw, ...preview.candidate]} stroke="#ffffff" dash={[5 / stageTransform.scale, 4 / stageTransform.scale]} strokeWidth={1 / stageTransform.scale} />
                  {crosshair(preview.raw, "#fff", `${side}-raw`, 5)}
                  {crosshair(preview.candidate, "#36e0b4", `${side}-preview`, 7)}
                </>
              )
            )}
          </Layer>
        </Stage>
      </div>
    );
  };

  const stepLabel = useMemo(() => {
    if (manualBall) {
      const label = view === "right" ? "右图" : "左图";
      return manualBallPoints.length === 0
        ? `手动校准（${label}）：点击参考球圆心`
        : `手动校准（${label}）：点击参考球圆周边缘`;
    }
    if (session.mode === "monocular" && !confirmedBalls.primary && !calibrationSkipped) {
      return candidates.length
        ? "第 1 步：在左侧确认参考球候选，或手动指定圆心与边缘"
        : "第 1 步：没有自动候选，请手动指定参考球";
    }
    if (pendingManualLeft) return "左图点已锁定：在右图点击对应位置";
    if (preview) return preview.snapped ? "已吸附：检查位置后 Enter 确认 / Esc 取消" : "未找到可靠边缘：Enter 使用原位置 / Esc 取消";
    if (diameterFirst) return "直径第一侧已锁定：点击枝条另一侧边缘";
    return measureMode === "length"
      ? "长度模式：点击枝条中心线，逐段选点"
      : "直径模式：点击截面一侧边缘";
  }, [manualBall, manualBallPoints.length, view, session.mode, confirmedBalls.primary, calibrationSkipped, candidates.length, pendingManualLeft, preview, diameterFirst, measureMode]);

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand"><ScanLine size={20} /><strong>PicMeasure</strong><span>{session.mode === "stereo" ? "双目" : "单目"}</span></div>
        <div className="toolbar-group segmented">
          <button className={measureMode === "length" ? "active" : ""} onClick={() => setMeasureModeSafe("length")} title="长度模式 (D)"><Ruler size={16} />长度</button>
          <button className={measureMode === "diameter" ? "active" : ""} onClick={() => setMeasureModeSafe("diameter")} title="直径模式 (D)"><CircleDot size={16} />直径</button>
        </div>
        <div className="icon-tools">
          <button title="选择工具" className={tool === "select" && !spacePan ? "active" : ""} onClick={() => setTool("select")}><MousePointer2 size={17} /></button>
          <button title="平移画布（或按住空格拖动）" className={tool === "pan" || spacePan ? "active" : ""} onClick={() => setTool("pan")}><Hand size={17} /></button>
          <span className="tool-sep" />
          <button title="放大 (+)" onClick={() => zoomBy(1.25)}><ZoomIn size={17} /></button>
          <button title="缩小 (-)" onClick={() => zoomBy(1 / 1.25)}><ZoomOut size={17} /></button>
          <button title="适合窗口" onClick={fitImage}><Maximize2 size={17} /></button>
          <span className="tool-sep" />
          <button title="撤销 (U)" onClick={undo} disabled={!canUndo}><Undo2 size={17} /></button>
          <button title="清除全部测量" onClick={clearMeasurements} disabled={!hasMeasurements}><Trash2 size={17} /></button>
          <button title={overlays ? "隐藏覆盖层 (V)" : "显示覆盖层 (V)"} onClick={() => setOverlays((value) => !value)}>{overlays ? <Eye size={17} /> : <EyeOff size={17} />}</button>
        </div>
        <label className="toggle" title="边缘吸附 (A)"><input type="checkbox" checked={snapping} onChange={(event) => setSnapping(event.target.checked)} /><span />吸附</label>
        {session.mode === "stereo" && <label className="toggle" title="自动匹配失败时手动指定右图对应点"><input type="checkbox" checked={manualMatch} onChange={(event) => setManualMatch(event.target.checked)} /><span />手动匹配</label>}
        <div className="topbar-spacer" />
        {onSkipNext && <button className="command quiet skip-command" onClick={() => void onSkipNext()} title="不保存当前图片，沿用筛选条件进入下一张"><ChevronRight size={16} />{nextMeasurementLabel ? `跳过，下一张 ${nextMeasurementLabel}` : "跳过，返回列表"}</button>}
        <button className="command quiet" onClick={() => void exportCanvas()} title="导出带 key 和数值的标注图片"><Download size={16} />标注图</button>
        <button className="command quiet" onClick={() => void saveLocal()} title="保存到本机数据目录"><Database size={16} />保存本地</button>
        {onSaveNext && <button className="command" onClick={() => void saveLocal(true)} title="沿用列表筛选条件进入下一张"><ChevronRight size={16} />{nextMeasurementLabel ? `保存并下一张 ${nextMeasurementLabel}` : "保存并返回列表"}</button>}
        <button className="command" onClick={exportResult} title="导出 JSON 测量结果"><Save size={16} />结果</button>
        <button className="icon-close" title="关闭当前会话" onClick={onClose}><X size={18} /></button>
      </header>

      <aside className="left-panel">
        <div className="panel-heading"><Settings2 size={16} /><span>校准与视图</span></div>
        <div className="panel-scroll">
          {session.mode === "monocular" && <div className="panel-section">
            <div className="section-title">
              <span>参考球</span>
            <small>{confirmedBalls[view] ? "已确认" : session.mode === "monocular" && calibrationSkipped ? "已跳过" : "待确认"}</small>
            </div>
            {!confirmedBalls[view] && !calibrationSkipped && (
              <>
                {candidates.length > 0 && !manualBall ? (
                  <div className="candidate-control">
                    <div className="candidate-nav">
                      <button onClick={() => setCandidateIndex((value) => (value - 1 + candidates.length) % candidates.length)} title="上一个候选"><ChevronLeft size={16} /></button>
                      <strong>{candidateIndex + 1} / {candidates.length}</strong>
                      <button onClick={() => setCandidateIndex((value) => (value + 1) % candidates.length)} title="下一个候选"><ChevronRight size={16} /></button>
                    </div>
                    <ScoreBar label="综合评分" value={currentCandidate.score} />
                    <ScoreBar label="圆度" value={currentCandidate.circularity} />
                    <ScoreBar label="边缘支持" value={currentCandidate.edge_support} />
                    <div className="candidate-meta"><span>半径</span><strong>{currentCandidate.radius.toFixed(1)} px</strong></div>
                    <button className="primary-command small" onClick={confirmBall}><Check size={16} />确认候选</button>
                  </div>
                ) : (
                  <p className="empty-copy">{manualBall ? (manualBallPoints.length ? "点击圆周边缘" : "点击球心") : "没有可靠自动候选"}</p>
                )}
                <button className="text-command" onClick={() => { setManualBall(true); setManualBallPoints([]); setMessage("请点击参考球圆心"); }}><MousePointer2 size={14} />手动指定圆心和边缘</button>
                {session.mode === "monocular" && (
                  <>
                    <button className="text-command muted" onClick={() => { setCalibrationSkipped(true); setMessage("已跳过参考球校验，可直接测量"); }}>跳过球体校验</button>
                    <p className="hint-line">跳过后将不进行像素尺度校验。</p>
                  </>
                )}
              </>
            )}
            {confirmedBalls[view] && (
              <div className="confirmed-calibration">
                <Check size={18} />
                <div><strong>{confirmedBalls[view]!.pixels_per_unit.toFixed(2)} px/{session.unit}</strong><span>{session.saved_calibration && confirmedBalls[view] === session.saved_calibration ? `固定标定 · ${session.saved_calibration.image_key}` : confirmedBalls[view]!.method === "manual" ? "手动校准" : "候选已确认"}</span></div>
                <button title="重新校准" onClick={() => resetBall(view)}><Undo2 size={14} /></button>
              </div>
            )}
          </div>}

          <div className="panel-section">
            <div className="section-title"><span>视图</span><small>滚轮缩放 · 空格拖动</small></div>
            <div className="view-controls">
              <button onClick={() => zoomBy(1 / 1.25)} disabled={stageTransform.scale <= 0.05} title="缩小 (-)"><ZoomOut size={15} /></button>
              <button onClick={fitImage} title="适合窗口"><Maximize2 size={15} /></button>
              <button onClick={() => zoomBy(1.25)} disabled={stageTransform.scale >= 20} title="放大 (+)"><ZoomIn size={15} /></button>
              <span>{Math.round(stageTransform.scale * 100)}%</span>
            </div>
            {session.mode === "stereo" && (
              <div className="segmented wide compact">
                <button className={view === "left" ? "active" : ""} onClick={() => setView("left")}>左图</button>
                <button className={view === "right" ? "active" : ""} onClick={() => setView("right")}>右图</button>
              </div>
            )}
          </div>

          <div className="panel-section">
            <div className="section-title"><span>图像</span></div>
            <div className="file-summary"><strong>{view === "right" ? names[1] : names[0]}</strong><small>{imageMeta.width} × {imageMeta.height} px</small></div>
          </div>
          {session.mode === "stereo" && session.alignment && (
            <div className="panel-section">
              <div className="section-title"><span>双目对齐</span><small>{session.alignment.source === "features" ? "当前图像特征" : "配置外参"}</small></div>
              <div className="candidate-meta"><span>特征 / 内点</span><strong>{session.alignment.matches} / {session.alignment.inliers}</strong></div>
              <div className="candidate-meta"><span>纵向误差 P50</span><strong>{session.alignment.median_vertical_error_px.toFixed(2)} px</strong></div>
              <div className="candidate-meta"><span>纵向误差 P90</span><strong>{session.alignment.p90_vertical_error_px.toFixed(2)} px</strong></div>
            </div>
          )}
        </div>
      </aside>

      <main className={`canvas-area${session.mode === "stereo" ? " stereo-canvas" : ""}${panning ? " panning" : ""}`} ref={canvasHost}>
        {session.mode === "stereo" ? <>{renderStage("left")}{renderStage("right")}</> : renderStage("primary")}
        <div className="step-banner">
          <b>{stepLabel.startsWith("第 1 步") ? 1 : stepLabel.startsWith("手动校准") ? "手" : "i"}</b>
          <span>{stepLabel}</span>
        </div>
      </main>

      <aside className="right-panel">
        <div className="panel-heading">
          <Ruler size={16} /><span>测量结果</span>
          <small>{visibleBranches.length} 分支 · {diameterCount} 直径</small>
          <button title="新建分支" onClick={newBranch} disabled={!hasMeasurements || !currentBranch.points.length && !currentBranch.diameters.length}><Plus size={15} /></button>
        </div>
        <div className="result-scroll">
          {visibleBranches.length === 0 ? (
            <div className="empty-copy empty-results">
              <Ruler size={22} />
              <p>还没有测量数据。<br />选择长度或直径模式后，在画布上点击即可开始。</p>
            </div>
          ) : visibleBranches.map((branch) => {
            const length = session.mode === "stereo" ? polylineLength(branch.points3d) : polylineLength(branch.points) / (monoScale ?? 1);
            return (
              <section className="branch-section" key={branch.id}>
                <header>
                  <input
                    className="branch-key-input"
                    value={branch.key}
                    placeholder="例如：树枝、叶片1"
                    onChange={(event) => setBranches((current) => current.map((item) => item.id === branch.id ? { ...item, key: event.target.value } : item))}
                  />
                  <div className="branch-actions">
                    <span>{branch.points.length} 点 · {branch.diameters.length} 直径</span>
                    <button title="删除此分支" onClick={() => removeBranch(branch.id)}><Trash2 size={13} /></button>
                  </div>
                </header>
                <div
                  className={`primary-value${selectedKey === `l-${branch.id}` ? " selected" : ""}`}
                  onClick={() => setSelectedKey(selectedKey === `l-${branch.id}` ? null : `l-${branch.id}`)}
                  title="点击在画布中高亮长度"
                >
                  <small>长度</small>
                  <strong>{Number.isFinite(length) ? length.toFixed(2) : "--"}</strong>
                  <span>{session.unit}</span>
                </div>
                {branch.diameters.map((diameter) => (
                  <div
                    className={`diameter-row${selectedKey === `d-${branch.id}-${diameter.sectionId}` ? " selected" : ""}`}
                    key={diameter.sectionId}
                    onClick={() => setSelectedKey(selectedKey === `d-${branch.id}-${diameter.sectionId}` ? null : `d-${branch.id}-${diameter.sectionId}`)}
                    title="点击在画布中高亮直径"
                  >
                    <span>D{diameter.sectionId}</span>
                    <strong>{diameter.value.toFixed(2)}</strong>
                    <small>{session.unit}</small>
                    <em>{Math.round(diameter.pixels)} px</em>
                    <button title="删除此直径" onClick={(event) => { event.stopPropagation(); removeDiameter(branch.id, diameter.sectionId); }}><X size={12} /></button>
                  </div>
                ))}
              </section>
            );
          })}
        </div>
      </aside>

      <footer className="statusbar">
        <span className={error ? "status-error" : "status-dot"} />
        <strong>{error || message}</strong>
        {hoverPoint && <span className="coords">X {hoverPoint[0]} · Y {hoverPoint[1]} px</span>}
        <span className="status-spacer" />
        <span className="zoom-readout">{Math.round(stageTransform.scale * 100)}%</span>
        <span className="status-shortcuts">
          <span>Enter 确认</span><kbd>D</kbd><span>模式</span><kbd>A</kbd><span>吸附</span><kbd>U</kbd><span>撤销</span>
        </span>
      </footer>
      <ConfirmBar
        preview={preview}
        diameterFirst={diameterFirst}
        pendingManualLeft={pendingManualLeft}
        sessionMode={session.mode}
        monoScale={monoScale}
        unit={session.unit}
        onConfirm={confirmPreview}
        onCancel={cancelPending}
      />
      {toast && (
        <div className={`toast ${toast.kind}`}>
          {toast.kind === "error" ? <XCircle size={15} /> : toast.kind === "success" ? <Check size={15} /> : <Info size={15} />}
          <span>{toast.text}</span>
        </div>
      )}
    </div>
  );
}

function TrendChart({ series, onRemeasure }: { series: Record<string, SeriesPoint[]>; onRemeasure: (point: SeriesPoint) => void }) {
  const [selected, setSelected] = useState<{ key: string; point: SeriesPoint } | null>(null);
  const entries = Object.entries(series);
  if (!entries.length) return <div className="remote-empty">保存带 key 的测量结果后，这里会显示时间曲线。</div>;
  const colors = ["#35c98b", "#f2b84b", "#74a7ff", "#ff7b72", "#c58cff"];
  const values = entries.flatMap(([, points]) => points.map((point) => point.value));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(max - min, 1);
  return (
    <div className="trend-linked-view">
      <div className="trend-card">
      <svg viewBox="0 0 900 380" role="img" aria-label="语义测量曲线">
        {[0, 1, 2, 3, 4].map((line) => <line key={line} x1="60" y1={30 + line * 75} x2="875" y2={30 + line * 75} className="chart-grid" />)}
        {entries.map(([key, points], seriesIndex) => {
          const path = points.map((point, index) => {
            const x = 60 + (points.length === 1 ? 407 : index * 815 / (points.length - 1));
            const y = 330 - ((point.value - min) / range) * 280;
            return `${index ? "L" : "M"}${x},${y}`;
          }).join(" ");
          return <g key={key}><path d={path} fill="none" stroke={colors[seriesIndex % colors.length]} strokeWidth="3" />{points.map((point, index) => { const x = 60 + (points.length === 1 ? 407 : index * 815 / (points.length - 1)); const y = 330 - ((point.value - min) / range) * 280; const active = selected?.key === key && selected.point.timestamp === point.timestamp && selected.point.target === point.target; return <circle className="chart-point" key={`${point.timestamp}-${point.target}-${index}`} cx={x} cy={y} r={active ? 9 : 6} fill={colors[seriesIndex % colors.length]} stroke={active ? "#ffffff" : "#171918"} strokeWidth={active ? 3 : 2} onClick={() => setSelected({ key, point })}><title>{key} {point.value.toFixed(2)} {point.unit} · {point.timestamp}</title></circle>; })}</g>;
        })}
        <text x="12" y="50" className="chart-label">{max.toFixed(1)}</text>
        <text x="12" y="334" className="chart-label">{min.toFixed(1)}</text>
      </svg>
      <div className="chart-legend">{entries.map(([key], index) => <span key={key}><i style={{ background: colors[index % colors.length] }} />{key}</span>)}</div>
      <p className="chart-help">点击曲线上的数据点，在下方查看对应标注图。</p>
      </div>
      <section className="trend-image-panel">
        {selected ? <>
          <header><div><strong>{selected.key}</strong><span>{selected.point.timestamp} · {selected.point.target ?? "图片"}</span></div><div className="trend-point-actions"><b>{selected.point.value.toFixed(2)} {selected.point.unit}</b><button className="command quiet" disabled={!selected.point.annotation_id} onClick={() => onRemeasure(selected.point)}><Ruler size={14} />重新测量这张图片</button></div></header>
          {selected.point.image_url ? <img src={selected.point.image_url} alt={`${selected.key} ${selected.point.timestamp} 标注图`} /> : <div className="remote-empty">这条旧测量记录没有保存标注图。重新打开并保存后即可显示。</div>}
        </> : <div className="trend-select-prompt"><ImagePlus size={28} /><strong>选择一个曲线数据点</strong><span>对应的测量标注图会显示在这里</span></div>}
      </section>
    </div>
  );
}

interface RemoteQueueTarget { capture: RemoteCapture; imageKey: string }

function localDateInput(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function RemoteHome({ onReady, onSetup, refreshToken }: { onReady: (session: SessionResponse, names: string[], queue?: RemoteQueueTarget[]) => void; onSetup: () => void; refreshToken: number }) {
  const [data, setData] = useState<RemoteCaptureResponse | null>(null);
  const [series, setSeries] = useState<Record<string, SeriesPoint[]>>({});
  const [savedRecords, setSavedRecords] = useState<SavedAnnotationRecord[]>([]);
  const [tab, setTab] = useState<"captures" | "trends" | "records">("captures");
  const [busy, setBusy] = useState(false);
  const [opening, setOpening] = useState<string | null>(null);
  const [calibrationFile, setCalibrationFile] = useState<File | undefined>();
  const [onlyUnmeasured, setOnlyUnmeasured] = useState(true);
  const [keyFilter, setKeyFilter] = useState("key3");
  const [error, setError] = useState("");
  const today = useMemo(() => new Date(), []);
  const defaultStart = useMemo(() => { const date = new Date(today); date.setDate(date.getDate() - 29); return date; }, [today]);
  const [startDate, setStartDate] = useState(localDateInput(defaultStart));
  const [endDate, setEndDate] = useState(localDateInput(today));
  const [appliedRange, setAppliedRange] = useState({ start: localDateInput(defaultStart), end: localDateInput(today) });
  const reload = useCallback(async () => {
    setBusy(true); setError("");
    try {
      setData(await listRemoteCaptures(3331, appliedRange.start, appliedRange.end));
      setSeries((await loadSeries(3331)).series);
      setSavedRecords((await listSavedAnnotations(3331)).records);
    }
    catch (reason) { setError(reason instanceof Error ? reason.message : "远程数据读取失败"); }
    finally { setBusy(false); }
  }, [appliedRange]);
  useEffect(() => { void reload(); }, [reload, refreshToken]);
  const dailyCaptures = useMemo(() => {
    const closestByDay = new Map<string, { capture: RemoteCapture; distance: number }>();
    for (const capture of data?.captures ?? []) {
      if (keyFilter !== "all" && !capture.images[keyFilter]) continue;
      const captured = new Date(capture.captured_at.replace(" ", "T"));
      if (Number.isNaN(captured.getTime())) continue;
      const day = localDateInput(captured);
      const target = new Date(captured);
      target.setHours(10, 0, 0, 0);
      const distance = Math.abs(captured.getTime() - target.getTime());
      const current = closestByDay.get(day);
      if (!current || distance < current.distance) closestByDay.set(day, { capture, distance });
    }
    return [...closestByDay.values()]
      .map((item) => item.capture)
      .sort((left, right) => left.captured_at.localeCompare(right.captured_at));
  }, [data, keyFilter]);
  const measurementQueue = useMemo<RemoteQueueTarget[]>(() => dailyCaptures.flatMap((capture) =>
    ["key1", "key2", "key3", "key4"]
      .filter((key) => capture.images[key])
      .filter((key) => keyFilter === "all" || key === keyFilter)
      .filter((key) => !onlyUnmeasured || !capture.images[key].measurement.measured)
      .map((imageKey) => ({ capture, imageKey })),
  ), [dailyCaptures, keyFilter, onlyUnmeasured]);
  const visibleCaptureIds = useMemo(() => new Set(measurementQueue.map((target) => target.capture.id)), [measurementQueue]);
  const openCapture = async (capture: RemoteCapture) => {
    setOpening(capture.id); setError("");
    try {
      const session = await createRemoteStereo(capture, calibrationFile);
      onReady(session, [`key3 · ${capture.captured_at}`, `key2 · ${capture.captured_at}`]);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "无法打开双目记录"); }
    finally { setOpening(null); }
  };
  const openMonocular = async (capture: RemoteCapture, imageKey: string) => {
    const operation = `${capture.id}-${imageKey}`;
    setOpening(operation); setError("");
    try {
      const session = await createRemoteMonocular(capture, imageKey);
      const index = measurementQueue.findIndex((target) => target.capture.id === capture.id && target.imageKey === imageKey);
      onReady(session, [`${imageKey} · ${capture.captured_at}`], index >= 0 ? measurementQueue.slice(index + 1) : []);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "无法打开单目记录"); }
    finally { setOpening(null); }
  };
  const removeSavedRecord = async (record: SavedAnnotationRecord) => {
    if (!window.confirm(`确定删除 ${record.captured_at ?? record.id} 的测量结果吗？`)) return;
    setError("");
    try {
      await deleteSavedAnnotation(3331, record.id);
      await reload();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "删除测量结果失败"); }
  };
  const remeasureSeriesPoint = async (point: SeriesPoint) => {
    if (!point.annotation_id) return;
    setOpening(point.annotation_id); setError("");
    try {
      const session = await reopenSavedAnnotation(3331, point.annotation_id);
      onReady(session, [`${point.target ?? "图片"} · ${point.timestamp}`]);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "无法重新打开测量图片"); }
    finally { setOpening(null); }
  };
  return (
    <main className="remote-shell">
      <header className="remote-header">
        <div className="product-mark"><ScanLine size={24} /><span>PicMeasure 数据工作台</span></div>
        <div className="remote-device"><Database size={15} /><strong>{data?.device.name ?? "设备 3331"}</strong><span>ID 3331 · {data?.device.status ?? "连接中"}</span></div>
        <a className="command export-bundle" href={deviceExportUrl(3331)}><Download size={15} />导出 Excel + 测量图片</a>
        <button className="command quiet" onClick={onSetup}>标定与本地工具</button>
      </header>
      <nav className="remote-tabs">
        <button className={tab === "captures" ? "active" : ""} onClick={() => setTab("captures")}><Camera size={16} />月度测量任务</button>
        <button className={tab === "trends" ? "active" : ""} onClick={() => setTab("trends")}><ChartNoAxesCombined size={16} />测量曲线</button>
        <button className={tab === "records" ? "active" : ""} onClick={() => setTab("records")}><Ruler size={16} />保存结果</button>
        <button className="refresh" onClick={() => void reload()} disabled={busy}><RefreshCw size={15} className={busy ? "spinning" : ""} />刷新</button>
      </nav>
      <div className="remote-calibration">
        <div><strong>双目标定文件</strong><span>{calibrationFile ? `本次使用：${calibrationFile.name}` : "默认使用根目录 stereo.toml"}</span></div>
        <label className="command quiet calibration-picker"><Upload size={15} />选择其他 TOML<input type="file" accept=".toml,application/toml,text/plain" onChange={(event) => setCalibrationFile(event.target.files?.[0])} /></label>
        {calibrationFile && <button className="text-command" onClick={() => setCalibrationFile(undefined)}>恢复默认</button>}
      </div>
      {error && <div className="remote-error"><XCircle size={16} />{error}</div>}
      {tab === "trends" ? <section className="trend-view"><div><h1>设备 3331 语义测量趋势</h1><p>按树枝、叶片等 key 汇总本地保存的长度结果。</p></div><TrendChart series={series} onRemeasure={(point) => void remeasureSeriesPoint(point)} /></section> : tab === "records" ? (
        <section className="records-view">
          <div className="capture-title"><div><h1>本地保存结果</h1><p>删除后，对应的曲线数据、已测量状态和标注图片也会移除。</p></div><strong>{savedRecords.length} 条记录</strong></div>
          <div className="records-table-wrap"><table className="records-table"><thead><tr><th>采集时间</th><th>图片</th><th>模式</th><th>测量结果</th><th>保存时间</th><th>操作</th></tr></thead><tbody>
            {savedRecords.map((record) => <tr key={record.id}><td>{record.captured_at ?? "—"}</td><td>{record.target}</td><td>{record.mode === "stereo" ? "双目" : "单目"}</td><td>{record.measurements.length ? record.measurements.map((item) => `${item.key || "未命名"}: ${typeof item.value === "number" ? item.value.toFixed(2) : "—"} ${item.unit ?? ""}`).join("；") : "无测量项"}</td><td>{record.saved_at ?? "—"}</td><td><button className="record-delete" onClick={() => void removeSavedRecord(record)}><Trash2 size={14} />删除</button></td></tr>)}
          </tbody></table>{savedRecords.length === 0 && <div className="remote-empty">目前没有本地保存的测量结果。</div>}</div>
        </section>
      ) : (
        <section className="capture-view">
          <div className="capture-title"><div><h1>月度测量任务</h1><p>{appliedRange.start} 至 {appliedRange.end} · key3 · 每天最接近上午 10:00 · 从旧到新</p></div><strong>{measurementQueue.length} 天待测量</strong></div>
          <div className="queue-controls">
            <label>开始日期<input type="date" value={startDate} max={endDate} onChange={(event) => setStartDate(event.target.value)} /></label>
            <label>结束日期<input type="date" value={endDate} min={startDate} onChange={(event) => setEndDate(event.target.value)} /></label>
            <button className="command quiet range-command" disabled={busy || !startDate || !endDate || startDate > endDate} onClick={() => setAppliedRange({ start: startDate, end: endDate })}>查询</button>
            <label><input type="checkbox" checked={onlyUnmeasured} onChange={(event) => setOnlyUnmeasured(event.target.checked)} />只看未测量</label>
            <label>图片<select value={keyFilter} onChange={(event) => setKeyFilter(event.target.value)}><option value="all">全部 key</option><option value="key1">key1</option><option value="key2">key2</option><option value="key3">key3</option><option value="key4">key4</option></select></label>
          </div>
          <div className="capture-list">{dailyCaptures.filter((capture) => visibleCaptureIds.has(capture.id)).map((capture) => (
            <article className="capture-card" key={capture.id}>
              <div className="capture-meta"><strong>{capture.captured_at}</strong><span className={capture.stereo_measurement.measured ? "measured" : "pending"}>{capture.stereo_measurement.measured ? "双目已测量" : capture.stereo_ready ? "双目未测量" : "双目图片不完整"}</span></div>
              <div className="capture-images">
                {(["key1", "key2", "key3", "key4"] as const).map((key) => capture.images[key] && (keyFilter === "all" || keyFilter === key) && (!onlyUnmeasured || !capture.images[key].measurement.measured) ? <figure key={key} className={capture.images[key].measurement.measured ? "image-measured" : ""}>
                  <img src={remoteImageUrl(capture.device_id, capture.images[key].path)} loading="lazy" />
                  <figcaption><span><b>{key}</b><em className={capture.images[key].measurement.measured ? "measured" : "pending"}>{capture.images[key].measurement.measured ? `已测量 · ${capture.images[key].measurement.branch_count ?? 0} 项` : "未测量"}</em></span><button disabled={opening !== null} onClick={() => void openMonocular(capture, key)}>{opening === `${capture.id}-${key}` ? "打开中…" : capture.images[key].measurement.measured ? "继续修改" : "开始测量"}</button></figcaption>
                </figure> : null)}
              </div>
              <button className="stereo-row-action" disabled={!capture.stereo_ready || opening !== null} onClick={() => void openCapture(capture)}>{opening === capture.id ? "正在下载并对齐…" : capture.stereo_measurement.measured ? "继续修改双目结果" : "测量 key3 + key2 双目"}</button>
            </article>
          ))}</div>
          {!busy && measurementQueue.length === 0 && <div className="remote-empty">当前筛选条件下没有待测量图片。</div>}
          {busy && !data && <div className="remote-empty">正在连接远程数据库并读取 OSS 图片…</div>}
        </section>
      )}
    </main>
  );
}

export default function App() {
  const [session, setSession] = useState<SessionResponse | null>(null);
  const [calibration, setCalibration] = useState<StereoCalibrationResult | null>(null);
  const [names, setNames] = useState<string[]>([]);
  const [showSetup, setShowSetup] = useState(false);
  const [measurementQueue, setMeasurementQueue] = useState<RemoteQueueTarget[]>([]);
  const [remoteRefreshToken, setRemoteRefreshToken] = useState(0);
  const openNextMeasurement = async () => {
    const [next, ...rest] = measurementQueue;
    if (!next) {
      setSession(null);
      return;
    }
    const nextSession = await createRemoteMonocular(next.capture, next.imageKey);
    setSession(nextSession);
    setNames([`${next.imageKey} · ${next.capture.captured_at}`]);
    setMeasurementQueue(rest);
  };
  const overlayOpen = Boolean(calibration || session || showSetup);
  return <>
    <div className={overlayOpen ? "preserved-home hidden" : "preserved-home"}>
      <RemoteHome refreshToken={remoteRefreshToken} onReady={(next, nextNames, queue = []) => { setSession(next); setNames(nextNames); setMeasurementQueue(queue); }} onSetup={() => setShowSetup(true)} />
    </div>
    {calibration ? (
      <div className="app-overlay"><CalibrationResult result={calibration} onClose={() => setCalibration(null)} /></div>
    ) : session ? (
      <div className="app-overlay"><Workbench key={session.session_id} session={session} names={names} onClose={() => { setSession(null); setMeasurementQueue([]); }} onSaved={() => setRemoteRefreshToken((value) => value + 1)} onSaveNext={session.mode === "monocular" && session.source?.kind === "remote" ? openNextMeasurement : undefined} onSkipNext={session.mode === "monocular" && session.source?.kind === "remote" ? openNextMeasurement : undefined} nextMeasurementLabel={measurementQueue[0]?.imageKey} /></div>
    ) : showSetup ? (
      <div className="app-overlay setup-with-back"><button className="setup-back" onClick={() => setShowSetup(false)}><ChevronLeft size={16} />返回远程数据</button><UploadScreen onReady={(next, nextNames) => { setSession(next); setNames(nextNames); }} onCalibrated={setCalibration} /></div>
    ) : null}
  </>;
}
