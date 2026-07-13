"""Four-step studio wizard orchestration (#45)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from windows_studio.dataset import DatasetConfig, build_dataset
from windows_studio.export_send import ExportConfig, SendConfig, export_onnx, send_to_inbox
from windows_studio.ingest import IngestConfig, ingest_cases
from windows_studio.review_ui import review_cases_batch
from windows_studio.train import TrainConfig, run_training

WIZARD_STEPS = ("ingest", "review", "train", "export")


@dataclass
class WizardConfig:
    workspace: Path = Path("windows_studio_data")
    outbox_source: str = ""
    inbox_target: str = ""
    dry_run: bool = True
    auto_confirm_review: bool = True
    epochs: int = 1

    @property
    def staging_dir(self) -> Path:
        return self.workspace / "ingest"

    @property
    def review_dir(self) -> Path:
        return self.workspace / "review"

    @property
    def dataset_dir(self) -> Path:
        return self.workspace / "dataset"

    @property
    def runs_dir(self) -> Path:
        return self.workspace / "runs"

    @property
    def export_dir(self) -> Path:
        return self.workspace / "export"

    def to_dict(self) -> dict:
        return {
            "workspace": str(self.workspace),
            "outbox_source": self.outbox_source,
            "inbox_target": self.inbox_target,
            "dry_run": self.dry_run,
            "auto_confirm_review": self.auto_confirm_review,
            "epochs": self.epochs,
        }


@dataclass
class WizardResult:
    steps: dict[str, dict] = field(default_factory=dict)
    success: bool = True
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "message": self.message,
            "steps": self.steps,
        }


def _seed_demo_outbox(root: Path) -> str:
    """Create a tiny local outbox when no source configured (smoke / dry-run)."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "demo_case.jpg").write_bytes(b"demo-hard-case")
    (root / "demo_case.txt").write_text("0 0.5 0.5 0.25 0.4\n", encoding="utf-8")
    (root / "demo_case.json").write_text(
        json.dumps({"reason": "low_confidence", "score": 0.28}),
        encoding="utf-8",
    )
    return str(root)


def run_wizard(config: WizardConfig) -> WizardResult:
    result = WizardResult()
    config.workspace.mkdir(parents=True, exist_ok=True)

    source = config.outbox_source
    if not source:
        source = _seed_demo_outbox(config.workspace / "_demo_outbox")

    # Step 1 — ingest
    ingest_cfg = IngestConfig(source=source, staging_dir=config.staging_dir)
    cases = ingest_cases(ingest_cfg)
    result.steps["ingest"] = {
        "case_count": len(cases),
        "source": source,
        "staging_dir": str(config.staging_dir),
    }

    # Step 2 — review (batch auto-confirm for wizard dry-run)
    review_items = review_cases_batch(cases, config.review_dir)
    if config.auto_confirm_review:
        for item in review_items:
            item.confirmed = True
    confirmed = sum(1 for i in review_items if i.confirmed)
    result.steps["review"] = {
        "reviewed": len(review_items),
        "confirmed": confirmed,
        "review_dir": str(config.review_dir),
    }

    # dataset build (between review and train)
    dataset_cfg = DatasetConfig(review_dir=config.review_dir, dataset_dir=config.dataset_dir)
    dataset_manifest = build_dataset(dataset_cfg)
    result.steps["dataset"] = dataset_manifest

    # Step 3 — train
    train_cfg = TrainConfig(
        dataset_dir=config.dataset_dir,
        runs_dir=config.runs_dir,
        epochs=config.epochs,
    )
    train_result = run_training(train_cfg, force_dry_run=config.dry_run)
    result.steps["train"] = train_result.to_dict()

    # Step 4 — export + send
    if train_result.best_weights is None:
        result.success = False
        result.message = "training produced no weights"
        return result

    export_cfg = ExportConfig(
        weights_path=train_result.best_weights,
        export_dir=config.export_dir,
    )
    export_result = export_onnx(export_cfg, force_dry_run=config.dry_run)
    result.steps["export"] = export_result.to_dict()

    inbox = config.inbox_target or str(config.workspace / "inbox")
    if export_result.onnx_path is not None:
        send_result = send_to_inbox(
            SendConfig(
                onnx_path=export_result.onnx_path,
                inbox=inbox,
                sent_log_dir=config.export_dir,
            )
        )
        result.steps["send"] = send_result.to_dict()
    else:
        result.success = False
        result.message = "export produced no ONNX"
        return result

    result.message = "wizard completed (dry-run)" if config.dry_run else "wizard completed"
    (config.workspace / "wizard_result.json").write_text(
        json.dumps(result.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return result
