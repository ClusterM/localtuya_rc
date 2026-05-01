"""
This module provides encoding and decoding functions for various IR protocols.

Author: Alexey Cluster, cluster@cluster.wtf, https://github.com/clusterm

Sources:
  - NEC: https://radioparty.ru/manuals/encyclopedia/213-ircontrol?start=1
  - RC5: https://www.mikrocontroller.net/articles/IRMP_-_english#RC5_.2B_RC5X, https://www.pcbheaven.com/userpages/The_Philips_RC5_Protocol/
  - RC6: https://www.mikrocontroller.net/articles/IRMP_-_english#RC6_.2B_RC6A, https://www.pcbheaven.com/userpages/The_Philips_RC6_Protocol/
  - Samsung: https://www.mikrocontroller.net/articles/IRMP_-_english#SAMSUNG
  - SIRC: https://www.sbprojects.net/knowledge/ir/sirc.php
  - Kaseikyo: https://github.com/Arduino-IRremote/Arduino-IRremote/blob/master/src/ir_Kaseikyo.hpp
  - RCA: https://www.sbprojects.net/knowledge/ir/rca.php
  - Pioneer: http://www.adrian-kingston.com/IRFormatPioneer.htm

Tested with Flipper Zero.
"""

try:
    from . import pulse
    from . import manchester
except ImportError:
    import pulse
    import manchester

global_toggle = 0

def get_toggle():
    """
    Toggles the value of the global variable 'global_toggle' between 0 and 1.

    Returns:
        int: The new value of 'global_toggle' after toggling.
    """
    global global_toggle
    global_toggle = 1 if global_toggle == 0 else 0
    return global_toggle


""" Protocol-specific functions """

""" NEC protocol and its variations """
NEC_LEADING_PULSE = 9000
NEC_LEADING_GAP = 4500
NEC_PULSE = 560
NEC_GAP_0 = 560
NEC_GAP_1 = 1690

def nec_decode(values):
    # Decode 32-bit NEC
    data = pulse.distance_decode(values, NEC_LEADING_PULSE, NEC_LEADING_GAP, NEC_PULSE, NEC_GAP_0, NEC_GAP_1, 32)
    if data[0] != data[1] ^ 0xFF or data[2] != data[3] ^ 0xFF:
        raise ValueError("Invalid NEC xored data")
    addr = data[0]
    cmd = data[2]
    return f"addr=0x{addr:02X},cmd=0x{cmd:02X}"

def nec_encode(addr, cmd):
    # Encode 32-bit NEC
    # NEC standard format: low-addr, ~low-addr, low-cmd, ~low-cmd
    if not (0x00 <= addr <= 0xFF):
        raise ValueError("Address must be in range 0x00-0xFF")
    if not (0x00 <= cmd <= 0xFF):
        raise ValueError("Command must be in range 0x00-0xFF")
    data = [addr & 0xFF, addr ^ 0xFF, cmd & 0xFF, cmd ^ 0xFF]
    return pulse.distance_encode(data, NEC_LEADING_PULSE, NEC_LEADING_GAP, NEC_PULSE, NEC_GAP_0, NEC_GAP_1)

def nec_ext_decode(values):
    # Decode 32-bit NEC (extended)
    data = pulse.distance_decode(values, NEC_LEADING_PULSE, NEC_LEADING_GAP, NEC_PULSE, NEC_GAP_0, NEC_GAP_1, 32)
    addr = data[0] | (data[1] << 8)
    cmd = data[2] | (data[3] << 8)
    return f"addr=0x{addr:04X},cmd=0x{cmd:04X}"

def nec_ext_encode(addr, cmd):
    # Encode 32-bit NEC
    if not (0x0000 <= addr <= 0xFFFF):
        raise ValueError("Address must be in range 0x0000-0xFFFF")
    if not (0x0000 <= cmd <= 0xFFFF):
        raise ValueError("Command must be in range 0x0000-0xFFFF")
    data = [addr & 0xFF, addr >> 8, cmd & 0xFF, cmd >> 8]
    return pulse.distance_encode(data, NEC_LEADING_PULSE, NEC_LEADING_GAP, NEC_PULSE, NEC_GAP_0, NEC_GAP_1)

def nec42_decode(pulses):
    # Decode 42-bit NEC (NEC42)
    data = pulse.distance_decode(pulses, NEC_LEADING_PULSE, NEC_LEADING_GAP, NEC_PULSE, NEC_GAP_0, NEC_GAP_1, 42)

    # We have 42 bits total. Let's reconstruct bits from data bytes.
    full_bits = 0
    bit_index = 0
    for byte_val in data:
        for bit_i in range(8):
            if bit_index == 42:
                break
            bit_value = (byte_val >> bit_i) & 1
            full_bits |= (bit_value << bit_index)
            bit_index += 1
        if bit_index == 42:
            break

    # According to the snippet:
    # bits:
    #   0-12: address (13 bits)
    #   13-25: address_inverse (13 bits)
    #   26-31: command (low 6 bits)
    #   32-33: command (high 2 bits)
    #   34-41: command_inverse (8 bits)
    address = full_bits & 0x1FFF
    address_inverse = (full_bits >> 13) & 0x1FFF
    command_low6 = (full_bits >> 26) & 0x3F
    # data2 = full_bits >> 32 gives us the top 10 bits (2 bits command high + 8 bits command_inv)
    data2 = full_bits >> 32
    command_high2 = data2 & 0x3
    command = command_low6 | (command_high2 << 6)
    command_inverse = (data2 >> 2) & 0xFF

    # Check if standard or extended
    if address != (~address_inverse & 0x1FFF) or command != (~command_inverse & 0xFF):
        raise ValueError("Invalid NEC42 xored data")
    # Standard NEC42
    return f"addr=0x{address:04X},cmd=0x{command:04X}"

def nec42_encode(addr, cmd):
    # Encode into a 42-bit NEC42 signal
    # Standard NEC42:
    #   address: 13 bits
    #   command: 8 bits
    #   address_inverse = ~address & 0x1FFF
    #   command_inverse = ~command & 0xFF
    if not (0x0000 <= addr <= 0x1FFF):
        raise ValueError("Address must be in range 0x0000-0x1FFF")
    if not (0x00 <= cmd <= 0xFF):
        raise ValueError("Command must be in range 0x00-0xFF")
    address = addr & 0x1FFF
    address_inv = (~address) & 0x1FFF
    command = cmd & 0xFF
    command_inv = (~command) & 0xFF

    full_bits = 0
    full_bits |= address
    full_bits |= address_inv << 13
    full_bits |= (command & 0x3F) << 26
    full_bits |= ((command >> 6) & 3) << 32
    full_bits |= command_inv << 34

    # Convert 42 bits into bytes
    values = []
    for i in range(6):
        byte_val = (full_bits >> (8 * i)) & 0xFF
        values.append(byte_val)

    return pulse.distance_encode(values, NEC_LEADING_PULSE, NEC_LEADING_GAP, NEC_PULSE, NEC_GAP_0, NEC_GAP_1, bit_length=42)

