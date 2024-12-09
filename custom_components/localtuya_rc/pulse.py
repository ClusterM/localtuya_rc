MAX_ERROR_PERCENT = 25

def in_range(value, target):
    """
    Checks if a given value is within a certain percentage range of a target value.

    Args:
        value (float): The value to check.
        target (float): The target value to compare against.

    Returns:
        bool: True if the value is within the specified range of the target, False otherwise.
    """
    # Checks if value is within MAX_ERROR_PERCENT% of target
    max_error = MAX_ERROR_PERCENT / 100
    return target * (1 - max_error) <= value <= target * (1 + max_error)

def distance_decode(pulses, leading_pulse, leading_gap, pulse, gap_0, gap_1, bit_length, msb_first=False):
    """
    Decode a sequence of pulses into bits based on provided timings and bit length.

    Args:
        pulses (list of int): The list of pulse lengths to decode.
        leading_pulse (int): The expected length of the leading pulse.
        leading_gap (int): The expected length of the leading gap.
        pulse (int): The expected length of the pulse.
        gap_0 (int): The expected length of the gap representing a '0' bit.
        gap_1 (int): The expected length of the gap representing a '1' bit.
        bit_length (int): The number of bits to decode.
        msb_first (bool, optional): If True, decode bits with the most significant bit first. Defaults to False.

    Returns:
        list of int: The decoded data as a list of bytes.

    Raises:
        ValueError: If the pulse sequence does not match the expected format.
    """
    # Decode pulses into bits based on provided timings and bit_length
    if not in_range(pulses[0], leading_pulse):
        raise ValueError(f"Invalid leading pulse length: {pulses[0]}")
    if not in_range(pulses[1], leading_gap):
        raise ValueError(f"Invalid leading gap length: {pulses[1]}")
    if len(pulses) < 3 + bit_length * 2:
        raise ValueError(f"Invalid data length: {len(pulses)} (must be at least {3 + bit_length * 2})")

    long_pulse_v = True if gap_1 > gap_0 else False
    short_pulse_v = not long_pulse_v
    decoded = 0
    data = []
    # Decode bits in chunks of 8
    while decoded < bit_length:
        i = 0
        for bit in range(8):
            p = 3 + decoded * 2
            if not in_range(pulses[p - 1], pulse):
                raise ValueError(f"Invalid pulse length: {pulses[p - 1]}")
            v = pulses[p]
            if not in_range(v, gap_0) and not in_range(v, gap_1):
                raise ValueError(f"Invalid gap length: {v}")
            v = long_pulse_v if v > (gap_0 + gap_1) / 2 else short_pulse_v
            if msb_first:
                i |= (1 if v else 0) << (7 - bit) # MSB
            else:
                i |= (1 if v else 0) << bit # LSB
            decoded += 1
            if decoded == bit_length:
                break
        data.append(i)
    return data

def width_decode(pulses, leading_pulse, leading_gap, gap, pulse_0, pulse_1, bit_length, msb_first=False):
    """
    Decode a sequence of pulses into a list of bytes based on provided timings and bit length.
    Args:
        pulses (list of int): The list of pulse lengths to decode.
        leading_pulse (int): The expected length of the leading pulse.
        leading_gap (int): The expected length of the leading gap.
        gap (int): The expected length of the gap between pulses.
        pulse_0 (int): The expected length of a pulse representing a '0' bit.
        pulse_1 (int): The expected length of a pulse representing a '1' bit.
        bit_length (int): The total number of bits to decode.
        msb_first (bool, optional): If True, decode bits with the most significant bit first. Defaults to False.
    Returns:
        list of int: The decoded data as a list of bytes.
    Raises:
        ValueError: If the pulse lengths do not match the expected values or if the data length is invalid.
    """
    # Decode gaps into bits based on provided timings and bit_length
    if not in_range(pulses[0], leading_pulse):
        raise ValueError(f"Invalid leading pulse length: {pulses[0]}")
    if not in_range(pulses[1], leading_gap):
        raise ValueError(f"Invalid leading gap length: {pulses[1]}")
    if len(pulses) < 2 + bit_length * 2:
        raise ValueError(f"Invalid data length: {len(pulses)} (must be at least {2 + bit_length * 2})")
    
    long_pulse_v = True if pulse_1 > pulse_0 else False
    short_pulse_v = not long_pulse_v
    decoded = 0
    data = []
    # Decode bits in chunks of 8
    while decoded < bit_length:
        i = 0
        for bit in range(8):
            p = 2 + decoded * 2
            v = pulses[p]
            if not in_range(v, pulse_0) and not in_range(v, pulse_1):
                raise ValueError(f"Invalid pulse length: {v}")
            v = long_pulse_v if v > (pulse_0 + pulse_1) / 2 else short_pulse_v
            if msb_first:
                i |= (1 if v else 0) << (7 - bit) # MSB
            else:
                i |= (1 if v else 0) << bit # LSB
            decoded += 1
            if decoded == bit_length:
                break
            if not in_range(pulses[p + 1], gap):
                raise ValueError(f"Invalid gap length: {pulses[p + 1]}")
        data.append(i)
    return data

