"""Tests for the Midea AC protocol decoder/encoder."""

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PKG_DIR = ROOT / "custom_components" / "flipper_rc"

# Load `pulse` and `manchester` as top-level modules first so `rc_encoder`
# can `import pulse` / `import manchester` from its fallback path.
for name in ("pulse", "manchester"):
    spec = importlib.util.spec_from_file_location(name, PKG_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules[name] = mod

spec = importlib.util.spec_from_file_location("rc_encoder", PKG_DIR / "rc_encoder.py")
rc_encoder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rc_encoder)


# Real captured sample from EAS Electric EADVA25NT2 (Midea-OEM split AC).
# Command: "Power off" via the original IR remote.
POWER_OFF_RAW = (
    "4454,4327,593,1557,592,482,592,1557,592,1558,591,483,591,483,591,1558,591,484,"
    "590,484,601,1548,601,474,590,484,601,1549,600,1549,600,475,599,1550,599,475,"
    "567,1582,598,1551,598,1551,598,1551,598,477,597,1552,597,1552,597,1553,596,478,"
    "596,478,596,478,596,478,596,1553,596,478,596,478,596,1554,595,1553,596,1554,"
    "595,479,595,479,595,479,595,479,595,480,594,480,594,480,594,480,594,1555,594,"
    "1555,594,1555,594,1556,593,1556,593,5148,4450,4331,599,1550,599,475,599,1551,"
    "598,1551,598,476,598,476,598,1551,598,477,597,477,597,1552,597,478,565,509,"
    "597,1552,597,1553,596,478,565,1584,596,478,596,1553,596,1553,596,1553,596,1554,"
    "595,479,595,1554,595,1554,595,1555,594,480,594,481,593,481,593,481,572,1577,"
    "593,481,593,481,593,1556,593,1556,593,1556,593,482,592,482,592,482,592,482,"
    "592,482,592,483,591,482,592,483,591,1557,592,1558,591,1558,591,1558,601,1548,601"
)


def parse_raw(s):
    return [int(v) for v in s.split(",")]


def test_decode_real_power_off_sample():
    values = parse_raw(POWER_OFF_RAW)
    decoded = rc_encoder.midea_decode(values)
    # Expected payload bytes in MSB-first reading: 0x7B, 0xE0
    # (vendor 0xB2, 0x4D and inverses 0x84, 0x1F are validated by midea_decode itself)
    assert decoded == "a=0x7B,b=0xE0"


def test_decode_rejects_non_midea_vendor():
    """A pure Gorenje/MDV packet (no 0xB2 vendor byte) must NOT decode as Midea."""
    # Hand-crafted: vendor byte = 0xA1 (something else), valid inverse pairs
    bytes_msb = [0xA1, 0xA1 ^ 0xFF, 0x12, 0x12 ^ 0xFF, 0x34, 0x34 ^ 0xFF]
    raw = rc_encoder.pulse.distance_encode(
        bytes_msb,
        rc_encoder.MIDEA_LEADING_PULSE, rc_encoder.MIDEA_LEADING_GAP,
        rc_encoder.MIDEA_PULSE, rc_encoder.MIDEA_GAP_0, rc_encoder.MIDEA_GAP_1,
        48, msb_first=True,
    )
    raw = raw + [rc_encoder.MIDEA_INTER_GAP] + raw
    with pytest.raises(ValueError, match="vendor byte expected 0xB2"):
        rc_encoder.midea_decode(raw)


def test_decode_rejects_broken_inverse_pair():
    """Tamper with B3 so the inverse-pair invariant fails."""
    bytes_msb = [0xB2, 0x4D, 0x12, 0x99, 0x34, 0x34 ^ 0xFF]  # B3 != ~B2
    raw = rc_encoder.pulse.distance_encode(
        bytes_msb,
        rc_encoder.MIDEA_LEADING_PULSE, rc_encoder.MIDEA_LEADING_GAP,
        rc_encoder.MIDEA_PULSE, rc_encoder.MIDEA_GAP_0, rc_encoder.MIDEA_GAP_1,
        48, msb_first=True,
    )
    raw = raw + [rc_encoder.MIDEA_INTER_GAP] + raw
    with pytest.raises(ValueError, match="invalid inverse pair"):
        rc_encoder.midea_decode(raw)


