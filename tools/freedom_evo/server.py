"""
Freedom EVO gRPC server — COM-based EVOware control via gRPC.

Usage (standalone)::

    python -m tools.freedom_evo.server --port=50051

The server manages the full EVOware lifecycle (Logon → Initialize →
PrepareScript → StartScript → ... → Logoff) and translates gRPC commands
into COM API calls against the EVOware system interface.
"""

from __future__ import annotations

import argparse
import logging
from typing import Optional

from tools.base_server import ToolServer, serve
from tools.grpc_interfaces.freedom_evo_pb2 import (
    Command,
    Config,
    SystemStatusFlag,
    ScriptStatus,
    ProcessStatus,
    LampStatus,
)
from tools.app_config import Config as AppConfig

from .driver import (
    FreedomEVODriver,
    # status constants
    STATUS_INITIALIZED,
    STATUS_IDLE,
    SS_IDLE,
    SS_BUSY,
    PS_FINISHED,
    # lamp
    LAMP_OFF,
    LAMP_GREEN,
    LAMP_GREEN_FLASH,
    LAMP_RED_FLASH,
)
from .script_builder import ESCBuilder


class FreedomEVOServer(ToolServer):
    """gRPC servicer for the Tecan Freedom EVO liquid handler.

    Manages EVOware COM lifecycle and translates each gRPC command
    into the appropriate EVOware API call.
    """

    toolType: str = "freedom_evo"
    driver: FreedomEVODriver
    config: Config

    def __init__(self) -> None:
        super().__init__()
        self.app_config = AppConfig()
        # Default: simulated, no credentials
        self.driver = FreedomEVODriver(simulate=True)

    # ── Configuration ──────────────────────────────────────────────────

    def _configure(self, config: Config) -> None:
        """Wire up the driver from the incoming Config message."""
        self.config = config
        self.driver = FreedomEVODriver(
            user_name=config.evoware_user or "",
            password=config.evoware_password or "",
            plus_mode=config.plus_mode,
            simulate=config.simulate,
            hide_gui=config.hide_gui,
            remote_mode=config.remote_mode,
        )
        logging.info(
            "FreedomEVO configured  user=%s  plus=%s  simulate=%s "
            "hide_gui=%s  remote=%s",
            config.evoware_user, config.plus_mode,
            config.simulate, config.hide_gui, config.remote_mode,
        )

    # ══════════════════════════════════════════════════════════════════
    # Lifecycle handlers
    # ══════════════════════════════════════════════════════════════════

    def Logon(self, params: Command.Logon) -> None:
        logging.info("Logon  user=%s  plus=%s  sim=%s",
                     params.user_name, params.plus_mode, params.simulation)
        ok = self.driver.logon()
        if not ok:
            raise RuntimeError(
                f"Logon failed: {self.driver._error or 'unknown error'}"
            )

    def Logoff(self, params: Command.Logoff) -> None:
        logging.info("Logoff")
        self.driver.logoff()

    def Initialize(self, params: Command.Initialize) -> None:
        logging.info("Initialize")
        ok = self.driver.initialize()
        if not ok:
            raise RuntimeError(
                f"Initialize failed: {self.driver._error or 'unknown error'}"
            )

    def Shutdown(self, params: Command.Shutdown) -> None:
        logging.info("Shutdown")
        ok = self.driver.shutdown()
        if not ok:
            raise RuntimeError("Shutdown failed")

    # ══════════════════════════════════════════════════════════════════
    # Script execution
    # ══════════════════════════════════════════════════════════════════

    def PrepareScript(self, params: Command.PrepareScript) -> None:
        logging.info("PrepareScript  name=%s", params.script_name)
        sid = self.driver.prepare_script(params.script_name)
        if sid is None:
            raise RuntimeError(
                f"PrepareScript failed: {self.driver._error or 'unknown'}"
            )
        logging.info("PrepareScript → script_id=%d", sid)

    def StartScript(self, params: Command.StartScript) -> None:
        logging.info("StartScript  id=%d  start=%d  end=%d",
                     params.script_id, params.start_line, params.end_line)
        ok = self.driver.start_script(
            params.script_id, params.start_line, params.end_line,
        )
        if not ok:
            raise RuntimeError(
                f"StartScript failed: {self.driver._error or 'unknown'}"
            )

    # ══════════════════════════════════════════════════════════════════
    # Process execution (Plus only)
    # ══════════════════════════════════════════════════════════════════

    def PrepareProcess(self, params: Command.PrepareProcess) -> None:
        logging.info("PrepareProcess  name=%s", params.process_name)
        ok = self.driver.prepare_process(params.process_name)
        if not ok:
            raise RuntimeError(f"PrepareProcess failed")

    def StartProcess(self, params: Command.StartProcess) -> None:
        logging.info("StartProcess  name=%s  objects=%s",
                     params.process_name, params.objects)
        pid = self.driver.start_process(
            params.process_name, params.objects,
            params.priority, params.emergency,
        )
        if pid is None:
            raise RuntimeError(
                f"StartProcess failed: {self.driver._error or 'unknown'}"
            )
        logging.info("StartProcess → process_id=%d", pid)

    def CancelProcess(self, params: Command.CancelProcess) -> None:
        logging.info("CancelProcess  id=%d", params.process_id)
        self.driver.cancel_process(params.process_id)

    # ══════════════════════════════════════════════════════════════════
    # Runtime control
    # ══════════════════════════════════════════════════════════════════

    def Pause(self, params: Command.Pause) -> None:
        logging.info("Pause")
        self.driver.pause()

    def Resume(self, params: Command.Resume) -> None:
        logging.info("Resume")
        self.driver.resume()

    def Stop(self, params: Command.Stop) -> None:
        logging.info("Stop")
        self.driver.stop()

    # ══════════════════════════════════════════════════════════════════
    # Liquid handling (.esc based)
    # ══════════════════════════════════════════════════════════════════

    def Aspirate(self, params: Command.Aspirate) -> None:
        logging.info("Aspirate  rack=%s  pos=%d  vol=%.1f µL",
                     params.rack_label, params.position, params.volume)
        self._run_esc_script("Aspirate", lambda b: b.add_aspirate(
            rack_label=params.rack_label,
            rack_id=params.rack_id,
            rack_type=params.rack_type,
            position=params.position,
            tube_id=params.tube_id,
            volume=params.volume,
            liquid_class=params.liquid_class,
            tip_type=params.tip_type,
            tip_mask=params.tip_mask,
        ))

    def Dispense(self, params: Command.Dispense) -> None:
        logging.info("Dispense  rack=%s  pos=%d  vol=%.1f µL",
                     params.rack_label, params.position, params.volume)
        self._run_esc_script("Dispense", lambda b: b.add_dispense(
            rack_label=params.rack_label,
            rack_id=params.rack_id,
            rack_type=params.rack_type,
            position=params.position,
            tube_id=params.tube_id,
            volume=params.volume,
            liquid_class=params.liquid_class,
            tip_type=params.tip_type,
            tip_mask=params.tip_mask,
        ))

    def Mix(self, params: Command.Mix) -> None:
        logging.info("Mix  rack=%s  pos=%d  vol=%.1f µL  cycles=%d",
                     params.rack_label, params.position,
                     params.volume, params.cycles)
        self._run_esc_script("Mix", lambda b: b.add_mix(
            rack_label=params.rack_label,
            rack_id=params.rack_id,
            rack_type=params.rack_type,
            position=params.position,
            tube_id=params.tube_id,
            volume=params.volume,
            liquid_class=params.liquid_class,
            tip_type=params.tip_type,
            tip_mask=params.tip_mask,
            cycles=max(1, params.cycles),
        ))

    def WashTips(self, params: Command.WashTips) -> None:
        logging.info("WashTips  station=%s", params.wash_station_id)
        self._run_esc_script(
            "WashTips",
            lambda b: b.add_wash(params.wash_station_id or "Wash1"),
        )

    def GetDiTi(self, params: Command.GetDiTi) -> None:
        logging.info("GetDiTi  rack=%s  pos=%d  count=%d",
                     params.rack_label, params.position, params.tip_count)
        self._run_esc_script("GetDiTi", lambda b: b.add_get_diti(
            tip_count=max(1, params.tip_count),
        ))

    def DropDiTi(self, params: Command.DropDiTi) -> None:
        logging.info("DropDiTi  rack=%s  pos=%d",
                     params.rack_label, params.position)
        self._run_esc_script("DropDiTi", lambda b: b.add_drop_diti(
            rack_label=params.rack_label,
            rack_id=params.rack_id,
            rack_type=params.rack_type,
            position=params.position,
        ))

    # ══════════════════════════════════════════════════════════════════
    # Status queries
    # ══════════════════════════════════════════════════════════════════

    def GetSystemStatus(self, params: Command.GetSystemStatus) -> None:
        status = self.driver.get_system_status()
        logging.info("GetSystemStatus → 0x%08X", status)

    def GetScriptStatus(self, params: Command.GetScriptStatus) -> None:
        status = self.driver.get_script_status(params.script_id)
        logging.info("GetScriptStatus  id=%d → 0x%02X", params.script_id, status)

    def GetProcessStatus(self, params: Command.GetProcessStatus) -> None:
        status = self.driver.get_process_status(params.process_id)
        logging.info("GetProcessStatus  id=%d → 0x%02X", params.process_id, status)

    # ══════════════════════════════════════════════════════════════════
    # System info
    # ══════════════════════════════════════════════════════════════════

    def GetSystemInfo(self, params: Command.GetSystemInfo) -> None:
        info = self.driver.get_system_info()
        logging.info(
            "GetSystemInfo  plus=%s  sim=%s  version=%s  serial=%s",
            info.plus_mode, info.simulation_mode,
            info.version, info.serial_number,
        )

    # ══════════════════════════════════════════════════════════════════
    # Remote mode & UI
    # ══════════════════════════════════════════════════════════════════

    def SetRemoteMode(self, params: Command.SetRemoteMode) -> None:
        logging.info("SetRemoteMode  enable=%s", params.enable)
        ok = self.driver.set_remote_mode(params.enable)
        if not ok:
            raise RuntimeError("SetRemoteMode failed")

    def HideGUI(self, params: Command.HideGUI) -> None:
        logging.info("HideGUI  hide=%s", params.hide)
        ok = self.driver.hide_gui(params.hide)
        if not ok:
            raise RuntimeError("HideGUI failed")

    def SetLamp(self, params: Command.SetLamp) -> None:
        lamp_map = {
            LampStatus.LAMP_OFF: LAMP_OFF,
            LampStatus.LAMP_GREEN: LAMP_GREEN,
            LampStatus.LAMP_GREEN_FLASH: LAMP_GREEN_FLASH,
            LampStatus.LAMP_RED_FLASH: LAMP_RED_FLASH,
        }
        val = lamp_map.get(params.status, LAMP_OFF)
        logging.info("SetLamp  status=%s", params.status)
        self.driver.set_lamp(val)

    def SetDoorLocks(self, params: Command.SetDoorLocks) -> None:
        logging.info("SetDoorLocks  close=%s", params.close_locked)
        self.driver.set_door_locks(params.close_locked)

    # ══════════════════════════════════════════════════════════════════
    # Liquid class queries
    # ══════════════════════════════════════════════════════════════════

    def GetLCCount(self, params: Command.GetLCCount) -> None:
        count = self.driver.get_lc_count()
        logging.info("GetLCCount → %d", count)

    def GetLCInfo(self, params: Command.GetLCInfo) -> None:
        info = self.driver.get_lc_info(params.index)
        if info:
            logging.info(
                "GetLCInfo  idx=%d → name=%s  default=%s  custom=%s",
                params.index, info.name, info.is_default, info.is_customized,
            )

    def GetSubLCCount(self, params: Command.GetSubLCCount) -> None:
        count = self.driver.get_sub_lc_count(params.lc_index)
        logging.info("GetSubLCCount  lc=%d → %d", params.lc_index, count)

    def GetSubLCInfo(self, params: Command.GetSubLCInfo) -> None:
        info = self.driver.get_sub_lc_info(params.lc_index, params.sub_lc_index)
        if info:
            logging.info(
                "GetSubLCInfo  lc=%d sub=%d → tip=%s  vol=[%.1f–%.1f]",
                params.lc_index, params.sub_lc_index,
                info.tip_type, info.min_volume, info.max_volume,
            )

    # ══════════════════════════════════════════════════════════════════
    # Device queries
    # ══════════════════════════════════════════════════════════════════

    def GetDeviceCount(self, params: Command.GetDeviceCount) -> None:
        count = self.driver.get_device_count()
        logging.info("GetDeviceCount → %d", count)

    def GetDevice(self, params: Command.GetDevice) -> None:
        name, version = self.driver.get_device(
            index=params.index, call_name=params.call_name,
        )
        logging.info("GetDevice → name=%s  driver=%s", name, version)

    # ══════════════════════════════════════════════════════════════════
    # Labware / Deck queries
    # ══════════════════════════════════════════════════════════════════

    def GetNumberOfRacks(self, params: Command.GetNumberOfRacks) -> None:
        count = self.driver.get_number_of_racks(params.script_id)
        logging.info("GetNumberOfRacks  sid=%d → %d", params.script_id, count)

    def GetRack(self, params: Command.GetRack) -> None:
        rack = self.driver.get_rack(params.script_id, params.index)
        if rack:
            logging.info(
                "GetRack  sid=%d idx=%d → name=%s  label=%s  "
                "loc=%d grid=%d site=%d carrier=%s",
                params.script_id, params.index,
                rack.name, rack.label,
                rack.location, rack.grid, rack.site, rack.carrier_name,
            )

    # ══════════════════════════════════════════════════════════════════
    # Variables
    # ══════════════════════════════════════════════════════════════════

    def GetScriptVariable(self, params: Command.GetScriptVariable) -> None:
        value = self.driver.get_script_variable(
            params.script_id, params.variable_name,
        )
        logging.info(
            "GetScriptVariable  sid=%d  var=%s → %s",
            params.script_id, params.variable_name, value,
        )

    def SetScriptVariable(self, params: Command.SetScriptVariable) -> None:
        logging.info(
            "SetScriptVariable  sid=%d  var=%s = %s",
            params.script_id, params.variable_name, params.value,
        )
        self.driver.set_script_variable(
            params.script_id, params.variable_name, params.value,
        )

    # ══════════════════════════════════════════════════════════════════
    # Script interface
    # ══════════════════════════════════════════════════════════════════

    def AddScriptLine(self, params: Command.AddScriptLine) -> None:
        logging.info("AddScriptLine: %s", params.esc_command)
        self.driver.add_script_line(params.esc_command)

    def SaveScript(self, params: Command.SaveScript) -> None:
        logging.info("SaveScript: %s", params.file_name)
        self.driver.save_script(params.file_name, params.directory)

    # ══════════════════════════════════════════════════════════════════
    # Error handling
    # ══════════════════════════════════════════════════════════════════

    def ClearError(self, params: Command.ClearError) -> None:
        self.driver.clear_error()
        logging.info("ClearError")

    # ══════════════════════════════════════════════════════════════════
    # Estimate helpers
    # ══════════════════════════════════════════════════════════════════

    def EstimateLogon(self, params: Command.Logon) -> int:
        return 5  # ~5 s to connect and authenticate

    def EstimateLogoff(self, params: Command.Logoff) -> int:
        return 2

    def EstimateInitialize(self, params: Command.Initialize) -> int:
        return 30  # ~30 s for hardware init

    def EstimateShutdown(self, params: Command.Shutdown) -> int:
        return 10

    def EstimatePrepareScript(self, params: Command.PrepareScript) -> int:
        return 3  # loading from disk

    def EstimateStartScript(self, params: Command.StartScript) -> int:
        return 2

    def EstimatePrepareProcess(self, params: Command.PrepareProcess) -> int:
        return 3

    def EstimateStartProcess(self, params: Command.StartProcess) -> int:
        return 2

    def EstimateCancelProcess(self, params: Command.CancelProcess) -> int:
        return 1

    def EstimatePause(self, params: Command.Pause) -> int:
        return 2

    def EstimateResume(self, params: Command.Resume) -> int:
        return 1

    def EstimateStop(self, params: Command.Stop) -> int:
        return 3

    def EstimateAspirate(self, params: Command.Aspirate) -> int:
        return 2

    def EstimateDispense(self, params: Command.Dispense) -> int:
        return 2

    def EstimateMix(self, params: Command.Mix) -> int:
        return 2 * max(1, params.cycles)

    def EstimateWashTips(self, params: Command.WashTips) -> int:
        return 5

    def EstimateGetDiTi(self, params: Command.GetDiTi) -> int:
        return 3

    def EstimateDropDiTi(self, params: Command.DropDiTi) -> int:
        return 3

    def EstimateGetSystemStatus(self, params: Command.GetSystemStatus) -> int:
        return 1

    def EstimateGetScriptStatus(self, params: Command.GetScriptStatus) -> int:
        return 1

    def EstimateGetProcessStatus(self, params: Command.GetProcessStatus) -> int:
        return 1

    def EstimateGetSystemInfo(self, params: Command.GetSystemInfo) -> int:
        return 1

    def EstimateSetRemoteMode(self, params: Command.SetRemoteMode) -> int:
        return 1

    def EstimateHideGUI(self, params: Command.HideGUI) -> int:
        return 1

    def EstimateSetLamp(self, params: Command.SetLamp) -> int:
        return 1

    def EstimateSetDoorLocks(self, params: Command.SetDoorLocks) -> int:
        return 1

    def EstimateGetLCCount(self, params: Command.GetLCCount) -> int:
        return 1

    def EstimateGetLCInfo(self, params: Command.GetLCInfo) -> int:
        return 1

    def EstimateGetSubLCCount(self, params: Command.GetSubLCCount) -> int:
        return 1

    def EstimateGetSubLCInfo(self, params: Command.GetSubLCInfo) -> int:
        return 1

    def EstimateGetDeviceCount(self, params: Command.GetDeviceCount) -> int:
        return 1

    def EstimateGetDevice(self, params: Command.GetDevice) -> int:
        return 1

    def EstimateGetNumberOfRacks(self, params: Command.GetNumberOfRacks) -> int:
        return 1

    def EstimateGetRack(self, params: Command.GetRack) -> int:
        return 1

    def EstimateGetScriptVariable(self, params: Command.GetScriptVariable) -> int:
        return 1

    def EstimateSetScriptVariable(self, params: Command.SetScriptVariable) -> int:
        return 1

    def EstimateAddScriptLine(self, params: Command.AddScriptLine) -> int:
        return 1

    def EstimateSaveScript(self, params: Command.SaveScript) -> int:
        return 2

    def EstimateClearError(self, params: Command.ClearError) -> int:
        return 1

    # ══════════════════════════════════════════════════════════════════
    # Internal helpers
    # ══════════════════════════════════════════════════════════════════

    def _run_esc_script(
        self,
        name: str,
        build_fn,
        script_name: str = "script",
    ) -> None:
        """Build an .esc script with *build_fn* and execute it via the COM API.

        Parameters
        ----------
        name : str
            Human-readable name for logging.
        build_fn : callable
            Receives an :class:`ESCBuilder` and adds steps to it.
        script_name : str
            Base name for the temporary .esc file.
        """
        builder = ESCBuilder()
        build_fn(builder)

        esc_content = builder.build()
        logging.debug(
            "ESC script for %s (%d steps):\n%s",
            name, len(builder), esc_content,
        )

        ok = self.driver.run_esc_script(
            esc_content,
            script_name=f"{script_name}_{name}.esc",
        )

        if not ok:
            raise RuntimeError(
                f"'{name}' script did not complete successfully. "
                f"Error: {self.driver._error or 'unknown'}"
            )


# ── Entry point ────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        description="Freedom EVO gRPC server (COM-based EVOware control)"
    )
    parser.add_argument(
        "--port", required=True, help="Port to listen on (e.g. 50051)"
    )
    args = parser.parse_args()

    serve(FreedomEVOServer(), str(args.port))