def distance_encode(values, leading_pulse, leading_gap, pulse, gap_0, gap_1, bit_length=None, msb_first=False):
    """
    Encode a list of bytes into pulses/gaps based on given timings.

    Args:
        values (list of int): List of byte values to encode.
        leading_pulse (int): Duration of the leading pulse.
        leading_gap (int): Duration of the gap following the leading pulse.
        pulse (int): Duration of each pulse.
        gap_0 (int): Duration of the gap representing a '0' bit.
        gap_1 (int): Duration of the gap representing a '1' bit.
        bit_length (int, optional): Total number of bits to encode. If None, encode all bits in `values`. Defaults to None.
        msb_first (bool, optional): If True, encode the most significant bit first. If False, encode the least significant bit first. Defaults to False.

    Returns:
        list of int: List of pulse and gap durations representing the encoded values.

    Raises:
        ValueError: If `bit_length` is greater than the number of bits in `values`.
    """
    # Encode a list of bytes into pulses/gaps based on given timings
    if bit_length is not None and bit_length > len(values) * 8:
        raise ValueError(f"bit_length {bit_length} is greater than the number of bits in values")
    pulses = []
    pulses.append(leading_pulse)
    pulses.append(leading_gap)
    total = 0
    for i in values:
        for bit in range(8):
            pulses.append(pulse)
            if msb_first:
                pulses.append(gap_1 if (i & (1 << (7 - bit))) > 0 else gap_0)
            else:
                pulses.append(gap_1 if (i & (1 << bit)) > 0 else gap_0)
            total += 1
            if bit_length is not None and total >= bit_length:
                break
        if bit_length is not None and total >= bit_length:
            break
    pulses.append(pulse)
    return pulses

def width_encode(values, leading_pulse, leading_gap, gap, pulse_0, pulse_1, bit_length=None, msb_first=False):
    """
    Encode a list of bytes into pulses and gaps based on given timings.

    Args:
        values (list of int): List of byte values to encode.
        leading_pulse (int): Duration of the leading pulse.
        leading_gap (int): Duration of the gap following the leading pulse.
        gap (int): Duration of the gap between pulses.
        pulse_0 (int): Duration of the pulse representing a '0' bit.
        pulse_1 (int): Duration of the pulse representing a '1' bit.
        bit_length (int, optional): Total number of bits to encode. If None, encode all bits in `values`. Defaults to None.
        msb_first (bool, optional): If True, encode the most significant bit first. If False, encode the least significant bit first. Defaults to False.

    Returns:
        list of int: List of pulse and gap durations representing the encoded values.

    Raises:
        ValueError: If `bit_length` is greater than the number of bits in `values`.
    """
    # Encode a list of bytes into pulses/gaps based on given timings
    if bit_length is not None and bit_length > len(values) * 8:
        raise ValueError(f"bit_length {bit_length} is greater than the number of bits in values")
    pulses = []
    pulses.append(leading_pulse)
    pulses.append(leading_gap)
    total = 0
    for i in values:
        for bit in range(8):
            if msb_first:
                pulses.append(pulse_1 if (i & (1 << (7 - bit))) > 0 else pulse_0)
            else:
                pulses.append(pulse_1 if (i & (1 << bit)) > 0 else pulse_0)
            pulses.append(gap)
            total += 1
            if bit_length is not None and total >= bit_length:
                break
        if bit_length is not None and total >= bit_length:
            break
    return pulses

