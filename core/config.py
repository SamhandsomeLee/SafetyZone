"""Load, validate, and persist application config (stdlib + dataclasses only)."""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

SourceType = Literal["usb", "video_file"]
DetectMode = Literal["person"]
PlcMode = Literal["command", "block"]


class ConfigError(ValueError):
    """Raised when config content fails validation."""


@dataclass
class CameraConfig:
    id: str
    source_type: SourceType
    label: str = ""
    device: str | None = None
    path: str | None = None
    loop: bool = True


@dataclass
class ParamGroup:
    id: str
    ref_width: int
    ref_height: int
    slow_polygon: list[list[float]]
    stop_polygon: list[list[float]]
    conf: float = 0.3
    enter_frames: int = 2
    exit_frames: int = 10
    hold_ms: int = 400
    min_overlap: float = 0.1
    nms_iou: float = 0.45
    min_box_area: float = 400.0


@dataclass
class StationConfig:
    id: str
    camera_id: str
    param_group_id: str
    detect_mode: DetectMode = "person"
    enabled: bool = True


@dataclass
class PlcConfig:
    enabled: bool = False
    simulate: bool = True
    ip: str = "192.168.0.10"
    rack: int = 0
    slot: int = 1
    mode: PlcMode = "command"
    watchdog_ms: int = 3000
    offline_hold: bool = True


@dataclass
class RecordConfig:
    pre_buffer_sec: int = 3
    post_buffer_sec: int = 5
    snapshot: bool = True
    short_clip: bool = True


@dataclass
class AppConfig:
    cameras: list[CameraConfig] = field(default_factory=list)
    param_groups: list[ParamGroup] = field(default_factory=list)
    stations: list[StationConfig] = field(default_factory=list)
    plc: PlcConfig = field(default_factory=PlcConfig)
    record: RecordConfig = field(default_factory=RecordConfig)


def _require_unique_ids(items: list[Any], id_attr: str, label: str) -> None:
    seen: set[str] = set()
    for item in items:
        item_id = getattr(item, id_attr)
        if item_id in seen:
            raise ConfigError(f"duplicate {label} id: {item_id!r}")
        seen.add(item_id)


def _validate_camera(cam: CameraConfig) -> None:
    if cam.source_type == "usb" and not cam.device:
        raise ConfigError(f"camera {cam.id!r}: usb source requires 'device'")
    if cam.source_type == "video_file" and not cam.path:
        raise ConfigError(f"camera {cam.id!r}: video_file source requires 'path'")


def _validate_param_group(pg: ParamGroup) -> None:
    if pg.ref_width <= 0 or pg.ref_height <= 0:
        raise ConfigError(f"param_group {pg.id!r}: ref_width/ref_height must be positive")
    if len(pg.slow_polygon) < 3 or len(pg.stop_polygon) < 3:
        raise ConfigError(f"param_group {pg.id!r}: polygons need at least 3 points")
    if not 0 <= pg.conf <= 1:
        raise ConfigError(f"param_group {pg.id!r}: conf must be in [0, 1]")
    if pg.enter_frames < 1 or pg.exit_frames < 1:
        raise ConfigError(f"param_group {pg.id!r}: enter_frames/exit_frames must be >= 1")
    if not 0 <= pg.min_overlap <= 1:
        raise ConfigError(f"param_group {pg.id!r}: min_overlap must be in [0, 1]")


def _validate_station(st: StationConfig, camera_ids: set[str], param_ids: set[str]) -> None:
    if st.detect_mode != "person":
        raise ConfigError(
            f"station {st.id!r}: only detect_mode 'person' is supported (D1)"
        )
    if st.camera_id not in camera_ids:
        raise ConfigError(f"station {st.id!r}: unknown camera_id {st.camera_id!r}")
    if st.param_group_id not in param_ids:
        raise ConfigError(f"station {st.id!r}: unknown param_group_id {st.param_group_id!r}")


def validate_config(config: AppConfig) -> AppConfig:
    """Validate cross-references and field constraints."""
    _require_unique_ids(config.cameras, "id", "camera")
    _require_unique_ids(config.param_groups, "id", "param_group")
    _require_unique_ids(config.stations, "id", "station")

    for cam in config.cameras:
        _validate_camera(cam)
    for pg in config.param_groups:
        _validate_param_group(pg)

    camera_ids = {c.id for c in config.cameras}
    param_ids = {p.id for p in config.param_groups}
    for st in config.stations:
        _validate_station(st, camera_ids, param_ids)

    return config


def _parse_camera(raw: dict[str, Any]) -> CameraConfig:
    return CameraConfig(
        id=str(raw["id"]),
        source_type=raw["source_type"],
        label=str(raw.get("label", "")),
        device=raw.get("device"),
        path=raw.get("path"),
        loop=bool(raw.get("loop", True)),
    )


