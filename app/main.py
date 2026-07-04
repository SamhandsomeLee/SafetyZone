#!/usr/bin/env python3
"""SafetyZone Jetson runtime UI entry (Sprint UI-1)."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _ensure_display() -> None:
    if os.environ.get("DISPLAY"):
        return
    if Path("/tmp/.X11-unix/X0").exists():
        os.environ["DISPLAY"] = ":0"


def main() -> int:
    parser = argparse.ArgumentParser(description="SafetyZone Jetson runtime UI")
    parser.add_argument("--config", default="configs/config.example.json")
    parser.add_argument("--engine", default="models/stock/yolov8s.engine")
    parser.add_argument("--station", default=None)
    args = parser.parse_args()

    _ensure_display()

    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        print("ERROR: PySide6 required. pip install PySide6", file=sys.stderr)
        raise SystemExit(1) from exc

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = ROOT / config_path
    engine_path = Path(args.engine)
    if not engine_path.is_absolute():
        engine_path = ROOT / engine_path

    app = QApplication(sys.argv)
    app.setApplicationName("SafetyZone")

    from ui.industrial_theme import apply_theme
    from ui.main_window import MainWindow

    apply_theme(app)
    window = MainWindow(
        config_path=config_path,
        engine_path=engine_path,
        project_root=ROOT,
        station_id=args.station,
    )
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
