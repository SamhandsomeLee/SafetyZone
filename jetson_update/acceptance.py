"""Frozen-testset recall acceptance gate (#49 / design §8.3).

Runs a candidate TensorRT FP16 engine against the field-locked testset and
**rejects** promotion when recall is below the D5 threshold.

D5 threshold
------------
``docs/decisions.md`` still lists D5 as「阶段三前与现场共定」. Until a site
value is written there, this module uses a **configurable placeholder**
default of ``0.95`` (``DEFAULT_RECALL_THRESHOLD``). Do not treat the
placeholder as a safety sign-off; M9 is pending a real D5 number.

API
---
::

    from jetson_update.acceptance import AcceptanceConfig, run_acceptance

    result = run_acceptance(
        AcceptanceConfig(engine_path=Path("cand.engine"), testset_dir=Path("jetson_update/testset")),
        evaluate_fn=my_mock,  # inject for tests / CI without GPU
    )
    if not result.passed:
        # must NOT hotswap (#50)
        ...

CLI
---
::

    PYTHONPATH=. python -m jetson_update.acceptance \\
        --engine jetson_update/candidates/model.engine \\
        --testset jetson_update/testset \\
        [--threshold 0.95] [--dry-run]

``--dry-run`` skips inference and **never** reports a production pass
(cannot claim M9). Use ``evaluate_fn`` in tests to exercise the threshold gate.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from jetson_update.testset.manifest import ManifestError, TestsetManifest, load_manifest

logger = logging.getLogger(__name__)

# Placeholder until D5 is written in docs/decisions.md (site co-decision).
DEFAULT_RECALL_THRESHOLD = 0.95
DEFAULT_IOU_MATCH = 0.5
DEFAULT_CONF = 0.25
DEFAULT_NMS_IOU = 0.45
DEFAULT_TESTSET_DIR = Path("jetson_update/testset")

EvaluateFn = Callable[["AcceptanceConfig", TestsetManifest], "EvalMetrics"]


@dataclass(frozen=True)
class AcceptanceConfig:
    """Inputs for a single acceptance run."""

    engine_path: Path
    testset_dir: Path = DEFAULT_TESTSET_DIR
    recall_threshold: float = DEFAULT_RECALL_THRESHOLD
    iou_match: float = DEFAULT_IOU_MATCH
    conf: float = DEFAULT_CONF
    nms_iou: float = DEFAULT_NMS_IOU
    person_class_id: int = 0


@dataclass(frozen=True)
class EvalMetrics:
    """Aggregate detection metrics over the frozen set."""

    true_positives: int
    false_positives: int
    false_negatives: int

    @property
    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        if denom <= 0:
            return 0.0
        return self.true_positives / denom

    @property
    def precision(self) -> float | None:
        denom = self.true_positives + self.false_positives
        if denom <= 0:
            return None
        return self.true_positives / denom


@dataclass(frozen=True)
class AcceptanceResult:
    """Gate outcome. ``passed=False`` ⇒ do not hotswap."""

    passed: bool
    recall: float
    reason: str
    precision: float | None = None
    threshold: float = DEFAULT_RECALL_THRESHOLD
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    frame_count: int = 0

    @property
    def precision_optional(self) -> float | None:
        """Alias for callers that prefer the design-doc naming."""
        return self.precision

    @property
    def allows_hotswap(self) -> bool:
        """True only when the recall gate passed (consumed by #50 hotswap)."""
        return self.passed


def _reject(
    *,
    reason: str,
    threshold: float,
    recall: float = 0.0,
    precision: float | None = None,
    metrics: EvalMetrics | None = None,
    frame_count: int = 0,
) -> AcceptanceResult:
    tp = metrics.true_positives if metrics else 0
    fp = metrics.false_positives if metrics else 0
    fn = metrics.false_negatives if metrics else 0
    return AcceptanceResult(
        passed=False,
        recall=recall,
        reason=reason,
        precision=precision if precision is not None else (metrics.precision if metrics else None),
        threshold=threshold,
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        frame_count=frame_count,
    )


def _box_iou_xyxy(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter <= 0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def parse_yolo_label_file(
    path: Path,
    *,
    img_w: int,
    img_h: int,
    person_class_id: int = 0,
) -> list[tuple[float, float, float, float]]:
    """Parse YOLO txt → absolute xyxy boxes for ``person_class_id`` only."""
    boxes: list[tuple[float, float, float, float]] = []
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return boxes
    for line_no, line in enumerate(text.splitlines(), start=1):
        parts = line.split()
        if len(parts) < 5:
            raise ValueError(f"{path}:{line_no}: expected class cx cy w h, got {line!r}")
        cls = int(float(parts[0]))
        if cls != person_class_id:
            continue
        cx, cy, w, h = (float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4]))
        x1 = (cx - w / 2.0) * img_w
        y1 = (cy - h / 2.0) * img_h
        x2 = (cx + w / 2.0) * img_w
        y2 = (cy + h / 2.0) * img_h
        boxes.append((x1, y1, x2, y2))
    return boxes


