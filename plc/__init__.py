"""PLC gateway: simulation and snap7 backends with optional worker process."""

from plc.gateway import PlcGateway, PlcWriteResult, create_backend, should_use_snap7
from plc.process_worker import PlcProcessGateway, PlcWorkerState, PlcWorkerStatus
from plc.simulate import SimulateBackend
from plc.snap7_backend import Snap7Backend

__all__ = [
    "PlcGateway",
    "PlcProcessGateway",
    "PlcWorkerState",
    "PlcWorkerStatus",
    "PlcWriteResult",
    "SimulateBackend",
    "Snap7Backend",
    "create_backend",
    "should_use_snap7",
]
