#!/usr/bin/env python3
"""SafetyZone Windows Studio entry — debug-personnel GPU training loop (phase 3)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from textwrap import dedent

from windows_studio.wizard import WizardConfig, run_wizard

WIZARD_STEPS: tuple[tuple[str, str], ...] = (
    (
        "1. 拉取难 case",
        "从 Jetson outbox 导入待复核样本（ingest；#40）。",
    ),
    (
        "2. 复核标注",
        "确认 / 拖框 / 删 / 补预标注；列表过滤与显示模式（review_ui；#41/#53）。",
    ),
    (
        "3. 微调训练",
        "本机 NVIDIA GPU 运行 YOLO 微调（train；#43/#54）；GUI 显示进度·曲线并可中断。"
        " 评估回环见步进「评估」（eval_ui；#54），不替代 Jetson acceptance。",
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
    四步向导已串联（#45）；默认 dry-run 可在无 GPU 环境冒烟。
    """
).strip()


def format_wizard_banner() -> str:
    lines = [BANNER, "", "四步向导:", ""]
    for title, detail in WIZARD_STEPS:
        lines.append(f"  [{title}]")
        lines.append(f"    {detail}")
        lines.append("")
    lines.append("子模块: ingest · review_ui · dataset · train · eval_ui · export_send")
    lines.append("启动: python -m windows_studio.app --run  |  GUI: --gui")
    return "\n".join(lines)


def run_cli_run(config: WizardConfig) -> int:
    print(format_wizard_banner())
    print("\n--- running wizard ---\n", file=sys.stderr)
    try:
        result = run_wizard(config)
    except Exception as exc:  # noqa: BLE001 — surface wizard failure to CLI user
        print(f"ERROR: wizard failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    print(f"\n{result.message}", file=sys.stderr)
    return 0 if result.success else 1


def run_cli_info() -> int:
    print(format_wizard_banner())
    return 0


def run_gui(config: WizardConfig) -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print(
            "ERROR: PySide6 required for GUI mode. "
            "Use CLI: python -m windows_studio.app --run",
            file=sys.stderr,
        )
        return 1

    from windows_studio.shell import StudioMainWindow

    app = QApplication(sys.argv)
    window = StudioMainWindow(config)
    window.show()
    return app.exec()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="SafetyZone Windows Studio — GPU fine-tuning wizard",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Run full ingest→review→train→export wizard (default dry-run)",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path("windows_studio_data"),
        help="Studio workspace root",
    )
    parser.add_argument(
        "--outbox",
        default="",
        help="Jetson outbox local path or rsync://user@host:/path/outbox",
    )
    parser.add_argument(
        "--inbox",
        default="",
        help="Jetson inbox local path or rsync://user@host:/path/inbox",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=1,
        help="Training epochs (wizard uses 1 for smoke)",
    )
    parser.add_argument(
        "--real",
        action="store_true",
        help="Attempt real CUDA train + ONNX export (requires Windows GPU stack)",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Launch wizard GUI (requires PySide6)",
    )
    args = parser.parse_args(argv)

    config = WizardConfig(
        workspace=args.workspace,
        outbox_source=args.outbox,
        inbox_target=args.inbox,
        dry_run=not args.real,
        epochs=args.epochs,
    )

    if args.gui:
        return run_gui(config)
    if args.run:
        return run_cli_run(config)
    return run_cli_info()


if __name__ == "__main__":
    raise SystemExit(main())