# NEC42 Extended
def nec42_ext_decode(pulses):
    # Decode a extended 42-bit NEC (NEC42)
    data = pulse.distance_decode(pulses, NEC_LEADING_PULSE, NEC_LEADING_GAP, NEC_PULSE, NEC_GAP_0, NEC_GAP_1, 42)

    # We have 42 bits total. Let's reconstruct bits from data bytes.
    full_bits = 0
    bit_index = 0
    for byte_val in data:
        for bit_i in range(8):
            if bit_index == 42:
                break
            bit_value = (byte_val >> bit_i) & 1
            full_bits |= (bit_value << bit_index)
            bit_index += 1
        if bit_index == 42:
            break

    address = full_bits & 0x1FFF
    address_inverse = (full_bits >> 13) & 0x1FFF
    command_low6 = (full_bits >> 26) & 0x3F
    # data2 = full_bits >> 32 gives us the top 10 bits (2 bits command high + 8 bits command_inv)
    data2 = full_bits >> 32
    command_high2 = data2 & 0x3
    command = command_low6 | (command_high2 << 6)
    command_inverse = (data2 >> 2) & 0xFF
    # Extended NEC42
    full_address = address | (address_inverse << 13)
    full_command = command | (command_inverse << 8)
    return f"addr=0x{full_address:04X},cmd=0x{full_command:04X}"

def nec42_ext_encode(addr, cmd):
    # Encode into a extended 42-bit NEC42 signal
    # Extended NEC42:
    #   full_address = 26 bits total (13 bits address + 13 bits address_inverse)
    #   full_command = 16 bits total (8 bits command + 8 bits command_inverse)
    #
    # Here we assume `addr` and `cmd` are the full extended values
    # So we break them down as per extended format:
    if not (0x000000 <= addr <= 0x3FFFFFF):
        raise ValueError("Address must be in range 0x000000-0x3FFFFFF")
    if not (0x0000 <= cmd <= 0xFFFF):
        raise ValueError("Command must be in range 0x0000-0xFFFF")
    address = addr & 0x1FFF
    address_inv = (addr >> 13) & 0x1FFF
    command = cmd & 0xFF
    command_inv = (cmd >> 8) & 0xFF

    full_bits = 0
    full_bits |= address
    full_bits |= address_inv << 13
    full_bits |= (command & 0x3F) << 26
    full_bits |= ((command >> 6) & 0x3) << 32
    full_bits |= command_inv << 34

    # Convert 42 bits into bytes
    values = []
    for i in range(6):
        byte_val = (full_bits >> (8*i)) & 0xFF
        values.append(byte_val)

    return pulse.distance_encode(values, NEC_LEADING_PULSE, NEC_LEADING_GAP, NEC_PULSE, NEC_GAP_0, NEC_GAP_1, bit_length=42)


""" Samsung protocol """
SAMSUNG_LEADING_PULSE = 4500
SAMSUNG_LEADING_GAP = 4500
SAMSUNG_PULSE = 550
SAMSUNG_GAP_0 = 550
SAMSUNG_GAP_1 = 1650

def samsung32_decode(pulsts):
    # Decode 32-bit Samsung
    data = pulse.distance_decode(pulsts, SAMSUNG_LEADING_PULSE, SAMSUNG_LEADING_GAP, SAMSUNG_PULSE, SAMSUNG_GAP_0, SAMSUNG_GAP_1, 32)
    if data[0] != data[1]:
        raise ValueError("Invalid address")
    if data[2] != (data[3] ^ 0xFF):
        raise ValueError("Invalid data")
    return f"addr=0x{data[0]:02X},cmd=0x{data[2]:02X}"

def samsung32_encode(addr, cmd):
    # Encode Samsung format
    # Samsung format: addr, addr, cmd, ~cmd
    if not (0x00 <= addr <= 0xFF):
        raise ValueError("Address must be in range 0x00-0xFF")
    if not (0x00 <= cmd <= 0xFF):
        raise ValueError("Command must be in range 0x00-0xFF")
    data = [addr, addr, cmd, cmd ^ 0xFF]
    return pulse.distance_encode(data, SAMSUNG_LEADING_PULSE, SAMSUNG_LEADING_GAP, SAMSUNG_PULSE, SAMSUNG_GAP_0, SAMSUNG_GAP_1)


""" RC6 protocol """
RC6_T = 444
RC6_START = [True] * 6 + [False] * 2

def rc6_decode(values):
    # Decode RC6
    data = manchester.decode(values, RC6_T, 21, RC6_START, phase=True, double_bits=[4], msb_first=True)
    start = data[0] >> 7
    if start != 1:
        raise ValueError("Invalid start bit")
    mode = (data[0] >> 4) & 0b111
    if mode != 0:
        raise ValueError("Invalid mode for RC6")
    # toggle = (data[0] >> 3) & 1
    addr = (data[0] & 0b111) << 5 | (data[1] >> 3)
    cmd = ((data[1] & 0b111) << 5) | (data[2] >> 3)
    return f"addr=0x{addr:02X},cmd=0x{cmd:02X}"

def rc6_encode(addr, cmd, toggle=None):
    # Encode RC6
    # RC6 format: 1-bit start, 3-bit mode (field), 1-bit toggle, 8-bit address, 8-bit command
    if not (0x00 <= addr <= 0xFF):
        raise ValueError("Address must be in range 0x00-0xFF")
    if not (0x00 <= cmd <= 0xFF):
        raise ValueError("Command must be in range 0x00-0xFF")
    if toggle is None:
        toggle = get_toggle()
    mode = 0
    values = [1 << 7 | (mode & 0b111) << 4 | toggle << 3 | (addr >> 5), (addr & 0x1F) << 3 | (cmd >> 5), (cmd & 0x1F) << 3]
    return manchester.encode(values, RC6_T, 21, RC6_START, phase=True, double_bits=[4], msb_first=True)


""" RC5 protocol """
RC5_T = 888
RC5_START = [True]

def rc5_decode(values):
    # Decode RC5
    data = manchester.decode(values, RC5_T, 13, RC5_START, phase=False, msb_first=True)
    # toggle = (data[0] >> 6) & 1
    addr = (data[0] >> 1) & 0b11111
    cmd = ((data[1] >> 3) & 0b11111) | ((data[0] & 1) << 5)
    if data[0] & 0x80 == 0:
        # RC5X
        cmd |= 0x40
    return f"addr=0x{addr:02X},cmd=0x{cmd:02X}"

def rc5_encode(addr, cmd, toggle=None):
    # Encode RC5
    # Field bit (inverted 6th cmd bit for RC5X) + toggle bit + 5-bit address + 6-bit command
    if not (0x00 <= addr <= 0x1F):
        raise ValueError("Address must be in range 0x00-0x1F")
    if not (0x00 <= cmd <= 0x7F):
        raise ValueError("Command must be in range 0x00-0x7F")
    if toggle is None:
        toggle = get_toggle()
    values = [
                # I'm C programmer, you know :)
                (((cmd << 1) & 0x80) ^ 0x80)
                | (toggle << 6)
                | ((addr & 0b11111) << 1)
                | ((cmd >> 6) & 1),
                (cmd & 0b11111) << 3
            ]
    return manchester.encode(values, RC5_T, 13, RC5_START, phase=False, msb_first=True)


