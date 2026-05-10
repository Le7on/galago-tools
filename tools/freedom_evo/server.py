"""
Freedom EVO gRPC server — exposes liquid-handling commands via gRPC.

Usage (standalone)::

    python -m tools.freedom_evo.server --port=50051

The server translates incoming gRPC commands into GWL scripts and
submits them to the FreedomEVODriver for execution (real or simulated).
"""

from __future__ import annotations

import argparse
import logging
import os
import tempfile
from typing import Optional

from tools.base_server import ToolServer, serve
from tools.grpc_interfaces.freedom_evo_pb2 import Command, Config
from tools.app_config import Config as AppConfig

from .driver import FreedomEVODriver
from .script_builder import GWLBuilder


class FreedomEVOServer(ToolServer):
    """gRPC servicer for the Hamilton Freedom EVO liquid handler.

    Translates each command into one or more GWL steps, builds a
    complete GWL script, and submits it to the driver.
    """

    toolType: str = "freedom_evo"
    driver: FreedomEVODriver
    config: Config

    def __init__(self) -> None:
        super().__init__()
        self.app_config = AppConfig()
        # The real driver is created in _configure().
        self.driver = FreedomEVODriver(simulate=True)

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def _configure(self, config: Config) -> None:
        """Wire up the driver from the incoming Config message."""
        self.config = config
        evoware_path = config.evoware_path or "EVOware.exe"
        self.driver = FreedomEVODriver(
            evoware_path=evoware_path,
            simulate=config.simulate,
        )
        logging.info(
            "FreedomEVO configured  path=%s  simulate=%s",
            evoware_path,
            config.simulate,
        )

    # ------------------------------------------------------------------
    # Command handlers
    # ------------------------------------------------------------------
    # Each handler creates one or more GWL steps, builds the script,
    # and calls self.driver.run_script().

    def Initialize(self, params: Command.Initialize) -> None:
        """Initialise the instrument (no‑op GWL — just a health check)."""
        logging.info("Initialize requested")
        self._run_gwl_script("Initialize", lambda b: None)

    def Aspirate(self, params: Command.Aspirate) -> None:
        """Aspirate liquid from a source well / tube."""
        logging.info("Aspirate  rack=%s  pos=%d  vol=%.1f µL",
                     params.rack_label, params.position, params.volume)

        def build(builder: GWLBuilder) -> None:
            builder.add_aspirate(
                rack_label=params.rack_label,
                rack_id=params.rack_id,
                rack_type=params.rack_type,
                position=params.position,
                tube_id=params.tube_id,
                volume=params.volume,
                liquid_class=params.liquid_class,
                tip_type=params.tip_type,
                tip_mask=params.tip_mask,
            )

        self._run_gwl_script("Aspirate", build)

    def Dispense(self, params: Command.Dispense) -> None:
        """Dispense liquid into a destination well / tube."""
        logging.info("Dispense  rack=%s  pos=%d  vol=%.1f µL",
                     params.rack_label, params.position, params.volume)

        def build(builder: GWLBuilder) -> None:
            builder.add_dispense(
                rack_label=params.rack_label,
                rack_id=params.rack_id,
                rack_type=params.rack_type,
                position=params.position,
                tube_id=params.tube_id,
                volume=params.volume,
                liquid_class=params.liquid_class,
                tip_type=params.tip_type,
                tip_mask=params.tip_mask,
            )

        self._run_gwl_script("Dispense", build)

    def Mix(self, params: Command.Mix) -> None:
        """Mix liquid by repeated aspirate + dispense cycles."""
        logging.info("Mix  rack=%s  pos=%d  vol=%.1f µL  cycles=%d",
                     params.rack_label, params.position,
                     params.volume, params.cycles)

        def build(builder: GWLBuilder) -> None:
            for _ in range(max(1, params.cycles)):
                builder.add_aspirate(
                    rack_label=params.rack_label,
                    rack_id=params.rack_id,
                    rack_type=params.rack_type,
                    position=params.position,
                    tube_id=params.tube_id,
                    volume=params.volume,
                    liquid_class=params.liquid_class,
                    tip_type=params.tip_type,
                    tip_mask=params.tip_mask,
                )
                builder.add_dispense(
                    rack_label=params.rack_label,
                    rack_id=params.rack_id,
                    rack_type=params.rack_type,
                    position=params.position,
                    tube_id=params.tube_id,
                    volume=params.volume,
                    liquid_class=params.liquid_class,
                    tip_type=params.tip_type,
                    tip_mask=params.tip_mask,
                )

        self._run_gwl_script("Mix", build)

    def WashTips(self, params: Command.WashTips) -> None:
        """Wash tips at a wash station."""
        logging.info("WashTips  station=%s", params.wash_station_id)

        def build(builder: GWLBuilder) -> None:
            builder.add_wash(
                wash_station_id=params.wash_station_id or "Wash1"
            )

        self._run_gwl_script("WashTips", build)

    def GetDiTi(self, params: Command.GetDiTi) -> None:
        """Pick up disposable tips from a rack."""
        logging.info("GetDiTi  rack=%s  pos=%d",
                     params.rack_label, params.position)

        def build(builder: GWLBuilder) -> None:
            builder.add_diti(
                operation="Set",
                rack_label=params.rack_label,
                rack_id=params.rack_id,
                rack_type=params.rack_type,
                position=params.position,
            )

        self._run_gwl_script("GetDiTi", build)

    def DropDiTi(self, params: Command.DropDiTi) -> None:
        """Drop (eject) disposable tips."""
        logging.info("DropDiTi  rack=%s  pos=%d",
                     params.rack_label, params.position)

        def build(builder: GWLBuilder) -> None:
            builder.add_diti(
                operation="Drop",
                rack_label=params.rack_label,
                rack_id=params.rack_id,
                rack_type=params.rack_type,
                position=params.position,
            )

        self._run_gwl_script("DropDiTi", build)

    def GetStatus(self, params: Command.GetStatus) -> None:
        """Query the driver status and log it."""
        status = self.driver.get_status()
        logging.info(
            "GetStatus  running=%s  script=%s  simulate=%s",
            status["running"],
            status.get("current_script"),
            status["simulate"],
        )

    # ------------------------------------------------------------------
    # Estimate helpers
    # ------------------------------------------------------------------

    def EstimateInitialize(self, params: Command.Initialize) -> int:
        return 5  # ~5 s for initialisation

    def EstimateAspirate(self, params: Command.Aspirate) -> int:
        return 2  # ~2 s per aspirate

    def EstimateDispense(self, params: Command.Dispense) -> int:
        return 2  # ~2 s per dispense

    def EstimateMix(self, params: Command.Mix) -> int:
        return 2 * max(1, params.cycles)  # 2 s per cycle

    def EstimateWashTips(self, params: Command.WashTips) -> int:
        return 5  # ~5 s for a wash

    def EstimateGetDiTi(self, params: Command.GetDiTi) -> int:
        return 3  # ~3 s to pick up tips

    def EstimateDropDiTi(self, params: Command.DropDiTi) -> int:
        return 3  # ~3 s to drop tips

    def EstimateGetStatus(self, params: Command.GetStatus) -> int:
        return 1

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run_gwl_script(
        self,
        name: str,
        build_fn,
        script_name: str = "script",
    ) -> None:
        """Build a GWL script with *build_fn* and submit it to the driver.

        Parameters
        ----------
        name : str
            Human-readable name for logging.
        build_fn : callable
            Receives a :class:`GWLBuilder` and adds steps to it.
        script_name : str
            Base name for the temporary GWL file.
        """
        builder = GWLBuilder()
        build_fn(builder)

        gwl_content = builder.build()
        logging.debug("GWL script for %s (%d steps):\n%s",
                      name, len(builder), gwl_content)

        ok = self.driver.run_script(
            gwl_content,
            script_name=f"{script_name}_{name}.gwl",
        )

        if not ok:
            raise RuntimeError(
                f"EVOware failed to accept the '{name}' script"
            )

        # Wait for completion (blocking for simplicity; could be async
        # in a production system).
        if not self.simulated:
            success = self.driver.wait_for_completion(timeout=3600)
            if not success:
                status = self.driver.get_status()
                raise RuntimeError(
                    f"'{name}' script did not complete successfully. "
                    f"Error: {status.get('error', 'unknown')}"
                )


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        description="Freedom EVO gRPC server"
    )
    parser.add_argument(
        "--port", required=True, help="Port to listen on (e.g. 50051)"
    )
    args = parser.parse_args()

    serve(FreedomEVOServer(), str(args.port))
