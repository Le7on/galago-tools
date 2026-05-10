"""Unit tests for freedom_evo.script_builder."""

import os
import tempfile

import pytest

from tools.freedom_evo.script_builder import (
    GWLBuilder,
    AspirateStep,
    DispenseStep,
    WashStep,
    BreakStep,
    DiTiStep,
)


# ── Step-level format tests ─────────────────────────────────────────

class TestAspirateStep:
    def test_basic_format(self):
        step = AspirateStep(
            rack_label="SrcPlate",
            rack_id="S001",
            rack_type="MTP",
            position=1,
            tube_id="SampleA",
            volume=50.0,
            liquid_class="Water",
            tip_type="1000ul",
            tip_mask=1,
        )
        assert step.to_gwl() == "A;SrcPlate;S001;MTP;1;SampleA;50.0;Water;1000ul;1;"

    def test_volume_zero(self):
        step = AspirateStep("R", "ID", "T", 5, "tube", 0.0, "LC", "tip", 1)
        assert step.to_gwl() == "A;R;ID;T;5;tube;0.0;LC;tip;1;"

    def test_negative_volume_still_emitted(self):
        step = AspirateStep("R", "ID", "T", 1, "t", -1.5, "LC", "tip", 2)
        assert step.to_gwl() == "A;R;ID;T;1;t;-1.5;LC;tip;2;"


class TestDispenseStep:
    def test_basic_format(self):
        step = DispenseStep(
            rack_label="DstPlate",
            rack_id="D001",
            rack_type="MTP",
            position=96,
            tube_id="DestA",
            volume=25.5,
            liquid_class="Water",
            tip_type="50ul",
            tip_mask=8,
        )
        assert step.to_gwl() == "D;DstPlate;D001;MTP;96;DestA;25.5;Water;50ul;8;"


class TestWashStep:
    def test_default_station(self):
        step = WashStep()
        assert step.to_gwl() == "W;Wash1;"

    def test_custom_station(self):
        step = WashStep("Wash2")
        assert step.to_gwl() == "W;Wash2;"


class TestBreakStep:
    def test_format(self):
        step = BreakStep()
        assert step.to_gwl() == "B;"


class TestDiTiStep:
    def test_set_format(self):
        step = DiTiStep("Set", "TipRack", "TR001", "DiTi_200ul", 1)
        assert step.to_gwl() == "S;Set;TipRack;TR001;DiTi_200ul;1;"

    def test_drop_format(self):
        step = DiTiStep("Drop", "TipRack", "TR001", "DiTi_200ul", 1)
        assert step.to_gwl() == "S;Drop;TipRack;TR001;DiTi_200ul;1;"


# ── GWLBuilder tests ────────────────────────────────────────────────