" Sony SIRC protocol and its variations "
SIRC_LEADING_PULSE = 2400
SIRC_LEADING_GAP = 600
SIRC_GAP = 600
SIRC_PULSE_0 = 600
SIRC_PULSE_1 = 1200
# Sony SIRC frame-period (start of one frame to start of the next), microseconds.
SIRC_FRAME_PERIOD = 45000
# Default number of frames per command. Sony receivers ignore single frames;
# the spec requires a minimum of 3 to filter random IR flashes.
SIRC_DEFAULT_REP = 3
# Hard cap on rep to avoid extremely long transmissions from typos/misuse.
SIRC_MAX_REP = 16

def _sirc_build_frame(data, bit_length):
    # Encode a single SIRC frame using width modulation. width_encode returns
    # 2 + 2*bit_length elements ending with a trailing 600μs gap.
    return pulse.width_encode(
        data, SIRC_LEADING_PULSE, SIRC_LEADING_GAP, SIRC_GAP,
        SIRC_PULSE_0, SIRC_PULSE_1, bit_length,
    )

def _sirc_repeat(frame, repeats):
    # Build the multi-frame SIRC transmission. A real Sony remote merges the
    # trailing 600μs bit-gap of each frame with the inter-frame silence, so
    # frame-period (start-to-start) stays at ~45 ms regardless of payload.
    # We mimic that: drop the last 600μs gap from each frame and put a single
    # inter-frame gap = 45000 - frame_len between copies. The very last frame
    # ends on a pulse, matching the shape produced by physical Sony remotes
    # and captured by Tuya blasters.
    if repeats < 1 or repeats > SIRC_MAX_REP:
        raise ValueError(f"rep must be in range 1-{SIRC_MAX_REP}")
    if repeats == 1:
        return frame
    frame_no_tail = frame[:-1]
    frame_len = sum(frame_no_tail)
    inter_gap = max(SIRC_FRAME_PERIOD - frame_len, SIRC_GAP * 2)
    out = []
    for i in range(repeats):
        out.extend(frame_no_tail)
        if i != repeats - 1:
            out.append(inter_gap)
    return out

def _sirc_decode_with_rep(values, bit_length):
    """Decode a SIRC stream and detect how many copies of the same frame are
    present. Returns (data_bytes, rep). Tolerates the last frame missing its
    trailing 600μs gap, which is normal for raw Tuya captures."""
    # Each frame occupies 2 + 2*bit_length elements when its trailing gap is
    # present (or got merged into the inter-frame gap). The minimum we need
    # to decode at least one frame is 2 + 2*bit_length - 1 elements, since
    # the very last gap may be missing.
    full_frame_size = 2 + bit_length * 2
    min_frame_size = full_frame_size - 1

    def _decode_at(start):
        remaining = values[start:]
        if len(remaining) < min_frame_size:
            raise ValueError(f"SIRC: not enough data at offset {start}")
        # width_decode insists on at least full_frame_size elements; if the
        # frame is missing its trailing gap, append a synthetic one. Doing so
        # is safe because width_decode does not validate the very last gap.
        if len(remaining) < full_frame_size:
            remaining = list(remaining) + [SIRC_GAP]
        return pulse.width_decode(
            remaining, SIRC_LEADING_PULSE, SIRC_LEADING_GAP, SIRC_GAP,
            SIRC_PULSE_0, SIRC_PULSE_1, bit_length,
        )

    first = _decode_at(0)
    rep = 1
    pos = full_frame_size
    while pos + min_frame_size <= len(values):
        try:
            following = _decode_at(pos)
        except (ValueError, IndexError):
            break
        if following != first:
            break
        rep += 1
        pos += full_frame_size
    return first, rep

def _format_sirc_result(addr_str, cmd, rep):
    base = f"addr={addr_str},cmd=0x{cmd:02X}"
    if rep > 1:
        return f"{base},rep={rep}"
    return base

def sirc_decode(values):
    # Decode Sony SIRC (12-bit = 5-bit address + 7-bit command)
    data, rep = _sirc_decode_with_rep(values, 12)
    cmd = data[0] & 0b1111111
    addr = ((data[1] & 0b1111)) << 1 | (data[0] >> 7)
    return _format_sirc_result(f"0x{addr:02X}", cmd, rep)

def sirc_encode(addr, cmd, rep=SIRC_DEFAULT_REP):
    # Encode Sony SIRC (12-bit = 5-bit address + 7-bit command)
    if not (0x00 <= addr <= 0x1F):
        raise ValueError("Address must be in range 0x00-0x1F")
    if not (0x00 <= cmd <= 0x7F):
        raise ValueError("Command must be in range 0x00-0x7F")
    data = [(cmd & 0b1111111) | ((addr & 1) << 7), (addr >> 1) & 0b1111]
    return _sirc_repeat(_sirc_build_frame(data, 12), rep)

def sirc15_decode(values):
    # Decode Sony SIRC (15-bit = 8-bit address + 7-bit command)
    data, rep = _sirc_decode_with_rep(values, 15)
    cmd = data[0] & 0b1111111
    addr = (data[1] << 1) | (data[0] >> 7)
    return _format_sirc_result(f"0x{addr:02X}", cmd, rep)

def sirc15_encode(addr, cmd, rep=SIRC_DEFAULT_REP):
    # Encode Sony SIRC (15-bit = 8-bit address + 7-bit command)
    if not (0x00 <= addr <= 0xFF):
        raise ValueError("Address must be in range 0x00-0xFF")
    if not (0x00 <= cmd <= 0x7F):
        raise ValueError("Command must be in range 0x00-0x7F")
    data = [(cmd & 0b1111111) | ((addr & 1) << 7), (addr >> 1)]
    return _sirc_repeat(_sirc_build_frame(data, 15), rep)

def sirc20_decode(values):
    # Decode Sony SIRC (20-bit = 13-bit address + 7-bit command)
    data, rep = _sirc_decode_with_rep(values, 20)
    cmd = data[0] & 0b1111111
    addr = (data[2] << 9) | (data[1] << 1) | (data[0] >> 7)
    return _format_sirc_result(f"0x{addr:04X}", cmd, rep)

def sirc20_encode(addr, cmd, rep=SIRC_DEFAULT_REP):
    # Encode Sony SIRC (20-bit = 13-bit address + 7-bit command)
    if not (0x0000 <= addr <= 0x1FFF):
        raise ValueError("Address must be in range 0x0000-0x1FFF")
    if not (0x00 <= cmd <= 0x7F):
        raise ValueError("Command must be in range 0x00-0x7F")
    data = [(cmd & 0b1111111) | ((addr & 1) << 7), (addr >> 1) & 0xFF, (addr >> 9) & 0b1111]
    return _sirc_repeat(_sirc_build_frame(data, 20), rep)


