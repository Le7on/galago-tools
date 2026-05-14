"""
Freedom EVO — ESC script generation and COM-based EVOware automation.

Provides classes for building .esc (EVOware Script Command) files that
can be executed on Tecan Freedom EVO liquid handling platforms, plus a
gRPC server exposing the full EVOware COM API.

Core modules (always available):
    from tools.freedom_evo import ESCBuilder, AspirateStep, DispenseStep, ...

Driver (requires comtypes, Windows only):
    from tools.freedom_evo.driver import FreedomEVODriver

Server (requires full galago-tools dependencies):
    from tools.freedom_evo.server import FreedomEVOServer
"""

from tools.freedom_evo.script_builder import (
    ESCBuilder,
    AspirateStep,
    DispenseStep,
    MixStep,
    WashStep,
    GetDiTiStep,
    DropDiTiStep,
    MoveLiHaStep,
    CommentStep,
    RawStep,
)

__all__ = [
    "ESCBuilder",
    "AspirateStep",
    "DispenseStep",
    "MixStep",
    "WashStep",
    "GetDiTiStep",
    "DropDiTiStep",
    "MoveLiHaStep",
    "CommentStep",
    "RawStep",
]
