"""Tests for jetson_update.acceptance (#49)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jetson_update.acceptance import (
    DEFAULT_RECALL_THRESHOLD,
    AcceptanceConfig,
    EvalMetrics,
    match_detections,
    parse_yolo_label_file,
    run_acceptance,
    main,
)
from jetson_update.testset.manifest import MANIFEST_SCHEMA_VERSION


def _write_manifest(testset: Path, frames: list[dict]) -> None:
    testset.mkdir(parents=True, exist_ok=True)
    (testset / "images").mkdir(exist_ok=True)
    (testset / "labels").mkdir(exist_ok=True)
    data = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "locked": True,
        "never_train": True,
        "class_names": ["person"],
        "description": "unit test frozen set",
        "created_at": "",
        "frames": frames,
    }
    (testset / "MANIFEST.json").write_text(
        json.dumps(data, indent=2) + "\n",
        encoding="utf-8",
    )


def _config(tmp_path: Path, *, threshold: float = DEFAULT_RECALL_THRESHOLD) -> AcceptanceConfig:
    engine = tmp_path / "cand.engine"
    engine.write_bytes(b"fake")
    testset = tmp_path / "testset"
    return AcceptanceConfig(
        engine_path=engine,
        testset_dir=testset,
        recall_threshold=threshold,
    )


def test_empty_testset_rejects(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    _write_manifest(cfg.testset_dir, frames=[])
    result = run_acceptance(cfg, evaluate_fn=lambda _c, _m: EvalMetrics(1, 0, 0))
    assert result.passed is False
    assert result.allows_hotswap is False
    assert "empty frozen testset" in result.reason
    assert "M9" in result.reason
    assert result.frame_count == 0


def test_dry_run_never_passes(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    _write_manifest(
        cfg.testset_dir,
        frames=[{"id": "f1", "image": "images/a.jpg", "label": "labels/a.txt"}],
    )
    result = run_acceptance(cfg, dry_run=True)
    assert result.passed is False
    assert "dry-run" in result.reason
    assert result.allows_hotswap is False
    assert result.frame_count == 1


def test_recall_below_threshold_rejects(tmp_path: Path) -> None:
    cfg = _config(tmp_path, threshold=0.95)
    _write_manifest(
        cfg.testset_dir,
        frames=[{"id": "f1", "image": "images/a.jpg", "label": "labels/a.txt"}],
    )

    def _eval(_c: AcceptanceConfig, _m: object) -> EvalMetrics:
        # recall = 9/10 = 0.9 < 0.95
        return EvalMetrics(true_positives=9, false_positives=1, false_negatives=1)

    result = run_acceptance(cfg, evaluate_fn=_eval)
    assert result.passed is False
    assert result.recall == pytest.approx(0.9)
    assert result.precision == pytest.approx(9 / 10)
    assert "reject" in result.reason
    assert result.allows_hotswap is False


def test_recall_at_threshold_passes(tmp_path: Path) -> None:
    cfg = _config(tmp_path, threshold=0.95)
    _write_manifest(
        cfg.testset_dir,
        frames=[{"id": "f1", "image": "images/a.jpg", "label": "labels/a.txt"}],
    )

    def _eval(_c: AcceptanceConfig, _m: object) -> EvalMetrics:
        # recall = 19/20 = 0.95
        return EvalMetrics(true_positives=19, false_positives=0, false_negatives=1)

    result = run_acceptance(cfg, evaluate_fn=_eval)
    assert result.passed is True
    assert result.recall == pytest.approx(0.95)
    assert result.allows_hotswap is True
    assert "passed" in result.reason


def test_recall_above_threshold_passes(tmp_path: Path) -> None:
    cfg = _config(tmp_path, threshold=0.90)
    _write_manifest(
        cfg.testset_dir,
        frames=[
            {"id": "f1", "image": "images/a.jpg", "label": "labels/a.txt"},
            {"id": "f2", "image": "images/b.jpg", "label": "labels/b.txt"},
        ],
    )

    def _eval(_c: AcceptanceConfig, _m: object) -> EvalMetrics:
        return EvalMetrics(true_positives=10, false_positives=2, false_negatives=0)

    result = run_acceptance(cfg, evaluate_fn=_eval)
    assert result.passed is True
    assert result.recall == pytest.approx(1.0)
    assert result.precision == pytest.approx(10 / 12)
    assert result.frame_count == 2


def test_evaluation_failure_rejects(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    _write_manifest(
        cfg.testset_dir,
        frames=[{"id": "f1", "image": "images/a.jpg", "label": "labels/a.txt"}],
    )

    def _boom(_c: AcceptanceConfig, _m: object) -> EvalMetrics:
        raise RuntimeError("trt exploded")

    result = run_acceptance(cfg, evaluate_fn=_boom)
    assert result.passed is False
    assert "evaluation failed" in result.reason
    assert result.allows_hotswap is False


def test_match_detections_basic() -> None:
    gt = [(0.0, 0.0, 10.0, 10.0), (20.0, 20.0, 30.0, 30.0)]
    pred = [(1.0, 1.0, 9.0, 9.0), (100.0, 100.0, 110.0, 110.0)]
    tp, fp, fn = match_detections(gt, pred, iou_match=0.5)
    assert tp == 1
    assert fp == 1
    assert fn == 1


def test_parse_yolo_label_file(tmp_path: Path) -> None:
    path = tmp_path / "a.txt"
    path.write_text("0 0.5 0.5 0.2 0.4\n1 0.1 0.1 0.1 0.1\n", encoding="utf-8")
    boxes = parse_yolo_label_file(path, img_w=100, img_h=200, person_class_id=0)
    assert len(boxes) == 1
    x1, y1, x2, y2 = boxes[0]
    assert x1 == pytest.approx(40.0)
    assert y1 == pytest.approx(60.0)
    assert x2 == pytest.approx(60.0)
    assert y2 == pytest.approx(140.0)


def test_cli_dry_run_empty_exit_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    engine = tmp_path / "x.engine"
    engine.write_bytes(b"x")
    testset = tmp_path / "ts"
    _write_manifest(testset, frames=[])
    code = main(
        [
            "--engine",
            str(engine),
            "--testset",
            str(testset),
            "--dry-run",
        ]
    )
    assert code == 1
    out = capsys.readouterr().out
    assert "REJECT" in out
    assert "hotswap: forbidden" in out


def test_cli_mock_pass_via_evaluate_not_exposed_but_threshold_flag(
    tmp_path: Path,
) -> None:
    """CLI --threshold is accepted; default placeholder documented."""
    from jetson_update.acceptance import build_arg_parser

    parser = build_arg_parser()
    args = parser.parse_args(
        ["--engine", "e.engine", "--testset", "t", "--threshold", "0.99"]
    )
    assert args.threshold == pytest.approx(0.99)
    assert DEFAULT_RECALL_THRESHOLD == pytest.approx(0.95)
