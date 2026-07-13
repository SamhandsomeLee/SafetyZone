#!/usr/bin/env python3
"""SafetyZone Windows Studio entry — debug-personnel GPU training loop (phase 3)."""

from __future__ import annotations

import argparse
import sys
from textwrap import dedent

WIZARD_STEPS: tuple[tuple[str, str], ...] = (
    (
        "1. 拉取难 case",
        "从 Jetson outbox 导入待复核样本（ingest；#40）。",
    ),
    (
        "2. 复核标注",
        "确认 / 改框 / 删 / 补预标注（review_ui；#41）。",
    ),
    (
        "3. 微调训练",
        "本机 NVIDIA GPU 运行 YOLO 微调（train；#43）。",
    ),
    (
        "4. 导出并下发",
        "导出 ONNX 并发送到 Jetson inbox（export_send；#44）。",
    ),
)

BANNER = dedent(
    """
    SafetyZone Windows Studio — 调试人员 GPU 训练闭环（阶段三）
    ============================================================
    运行于 Windows 11 + NVIDIA GPU；不依赖 Jetson 运行 UI。
    当前为空壳占位（#28）；四步向导将在 #45 串联。
    """
).strip()


def format_wizard_placeholder() -> str:
    lines = [BANNER, "", "四步向导（占位）:", ""]
    for title, detail in WIZARD_STEPS:
        lines.append(f"  [{title}]")
        lines.append(f"    {detail}")
        lines.append("")
    lines.append("子模块: ingest · review_ui · dataset · train · export_send")
    return "\n".join(lines)


def run_cli() -> int:
    print(format_wizard_placeholder())
    return 0


def run_gui() -> int:
    try:
        from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QVBoxLayout, QWidget
    except ImportError:
        print(
            "ERROR: PySide6 required for GUI mode. "
            "Use CLI (default) or: pip install -e \".[windows]\"",
            file=sys.stderr,
        )
        return 1

    app = QApplication(sys.argv)
    window = QMainWindow()
    window.setWindowTitle("SafetyZone Windows Studio")
    window.resize(640, 480)

    central = QWidget()
    layout = QVBoxLayout(central)
    label = QLabel(format_wizard_placeholder().replace("\n", "<br>"))
    label.setWordWrap(True)
    layout.addWidget(label)
    window.setCentralWidget(central)
    window.show()

    return app.exec()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="SafetyZone Windows Studio — GPU fine-tuning wizard (phase 3 shell)",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Launch empty placeholder window (requires PySide6; default is CLI)",
    )
    args = parser.parse_args(argv)

    if args.gui:
        return run_gui()
    return run_cli()


if __name__ == "__main__":
    raise SystemExit(main())