def test_decode_two_frame_signal_extracts_command_and_preamble():
    """A 3-packet signal (preamble + command + command) decodes both bytes
    of the actual command and exposes the preamble as `pa`/`pb`."""
    preamble = rc_encoder._midea_pack(0xE0, 0x03)
    command = rc_encoder._midea_pack(0xBF, 0xD0)
    raw = (
        preamble + [rc_encoder.MIDEA_INTER_GAP]
        + command + [rc_encoder.MIDEA_INTER_GAP]
        + command
    )
    decoded = rc_encoder.midea_decode(raw)
    assert decoded == "a=0xBF,b=0xD0,pa=0xE0,pb=0x03"


def test_decode_three_identical_frames_returns_simple_form():
    """If all 3 packets are identical (no preamble), no `pa`/`pb` annotation."""
    packet = rc_encoder._midea_pack(0xAA, 0x55)
    raw = (
        packet + [rc_encoder.MIDEA_INTER_GAP]
        + packet + [rc_encoder.MIDEA_INTER_GAP]
        + packet
    )
    assert rc_encoder.midea_decode(raw) == "a=0xAA,b=0x55"


def test_encode_round_trip_with_preamble():
    encoded = rc_encoder.midea_encode(a=0xBF, b=0xD0, pa=0xE0, pb=0x03)
    assert len(encoded) == 99 * 3 + 2  # 3 packets, 2 inter-packet gaps
    assert rc_encoder.midea_decode(encoded) == "a=0xBF,b=0xD0,pa=0xE0,pb=0x03"


def test_encode_rejects_partial_preamble():
    with pytest.raises(ValueError, match="must be provided together"):
        rc_encoder.midea_encode(a=0x12, b=0x34, pa=0x56)
    with pytest.raises(ValueError, match="must be provided together"):
        rc_encoder.midea_encode(a=0x12, b=0x34, pb=0x78)


def test_encode_round_trip_zero_payload():
    encoded = rc_encoder.midea_encode(a=0x00, b=0x00)
    decoded = rc_encoder.midea_decode(encoded)
    assert decoded == "a=0x00,b=0x00"


def test_encode_round_trip_arbitrary_payload():
    encoded = rc_encoder.midea_encode(a=0xA5, b=0x5A)
    decoded = rc_encoder.midea_decode(encoded)
    assert decoded == "a=0xA5,b=0x5A"


def test_encode_round_trip_power_off_payload():
    """Encoding the real Power off payload should produce a packet that
    decodes back to the same bytes."""
    encoded = rc_encoder.midea_encode(a=0x7B, b=0xE0)
    decoded = rc_encoder.midea_decode(encoded)
    assert decoded == "a=0x7B,b=0xE0"
    # And the encoded length matches the real captured signal (199 elements).
    assert len(encoded) == 199


def test_encode_rejects_out_of_range():
    with pytest.raises(ValueError, match="'a' must be in range"):
        rc_encoder.midea_encode(a=0x100, b=0)
    with pytest.raises(ValueError, match="'b' must be in range"):
        rc_encoder.midea_encode(a=0, b=-1)


def test_auto_decode_picks_midea_for_real_sample():
    """rc_auto_decode should pick midea (not ac) for a 0xB2-vendor packet."""
    values = parse_raw(POWER_OFF_RAW)
    decoded = rc_encoder.rc_auto_decode(values)
    assert decoded.startswith("midea:")
    assert decoded == "midea:a=0x7B,b=0xE0"


def test_auto_decode_falls_back_to_ac_for_non_midea_vendor():
    """For Gorenje/MDV-style packets (vendor != 0xB2), midea must be skipped
    and `ac` should still pick them up."""
    # Build a Gorenje-like packet: 6 bytes, inverse pairs, vendor = 0x4C (any non-0xB2).
    addr = 0x4C
    cmd = 0x1234
    encoded = rc_encoder.air_conditioner_encode(addr=addr, cmd=cmd, double=1)
    decoded = rc_encoder.rc_auto_decode(encoded)
    assert decoded.startswith("ac:")
    # The ac decoder reports addr/cmd in its own format
    assert "addr=0x4C" in decoded
    assert "cmd=0x1234" in decoded


def test_auto_encode_round_trip():
    """rc_auto_encode("midea:a=0xXX,b=0xYY") must produce a signal that
    rc_auto_decode reads back as the same midea string."""
    cmd_str = "midea:a=0x7B,b=0xE0"
    encoded = rc_encoder.rc_auto_encode(cmd_str)
    assert rc_encoder.rc_auto_decode(encoded) == cmd_str


