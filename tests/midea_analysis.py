"""
Diagnostic helper for analyzing raw Midea AC samples.

Run as:
    python tests/midea_analysis.py

It expects user-supplied samples in MIDEA_SAMPLES below. Decodes each one
into 6 bytes (LSB-first wire convention), validates Midea invariants
(B0=0xB2, B1=~B0, B3=~B2, B5=~B4, second half repeats first), and prints
a side-by-side diff so you can see which bits differ between commands.

Use this BEFORE writing the real decoder to confirm your AC speaks Midea
and to figure out the field layout.
"""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PULSE_PATH = ROOT / "custom_components" / "flipper_rc" / "pulse.py"
spec = importlib.util.spec_from_file_location("pulse", PULSE_PATH)
pulse = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pulse)


# Real samples captured by Flipper IR learn from EAS Electric EADVA25NT2
# (Midea-OEM split AC). Add more samples here as you collect them — at
# minimum: ac_off, cool_22, cool_24, cool_26, ideally also heat_22 and
# differing fan speeds, so we can identify which bits encode each field.
MIDEA_SAMPLES = {
    "Power off": (
        "raw:4454,4327,593,1557,592,482,592,1557,592,1558,591,483,591,483,591,1558,591,484,590,484,601,1548,601,474,590,484,601,1549,600,1549,600,475,599,1550,599,475,567,1582,598,1551,598,1551,598,1551,598,477,597,1552,597,1552,597,1553,596,478,596,478,596,478,596,478,596,1553,596,478,596,478,596,1554,595,1553,596,1554,595,479,595,479,595,479,595,479,595,480,594,480,594,480,594,480,594,1555,594,1555,594,1555,594,1556,593,1556,593,5148,4450,4331,599,1550,599,475,599,1551,598,1551,598,476,598,476,598,1551,598,477,597,477,597,1552,597,478,565,509,597,1552,597,1553,596,478,565,1584,596,478,596,1553,596,1553,596,1553,596,1554,595,479,595,1554,595,1554,595,1555,594,480,594,481,593,481,593,481,572,1577,593,481,593,481,593,1556,593,1556,593,1556,593,482,592,482,592,482,592,482,592,482,592,483,591,482,592,483,591,1557,592,1558,591,1558,591,1558,601,1548,601"
    ),
}

# Midea reference timings (matches Flipper's AC parser)
LEAD_PULSE = 4500
LEAD_GAP = 4500
PULSE = 560
GAP_0 = 560
GAP_1 = 1690
INTER_MSG_GAP = 5100  # observed ~5148


def parse_raw(s):
    assert s.startswith("raw:")
    return [int(v) for v in s[4:].split(",")]


def split_halves(values):
    """
    Midea is two 48-bit messages with ~5100µs gap between them. Locate the
    inter-message gap in the middle of the pulse stream and split.
    """
    # Bit pulses: 1 leading pulse + 1 leading gap + 48 * (pulse+gap) + closing pulse = 99 elements per half.
    # The 100th element is either the closing gap to the inter-msg gap (~5100)
    # or it IS the inter-msg gap. Then the second half follows.
    # Use the actual gap value: find position where a gap > 4000 appears (after element 50+).
    if len(values) < 100:
        raise ValueError(f"Too short for Midea: {len(values)} elements")

    # Look for the inter-message gap candidate around position 99..103
    for i in range(95, min(110, len(values))):
        if values[i] > 3000 and values[i] < 6000 and values[i] != LEAD_GAP:
            # Could be the inter-message gap. Split here.
            return values[:i], values[i + 1 :]
    # Fall back: assume position 99
    return values[:99], values[100:]


def decode_half(values):
    """Decode 48 bits using the same engine as flipper_rc's `ac` parser."""
    return pulse.distance_decode(
        values, LEAD_PULSE, LEAD_GAP, PULSE, GAP_0, GAP_1, 48
    )


def byte_lsb_to_msb(b):
    """Reverse bit order in a byte: LSB-first wire encoding -> MSB-first (Midea docs convention)."""
    out = 0
    for i in range(8):
        if b & (1 << i):
            out |= 1 << (7 - i)
    return out


def fmt_bits_msb(b):
    """Render a byte as 8-bit MSB-first binary string."""
    return f"{b:08b}"


def analyze(name, raw_str):
    print(f"\n{'=' * 70}")
    print(f"Sample: {name}")
    print(f"{'=' * 70}")
    values = parse_raw(raw_str)
    print(f"Total elements: {len(values)}")
    print(f"Header: {values[0]}, {values[1]}  (expected ~{LEAD_PULSE}/{LEAD_GAP})")

    h1, h2 = split_halves(values)
    print(f"Half 1 length: {len(h1)} elements")
    print(f"Half 2 length: {len(h2)} elements")

    try:
        bytes1 = decode_half(h1)
    except ValueError as e:
        print(f"!! Half 1 decode failed: {e}")
        return None
    try:
        bytes2 = decode_half(h2)
    except ValueError as e:
        print(f"!! Half 2 decode failed: {e}")
        bytes2 = None

    print(f"\nWire-LSB bytes (as flipper_rc reads them):")
    print(f"  Half 1: {[f'0x{b:02X}' for b in bytes1]}")
    if bytes2 is not None:
        print(f"  Half 2: {[f'0x{b:02X}' for b in bytes2]}")
        match = bytes1 == bytes2
        print(f"  Halves match: {match}")

    # Convert to MSB-first to align with IRremoteESP8266 / Midea spec docs.
    msb = [byte_lsb_to_msb(b) for b in bytes1]
    print(f"\nMSB-first bytes (Midea spec convention):")
    for i, b in enumerate(msb):
        print(f"  B{i}: 0x{b:02X}  ({fmt_bits_msb(b)})")

    # Validate Midea invariants
    print(f"\nMidea invariants:")
    print(f"  B0 == 0xB2 (Midea AC marker, MSB):  {msb[0] == 0xB2}  (got 0x{msb[0]:02X})")
    print(f"  B1 == ~B0 (LSB):  {bytes1[0] == bytes1[1] ^ 0xFF}")
    print(f"  B3 == ~B2 (LSB):  {bytes1[2] == bytes1[3] ^ 0xFF}")
    print(f"  B5 == ~B4 (LSB):  {bytes1[4] == bytes1[5] ^ 0xFF}")

    return msb


def diff_samples(samples_decoded):
    """Print which bits differ across samples — helps map fields."""
    if len(samples_decoded) < 2:
        return
    print(f"\n{'=' * 70}")
    print("Bit-level diff across samples")
    print(f"{'=' * 70}")
    names = list(samples_decoded.keys())
    print(f"Comparing: {names}")
    for byte_idx in range(6):
        col = [samples_decoded[n][byte_idx] for n in names]
        if len(set(col)) == 1:
            print(f"  B{byte_idx}: identical (0x{col[0]:02X})")
            continue
        print(f"  B{byte_idx}: differs!")
        for n, v in zip(names, col):
            print(f"     {n:<20}  0x{v:02X}  {fmt_bits_msb(v)}")
        # Highlight which bits change
        diff_mask = 0
        ref = col[0]
        for v in col[1:]:
            diff_mask |= ref ^ v
        print(f"     diff mask:           0x{diff_mask:02X}  {fmt_bits_msb(diff_mask)}")


def main():
    decoded = {}
    for name, raw in MIDEA_SAMPLES.items():
        msb = analyze(name, raw)
        if msb is not None:
            decoded[name] = msb
    diff_samples(decoded)


if __name__ == "__main__":
    main()
