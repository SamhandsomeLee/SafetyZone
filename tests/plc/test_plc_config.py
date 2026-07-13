"""Tests for PlcConfig simulate field round-trip."""

from __future__ import annotations

import json
from pathlib import Path

from core.config import PlcConfig, load_config, save_config


def test_plc_simulate_default_true() -> None:
    assert PlcConfig().simulate is True


def test_load_example_config_has_simulate_true() -> None:
    cfg = load_config(Path("configs/config.example.json"))
    assert cfg.plc.simulate is True


def test_plc_simulate_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "cameras": [],
                "param_groups": [],
                "stations": [],
                "plc": {"enabled": True, "simulate": False},
            }
        ),
        encoding="utf-8",
    )
    loaded = load_config(path)
    assert loaded.plc.enabled is True
    assert loaded.plc.simulate is False

    save_config(loaded, path)
    reloaded = load_config(path)
    assert reloaded.plc.simulate is False


def test_plc_snap7_fields_defaults_and_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "cameras": [],
                "param_groups": [],
                "stations": [],
                "plc": {
                    "enabled": True,
                    "simulate": False,
                    "db_number": 10,
                    "result_offset": 4,
                    "verify_readback": False,
                },
            }
        ),
        encoding="utf-8",
    )
    loaded = load_config(path)
    assert loaded.plc.db_number == 10
    assert loaded.plc.result_offset == 4
    assert loaded.plc.verify_readback is False
