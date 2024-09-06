from io import BytesIO
from typing import Optional, Union, BinaryIO, List

from chipchune._util import read_short, read_int, read_str
from .data_types import WavetableMeta
from .enums import _FurWavetableImportType

FILE_MAGIC_STR = b'-Furnace waveta-'
EMBED_MAGIC_STR = b'WAVE'


class FurnaceWavetable:
    def __init__(self, file_name: Optional[str] = None) -> None:
        """
        Creates or opens a new Furnace wavetable as a Python object.

        :param file_name: (Optional)
            If specified, then it will parse a file as a FurnaceWavetable. If file name (str) is
            given, it will load that file.

            Defaults to None.
        """
        self.file_name: Optional[str] = None
        """
        Original file name, if the object was initialized with one.
        """
        self.meta: WavetableMeta = WavetableMeta()
        """
        Wavetable metadata.
        """
        self.data: List[int] = []
        """
        Wavetable data.
        """

        if isinstance(file_name, str):
            self.load_from_file(file_name)

    def load_from_file(self, file_name: Optional[str] = None) -> None:
        if isinstance(file_name, str):
            self.file_name = file_name
        if self.file_name is None:
            raise RuntimeError('No file name set, either set self.file_name or pass file_name to the function')

        # since we're loading from an uncompressed file, we can just check the file magic number
        with open(self.file_name, 'rb') as f:
            detect_magic = f.peek(len(FILE_MAGIC_STR))[:len(FILE_MAGIC_STR)]
            if detect_magic == FILE_MAGIC_STR:
                return self.load_from_stream(f, _FurWavetableImportType.FILE)
            else:  # uncompressed for sure
                raise ValueError('No recognized file type magic')

    def load_from_bytes(self, data: bytes, import_as: Union[int, _FurWavetableImportType]) -> None:
        """
        Load a wavetable from a series of bytes.

        :param data: Bytes
        """
        return self.load_from_stream(
            BytesIO(data),
            import_as
        )
    
    def load_from_stream(self, stream: BinaryIO, import_as: Union[int, _FurWavetableImportType]) -> None:
        """
        Load a wavetable from an **uncompressed** stream.

        :param stream: File-like object containing the uncompressed wavetable.
        :param import_as: int
            - 0 = wavetable file
            - 1 = wavetable embedded in module
        """
        if import_as == _FurWavetableImportType.FILE:
            if stream.read(len(FILE_MAGIC_STR)) != FILE_MAGIC_STR:
                raise ValueError('Bad magic value for a wavetable file')
            version = read_short(stream)
            read_short(stream)  # reserved
            self.__load_embed(stream)

        elif import_as == _FurWavetableImportType.EMBED:
            return self.__load_embed(stream)

        else:
            raise ValueError('Invalid import type')

    def __load_embed(self, stream: BinaryIO) -> None:
        if stream.read(len(EMBED_MAGIC_STR)) != EMBED_MAGIC_STR:
            raise RuntimeError('Bad magic value for a wavetable embed')
        
        blk_size = read_int(stream)
        if blk_size > 0:
            wt_data = BytesIO(stream.read(blk_size))
        else:
            wt_data = stream

        self.meta.name = read_str(wt_data)
        self.meta.width = read_int(wt_data)
        read_int(wt_data)  # reserved
        self.meta.height = read_int(wt_data) + 1  # serialized height is 1 lower than actual value

        self.data = [read_int(wt_data) for _ in range(self.meta.width)]