def match_detections(
    gt_boxes: Sequence[tuple[float, float, float, float]],
    pred_boxes: Sequence[tuple[float, float, float, float]],
    *,
    iou_match: float,
) -> tuple[int, int, int]:
    """Greedy IoU matching → (tp, fp, fn)."""
    if not gt_boxes and not pred_boxes:
        return 0, 0, 0
    if not gt_boxes:
        return 0, len(pred_boxes), 0
    if not pred_boxes:
        return 0, 0, len(gt_boxes)

    used_pred: set[int] = set()
    tp = 0
    for gt in gt_boxes:
        best_j = -1
        best_iou = 0.0
        for j, pred in enumerate(pred_boxes):
            if j in used_pred:
                continue
            iou = _box_iou_xyxy(gt, pred)
            if iou > best_iou:
                best_iou = iou
                best_j = j
        if best_j >= 0 and best_iou >= iou_match:
            used_pred.add(best_j)
            tp += 1
    fp = len(pred_boxes) - len(used_pred)
    fn = len(gt_boxes) - tp
    return tp, fp, fn


def evaluate_trt(config: AcceptanceConfig, manifest: TestsetManifest) -> EvalMetrics:
    """Run candidate engine on each MANIFEST frame (Jetson + TensorRT path).

    Lazy-imports ``cv2`` / ``detect`` so unit tests that inject ``evaluate_fn``
    never need GPU deps.
    """
    import cv2  # local: keep module importable without OpenCV in dry CI

    import numpy as np

    from core.postprocess import postprocess_yolo
    from detect.backend import create_backend
    from detect.letterbox import preprocess_bgr, scale_boxes_xyxy

    engine = Path(config.engine_path)
    if not engine.is_file():
        raise FileNotFoundError(f"engine not found: {engine}")

    backend = create_backend("tensorrt", engine)
    root = Path(config.testset_dir)
    tp = fp = fn = 0
    try:
        backend.warmup(1)
        for fr in manifest.frames:
            img_path = root / fr.image
            lbl_path = root / fr.label
            if not img_path.is_file():
                raise FileNotFoundError(f"missing image: {img_path}")
            if not lbl_path.is_file():
                raise FileNotFoundError(f"missing label: {lbl_path}")

            bgr = cv2.imread(str(img_path))
            if bgr is None:
                raise RuntimeError(f"failed to read image: {img_path}")
            img_h, img_w = bgr.shape[:2]

            batch, meta = preprocess_bgr(bgr, input_size=backend.input_size)
            raw = backend.infer_batch(batch)
            dets = postprocess_yolo(
                raw,
                conf=config.conf,
                nms_iou=config.nms_iou,
                min_area=0.0,
                class_ids=(config.person_class_id,),
            )
            if dets:
                boxes_lb = np.array(
                    [(d.x1, d.y1, d.x2, d.y2) for d in dets],
                    dtype=np.float64,
                )
                mapped = scale_boxes_xyxy(boxes_lb, meta)
                pred_boxes = [tuple(row) for row in mapped.tolist()]
            else:
                pred_boxes = []

            gt_boxes = parse_yolo_label_file(
                lbl_path,
                img_w=img_w,
                img_h=img_h,
                person_class_id=config.person_class_id,
            )
            t, f_p, f_n = match_detections(gt_boxes, pred_boxes, iou_match=config.iou_match)
            tp += t
            fp += f_p
            fn += f_n
    finally:
        backend.close()

    return EvalMetrics(true_positives=tp, false_positives=fp, false_negatives=fn)


