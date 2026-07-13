"""High-level ingest API for listing and pulling hard cases."""

from __future__ import annotations

import json
from pathlib import Path

from windows_studio.ingest.models import HardCase, IngestConfig
from windows_studio.ingest.source import list_outbox_cases, pull_outbox

MANIFEST_NAME = "ingest_manifest.json"


def list_cases(config: IngestConfig) -> list[HardCase]:
    return list_outbox_cases(config.source)


def ingest_cases(config: IngestConfig) -> list[HardCase]:
    cases = pull_outbox(config.source, config.staging_dir)
    _write_manifest(config.staging_dir, cases)
    return cases


def load_staged_cases(staging_dir: Path) -> list[HardCase]:
    manifest = staging_dir / MANIFEST_NAME
    if manifest.is_file():
        data = json.loads(manifest.read_text(encoding="utf-8"))
        return [
            HardCase(
                case_id=item["case_id"],
                image_path=Path(item["image_path"]),
                label_path=Path(item["label_path"]) if item.get("label_path") else None,
                metadata=item.get("metadata", {}),
            )
            for item in data
        ]
    outbox = staging_dir / "outbox"
    if outbox.is_dir():
        from windows_studio.ingest.source import discover_cases

        return discover_cases(outbox)
    return []


def _write_manifest(staging_dir: Path, cases: list[HardCase]) -> None:
    staging_dir.mkdir(parents=True, exist_ok=True)
    manifest = staging_dir / MANIFEST_NAME
    payload = [case.to_dict() for case in cases]
    manifest.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