# === Field-level encoding ===
#
# Reference table — confirmed against real captures from EAS Electric
# EADVA25NT2 (Midea OEM):
#
#   Power off                  → a=0x7B b=0xE0
#   Auto 22°  fan=auto         → a=0x1F b=0x78
#   Auto 24°  fan=auto         → a=0x1F b=0x48
#   Cool 22°  fan=auto         → a=0xBF b=0x70
#   Cool 22°  fan=low          → a=0x9F b=0x70
#   Cool 22°  fan=med          → a=0x5F b=0x70
#   Cool 22°  fan=high         → a=0x3F b=0x70
#   Cool 26°  fan=auto         → a=0xBF b=0xD0
#   Heat 22°  fan=auto         → a=0xBF b=0x7C


@pytest.mark.parametrize("mode,temp,fan,expected_a,expected_b", [
    # Cool mode, all fans, temp 22
    ("cool", 22, "auto", 0xBF, 0x70),
    ("cool", 22, "low",  0x9F, 0x70),
    ("cool", 22, "med",  0x5F, 0x70),
    ("cool", 22, "high", 0x3F, 0x70),
    # Cool mode, temp variations
    ("cool", 26, "auto", 0xBF, 0xD0),
    # Heat mode
    ("heat", 22, "auto", 0xBF, 0x7C),
    # Auto mode (fan is forced, but accept any value for caller convenience)
    ("auto", 22, "auto", 0x1F, 0x78),
    ("auto", 24, "auto", 0x1F, 0x48),
    # Heat 25 — temp Gray code 0xC, mode 0b11
    ("heat", 25, "auto", 0xBF, 0xCC),
    # Dry mode (fan locked to AC-controlled, like auto)
    ("dry",  24, "auto", 0x1F, 0x44),
    # Fan mode (temp ignored, sentinel 0xE)
    ("fan",  None, "auto", 0xBF, 0xE4),
])
def test_fields_to_bytes_matches_real_captures(mode, temp, fan, expected_a, expected_b):
    a, b = rc_encoder._midea_fields_to_bytes(mode=mode, temp=temp, fan=fan)
    assert (a, b) == (expected_a, expected_b), (
        f"mode={mode}, temp={temp}, fan={fan} produced "
        f"a=0x{a:02X}, b=0x{b:02X}, expected a=0x{expected_a:02X}, b=0x{expected_b:02X}"
    )


def test_fields_to_bytes_power_off_returns_magic_bytes():
    a, b = rc_encoder._midea_fields_to_bytes(power="off")
    assert (a, b) == (0x7B, 0xE0)
    a, b = rc_encoder._midea_fields_to_bytes(power=False)
    assert (a, b) == (0x7B, 0xE0)
    # Power=off ignores other field params.
    a, b = rc_encoder._midea_fields_to_bytes(mode="cool", temp=24, fan="high", power="off")
    assert (a, b) == (0x7B, 0xE0)


def test_fields_to_bytes_defaults():
    """Defaults: mode=cool, temp=22, fan=auto, power=on."""
    a, b = rc_encoder._midea_fields_to_bytes()
    assert (a, b) == (0xBF, 0x70)


def test_fields_to_bytes_rejects_bad_input():
    with pytest.raises(ValueError, match="unsupported mode"):
        rc_encoder._midea_fields_to_bytes(mode="freeze")
    with pytest.raises(ValueError, match="unsupported fan"):
        rc_encoder._midea_fields_to_bytes(mode="cool", fan="turbo")
    with pytest.raises(ValueError, match="out of supported range"):
        rc_encoder._midea_fields_to_bytes(mode="cool", temp=99)


