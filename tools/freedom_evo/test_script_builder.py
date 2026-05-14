"""Unit tests for freedom_evo.script_builder (.esc format)."""

import os
import tempfile

import pytest

from tools.freedom_evo.script_builder import (
    ESCBuilder,
    AspirateStep,
    DispenseStep,
    MixStep,
    WashStep,
    GetDiTiStep,
    DropDiTiStep,
    CommentStep,
    RawStep,
    MoveLiHaStep,
)


# ── Step-level format tests ───────────────────────────────────────────

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
        esc = step.to_esc()
        assert esc == (
            'Aspirate("SrcPlate", "S001", "MTP", 1, "SampleA", 50.0, '
            '"Water", "1000ul", 1);'
        )

    def test_volume_zero(self):
        step = AspirateStep("R", "ID", "T", 5, "tube", 0.0, "LC", "tip", 1)
        assert step.to_esc().endswith(");")

    def test_negative_volume_still_emitted(self):
        step = AspirateStep("R", "ID", "T", 1, "t", -1.5, "LC", "tip", 2)
        assert "-1.5" in step.to_esc()


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
        esc = step.to_esc()
        assert esc == (
            'Dispense("DstPlate", "D001", "MTP", 96, "DestA", 25.5, '
            '"Water", "50ul", 8);'
        )


class TestMixStep:
    def test_basic_format(self):
        step = MixStep(
            rack_label="SrcPlate",
            rack_id="S001",
            rack_type="MTP",
            position=1,
            tube_id="SampleA",
            volume=50.0,
            liquid_class="Water",
            tip_type="200ul",
            tip_mask=1,
            cycles=5,
        )
        esc = step.to_esc()
        assert "Mix(" in esc
        assert "50.0" in esc
        assert "5);" in esc


class TestWashStep:
    def test_default_station(self):
        step = WashStep()
        assert step.to_esc() == 'Wash("Wash1");'

    def test_custom_station(self):
        step = WashStep("Wash2")
        assert step.to_esc() == 'Wash("Wash2");'


class TestGetDiTiStep:
    def test_default_count(self):
        step = GetDiTiStep()
        assert step.to_esc() == "GetDITI(1, 0, 0, 0);"

    def test_custom_count(self):
        step = GetDiTiStep(tip_count=4)
        assert step.to_esc() == "GetDITI(4, 0, 0, 0);"


class TestDropDiTiStep:
    def test_format(self):
        step = DropDiTiStep("TipRack", "TR001", "DiTi_200ul", 1)
        esc = step.to_esc()
        assert esc == 'DropDITI("TipRack", "TR001", "DiTi_200ul", 1);'


class TestCommentStep:
    def test_format(self):
        step = CommentStep("Pick up tips")
        assert step.to_esc() == "// Pick up tips"


class TestRawStep:
    def test_format(self):
        step = RawStep("CustomCommand(1, 2, 3);")
        assert step.to_esc() == "CustomCommand(1, 2, 3);"


class TestMoveLiHaStep:
    def test_format(self):
        step = MoveLiHaStep(arm=1, coord_string="0C08@Grid1")
        esc = step.to_esc()
        assert 'MoveLiHa(1, 0, 0, 0, "0C08@Grid1");' == esc


# ── ESCBuilder tests ──────────────────────────────────────────────────

