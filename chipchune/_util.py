import struct
from enum import Enum
from typing import BinaryIO, Any, cast
import io

known_sizes = {
    'c': 1,
    'b': 1, 'B': 1,
    '?': 1,
    'h': 2, 'H': 2,
    'i': 4, 'I': 4,
    'l': 4, 'L': 4,
    'q': 8, 'Q': 8,
    'e': 2, 'f': 4,
    'd': 8
}


class EnumShowNameOnly(Enum):
    """
    Just an Enum, except its string repr is
    just the enum's name
    """
    def __repr__(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.__repr__()


class EnumValueEquals(Enum):
    """
    Enum that can be compared to its raw value.
    """
    def __eq__(self, other: Any) -> bool:
        return cast(bool, self.value == other)


def truthy_to_boolbyte(value: Any) -> bytes:
    """
    If value is truthy, output b'\x01'. Else output b'\x00'.

    :param value: anything
    """
    if value:
        return b'\x01'
    else:
        return b'\x00'


# these are just to make the typehinter happy
# cast(dolphin, foobar) should've been named trust_me_bro_im_a(dolphin, foobar)


def read_int(file: BinaryIO, signed: bool = False) -> int:
    """
    4 bytes
    """
    if signed:
        return cast(int, struct.unpack('<i', file.read(known_sizes['i']))[0])
    return cast(int, struct.unpack('<I', file.read(known_sizes['I']))[0])


def read_short(file: BinaryIO, signed: bool = False) -> int:
    """
    2 bytes
    """
    if signed:
        return cast(int, struct.unpack('<h', file.read(known_sizes['h']))[0])
    return cast(int, struct.unpack('<H', file.read(known_sizes['H']))[0])


def read_byte(file: BinaryIO, signed: bool = False) -> int:
    """
   1 bytes
    """
    if signed:
        return cast(int, struct.unpack('<b', file.read(known_sizes['b']))[0])
    return cast(int, struct.unpack('<B', file.read(known_sizes['B']))[0])


def read_float(file: BinaryIO) -> float:
    """
    4 bytes
    """
    return cast(float, struct.unpack('<f', file.read(known_sizes['f']))[0])


def read_str(file: BinaryIO) -> str:
    """
    variable string (ends in \\x00)
    """
    buffer = bytearray()
    char = file.read(1)
    while char != b'\x00':
        buffer += char
        char = file.read(1)
    return buffer.decode('utf-8')
