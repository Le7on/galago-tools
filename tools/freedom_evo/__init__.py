"""
Freedom EVO — GWL script generation and automation tools.

Provides classes for building GWL (Gemini Worklist) files that can be
executed on Tecan Freedom EVO liquid handling platforms, plus a
gRPC server that exposes liquid-handling commands.

Core modules (always available):
    from tools.freedom_evo import GWLBuilder, AspirateStep, ...

Driver (requires grpcio, pydantic, appdirs):
    from tools.freedom_evo.driver import FreedomEVODriver

Server (requires full galago-tools dependencies):
    from tools.freedom_evo.server import FreedomEVOServer
"""

from tools.freedom_evo.script_builder import (
    GWLBuilder,
    AspirateStep,
    DispenseStep,
    WashStep,
    BreakStep,
    DiTiStep,
)

__all__ = [
    "GWLBuilder",
    "AspirateStep",
    "DispenseStep",
    "WashStep",
    "BreakStep",
    "DiTiStep",
]
