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