def test_bytes_to_fields_round_trip_for_all_known_combos():
    """For every (mode, temp, fan) combo we know how to encode, the bytes
    decoded back must yield the same fields."""
    for mode in ("cool", "heat"):
        for temp in (17, 22, 24, 26, 30):
            for fan in ("auto", "low", "med", "high"):
                a, b = rc_encoder._midea_fields_to_bytes(mode=mode, temp=temp, fan=fan)
                fields = rc_encoder.midea_bytes_to_fields(a, b)
                assert fields == {
                    "power": True, "mode": mode, "temp": temp, "fan": fan,
                }, f"round-trip failed for ({mode}, {temp}, {fan}): got {fields}"

    # Auto / dry: fan is locked to "auto" (AC decides)
    for mode in ("auto", "dry"):
        for temp in (17, 22, 24, 26, 30):
            a, b = rc_encoder._midea_fields_to_bytes(mode=mode, temp=temp)
            fields = rc_encoder.midea_bytes_to_fields(a, b)
            assert fields == {
                "power": True, "mode": mode, "temp": temp, "fan": "auto",
            }, f"round-trip failed for ({mode}, {temp}): got {fields}"

    # Fan mode: temp is omitted from the decoded output (sentinel 0xE).
    for fan in ("auto", "low", "med", "high"):
        a, b = rc_encoder._midea_fields_to_bytes(mode="fan", fan=fan)
        fields = rc_encoder.midea_bytes_to_fields(a, b)
        assert fields == {
            "power": True, "mode": "fan", "fan": fan,
        }, f"round-trip failed for fan/{fan}: got {fields}"


def test_bytes_to_fields_recognizes_power_off():
    assert rc_encoder.midea_bytes_to_fields(0x7B, 0xE0) == {"power": False}


def test_midea_encode_field_form_matches_byte_form():
    """midea:mode=cool,temp=22,fan=auto,power=on must produce bytes
    identical to midea:a=0xBF,b=0x70."""
    by_fields = rc_encoder.midea_encode(mode="cool", temp=22, fan="auto", power="on")
    by_bytes = rc_encoder.midea_encode(a=0xBF, b=0x70)
    assert by_fields == by_bytes


def test_midea_encode_rejects_mixed_forms():
    with pytest.raises(ValueError, match="not both"):
        rc_encoder.midea_encode(a=0x12, b=0x34, mode="cool")


def test_midea_encode_sleep_shorthand_matches_explicit_preamble():
    """midea:mode=cool,sleep=on must equal midea:a=...,b=...,pa=0xE0,pb=0x03."""
    by_sleep = rc_encoder.midea_encode(mode="cool", temp=22, fan="auto", sleep="on")
    by_explicit = rc_encoder.midea_encode(a=0xBF, b=0x70, pa=0xE0, pb=0x03)
    assert by_sleep == by_explicit


def test_midea_encode_sleep_off_omits_preamble():
    by_sleep_off = rc_encoder.midea_encode(mode="cool", temp=22, fan="auto", sleep="off")
    by_no_sleep = rc_encoder.midea_encode(mode="cool", temp=22, fan="auto")
    assert by_sleep_off == by_no_sleep


def test_midea_encode_sleep_with_pa_raises():
    with pytest.raises(ValueError, match="cannot use both"):
        rc_encoder.midea_encode(a=0xBF, b=0x70, pa=0xE0, pb=0x03, sleep="on")


@pytest.mark.parametrize("cmd_str,expected_ab", [
    ("midea:mode=cool,temp=22,fan=auto", (0xBF, 0x70)),
    ("midea:mode=cool,temp=26,fan=auto", (0xBF, 0xD0)),
    ("midea:mode=heat,temp=22,fan=auto", (0xBF, 0x7C)),
    ("midea:mode=auto,temp=24", (0x1F, 0x48)),
    ("midea:power=off", (0x7B, 0xE0)),
])
def test_rc_auto_encode_field_form_round_trip(cmd_str, expected_ab):
    """rc_auto_encode must accept field-level midea strings and produce
    a signal that decodes to the matching a/b bytes."""
    encoded = rc_encoder.rc_auto_encode(cmd_str)
    decoded = rc_encoder.midea_decode(encoded)
    a_str, b_str = decoded.split(",")[:2]
    a = int(a_str.split("=")[1], 0)
    b = int(b_str.split("=")[1], 0)
    assert (a, b) == expected_ab


def test_rc_auto_encode_sleep_string():
    """rc_auto_encode must thread the `sleep=on` string through to midea_encode
    and produce the 3-frame signal with the standard preamble."""
    encoded = rc_encoder.rc_auto_encode("midea:mode=cool,temp=22,fan=auto,sleep=on")
    decoded = rc_encoder.midea_decode(encoded)
    assert decoded == "a=0xBF,b=0x70,pa=0xE0,pb=0x03"
