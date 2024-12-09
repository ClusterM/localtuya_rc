def decode(values, T, bit_length, start_sequence, phase, double_bits=[], msb_first=True):
    """
    Decodes a list of values into a sequence of bytes using Manchester encoding.
    Args:
        values (list of int): The list of values to decode.
        T (float): The time period for one bit.
        bit_length (int): The expected length of the decoded bit sequence.
        start_sequence (list of bool): The expected start sequence to validate the input.
        phase (bool): If True, the phase of the bits will be inverted.
        double_bits (list of int, optional): Indices of bits that are doubled and need to be checked. Defaults to [].
        msb_first (bool, optional): If True, the most significant bit is processed first. Defaults to True.
    Returns:
        list of int: The decoded byte sequence.
    Raises:
        ValueError: If the start sequence is invalid.
        ValueError: If a double bit is invalid.
        ValueError: If the data length is invalid.
        ValueError: If an invalid bit sequence is encountered.
    """
    bits = []
    for i in range(len(values)):
        n = round(values[i] / T)
        bits = bits + [True] * n if i % 2 == 0 else bits + [False] * n

    # Check and remove start sequence
    if bits[:len(start_sequence)] != start_sequence:
        raise ValueError("Invalid start sequence")
    bits = bits[len(start_sequence):]

    # Check and remove double bits
    for i in sorted(double_bits, reverse=True):
        if bits[i * 2] != bits[i * 2 + 1] or bits[i * 2 + 2] != bits[i * 2 + 3]:
            raise ValueError("Invalid double bit")
        bits = bits[:i * 2 + 1] + bits[i * 2 + 3:]

    if len(bits) % 2 == 1:
        bits += [False]

    if len(bits) < bit_length * 2:
        raise ValueError(f"Invalid data length: {len(bits)} (must be at least {bit_length * 2})")
    
    if phase:
        bits = [not bits[i] for i in range(len(bits))]

    decoded = 0
    data = []
    # Decode bits in chunks of 8
    while decoded < bit_length:
        i = 0
        for bit in range(8):
            if not bits[decoded * 2] and bits[decoded * 2 + 1]:
                i |= 1 << (7 - bit) if msb_first else 1 << bit
            elif bits[decoded * 2] and not bits[decoded * 2 + 1]:
                pass
            else:
                raise ValueError("Invalid bit sequence")
            decoded += 1
            if decoded == bit_length:
                break
        data.append(i)
    return data

def encode(values, T, bit_length, start_sequence, phase, double_bits=[], msb_first=True):
    """
    Encode a sequence of values into a series of pulses.

    Parameters:
    values (list of int): The values to encode.
    T (int): The base time unit for the pulses.
    bit_length (int): The maximum number of bits to encode. If None, encode all bits.
    start_sequence (list of bool): The initial sequence of bits to start with.
    phase (bool): The phase of the encoding. If True, use one phase, otherwise use the opposite phase.
    double_bits (list of int, optional): Indices of bits that should be doubled in the output.
    msb_first (bool, optional): If True, encode the most significant bit first. Defaults to True.

    Returns:
    list of int: The encoded sequence of pulses.

    Raises:
    ValueError: If bit_length is greater than the number of bits in values.
    """
    if bit_length is not None and bit_length > len(values) * 8:
        raise ValueError(f"bit_length {bit_length} is greater than the number of bits in values")
    bits = start_sequence[:]
    total = 0
    for i in values:
        for bit in range(8):
            if i & (1 << (7 - bit) if msb_first else 1 << bit):
                bits += [True, False] if phase else [False, True]
            else:
                bits += [False, True] if phase else [True, False]
            if total in double_bits:
                bits = bits[:-1] + [bits[-2], bits[-1], bits[-1]]
            total += 1
            if bit_length is not None and total >= bit_length:
                break

    last_v = False
    pulses = []
    for v in bits:
        if len(pulses) > 0 and v == last_v:
            pulses[-1] += T
        else:
            pulses.append(T)
            last_v = v

    if len(pulses) % 2 == 0:
        pulses = pulses[:-1]
    return pulses