""" Kaseikyo protocol """
"""
Kaseikyo format:
    vendor_id: 16 bits
    vendor_parity: 4 bits
    genre1: 4 bits
    genre2: 4 bits
    data: 12 bits
    id: 2 bits
    parity: 8 bits
"""

KASEIKYO_UNIT = 432
KASEIKYO_LEADING_PULSE = KASEIKYO_UNIT * 8
KASEIKYO_LEADING_GAP = KASEIKYO_UNIT * 4
KASEIKYO_PULSE = KASEIKYO_UNIT
KASEIKYO_GAP_0 = KASEIKYO_UNIT
KASEIKYO_GAP_1 = KASEIKYO_UNIT * 3

def kaseikyo_decode(values):
    # Decode Kaseikyo
    data = pulse.distance_decode(values, KASEIKYO_LEADING_PULSE, KASEIKYO_LEADING_GAP, KASEIKYO_PULSE, KASEIKYO_GAP_0, KASEIKYO_GAP_1, 48)
    vendor_id = (data[1] << 8) | data[0]
    vendor_parity = data[2] & 0x0F
    genre1 = data[2] >> 4
    genre2 = data[3] & 0x0F
    data_value = (data[3] >> 4) | ((data[4] & 0x3F) << 4)
    id_value = data[4] >> 6
    parity = data[5]

    vendor_parity_check = data[0] ^ data[1]
    vendor_parity_check = (vendor_parity_check & 0xF) ^ (vendor_parity_check >> 4)
    parity_check = data[2] ^ data[3] ^ data[4]

    if vendor_parity != vendor_parity_check or parity != parity_check:
        raise ValueError("Invalid Kaseikyo parity data")

    return f"vendor_id=0x{vendor_id:04X},genre1=0x{genre1:01X},genre2=0x{genre2:01X},data=0x{data_value:04X},id=0x{id_value:01X}"

def kaseikyo_encode(vendor_id, genre1, genre2, data, id):
    # Encode Kaseikyo
    # Kaseikyo format: vendor_id (16 bits), vendor_parity (4 bits), genre1 (4 bits), genre2 (4 bits), data (12 bits), id (2 bits), parity (8 bits)
    if not (0x0000 <= vendor_id <= 0xFFFF):
        raise ValueError("Vendor ID must be in range 0x0000-0xFFFF")
    if not (0x0 <= genre1 <= 0xF):
        raise ValueError("Genre1 must be in range 0x0-0xF")
    if not (0x0 <= genre2 <= 0xF):
        raise ValueError("Genre2 must be in range 0x0-0xF")
    if not (0x000 <= data <= 0xFFF):
        raise ValueError("Data must be in range 0x000-0xFFF")
    if not (0x0 <= id <= 0x3):
        raise ValueError("ID must be in range 0x0-0x3")
    output = [
        vendor_id & 0xFF,
        vendor_id >> 8
    ]
    vendor_parity = output[0] ^ output[1]
    vendor_parity = (vendor_parity & 0xF) ^ (vendor_parity >> 4)
    output.append((vendor_parity & 0xF) | (genre1 << 4))
    output.append((genre2 & 0xF) | ((data & 0xF) << 4))
    output.append((id << 6) | (data >> 4))
    output.append(output[2] ^ output[3] ^ output[4])
    return pulse.distance_encode(output, KASEIKYO_LEADING_PULSE, KASEIKYO_LEADING_GAP, KASEIKYO_PULSE, KASEIKYO_GAP_0, KASEIKYO_GAP_1, 48)


""" RCA protocol """
RCA_LEADING_PULSE = 4000
RCA_LEADING_GAP = 4000
RCA_PULSE = 500
RCA_GAP_0 = 1000
RCA_GAP_1 = 2000

def rca_decode(values):
    # Decode RCA
    data = pulse.distance_decode(values, RCA_LEADING_PULSE, RCA_LEADING_GAP, RCA_PULSE, RCA_GAP_0, RCA_GAP_1, 12)
    addr = data[0] & 0b1111
    cmd = (data[0] >> 4 & 0b1111) | ((data[1] & 0b1111) << 4)
    return f"addr=0x{addr:02X},cmd=0x{cmd:02X}"

def rca_encode(addr, cmd):
    # Encode RCA
    # RCA format: 4-bit address, 8-bit command
    if not (0x00 <= addr <= 0x0F):
        raise ValueError("Address must be in range 0x00-0x0F")
    if not (0x00 <= cmd <= 0xFF):
        raise ValueError("Command must be in range 0x00-0xFF")
    data = [(addr & 0b1111) | ((cmd & 0b1111) << 4), (cmd >> 4)]
    return pulse.distance_encode(data, RCA_LEADING_PULSE, RCA_LEADING_GAP, RCA_PULSE, RCA_GAP_0, RCA_GAP_1, 12)


""" Pioneer protocol """
PIONEER_LEADING_PULSE = 8500
PIONEER_LEADING_GAP = 4225
PIONEER_PULSE = 500
PIONEER_GAP_0 = 500
PIONEER_GAP_1 = 1500

def pioneer_decode(values):
    # Decode Pioneer
    data = pulse.distance_decode(values, PIONEER_LEADING_PULSE, PIONEER_LEADING_GAP, PIONEER_PULSE, PIONEER_GAP_0, PIONEER_GAP_1, 32)
    if data[0] != data[1] ^ 0xFF or data[2] != data[3] ^ 0xFF:
        raise ValueError("Invalid Pioneer xored data")
    addr = data[0]
    cmd = data[1]
    return f"addr=0x{addr:02X},cmd=0x{cmd:02X}"

def pioneer_encode(addr, cmd):
    # Encode Pioneer
    # Pioneer format: 8-bit address, 8-bit command
    if not (0x00 <= addr <= 0xFF):
        raise ValueError("Address must be in range 0x00-0xFF")
    if not (0x00 <= cmd <= 0xFF):
        raise ValueError("Command must be in range 0x00-0xFF")
    data = [addr, addr ^ 0xFF, cmd, cmd ^ 0xFF, 0]
    return pulse.distance_encode(data, PIONEER_LEADING_PULSE, PIONEER_LEADING_GAP, PIONEER_PULSE, PIONEER_GAP_0, PIONEER_GAP_1, 33)


"""
Some air conditioners use this protocol (at least Gorenie and MDV).
This signal contains 24 bits of data: 8 bits for address and 16 bits for command.
Each byte followed by its inverse. Also, usually (but not always) the whole signal is repeated twice (72 bits total).
Usually 16-bit command contains 4-bit mode, 4-bit fan speed, 4-bit temperature and some other bits.
"""
AC_LEADING_PULSE = 4500
AC_LEADING_GAP = 4500
AC_PULSE = 560
AC_GAP_0 = 560
AC_GAP_1 = 1690

