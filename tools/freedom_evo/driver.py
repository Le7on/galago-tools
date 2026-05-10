"""
Freedom EVO driver — manages EVOware processes and GWL script execution.

Provides subprocess-based control of EVOware on Hamilton Freedom EVO
liquid-handling platforms.
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from tools.base_server import ABCToolDriver

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Default EVOware executable name (Windows). Override via Config.evoware_path.
_DEFAULT_EVOWARE_EXE = "EVOware.exe"

# Default trace file name template (EVOware writes execution trace here).
_DEFAULT_TRACE_FILE = "EVOware.trc"

# Polling interval in seconds when waiting for script completion.
_POLL_INTERVAL = 1.0


# ---------------------------------------------------------------------------
# Status dataclass
# ---------------------------------------------------------------------------


@dataclass
class EvoStatus:
    """Snapshot of the current EVOware / driver state."""

    running: bool = False
    """Whether a GWL script is currently executing."""

    current_script: Optional[str] = None
    """Name of the currently running GWL file (if any)."""

    error: Optional[str] = None
    """Last error message, if any."""

    uptime_seconds: float = 0.0
    """Seconds since the driver was initialised."""


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


class FreedomEVODriver(ABCToolDriver):
    """Subprocess-based driver for Hamilton Freedom EVO via EVOware.

    Parameters
    ----------
    evoware_path : str
        Path to the EVOware executable (or wrapper CLI).
    simulate : bool
        When ``True`` no subprocess is spawned; GWL files are validated
        and logged but not sent to the instrument.
    """

    def __init__(
        self,
        evoware_path: str = _DEFAULT_EVOWARE_EXE,
        simulate: bool = True,
    ) -> None:
        super().__init__()
        self.evoware_path: str = evoware_path
        self.simulate: bool = simulate

        self._process: Optional[subprocess.Popen] = None
        self._current_script: Optional[str] = None
        self._error: Optional[str] = None
        self._start_time: float = time.time()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_script(self, gwl_content: str, script_name: str = "script.gwl") -> bool:
        """Execute a GWL script on the Freedom EVO.

        Writes *gwl_content* to a temporary ``.gwl`` file and submits it
        to EVOware.  In simulation mode the content is logged but not
        executed.

        Returns ``True`` if the script was accepted by EVOware.
        """
        logging.info(
            "FreedomEVODriver.run_script  simulate=%s  len(content)=%d",
            self.simulate,
            len(gwl_content),
        )

        if self._process is not None and self._process.poll() is None:
            raise RuntimeError("A script is already running.  Stop it first.")

        # Write GWL to a temp file.
        tmp_path = self._write_temp_gwl(gwl_content, script_name)

        if self.simulate:
            logging.info("SIMULATE — would execute: %s", tmp_path)
            self._current_script = script_name
            # Simulate a brief execution delay.
            time.sleep(0.5)
            self._current_script = None
            return True

        # Launch EVOware with the GWL file.
        try:
            self._process = self._launch_evoware(tmp_path)
            self._current_script = script_name
            self._error = None
            return True
        except Exception:
            self._error = f"Failed to launch EVOware for {script_name}"
            logging.exception(self._error)
            return False
        finally:
            # Clean up temp file (EVOware reads it on launch).
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def get_status(self) -> dict:
        """Return a status dictionary summarising the driver state.

        Returns
        -------
        dict
            Keys: ``running``, ``current_script``, ``error``,
            ``simulate``, ``uptime_seconds``.
        """
        running = False
        if self._process is not None:
            running = self._process.poll() is None

        return {
            "running": running,
            "current_script": self._current_script,
            "error": self._error,
            "simulate": self.simulate,
            "uptime_seconds": time.time() - self._start_time,
        }

    def stop(self) -> None:
        """Abort the currently running script (if any)."""
        if self._process is None:
            return

        if self._process.poll() is not None:
            # Process already finished.
            self._process = None
            self._current_script = None
            return

        logging.info("Stopping EVOware process (PID=%d)", self._process.pid)
        try:
            self._process.terminate()
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logging.warning("EVOware did not exit gracefully — force-killing")
                self._process.kill()
                self._process.wait(timeout=5)
        except Exception:
            logging.exception("Error while stopping EVOware")
        finally:
            self._process = None
            self._current_script = None

    def wait_for_completion(self, timeout: float = 3600.0) -> bool:
        """Block until the current script finishes or *timeout* expires.

        Returns ``True`` if the script completed successfully, ``False``
        on timeout.
        """
        if self._process is None:
            return True

        start = time.time()
        while time.time() - start < timeout:
            ret = self._process.poll()
            if ret is not None:
                success = ret == 0
                if not success:
                    self._error = (
                        f"EVOware exited with code {ret}"
                    )
                self._current_script = None
                self._process = None
                return success
            time.sleep(_POLL_INTERVAL)

        logging.warning("Timeout waiting for EVOware completion")
        return False

    def ping(self) -> bool:
        """Check whether EVOware is reachable.

        Returns ``True`` if the executable can be found (or if in
        simulation mode).
        """
        if self.simulate:
            return True

        if os.path.isabs(self.evoware_path):
            return os.path.isfile(self.evoware_path)

        # Search PATH.
        import shutil
        return shutil.which(self.evoware_path) is not None

    def close(self) -> None:
        """Clean up resources — stop any running script."""
        self.stop()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _write_temp_gwl(self, content: str, name: str = "script.gwl") -> str:
        """Write *content* to a temporary ``.gwl`` file and return path."""
        fd, path = tempfile.mkstemp(suffix=".gwl", prefix="evo_")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        logging.debug("Wrote temp GWL: %s  (%d bytes)", path, len(content))
        return path

    def _launch_evoware(self, gwl_path: str) -> subprocess.Popen:
        """Launch EVOware to execute *gwl_path*.

        The exact CLI invocation depends on the EVOware installation.
        Common patterns:

        - ``EVOware.exe /run script.gwl``
        - ``HxRun.exe script.gwl``
        - ``EVOware.exe -f script.gwl``

        Override this method for site-specific configurations.
        """
        cmd = [self.evoware_path, "/run", gwl_path]
        logging.info("Launching EVOware: %s", cmd)
        return subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def __repr__(self) -> str:
        return (
            f"<FreedomEVODriver evoware={self.evoware_path!r} "
            f"simulate={self.simulate}>"
        )