def run_acceptance(
    config: AcceptanceConfig,
    *,
    evaluate_fn: EvaluateFn | None = None,
    dry_run: bool = False,
) -> AcceptanceResult:
    """Evaluate candidate engine recall against the frozen testset.

    Parameters
    ----------
    evaluate_fn
        Optional injectable evaluator (unit tests / CI). When set, TRT is not used.
    dry_run
        Skip inference. Always returns ``passed=False`` with an explicit reason
        (empty set or dry-run). Never claims M9 / production pass.
    """
    threshold = float(config.recall_threshold)
    if not (0.0 <= threshold <= 1.0):
        raise ValueError(f"recall_threshold must be in [0, 1], got {threshold}")

    testset_dir = Path(config.testset_dir)
    try:
        manifest = load_manifest(testset_dir, require_files=False)
    except ManifestError as exc:
        return _reject(reason=f"manifest error: {exc}", threshold=threshold)

    frame_count = manifest.frame_count
    if frame_count == 0:
        return _reject(
            reason="empty frozen testset (frames=[]); cannot claim M9 / acceptance pass",
            threshold=threshold,
            frame_count=0,
        )

    if dry_run and evaluate_fn is None:
        return _reject(
            reason=(
                f"dry-run: inference skipped ({frame_count} frames); "
                "cannot claim M9 / acceptance pass"
            ),
            threshold=threshold,
            frame_count=frame_count,
        )

    evaluator = evaluate_fn if evaluate_fn is not None else evaluate_trt
    try:
        metrics = evaluator(config, manifest)
    except Exception as exc:  # noqa: BLE001 — surface as gate failure, not crash
        logger.exception("acceptance evaluation failed")
        return _reject(
            reason=f"evaluation failed: {exc}",
            threshold=threshold,
            frame_count=frame_count,
        )

    recall = metrics.recall
    precision = metrics.precision
    if recall < threshold:
        return _reject(
            reason=(
                f"recall {recall:.4f} < threshold {threshold:.4f}; "
                "reject candidate (do not hotswap)"
            ),
            threshold=threshold,
            recall=recall,
            precision=precision,
            metrics=metrics,
            frame_count=frame_count,
        )

    return AcceptanceResult(
        passed=True,
        recall=recall,
        reason=f"recall {recall:.4f} >= threshold {threshold:.4f}; acceptance passed",
        precision=precision,
        threshold=threshold,
        true_positives=metrics.true_positives,
        false_positives=metrics.false_positives,
        false_negatives=metrics.false_negatives,
        frame_count=frame_count,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "SafetyZone jetson_update — frozen-testset recall gate (#49). "
            f"Default threshold {DEFAULT_RECALL_THRESHOLD} is a D5 placeholder "
            "(write the site value into docs/decisions.md)."
        ),
    )
    parser.add_argument(
        "--engine",
        type=Path,
        required=True,
        help="Candidate TensorRT .engine path (from build_engine / candidates/)",
    )
    parser.add_argument(
        "--testset",
        type=Path,
        default=DEFAULT_TESTSET_DIR,
        help=f"Frozen testset directory with MANIFEST.json (default: {DEFAULT_TESTSET_DIR})",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_RECALL_THRESHOLD,
        help=(
            f"Recall threshold D5 (default: {DEFAULT_RECALL_THRESHOLD} placeholder; "
            "override after site co-decision)"
        ),
    )
    parser.add_argument(
        "--iou-match",
        type=float,
        default=DEFAULT_IOU_MATCH,
        help=f"IoU match threshold for TP (default: {DEFAULT_IOU_MATCH})",
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=DEFAULT_CONF,
        help=f"Detection confidence (default: {DEFAULT_CONF})",
    )
    parser.add_argument(
        "--nms-iou",
        type=float,
        default=DEFAULT_NMS_IOU,
        help=f"NMS IoU (default: {DEFAULT_NMS_IOU})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip inference; never reports production pass (CI / wiring smoke)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="DEBUG logging",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(list(argv) if argv is not None else None)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    config = AcceptanceConfig(
        engine_path=Path(args.engine),
        testset_dir=Path(args.testset),
        recall_threshold=float(args.threshold),
        iou_match=float(args.iou_match),
        conf=float(args.conf),
        nms_iou=float(args.nms_iou),
    )
    result = run_acceptance(config, dry_run=bool(args.dry_run))
    status = "PASS" if result.passed else "REJECT"
    print(
        f"{status} recall={result.recall:.4f} threshold={result.threshold:.4f} "
        f"precision={result.precision if result.precision is not None else 'n/a'} "
        f"frames={result.frame_count} tp={result.true_positives} "
        f"fp={result.false_positives} fn={result.false_negatives}",
        flush=True,
    )
    print(f"reason: {result.reason}", flush=True)
    if result.allows_hotswap:
        print("hotswap: allowed (jetson_update.hotswap / #50)", flush=True)
    else:
        print("hotswap: forbidden", flush=True)
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