def air_conditioner_decode(values):
    if len(values) < 100:
        raise ValueError("Invalid AC data: too short")
    def ac_decode_half(values):
        data = pulse.distance_decode(values, AC_LEADING_PULSE, AC_LEADING_GAP, AC_PULSE, AC_GAP_0, AC_GAP_1, 48)
        if data[0] != data[1] ^ 0xFF or data[2] != data[3] ^ 0xFF or data[4] != data[5] ^ 0xFF:
            raise ValueError("Invalid AC xored data")
        addr = data[0]
        cmd = data[2] | (data[4] << 8)
        return (addr, cmd)
    addr, cmd = ac_decode_half(values[:100])
    double = 0
    closing = NEC_GAP_0
    if len(values) >= 200:
        # closing gap is known to be either AC_LEADING_GAP or NEC_GAP_0
        if pulse.in_range(values[99], AC_LEADING_GAP):
            closing = AC_LEADING_GAP
        addr2, cmd2 = ac_decode_half(values[100:])
        if addr == addr2 and cmd == cmd2:
            double = 1
    result = f"addr=0x{addr:02X},cmd=0x{cmd:04X}"
    if double:
        result += f",double={double}"
    if closing != NEC_GAP_0:
        result += f",closing={closing}"
    return result

def air_conditioner_encode(addr, cmd, double=0, closing=NEC_GAP_0):
    if not (0x00 <= addr <= 0xFF):
        raise ValueError("Address must be in range 0x00-0xFF")
    if not (0x0000 <= cmd <= 0xFFFF):
        raise ValueError("Command must be in range 0x0000-0xFFFF")
    data = [addr, addr ^ 0xFF, cmd & 0xFF, cmd & 0xFF ^ 0xFF, cmd >> 8, cmd >> 8 ^ 0xFF]
    v = pulse.distance_encode(data, AC_LEADING_PULSE, AC_LEADING_GAP, AC_PULSE, AC_GAP_0, AC_GAP_1, 48)
    if double:
        # Need to repeat the signal twice
        if len(v) % 2 == 1:
            v.append(closing)
        v *= 2
    return v


# Midea AC protocol (48-bit, packet repeated as-is, no inter-packet inversion).
#
# This is the variant used by Midea-OEM rebranders such as EAS Electric, MDV,
# Comfee, Pioneer System, Kaysun, Trotec, Lennox, and many no-name Chinese
# splits. It differs from the IRremoteESP8266 "Midea" protocol (which sends
# the second 48-bit packet bit-inverted); here both packets are identical.
#
# Frame structure (MSB-first on the wire):
#     Byte 0: 0xB2 (state commands) or 0xB5 (special toggle commands like
#             turbo / LED) — Midea AC vendor marker.
#     Byte 1: inverse of byte 0 (0x4D for 0xB2, 0x4A for 0xB5).
#     Byte 2: payload byte A (mode + fan + power for state commands;
#             button magic for special-vendor commands).
#     Byte 3: ~A   - inverse
#     Byte 4: payload byte B (temperature + mode for state commands;
#             button magic for special-vendor commands).
#     Byte 5: ~B   - inverse
#
# Useful payload is just 16 bits (A and B). The flipper_rc API exposes both
# byte-level (`a`/`b`) and field-level (`mode`/`temp`/`fan`/`power`) forms;
# OEM-specific mappings can still vary slightly, so when a field-level
# command is rejected by an AC, fall back to the byte-level form using
# captured samples.
#
# Wire format (timings in µs):
#     Header pulse: ~4500
#     Header gap:   ~4500
#     Bit-0:        ~560 pulse + ~560 gap
#     Bit-1:        ~560 pulse + ~1690 gap
#     Inter-packet gap: ~5100 (between the two identical 48-bit packets)
#     Closing pulse: ~560
#
# References:
#     - IRremoteESP8266 ir_Midea.h / ir_Midea.cpp
#     - Midea protocol spreadsheet:
#       https://docs.google.com/spreadsheets/d/1TZh4jWrx4h9zzpYUI9aYXMl1fYOiqu-xVuOOMqagxrs
#     - The 48-bit-only variant captured on EAS Electric EADVA25NT2 splits.
MIDEA_LEADING_PULSE = 4500
MIDEA_LEADING_GAP = 4500
MIDEA_PULSE = 560
MIDEA_GAP_0 = 560
MIDEA_GAP_1 = 1690
MIDEA_INTER_GAP = 5100
MIDEA_VENDOR_MSB = 0xB2          # State commands (cool/heat/auto/dry/fan)
MIDEA_SPECIAL_VENDOR_MSB = 0xB5  # Special toggle commands (turbo, LED, ...)
MIDEA_HALF_LEN = 99      # 1 leading_pulse + 1 leading_gap + 48*2 bit ticks + 1 closing_pulse

# Magic byte values for the user-facing toggle buttons. Captured from
# an EAS Electric EADVA25NT2 remote; same values are reported to work on
# other Midea-OEM AC remotes that share the 48-bit-no-bit-inversion
# variant. Each entry is `(vendor, a, b)` in MSB convention.
#
# - swing: travels on the regular state-command vendor (0xB2). The AC
#          interprets these specific bytes as "toggle vertical swing"
#          regardless of current state.
# - turbo: special-vendor (0xB5) command. Pressing once enables turbo
#          for ~10 minutes; pressing again returns to previous state.
# - led:   special-vendor (0xB5) command. Toggles the indoor unit's
#          display panel and confirmation beep.
MIDEA_BUTTONS = {
    "swing": (MIDEA_VENDOR_MSB,         0x6B, 0xE0),
    "turbo": (MIDEA_SPECIAL_VENDOR_MSB, 0xF5, 0xA2),
    "led":   (MIDEA_SPECIAL_VENDOR_MSB, 0xF5, 0xA5),
}
# Reverse map for decoding: (vendor, a, b) → button name.
MIDEA_BUTTONS_REVERSE = {v: k for k, v in MIDEA_BUTTONS.items()}

# Field-level encoding tables, derived empirically from EAS Electric
# EADVA25NT2 captures and matched against the IRremoteESP8266 Midea
# 4-bit Gray-coded temperature table.
#
# Byte b (MSB):
#     bits 7..4 — Gray-coded temperature (17..30°C)
#     bits 3..2 — mode
#     bits 1..0 — always 0 in observed samples
#
# Byte a (MSB):
#     bits 7..5 — fan code (in cool/heat); auto-mode forces 0b000
#     bit  4    — always 1 when on
#     bit  3    — always 1
#     bit  2    — power (1 = on, 0 = off)
#     bit  1    — always 1
#     bit  0    — always 1
#
# "Power off" is sent as a fixed magic value (0x7B, 0xE0); this matches
# what the original remote emits and the AC accepts. Some commands (e.g.
# enabling Sleep mode) require an additional preamble frame (0xE0, 0x03)
# transmitted before the state frame.
MIDEA_TEMP_GRAY = {
    17: 0x0, 18: 0x1, 19: 0x3, 20: 0x2, 21: 0x6, 22: 0x7, 23: 0x5,
    24: 0x4, 25: 0xC, 26: 0xD, 27: 0x9, 28: 0x8, 29: 0xA, 30: 0xB,
}
MIDEA_TEMP_REVERSE = {v: k for k, v in MIDEA_TEMP_GRAY.items()}