class TestGWLBuilder:
    def test_empty_build(self):
        builder = GWLBuilder()
        assert builder.build() == "\n"  # just the trailing newline
        assert len(builder) == 0

    def test_add_aspirate(self):
        builder = GWLBuilder()
        builder.add_aspirate("Src", "S1", "MTP", 1, "A1", 10.0, "LC", "tip", 1)
        assert len(builder) == 1
        assert builder.build() == "A;Src;S1;MTP;1;A1;10.0;LC;tip;1;\n"

    def test_add_dispense(self):
        builder = GWLBuilder()
        builder.add_dispense("Dst", "D1", "MTP", 1, "B1", 10.0, "LC", "tip", 1)
        assert len(builder) == 1
        assert builder.build() == "D;Dst;D1;MTP;1;B1;10.0;LC;tip;1;\n"

    def test_add_wash(self):
        builder = GWLBuilder()
        builder.add_wash()
        assert len(builder) == 1
        assert builder.build() == "W;Wash1;\n"

    def test_add_break(self):
        builder = GWLBuilder()
        builder.add_break()
        assert len(builder) == 1
        assert builder.build() == "B;\n"

    def test_add_diti_set(self):
        builder = GWLBuilder()
        builder.add_diti("Set", "TipRack", "TR1", "DiTi_200ul", 1)
        assert builder.build() == "S;Set;TipRack;TR1;DiTi_200ul;1;\n"

    def test_add_diti_drop(self):
        builder = GWLBuilder()
        builder.add_diti("Drop", "TipRack", "TR1", "DiTi_200ul", 1)
        assert builder.build() == "S;Drop;TipRack;TR1;DiTi_200ul;1;\n"

    def test_add_diti_invalid_operation(self):
        builder = GWLBuilder()
        with pytest.raises(ValueError, match="must be 'Set' or 'Drop'"):
            builder.add_diti("Pick", "R", "ID", "T", 1)

    def test_full_pipetting_workflow(self):
        """End-to-end: pick tips, aspirate, dispense, wash, drop tips."""
        builder = GWLBuilder()

        # Pick up tips
        builder.add_diti("Set", "TipRack200", "TR200", "DiTi_200ul", 1)

        # Aspirate 50 µL from source plate well A1
        builder.add_aspirate(
            rack_label="SrcMTP",
            rack_id="S123",
            rack_type="MTP",
            position=1,
            tube_id="Sample01",
            volume=50.0,
            liquid_class="Water_Asp",
            tip_type="200ul",
            tip_mask=1,
        )

        # Dispense into destination plate well H12
        builder.add_dispense(
            rack_label="DstMTP",
            rack_id="D456",
            rack_type="MTP",
            position=96,
            tube_id="Sample01_dst",
            volume=50.0,
            liquid_class="Water_Disp",
            tip_type="200ul",
            tip_mask=1,
        )

        # Wash tips
        builder.add_wash("Wash1")

        # Drop tips
        builder.add_diti("Drop", "TipRack200", "TR200", "DiTi_200ul", 1)

        # Add final break for user check
        builder.add_break()

        expected = (
            "S;Set;TipRack200;TR200;DiTi_200ul;1;\n"
            "A;SrcMTP;S123;MTP;1;Sample01;50.0;Water_Asp;200ul;1;\n"
            "D;DstMTP;D456;MTP;96;Sample01_dst;50.0;Water_Disp;200ul;1;\n"
            "W;Wash1;\n"
            "S;Drop;TipRack200;TR200;DiTi_200ul;1;\n"
            "B;\n"
        )
        assert builder.build() == expected
        assert len(builder) == 6

    def test_save_creates_file(self):
        builder = GWLBuilder()
        builder.add_aspirate("Src", "S1", "MTP", 1, "A1", 10.0, "LC", "tip", 1)
        builder.add_dispense("Dst", "D1", "MTP", 1, "B1", 10.0, "LC", "tip", 1)

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "subdir", "test.gwl")
            result = builder.save(filepath)
            assert result == filepath
            assert os.path.isfile(filepath)
            with open(filepath, "r") as fh:
                assert fh.read() == builder.build()

    def test_repr(self):
        builder = GWLBuilder()
        builder.add_break()
        assert repr(builder) == "<GWLBuilder steps=1>"

    def test_steps_property_is_copy(self):
        builder = GWLBuilder()
        builder.add_break()
        steps = builder.steps
        steps.append(None)  # mutating the copy should not affect builder
        assert len(builder) == 1

    def test_multiple_aspirates_same_well(self):
        """Multiple aspirations from the same well produce distinct lines."""
        builder = GWLBuilder()
        for vol in [10.0, 20.0, 30.0]:
            builder.add_aspirate("Src", "S1", "MTP", 1, "A1", vol, "LC", "tip", 1)
        lines = builder.build().strip().split("\n")
        assert len(lines) == 3
        assert all(line.startswith("A;") for line in lines)
        assert "10.0" in lines[0]
        assert "20.0" in lines[1]
        assert "30.0" in lines[2]
