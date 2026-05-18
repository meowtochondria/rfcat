def bit_read(value: int, bit: int) -> int:
    return (value >> bit) & 1


def bit_set(value: int, bit: int) -> int:
    return value | (1 << bit)


def bit_clear(value: int, bit: int) -> int:
    return value & ~(1 << bit)


def bit_write(value: int, bit: int, bitvalue: int) -> int:
    if bitvalue:
        return bit_set(value, bit)
    return bit_clear(value, bit)


def duration_diff(x: int, y: int) -> int:
    return abs(x - y)


def reverse_key(key: int, bit_count: int) -> int:
    result = 0
    for i in range(bit_count):
        result = (result << 1) | bit_read(key, i)
    return result


def get_parity(key: int, bit_count: int) -> int:
    return sum(bit_read(key, i) for i in range(bit_count)) & 1


def parity8(byte: int) -> int:
    byte ^= byte >> 4
    return (0x6996 >> (byte & 0xf)) & 1


def add_bytes(data: bytes) -> int:
    return sum(data) & 0xff


def xor_bytes(data: bytes) -> int:
    result = 0
    for byte in data:
        result ^= byte
    return result


def crc8(data: bytes, polynomial: int, init: int = 0) -> int:
    remainder = init
    for byte in data:
        remainder ^= byte
        for _ in range(8):
            if remainder & 0x80:
                remainder = (remainder << 1) ^ polynomial
            else:
                remainder = remainder << 1
    return remainder & 0xFF


def crc8le(data: bytes, polynomial: int, init: int = 0) -> int:
    remainder = reverse_key(init, 8)
    polynomial = reverse_key(polynomial, 8)
    for byte in data:
        remainder ^= byte
        for _ in range(8):
            if remainder & 1:
                remainder = (remainder >> 1) ^ polynomial
            else:
                remainder = remainder >> 1
    return remainder & 0xFF


def crc16(data: bytes, polynomial: int, init: int = 0) -> int:
    remainder = init
    for byte in data:
        remainder ^= byte << 8
        for _ in range(8):
            if remainder & 0x8000:
                remainder = (remainder << 1) ^ polynomial
            else:
                remainder = remainder << 1
    return remainder & 0xFFFF


def crc16lsb(data: bytes, polynomial: int, init: int = 0) -> int:
    remainder = init
    for byte in data:
        remainder ^= byte
        for _ in range(8):
            if remainder & 1:
                remainder = (remainder >> 1) ^ polynomial
            else:
                remainder = remainder >> 1
    return remainder & 0xFFFF


def lfsr_digest8(data: bytes, gen: int, key: int) -> int:
    result = 0
    for byte in data:
        for i in range(7, -1, -1):
            if (byte >> i) & 1:
                result ^= key
            if key & 1:
                key = (key >> 1) ^ gen
            else:
                key = key >> 1
    return result & 0xFF


def lfsr_digest8_reflect(data: bytes, gen: int, key: int) -> int:
    result = 0
    for byte in data:
        for i in range(8):
            if (byte >> i) & 1:
                result ^= key
            if key & 1:
                key = (key >> 1) ^ gen
            else:
                key = key >> 1
    return result & 0xFF


def lfsr_digest16(data: bytes, gen: int, key: int) -> int:
    result = 0
    for byte in data:
        for i in range(7, -1, -1):
            if (byte >> i) & 1:
                result ^= key
            if key & 1:
                key = (key >> 1) ^ gen
            else:
                key = key >> 1
    return result & 0xFFFF


def crc4(data: bytes, polynomial: int, init: int = 0) -> int:
    remainder = init
    for byte in data:
        remainder ^= byte
        for _ in range(8):
            if remainder & 0x80:
                remainder = (remainder << 1) ^ polynomial
            else:
                remainder = remainder << 1
    return (remainder >> 4) & 0x0F


def crc7(data: bytes, polynomial: int, init: int = 0) -> int:
    remainder = init
    for byte in data:
        remainder ^= byte
        for _ in range(8):
            if remainder & 0x80:
                remainder = (remainder << 1) ^ polynomial
            else:
                remainder = remainder << 1
    return (remainder >> 1) & 0x7F


def get_hash_data(decode_data: int, decode_count_bit: int) -> int:
    byte_count = (decode_count_bit // 8) + 1
    data_bytes = decode_data.to_bytes(byte_count if byte_count > 0 else 1, 'little')
    return sum(data_bytes) ^ data_bytes[0] if data_bytes else 0


def add_bit(decoder, bit: int):
    decoder.decode_data = (decoder.decode_data << 1) | bit
    decoder.decode_count_bit += 1