MIDEA_MODE_BITS = {
    "cool": 0b00,
    "heat": 0b11,
    "auto": 0b10,
    # Both "dry" and "fan" share mode_bits=0b01 — they're disambiguated
    # by fan_bits in byte a:
    #   dry:  mode_bits=01 + fan_bits=000 (locked, AC decides)
    #   fan:  mode_bits=01 + fan_bits=any (user-selectable, like cool/heat)
    "dry":  0b01,
    "fan":  0b01,
}
# Note: MIDEA_MODE_REVERSE intentionally NOT a simple dict-reverse —
# `dry` and `fan` collide on 0b01 and need fan_bits to disambiguate.

# Modes that force the fan-bits field to 0b000 regardless of any user-
# supplied `fan` value. In these modes the remote signals "AC chooses
# fan speed" by zeroing out the fan field.
MIDEA_FAN_LOCKED_MODES = {"auto", "dry"}

# Modes that ignore temperature: the temp Gray-code field is set to a
# sentinel (0xE) that doesn't map to any value in the 17..30°C table.
MIDEA_TEMP_IGNORED_MODES = {"fan"}
MIDEA_TEMP_SENTINEL = 0xE

# Fan encoding for cool/heat/fan modes (bits 7..5 of byte a). For modes
# in MIDEA_FAN_LOCKED_MODES, the wire field is forced to 0b000 — the
# user's fan choice is ignored.
MIDEA_FAN_BITS = {
    "auto": 0b101,
    "low":  0b100,
    "med":  0b010,
    "high": 0b001,
}
MIDEA_FAN_REVERSE = {v: k for k, v in MIDEA_FAN_BITS.items()}

# Magic bytes for the "power off" command.
MIDEA_OFF_A = 0x7B
MIDEA_OFF_B = 0xE0

# Preamble for the Sleep-mode toggle. Observed prepended to a normal
# state frame whenever the user pressed the Sleep button on the remote.
MIDEA_SLEEP_PA = 0xE0
MIDEA_SLEEP_PB = 0x03

def midea_decode(values):
    """Decode a 48-bit Midea AC packet (with one repetition).

    Returns "a=0xXX,b=0xYY" on success. Raises ValueError if the signal
    does not match the Midea structure (vendor byte, inverse-pair check,
    matching repeated half).
    """
    if len(values) < MIDEA_HALF_LEN:
        raise ValueError(f"Midea: too short, need at least {MIDEA_HALF_LEN} elements")

    def decode_half(half):
        data = pulse.distance_decode(
            half,
            MIDEA_LEADING_PULSE, MIDEA_LEADING_GAP,
            MIDEA_PULSE, MIDEA_GAP_0, MIDEA_GAP_1,
            48, msb_first=True,
        )
        if data[0] != data[1] ^ 0xFF:
            raise ValueError("Midea: invalid inverse pair (B0/B1)")
        if data[2] != data[3] ^ 0xFF:
            raise ValueError("Midea: invalid inverse pair (B2/B3)")
        if data[4] != data[5] ^ 0xFF:
            raise ValueError("Midea: invalid inverse pair (B4/B5)")
        if data[0] not in (MIDEA_VENDOR_MSB, MIDEA_SPECIAL_VENDOR_MSB):
            raise ValueError(
                f"Midea: vendor byte expected 0x{MIDEA_VENDOR_MSB:02X} or "
                f"0x{MIDEA_SPECIAL_VENDOR_MSB:02X}, got 0x{data[0]:02X}"
            )
        return data[0], data[2], data[4]

    # The signal contains one or more 48-bit packets, each occupying exactly
    # MIDEA_HALF_LEN elements (1 leading_pulse + 1 leading_gap + 48*2 bit
    # ticks + 1 closing pulse), separated by ~5100µs inter-packet gaps.
    #
    # Some Midea remotes send a single payload packet repeated twice for
    # redundancy. Others (observed on EAS Electric / Comfee mode-switch
    # commands) send a "preamble" packet first, followed by the actual
    # state packet repeated twice. Total length is therefore either
    # MIDEA_HALF_LEN * N + (N-1) for N packets.
    packets = []
    pos = 0
    while pos + MIDEA_HALF_LEN <= len(values):
        try:
            packets.append(decode_half(values[pos:pos + MIDEA_HALF_LEN]))
        except ValueError:
            # A whole-packet slice failed to decode. If we already collected
            # at least one valid packet AND we're at the tail (less than a
            # full packet remaining after this one), tolerate it as a
            # truncated capture. Otherwise the signal is corrupted and we
            # should not silently return whatever we got so far.
            if not packets:
                raise
            remaining = len(values) - pos
            if remaining >= MIDEA_HALF_LEN:
                raise ValueError(
                    "Midea: malformed packet at offset "
                    f"{pos} (remaining={remaining})"
                )
            break
        # Skip the inter-packet gap (1 element) before the next packet.
        pos += MIDEA_HALF_LEN + 1

    if not packets:
        # Re-raise the original error with full context.
        decode_half(values[:MIDEA_HALF_LEN])  # raises
        raise ValueError("Midea: no valid packets")  # unreachable

    # Real captures always contain at least one repeated state packet (the
    # AC ignores single-shot transmissions). Validate that the last two
    # packets are identical — this both rejects corrupted captures and
    # disambiguates "preamble + state(x2)" from "two unrelated frames".
    last = packets[-1]
    if len(packets) >= 2 and packets[-2] != last:
        raise ValueError(
            "Midea: expected the trailing state packet to repeat, got "
            f"{packets[-2]} != {last}"
        )

    # Special-vendor (0xB5) packets are toggle-style buttons (turbo, LED,
    # etc.). They don't carry mode/temp state, so report them as `button=`.
    if last in MIDEA_BUTTONS_REVERSE:
        return f"button={MIDEA_BUTTONS_REVERSE[last]}"

    vendor, a, b = last
    if vendor == MIDEA_SPECIAL_VENDOR_MSB:
        # Special-vendor packet we don't have a name for; expose raw bytes.
        return f"button=unknown,a=0x{a:02X},b=0x{b:02X}"

    if len(packets) > 1 and packets[0] != packets[-1]:
        # There's a preamble. Expose it via a `pa`/`pb` annotation so the
        # encoder can faithfully reproduce the original two-frame sequence.
        _, pa, pb = packets[0]
        return f"a=0x{a:02X},b=0x{b:02X},pa=0x{pa:02X},pb=0x{pb:02X}"
    return f"a=0x{a:02X},b=0x{b:02X}"