def _parse_param_group(raw: dict[str, Any]) -> ParamGroup:
    return ParamGroup(
        id=str(raw["id"]),
        ref_width=int(raw["ref_width"]),
        ref_height=int(raw["ref_height"]),
        slow_polygon=raw["slow_polygon"],
        stop_polygon=raw["stop_polygon"],
        conf=float(raw.get("conf", 0.3)),
        enter_frames=int(raw.get("enter_frames", 2)),
        exit_frames=int(raw.get("exit_frames", 10)),
        hold_ms=int(raw.get("hold_ms", 400)),
        min_overlap=float(raw.get("min_overlap", 0.1)),
        nms_iou=float(raw.get("nms_iou", 0.45)),
        min_box_area=float(raw.get("min_box_area", 400)),
    )


def _parse_station(raw: dict[str, Any]) -> StationConfig:
    return StationConfig(
        id=str(raw["id"]),
        camera_id=str(raw["camera_id"]),
        param_group_id=str(raw["param_group_id"]),
        detect_mode=raw.get("detect_mode", "person"),
        enabled=bool(raw.get("enabled", True)),
    )


def _parse_plc(raw: dict[str, Any] | None) -> PlcConfig:
    if not raw:
        return PlcConfig()
    return PlcConfig(
        enabled=bool(raw.get("enabled", False)),
        simulate=bool(raw.get("simulate", True)),
        ip=str(raw.get("ip", "192.168.0.10")),
        rack=int(raw.get("rack", 0)),
        slot=int(raw.get("slot", 1)),
        mode=raw.get("mode", "command"),
        watchdog_ms=int(raw.get("watchdog_ms", 3000)),
        offline_hold=bool(raw.get("offline_hold", True)),
    )


def _parse_record(raw: dict[str, Any] | None) -> RecordConfig:
    if not raw:
        return RecordConfig()
    return RecordConfig(
        pre_buffer_sec=int(raw.get("pre_buffer_sec", 3)),
        post_buffer_sec=int(raw.get("post_buffer_sec", 5)),
        snapshot=bool(raw.get("snapshot", True)),
        short_clip=bool(raw.get("short_clip", True)),
    )


def config_from_dict(data: dict[str, Any]) -> AppConfig:
    config = AppConfig(
        cameras=[_parse_camera(c) for c in data.get("cameras", [])],
        param_groups=[_parse_param_group(p) for p in data.get("param_groups", [])],
        stations=[_parse_station(s) for s in data.get("stations", [])],
        plc=_parse_plc(data.get("plc")),
        record=_parse_record(data.get("record")),
    )
    return validate_config(config)


def config_to_dict(config: AppConfig) -> dict[str, Any]:
    return {
        "cameras": [asdict(c) for c in config.cameras],
        "param_groups": [asdict(p) for p in config.param_groups],
        "stations": [asdict(s) for s in config.stations],
        "plc": asdict(config.plc),
        "record": asdict(config.record),
    }


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _find_latest_backup(path: Path) -> Path | None:
    pattern = f"{path.name}.bak.*"
    backups = sorted(path.parent.glob(pattern), reverse=True)
    return backups[0] if backups else None


def load_config(path: str | Path) -> AppConfig:
    """
    Load config from JSON. On parse failure, fall back to newest timestamped backup.
    """
    cfg_path = Path(path)
    if not cfg_path.is_file():
        backup = _find_latest_backup(cfg_path)
        if backup is None:
            raise FileNotFoundError(f"config not found: {cfg_path}")
        cfg_path = backup

    try:
        data = _read_json(cfg_path)
    except json.JSONDecodeError as exc:
        backup = _find_latest_backup(cfg_path)
        if backup is None:
            raise ConfigError(f"config corrupt and no backup: {cfg_path}") from exc
        data = _read_json(backup)

    return config_from_dict(data)


def save_config(config: AppConfig, path: str | Path) -> None:
    """Atomic write with timestamped backup of previous file."""
    cfg_path = Path(path)
    cfg_path.parent.mkdir(parents=True, exist_ok=True)

    if cfg_path.is_file():
        ts = time.strftime("%Y%m%d_%H%M%S")
        backup = cfg_path.with_name(f"{cfg_path.name}.bak.{ts}")
        shutil.copy2(cfg_path, backup)

    payload = json.dumps(config_to_dict(config), indent=2, ensure_ascii=False) + "\n"
    tmp_path = cfg_path.with_suffix(cfg_path.suffix + ".tmp")
    tmp_path.write_text(payload, encoding="utf-8")
    tmp_path.replace(cfg_path)


def get_param_group(config: AppConfig, param_group_id: str) -> ParamGroup:
    for pg in config.param_groups:
        if pg.id == param_group_id:
            return pg
    raise KeyError(param_group_id)


def get_camera(config: AppConfig, camera_id: str) -> CameraConfig:
    for cam in config.cameras:
        if cam.id == camera_id:
            return cam
    raise KeyError(camera_id)
