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

def sirc_decode(values):
    # Decode Sony SIRC (12-bit = 5-bit address + 7-bit command)
    data = pulse.width_decode(values, SIRC_LEADING_PULSE, SIRC_LEADING_GAP, SIRC_GAP, SIRC_PULSE_0, SIRC_PULSE_1, 12)
    cmd = data[0] & 0b1111111
    addr = ((data[1] & 0b1111)) << 1 | (data[0] >> 7)
    return f"addr=0x{addr:02X},cmd=0x{cmd:02X}"

def sirc_encode(addr, cmd):
    # Encode Sony SIRC (12-bit = 5-bit address + 7-bit command)
    if not (0x00 <= addr <= 0x1F):
        raise ValueError("Address must be in range 0x00-0x1F")
    if not (0x00 <= cmd <= 0x7F):
        raise ValueError("Command must be in range 0x00-0x7F")
    data = [(cmd & 0b1111111) | ((addr & 1) << 7), (addr >> 1) & 0b1111]
    return pulse.width_encode(data, SIRC_LEADING_PULSE, SIRC_LEADING_GAP, SIRC_GAP, SIRC_PULSE_0, SIRC_PULSE_1, 12)

def sirc15_decode(values):
    # Decode Sony SIRC (15-bit = 8-bit address + 7-bit command)
    data = pulse.width_decode(values, SIRC_LEADING_PULSE, SIRC_LEADING_GAP, SIRC_GAP, SIRC_PULSE_0, SIRC_PULSE_1, 15)
    cmd = data[0] & 0b1111111
    addr = (data[1] << 1) | (data[0] >> 7)
    return f"addr=0x{addr:02X},cmd=0x{cmd:02X}"

def sirc15_encode(addr, cmd):
    # Encode Sony SIRC (15-bit = 8-bit address + 7-bit command)
    if not (0x00 <= addr <= 0xFF):
        raise ValueError("Address must be in range 0x00-0xFF")
    if not (0x00 <= cmd <= 0x7F):
        raise ValueError("Command must be in range 0x00-0x7F")
    data = [(cmd & 0b1111111) | ((addr & 1) << 7), (addr >> 1)]
    return pulse.width_encode(data, SIRC_LEADING_PULSE, SIRC_LEADING_GAP, SIRC_GAP, SIRC_PULSE_0, SIRC_PULSE_1, 15)

def sirc20_decode(values):
    # Decode Sony SIRC (20-bit = 13-bit address + 7-bit command)
    data = pulse.width_decode(values, SIRC_LEADING_PULSE, SIRC_LEADING_GAP, SIRC_GAP, SIRC_PULSE_0, SIRC_PULSE_1, 20)
    cmd = data[0] & 0b1111111
    addr = (data[2] << 9) | (data[1] << 1) | (data[0] >> 7)
    return f"addr=0x{addr:04X},cmd=0x{cmd:02X}"

def sirc20_encode(addr, cmd):
    # Encode Sony SIRC (20-bit = 13-bit address + 7-bit command)
    if not (0x0000 <= addr <= 0x1FFF):
        raise ValueError("Address must be in range 0x0000-0x1FFF")
    if not (0x00 <= cmd <= 0x7F):
        raise ValueError("Command must be in range 0x00-0x7F")
    data = [(cmd & 0b1111111) | ((addr & 1) << 7), (addr >> 1) & 0xFF, (addr >> 9) & 0b1111]
    return pulse.width_encode(data, SIRC_LEADING_PULSE, SIRC_LEADING_GAP, SIRC_GAP, SIRC_PULSE_0, SIRC_PULSE_1, 20)


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
    if len(values) >= 200:
        addr2, cmd2 = ac_decode_half(values[100:])
        if addr == addr2 and cmd == cmd2:
            double = 1
    return f"addr=0x{addr:02X},cmd=0x{cmd:04X},double={double}"

def air_conditioner_encode(addr, cmd, double=0):
    if not (0x00 <= addr <= 0xFF):
        raise ValueError("Address must be in range 0x00-0xFF")
    if not (0x0000 <= cmd <= 0xFFFF):
        raise ValueError("Command must be in range 0x0000-0xFFFF")
    data = [addr, addr ^ 0xFF, cmd & 0xFF, cmd & 0xFF ^ 0xFF, cmd >> 8, cmd >> 8 ^ 0xFF]
    v = pulse.distance_encode(data, AC_LEADING_PULSE, AC_LEADING_GAP, AC_PULSE, AC_GAP_0, AC_GAP_1, 48)
    if double:
        # Need to repeat the signal twice
        if len(v) % 2 == 1:
            v.append(NEC_GAP_0)
        v *= 2
    return v


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
    "ac": (air_conditioner_encode, air_conditioner_decode),
}

def rc_auto_decode(values):
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
    try:
        fmt, data = s.split(":", 1)
        if fmt == "raw":
            return [int(v, 0) for v in data.split(",")]
        data = dict(v.split("=") for v in data.split(","))
        data = {k: int(v, 0) for k, v in data.items()}
    except:
        raise ValueError(f"Invalid command format: {s}")
    if fmt not in RC_CONVERTERS:
        raise ValueError(f"Unknown format: {fmt}")
    encoder, _ = RC_CONVERTERS[fmt]
    data = encoder(**data)
    # Convert to ints
    data = [int(v) for v in data]
    return data