def _midea_normalize_bool(value, name):
    """Coerce on/off/1/0/true/false (str/int/bool) into bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("on", "1", "true", "yes"):
            return True
        if s in ("off", "0", "false", "no"):
            return False
    raise ValueError(f"Midea: unsupported value for {name}: {value!r}")


def _midea_fields_to_bytes(mode=None, temp=None, fan=None, power=None):
    """Convert Midea (mode, temp, fan, power) into the (a, b) payload bytes.

    Defaults: mode='cool', temp=22, fan='auto', power='on'. When power=off
    the magic off command is returned regardless of other parameters.
    """
    if power is None:
        power_on = True
    else:
        power_on = _midea_normalize_bool(power, "power")

    if not power_on:
        return MIDEA_OFF_A, MIDEA_OFF_B

    if mode is None:
        mode = "cool"
    if isinstance(mode, str):
        mode_key = mode.strip().lower()
    else:
        raise ValueError(f"Midea: mode must be a string, got {mode!r}")
    if mode_key not in MIDEA_MODE_BITS:
        raise ValueError(
            f"Midea: unsupported mode {mode!r}, expected one of "
            f"{sorted(MIDEA_MODE_BITS)}"
        )
    mode_bits = MIDEA_MODE_BITS[mode_key]

    # Always validate `temp` if supplied, even in modes that ignore it on
    # the wire — silently accepting `temp=99` only to drop it would mask
    # caller bugs. The validated value is then either encoded or replaced
    # with the sentinel for fan-mode.
    if temp is not None:
        try:
            temp_int = int(temp)
        except (TypeError, ValueError):
            raise ValueError(f"Midea: temp must be an integer, got {temp!r}")
        if temp_int not in MIDEA_TEMP_GRAY:
            raise ValueError(
                f"Midea: temp {temp_int} out of supported range 17-30"
            )
    else:
        temp_int = 22  # default

    if mode_key in MIDEA_TEMP_IGNORED_MODES:
        # "fan" mode doesn't carry a real temperature — the remote sends
        # a sentinel value (0xE, outside the 17..30°C Gray code range).
        temp_gray = MIDEA_TEMP_SENTINEL
    else:
        temp_gray = MIDEA_TEMP_GRAY[temp_int]

    # Always validate `fan` if supplied, even in modes that lock it on the
    # wire (auto/dry). The validated value is then either encoded or
    # replaced with 0b000 (AC-controlled).
    if fan is not None:
        if not isinstance(fan, str):
            raise ValueError(f"Midea: fan must be a string, got {fan!r}")
        fan_key = fan.strip().lower()
        if fan_key not in MIDEA_FAN_BITS:
            raise ValueError(
                f"Midea: unsupported fan {fan!r}, expected one of "
                f"{sorted(MIDEA_FAN_BITS)}"
            )
    else:
        fan_key = "auto"  # default

    if mode_key in MIDEA_FAN_LOCKED_MODES:
        # auto / dry: AC decides fan speed; the wire field is forced to 0b000.
        fan_bits = 0b000
    else:
        fan_bits = MIDEA_FAN_BITS[fan_key]

    # Bits 4,3,1,0 of `a` are always 1 in observed samples; bit 2 is power.
    # Result: lower 5 bits = 0b11111 = 0x1F when on.
    a = (fan_bits << 5) | 0x1F
    # Bits 1,0 of `b` are always 0 in observed samples; bits 3,2 = mode.
    b = (temp_gray << 4) | (mode_bits << 2)
    return a, b


def midea_bytes_to_fields(a, b):
    """Decode (a, b) bytes into a dict of (mode, temp, fan, power) fields.

    Returns a dict of recognized fields plus, for unrecognized bit
    patterns, an `unknown` list with the offending field names. Useful
    for diagnostics: the 'a/b' interface is the source of truth, this
    helper just gives you semantic context.
    """
    if a == MIDEA_OFF_A and b == MIDEA_OFF_B:
        return {"power": False}

    fields = {"power": bool((a >> 2) & 1)}
    unknown = []

    mode_bits = (b >> 2) & 0b11
    fan_bits = (a >> 5) & 0b111
    temp_gray = (b >> 4) & 0xF

    # Mode disambiguation: bits 3..2 of b carry 4 distinct main modes,
    # but 0b01 is shared between dry and fan — fan_bits in `a` resolves
    # the ambiguity (dry forces fan to 000, fan-mode allows any value).
    if mode_bits == 0b00:
        fields["mode"] = "cool"
    elif mode_bits == 0b10:
        fields["mode"] = "auto"
    elif mode_bits == 0b11:
        fields["mode"] = "heat"
    elif mode_bits == 0b01:
        fields["mode"] = "dry" if fan_bits == 0b000 else "fan"
    else:
        unknown.append(f"mode_bits=0b{mode_bits:02b}")

    if fields.get("mode") in MIDEA_TEMP_IGNORED_MODES:
        # "fan" mode reports temp_gray=0xE (sentinel); skip temp.
        pass
    elif temp_gray in MIDEA_TEMP_REVERSE:
        fields["temp"] = MIDEA_TEMP_REVERSE[temp_gray]
    else:
        unknown.append(f"temp_gray=0x{temp_gray:X}")

    if fields.get("mode") in MIDEA_FAN_LOCKED_MODES:
        fields["fan"] = "auto"  # AC-controlled
    elif fan_bits in MIDEA_FAN_REVERSE:
        fields["fan"] = MIDEA_FAN_REVERSE[fan_bits]
    else:
        unknown.append(f"fan_bits=0b{fan_bits:03b}")

    if unknown:
        fields["unknown"] = unknown
    return fields


def _midea_pack(a, b, vendor=MIDEA_VENDOR_MSB):
    """Pack a 48-bit Midea packet for payload bytes (a, b) in MSB convention.

    `vendor` selects the leading vendor/Type byte: MIDEA_VENDOR_MSB (0xB2)
    for state commands (the default), MIDEA_SPECIAL_VENDOR_MSB (0xB5) for
    special toggle commands like Turbo / LED.
    """
    bytes_msb = [
        vendor, vendor ^ 0xFF,
        a & 0xFF, (a ^ 0xFF) & 0xFF,
        b & 0xFF, (b ^ 0xFF) & 0xFF,
    ]
    return pulse.distance_encode(
        bytes_msb,
        MIDEA_LEADING_PULSE, MIDEA_LEADING_GAP,
        MIDEA_PULSE, MIDEA_GAP_0, MIDEA_GAP_1,
        48, msb_first=True,
    )

def midea_encode(a=None, b=None, pa=None, pb=None,
                 mode=None, temp=None, fan=None, power=None, sleep=None,
                 button=None):
    """Encode a Midea AC command.

    Three mutually-exclusive parameter forms:
        Byte-level:   pass `a` and `b` (raw payload bytes).
        Field-level:  pass `mode` ("cool"/"heat"/"auto"/"dry"/"fan"),
                      `temp` (17-30), `fan` ("auto"/"low"/"med"/"high"),
                      and `power` ("on"/"off"). Sensible defaults apply.
        Button-level: pass `button` ("swing"/"turbo"/"led") for one of
                      the toggle/special commands. The vendor byte and
                      payload are looked up from `MIDEA_BUTTONS`.

    Optional (only valid with byte- and field-level forms):
        pa/pb: explicit preamble bytes (sent BEFORE the state frame).
        sleep: shorthand — when truthy, prepends the standard sleep
               preamble (0xE0, 0x03). Mutually exclusive with pa/pb.
    """
    field_form = any(v is not None for v in (mode, temp, fan, power))
    byte_form = a is not None or b is not None
    button_form = button is not None
    forms_used = [field_form, byte_form, button_form]
    if sum(forms_used) > 1:
        raise ValueError(
            "Midea: choose only one of (a,b), (mode,...) or button=..."
        )

    if button_form:
        if pa is not None or pb is not None or sleep is not None:
            raise ValueError(
                "Midea: button commands do not support pa/pb/sleep"
            )
        if isinstance(button, str):
            button_key = button.strip().lower()
        else:
            raise ValueError(f"Midea: button must be a string, got {button!r}")
        if button_key not in MIDEA_BUTTONS:
            raise ValueError(
                f"Midea: unknown button {button!r}, expected one of "
                f"{sorted(MIDEA_BUTTONS)}"
            )
        vendor, btn_a, btn_b = MIDEA_BUTTONS[button_key]
        packet = _midea_pack(btn_a, btn_b, vendor=vendor)
        return packet + [MIDEA_INTER_GAP] + packet

    if field_form:
        a, b = _midea_fields_to_bytes(
            mode=mode, temp=temp, fan=fan, power=power
        )
    elif a is None or b is None:
        raise ValueError(
            "Midea: must provide either (a,b), field-level params, or button=..."
        )

    if not (0x00 <= a <= 0xFF):
        raise ValueError("Midea: 'a' must be in range 0x00-0xFF")
    if not (0x00 <= b <= 0xFF):
        raise ValueError("Midea: 'b' must be in range 0x00-0xFF")
    if (pa is None) != (pb is None):
        raise ValueError("Midea: 'pa' and 'pb' must be provided together")

    if sleep is not None:
        if _midea_normalize_bool(sleep, "sleep"):
            if pa is not None or pb is not None:
                raise ValueError(
                    "Midea: cannot use both `sleep=on` and explicit pa/pb"
                )
            pa, pb = MIDEA_SLEEP_PA, MIDEA_SLEEP_PB

    cmd_packet = _midea_pack(a, b)

    if pa is not None:
        if not (0x00 <= pa <= 0xFF):
            raise ValueError("Midea: 'pa' must be in range 0x00-0xFF")
        if not (0x00 <= pb <= 0xFF):
            raise ValueError("Midea: 'pb' must be in range 0x00-0xFF")
        preamble = _midea_pack(pa, pb)
        # Sequence: preamble + gap + command + gap + command (matches the
        # 299-element multi-frame structure observed in real captures).
        return (
            preamble + [MIDEA_INTER_GAP]
            + cmd_packet + [MIDEA_INTER_GAP]
            + cmd_packet
        )

    # Single-frame command repeated twice for redundancy (199 elements).
    return cmd_packet + [MIDEA_INTER_GAP] + cmd_packet


# Dictionary of supported RC converters
RC_CONVERTERS = {
    "nec42": (nec42_encode, nec42_decode),
    "nec": (nec_encode, nec_decode),
    "nec42-ext": (nec42_ext_encode, nec42_ext_decode),
    "nec-ext": (nec_ext_encode, nec_ext_decode),
    "rc5": (rc5_encode, rc5_decode),
    "rc6": (rc6_encode, rc6_decode),
    "samsung32": (samsung32_encode, samsung32_decode),
    "sirc20": (sirc20_encode, sirc20_decode),
    "sirc15": (sirc15_encode, sirc15_decode),
    "sirc": (sirc_encode, sirc_decode),
    "kaseikyo": (kaseikyo_encode, kaseikyo_decode),
    "rca": (rca_encode, rca_decode),
    "pioneer": (pioneer_encode, pioneer_decode),
    "midea": (midea_encode, midea_decode),
    "ac": (air_conditioner_encode, air_conditioner_decode),
}

def rc_auto_decode(values, force_raw=False):
    """
    Attempt to decode a list of pulse and gap durations using various decoders.

    This function iterates through a collection of decoders defined in RC_CONVERTERS.
    It tries to decode the provided values using each decoder until one succeeds.
    If a decoder successfully decodes the values, it returns a string in the format
    "decoder_name:decoded_value". If none of the decoders succeed, it returns the raw
    data as a comma-separated string prefixed with "raw:".

    Args:
        values (list of int): A list of integers representing the pulse and gap durations.

    Returns:
        str: The decoded value prefixed with the decoder name, or the raw data if decoding fails.
    """
    # Try every decoder
    if not force_raw:
        for name, (_, decoder) in RC_CONVERTERS.items():
            try:
                return f"{name}:{decoder(values)}"
            except ValueError:
                pass
    # Return raw data otherwise
    if len(values) % 2 == 0:
        # Must be odd
        values = values[:-1]
    return "raw:" + ",".join(str(int(v)) for v in values)

def rc_auto_encode(s):
    """
    Encodes a string command into a list of pulse and gap durations based on the specified format.

    The input string `s` should be in the format "fmt:data", where `fmt` is the format
    identifier and `data` is the data to be encoded. The function supports the following formats:
    - "raw": The data is a comma-separated list of values to be converted to integers.
    - Other formats: The data is a comma-separated list of key=value pairs, where the values
      are converted to integers and passed to the corresponding encoder function.

    Args:
        s (str): The input string command to be encoded.

    Returns:
        list: A list of integers representing the pulse and gap durations.

    Raises:
        ValueError: If the input string is not in the correct format, or if the format identifier
                    is unknown.
    """
    def _coerce(v):
        # Try int first (handles 0xAB, 0b101, 42); fall back to the raw
        # string so encoders that accept named parameters (e.g. midea
        # mode="cool") receive them unchanged.
        try:
            return int(v, 0)
        except (ValueError, TypeError):
            return v

    try:
        fmt, data = s.split(":", 1)
        if fmt == "raw":
            return [int(v, 0) for v in data.split(",")]
        if fmt == "tuya":
            return data  # raw base64 Tuya-format
        # Each k=v pair must contain exactly one '='; split(...) returns a
        # list of length 1 or >2 otherwise, which dict() then rejects with
        # ValueError. We catch ValueError specifically (parse failure) so
        # that genuine bugs in encoders surface with their original trace.
        data = dict(v.split("=") for v in data.split(","))
        data = {k: _coerce(v) for k, v in data.items()}
    except ValueError as exc:
        raise ValueError(f"Invalid command format: {s}") from exc
    if fmt not in RC_CONVERTERS:
        raise ValueError(f"Unknown format: {fmt}")
    encoder, _ = RC_CONVERTERS[fmt]
    data = encoder(**data)
    # Convert to ints
    data = [int(v) for v in data]
    return data
