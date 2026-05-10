"""
GWL (Gemini Worklist) file builder for Hamilton Freedom EVO platforms.

Supports generating `.gwl` files with standard record types:

  - A: Aspirate (pick up liquid)
  - D: Dispense (eject liquid)
  - W: Wash (clean tips)
  - B: Break (pause / user interaction)
  - S: DiTi set / drop (attach or eject disposable tips)

Reference
---------
Each record is a semicolon-delimited line terminated with a semicolon.
Fields are positional; empty fields retain the semicolon separator.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional


# ── Step dataclasses ────────────────────────────────────────────────

@dataclass
class AspirateStep:
    """An aspirate (A) record.

    Parameters
    ----------
    rack_label : str
        User-defined label for the source rack.
    rack_id : str
        Physical identifier of the rack (barcode or system ID).
    rack_type : str
        Rack type code known to the EVOware system (e.g. 'Eppi', 'MTP').
    position : int
        Well / tube position (1‑based).
    tube_id : str
        Identifier for the tube at this position.
    volume : float
        Aspirate volume in µL.
    liquid_class : str
        Liquid-class name defined in EVOware.
    tip_type : str
        Tip type code (e.g. '1000ul', '50ul').
    tip_mask : int
        Bitmask selecting tips on a multi‑tip arm (1 = tip 1).
    """

    rack_label: str
    rack_id: str
    rack_type: str
    position: int
    tube_id: str
    volume: float
    liquid_class: str
    tip_type: str
    tip_mask: int

    def to_gwl(self) -> str:
        return (
            f"A;{self.rack_label};{self.rack_id};{self.rack_type};"
            f"{self.position};{self.tube_id};{self.volume};"
            f"{self.liquid_class};{self.tip_type};{self.tip_mask};"
        )


@dataclass
class DispenseStep:
    """A dispense (D) record.

    Parameters
    ----------
    rack_label : str
    rack_id : str
    rack_type : str
    position : int
    tube_id : str
    volume : float
    liquid_class : str
    tip_type : str
    tip_mask : int
    """

    rack_label: str
    rack_id: str
    rack_type: str
    position: int
    tube_id: str
    volume: float
    liquid_class: str
    tip_type: str
    tip_mask: int

    def to_gwl(self) -> str:
        return (
            f"D;{self.rack_label};{self.rack_id};{self.rack_type};"
            f"{self.position};{self.tube_id};{self.volume};"
            f"{self.liquid_class};{self.tip_type};{self.tip_mask};"
        )


@dataclass
class WashStep:
    """A wash (W) record — cleans tips at a wash station.

    Parameters
    ----------
    wash_station_id : str
        Wash station identifier (e.g. 'Wash1', 'Wash2').
    """

    wash_station_id: str = "Wash1"

    def to_gwl(self) -> str:
        return f"W;{self.wash_station_id};"


@dataclass
class BreakStep:
    """A break (B) record — pauses execution for user interaction."""

    def to_gwl(self) -> str:
        return "B;"


@dataclass
class DiTiStep:
    """A DiTi (S) record — attach or drop disposable tips.

    Parameters
    ----------
    operation : str
        Either 'Set' (pick up tips) or 'Drop' (eject tips).
    rack_label : str
        Label of the tip rack.
    rack_id : str
        Barcode / ID of the tip rack.
    rack_type : str
        Rack type code.
    position : int
        Position on the tip rack.
    """

    operation: str  # 'Set' or 'Drop'
    rack_label: str
    rack_id: str
    rack_type: str
    position: int

    def to_gwl(self) -> str:
        return (
            f"S;{self.operation};{self.rack_label};{self.rack_id};"
            f"{self.rack_type};{self.position};"
        )


# ── GWL Builder ─────────────────────────────────────────────────────

class GWLBuilder:
    """Build a complete GWL file programmatically.

    Usage::

        builder = GWLBuilder()
        builder.add_diti("Set", "TipRack", "12345", "DiTi_200ul", 1)
        builder.add_aspirate(
            rack_label="SrcPlate", rack_id="S001", rack_type="MTP",
            position=1, tube_id="SampleA", volume=50.0,
            liquid_class="Water", tip_type="200ul", tip_mask=1,
        )
        builder.add_dispense(
            rack_label="DstPlate", rack_id="D001", rack_type="MTP",
            position=1, tube_id="DestA", volume=50.0,
            liquid_class="Water", tip_type="200ul", tip_mask=1,
        )
        builder.add_wash()
        builder.add_diti("Drop", "TipRack", "12345", "DiTi_200ul", 1)
        print(builder.build())
    """

    def __init__(self) -> None:
        self._steps: List[object] = []

    # -- Adders -------------------------------------------------------

    def add_aspirate(
        self,
        rack_label: str,
        rack_id: str,
        rack_type: str,
        position: int,
        tube_id: str,
        volume: float,
        liquid_class: str,
        tip_type: str,
        tip_mask: int,
    ) -> AspirateStep:
        """Append an aspirate step and return it."""
        step = AspirateStep(
            rack_label=rack_label,
            rack_id=rack_id,
            rack_type=rack_type,
            position=position,
            tube_id=tube_id,
            volume=volume,
            liquid_class=liquid_class,
            tip_type=tip_type,
            tip_mask=tip_mask,
        )
        self._steps.append(step)
        return step

    def add_dispense(
        self,
        rack_label: str,
        rack_id: str,
        rack_type: str,
        position: int,
        tube_id: str,
        volume: float,
        liquid_class: str,
        tip_type: str,
        tip_mask: int,
    ) -> DispenseStep:
        """Append a dispense step and return it."""
        step = DispenseStep(
            rack_label=rack_label,
            rack_id=rack_id,
            rack_type=rack_type,
            position=position,
            tube_id=tube_id,
            volume=volume,
            liquid_class=liquid_class,
            tip_type=tip_type,
            tip_mask=tip_mask,
        )
        self._steps.append(step)
        return step

    def add_wash(self, wash_station_id: str = "Wash1") -> WashStep:
        """Append a wash step and return it."""
        step = WashStep(wash_station_id=wash_station_id)
        self._steps.append(step)
        return step

    def add_break(self) -> BreakStep:
        """Append a break (pause) step and return it."""
        step = BreakStep()
        self._steps.append(step)
        return step

    def add_diti(
        self,
        operation: str,
        rack_label: str,
        rack_id: str,
        rack_type: str,
        position: int,
    ) -> DiTiStep:
        """Append a DiTi step (Set or Drop) and return it.

        Parameters
        ----------
        operation : str
            ``"Set"`` to pick up tips, ``"Drop"`` to eject tips.
        """
        if operation not in ("Set", "Drop"):
            raise ValueError(
                f"DiTi operation must be 'Set' or 'Drop', got {operation!r}"
            )
        step = DiTiStep(
            operation=operation,
            rack_label=rack_label,
            rack_id=rack_id,
            rack_type=rack_type,
            position=position,
        )
        self._steps.append(step)
        return step

    # -- Builder / output ---------------------------------------------

    @property
    def steps(self) -> List[object]:
        """Return the list of added steps (read-only)."""
        return list(self._steps)

    def build(self) -> str:
        """Return the complete GWL file content as a string."""
        lines = [step.to_gwl() for step in self._steps]  # type: ignore[union-attr]
        return "\n".join(lines) + "\n"

    def save(self, filepath: str) -> str:
        """Write the GWL content to *filepath* and return the path.

        Creates parent directories if they don't exist.
        """
        content = self.build()
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as fh:
            fh.write(content)
        return filepath

    def __len__(self) -> int:
        return len(self._steps)

    def __repr__(self) -> str:
        return f"<GWLBuilder steps={len(self._steps)}>"
