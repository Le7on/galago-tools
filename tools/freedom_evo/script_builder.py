"""
ESC script builder for Tecan Freedom EVO platforms.

Generates ``.esc`` format scripts — EVOware's native executable script
language.  Commands use C-style function syntax terminated by semicolons:

    CommandName(arg1, arg2, "string_arg", ...);

Reference
---------
EVOware API manual (Doc ID 393396, V2.13):
  - ExecuteScriptCommand() accepts .esc format strings
  - AddScriptLine() appends .esc commands to a script
  - PrepareScript() / StartScript() execute .esc files

Common .esc commands:

  - ``Aspirate(rackLabel, rackID, rackType, position, tubeID, volume,
      liquidClass, tipType, tipMask);``
  - ``Dispense(rackLabel, rackID, rackType, position, tubeID, volume,
      liquidClass, tipType, tipMask);``
  - ``Mix(rackLabel, rackID, rackType, position, tubeID, volume,
      liquidClass, tipType, tipMask, cycles);``
  - ``Wash(washStationID);``
  - ``GetDITI(tipCount, 0, 0, 0);``
  - ``DropDITI(rackLabel, rackID, rackType, position);``
  - ``MoveLiHa(arm, 0, 0, 0, "worklist");``

Each record is a single line ending with a semicolon.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional


# ── Helpers ────────────────────────────────────────────────────────────

def _esc_str(s: str) -> str:
    """Escape a string for embedding in .esc command arguments."""
    return f'"{s}"'


def _esc_num(n) -> str:
    """Format a number for .esc output."""
    if isinstance(n, float):
        return f"{n:.1f}"
    return str(n)


# ── Step dataclasses ───────────────────────────────────────────────────

@dataclass
class AspirateStep:
    """Aspirate command: ``Aspirate(rackLabel, ...);``"""

    rack_label: str
    rack_id: str
    rack_type: str
    position: int
    tube_id: str
    volume: float
    liquid_class: str
    tip_type: str
    tip_mask: int

    def to_esc(self) -> str:
        return (
            f"Aspirate({_esc_str(self.rack_label)}, {_esc_str(self.rack_id)}, "
            f"{_esc_str(self.rack_type)}, {self.position}, "
            f"{_esc_str(self.tube_id)}, {_esc_num(self.volume)}, "
            f"{_esc_str(self.liquid_class)}, {_esc_str(self.tip_type)}, "
            f"{self.tip_mask});"
        )


@dataclass
class DispenseStep:
    """Dispense command: ``Dispense(rackLabel, ...);``"""

    rack_label: str
    rack_id: str
    rack_type: str
    position: int
    tube_id: str
    volume: float
    liquid_class: str
    tip_type: str
    tip_mask: int

    def to_esc(self) -> str:
        return (
            f"Dispense({_esc_str(self.rack_label)}, {_esc_str(self.rack_id)}, "
            f"{_esc_str(self.rack_type)}, {self.position}, "
            f"{_esc_str(self.tube_id)}, {_esc_num(self.volume)}, "
            f"{_esc_str(self.liquid_class)}, {_esc_str(self.tip_type)}, "
            f"{self.tip_mask});"
        )


@dataclass
class MixStep:
    """Mix command: ``Mix(rackLabel, ..., cycles);``"""

    rack_label: str
    rack_id: str
    rack_type: str
    position: int
    tube_id: str
    volume: float
    liquid_class: str
    tip_type: str
    tip_mask: int
    cycles: int = 3

    def to_esc(self) -> str:
        return (
            f"Mix({_esc_str(self.rack_label)}, {_esc_str(self.rack_id)}, "
            f"{_esc_str(self.rack_type)}, {self.position}, "
            f"{_esc_str(self.tube_id)}, {_esc_num(self.volume)}, "
            f"{_esc_str(self.liquid_class)}, {_esc_str(self.tip_type)}, "
            f"{self.tip_mask}, {self.cycles});"
        )


@dataclass
class WashStep:
    """Wash command: ``Wash(washStationID);``"""

    wash_station_id: str = "Wash1"

    def to_esc(self) -> str:
        return f"Wash({_esc_str(self.wash_station_id)});"


@dataclass
class GetDiTiStep:
    """Get disposable tips: ``GetDITI(tipCount, 0, 0, 0);``"""

    tip_count: int = 1

    def to_esc(self) -> str:
        return f"GetDITI({self.tip_count}, 0, 0, 0);"


@dataclass
class DropDiTiStep:
    """Drop disposable tips: ``DropDITI(rackLabel, ...);``"""

    rack_label: str
    rack_id: str
    rack_type: str
    position: int

    def to_esc(self) -> str:
        return (
            f"DropDITI({_esc_str(self.rack_label)}, {_esc_str(self.rack_id)}, "
            f"{_esc_str(self.rack_type)}, {self.position});"
        )


@dataclass
class MoveLiHaStep:
    """Move LiHa arm to a position via worklist coords."""

    arm: int = 1
    coord_string: str = ""

    def to_esc(self) -> str:
        return f"MoveLiHa({self.arm}, 0, 0, 0, {_esc_str(self.coord_string)});"


@dataclass
class CommentStep:
    """Comment / remark in ESC script (non-executable)."""

    text: str

    def to_esc(self) -> str:
        return f"// {self.text}"


@dataclass
class RawStep:
    """Raw .esc command line (pass-through for unsupported commands)."""

    command: str

    def to_esc(self) -> str:
        return self.command


# ── ESC Builder ────────────────────────────────────────────────────────

class ESCBuilder:
    """Build a complete .esc script programmatically.

    Usage::

        builder = ESCBuilder()
        builder.add_comment("Pick up 200 µL tips")
        builder.add_get_diti(4)
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
        builder.add_drop_diti("TipRack", "TR001", "DiTi_200ul", 1)
        print(builder.build())
    """

    def __init__(self) -> None:
        self._steps: List[object] = []

    # -- Adders ---------------------------------------------------------

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
        step = AspirateStep(
            rack_label=rack_label, rack_id=rack_id, rack_type=rack_type,
            position=position, tube_id=tube_id, volume=volume,
            liquid_class=liquid_class, tip_type=tip_type, tip_mask=tip_mask,
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
        step = DispenseStep(
            rack_label=rack_label, rack_id=rack_id, rack_type=rack_type,
            position=position, tube_id=tube_id, volume=volume,
            liquid_class=liquid_class, tip_type=tip_type, tip_mask=tip_mask,
        )
        self._steps.append(step)
        return step

    def add_mix(
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
        cycles: int = 3,
    ) -> MixStep:
        step = MixStep(
            rack_label=rack_label, rack_id=rack_id, rack_type=rack_type,
            position=position, tube_id=tube_id, volume=volume,
            liquid_class=liquid_class, tip_type=tip_type, tip_mask=tip_mask,
            cycles=cycles,
        )
        self._steps.append(step)
        return step

    def add_wash(self, wash_station_id: str = "Wash1") -> WashStep:
        step = WashStep(wash_station_id=wash_station_id)
        self._steps.append(step)
        return step

    def add_get_diti(self, tip_count: int = 1) -> GetDiTiStep:
        """Pick up disposable tips."""
        step = GetDiTiStep(tip_count=tip_count)
        self._steps.append(step)
        return step

    def add_drop_diti(
        self,
        rack_label: str,
        rack_id: str,
        rack_type: str,
        position: int,
    ) -> DropDiTiStep:
        """Drop (eject) disposable tips."""
        step = DropDiTiStep(
            rack_label=rack_label, rack_id=rack_id,
            rack_type=rack_type, position=position,
        )
        self._steps.append(step)
        return step

    def add_comment(self, text: str) -> CommentStep:
        step = CommentStep(text=text)
        self._steps.append(step)
        return step

    def add_raw(self, esc_command: str) -> RawStep:
        """Add a raw .esc command line (for unsupported commands)."""
        step = RawStep(command=esc_command)
        self._steps.append(step)
        return step

    def add_move_liha(self, arm: int = 1, coord_string: str = "") -> MoveLiHaStep:
        step = MoveLiHaStep(arm=arm, coord_string=coord_string)
        self._steps.append(step)
        return step

    # -- Builder / output -----------------------------------------------

    @property
    def steps(self) -> List[object]:
        return list(self._steps)

    def build(self) -> str:
        """Return the complete .esc file content."""
        lines = [step.to_esc() for step in self._steps]  # type: ignore[union-attr]
        return "\n".join(lines) + "\n"

    def save(self, filepath: str) -> str:
        """Write the .esc content to *filepath* and return the path."""
        content = self.build()
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as fh:
            fh.write(content)
        return filepath

    def __len__(self) -> int:
        return len(self._steps)

    def __repr__(self) -> str:
        return f"<ESCBuilder steps={len(self._steps)}>"
