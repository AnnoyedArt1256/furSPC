from io import BytesIO
from typing import Optional, Union, BinaryIO, List

from chipchune._util import read_short, read_int, read_str
from .data_types import SampleMeta
from .enums import _FurSampleType

FILE_MAGIC_STR = b'SMP2'


class FurnaceSample:
    def __init__(self) -> None:
        self.meta: SampleMeta = SampleMeta()
        """
        Sample metadata.
        """
        self.data: bytearray = b''
        """
        Sample data.
        """

    def load_from_stream(self, stream: BinaryIO) -> None:
        """
        Load a sample from an **uncompressed** stream.

        :param stream: File-like object containing the uncompressed wavetable.
        """
        if stream.read(len(FILE_MAGIC_STR)) != FILE_MAGIC_STR:
            raise ValueError('Bad magic value for a wavetable file')
        blk_size = read_int(stream)
        if blk_size > 0:
            smp_data = BytesIO(stream.read(blk_size))
        else:
            smp_data = stream

        self.meta.name = read_str(smp_data)
        self.meta.length = read_int(smp_data)
        read_int(smp_data) # compatablity rate
        self.meta.sample_rate = read_int(smp_data)
        self.meta.depth = int(smp_data.read(1)[0])
        smp_data.read(1) # loop direction
        smp_data.read(1) # flags
        smp_data.read(1) # flags 2
        self.meta.loop_start = read_int(smp_data)
        self.meta.loop_end = read_int(smp_data)
        smp_data.read(16) # sample presence bitfields
        self.data = smp_data.read(self.meta.length)
