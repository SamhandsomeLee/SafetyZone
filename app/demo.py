"""Offline pipeline demo CLI (phase 1)."""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="SafetyZone offline demo")
    parser.add_argument("--config", default="configs/config.example.json")
    args = parser.parse_args()
    print(f"SafetyZone demo — config={args.config} (pipeline wiring in sprint 1.3)")


if __name__ == "__main__":
    main()