class TestESCBuilder:
    def test_empty_build(self):
        builder = ESCBuilder()
        assert builder.build() == "\n"
        assert len(builder) == 0

    def test_add_aspirate(self):
        builder = ESCBuilder()
        builder.add_aspirate("Src", "S1", "MTP", 1, "A1", 10.0, "LC", "tip", 1)
        assert len(builder) == 1
        esc = builder.build()
        assert esc.startswith("Aspirate(")
        assert esc.endswith(";\n")

    def test_add_dispense(self):
        builder = ESCBuilder()
        builder.add_dispense("Dst", "D1", "MTP", 1, "B1", 10.0, "LC", "tip", 1)
        assert len(builder) == 1
        esc = builder.build()
        assert esc.startswith("Dispense(")
        assert esc.endswith(";\n")

    def test_add_wash(self):
        builder = ESCBuilder()
        builder.add_wash()
        assert len(builder) == 1
        assert builder.build() == 'Wash("Wash1");\n'

    def test_add_comment(self):
        builder = ESCBuilder()
        builder.add_comment("hello world")
        assert len(builder) == 1
        assert builder.build() == "// hello world\n"

    def test_add_get_diti(self):
        builder = ESCBuilder()
        builder.add_get_diti(8)
        assert builder.build() == "GetDITI(8, 0, 0, 0);\n"

    def test_add_drop_diti(self):
        builder = ESCBuilder()
        builder.add_drop_diti("TipRack", "TR1", "DiTi_200ul", 1)
        assert len(builder) == 1
        assert "DropDITI(" in builder.build()

    def test_full_pipetting_workflow(self):
        """End-to-end: pick tips, aspirate, dispense, wash, drop tips."""
        builder = ESCBuilder()

        builder.add_comment("Pick up 200 µL tips")
        builder.add_get_diti(4)
        builder.add_comment("Aspirate 50 µL from source")
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
        builder.add_comment("Dispense to destination")
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
        builder.add_wash("Wash1")
        builder.add_drop_diti("TipRack200", "TR200", "DiTi_200ul", 1)
        builder.add_comment("Done")

        esc_content = builder.build()
        lines = esc_content.strip().split("\n")

        assert len(lines) == 9
        assert lines[0] == "// Pick up 200 µL tips"
        assert lines[1] == "GetDITI(4, 0, 0, 0);"
        assert "Aspirate(" in lines[3]
        assert "SrcMTP" in lines[3]
        assert "50.0" in lines[3]
        assert "Dispense(" in lines[5]
        assert "DstMTP" in lines[5]
        assert 'Wash("Wash1");' in lines[6]
        assert lines[8] == "// Done"

    def test_save_creates_file(self):
        builder = ESCBuilder()
        builder.add_comment("Test script")
        builder.add_aspirate("Src", "S1", "MTP", 1, "A1", 10.0, "LC", "tip", 1)

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "subdir", "test.esc")
            result = builder.save(filepath)
            assert result == filepath
            assert os.path.isfile(filepath)
            with open(filepath, "r") as fh:
                assert fh.read() == builder.build()

    def test_repr(self):
        builder = ESCBuilder()
        builder.add_comment("test")
        assert repr(builder) == "<ESCBuilder steps=1>"

    def test_steps_property_is_copy(self):
        builder = ESCBuilder()
        builder.add_comment("test")
        steps = builder.steps
        steps.append(None)
        assert len(builder) == 1

    def test_multiple_aspirates_same_well(self):
        builder = ESCBuilder()
        for vol in [10.0, 20.0, 30.0]:
            builder.add_aspirate("Src", "S1", "MTP", 1, "A1", vol, "LC", "tip", 1)
        lines = builder.build().strip().split("\n")
        assert len(lines) == 3
        for i, vol in enumerate([10.0, 20.0, 30.0]):
            assert f"{vol:.1f}" in lines[i]

    def test_add_mix(self):
        builder = ESCBuilder()
        builder.add_mix("Src", "S1", "MTP", 1, "A1", 50.0, "LC", "200ul", 1, cycles=3)
        esc = builder.build()
        assert esc.startswith("Mix(")
        assert "3);" in esc
        assert "50.0" in esc

    def test_add_raw_passthrough(self):
        builder = ESCBuilder()
        builder.add_raw("SomeUnknownCmd(42, \"foo\");")
        assert builder.build() == 'SomeUnknownCmd(42, "foo");\n'

    def test_pipetting_without_tips_in_script(self):
        """User can construct any .esc sequence — tips are optional."""
        builder = ESCBuilder()
        builder.add_aspirate("Src", "S1", "MTP", 1, "A1", 30.0, "LC", "50ul", 1)
        builder.add_dispense("Dst", "D1", "MTP", 96, "H12", 30.0, "LC", "50ul", 1)
        esc = builder.build()
        assert "Aspirate(" in esc
        assert "Dispense(" in esc
