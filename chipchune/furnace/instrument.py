from io import BytesIO
from typing import Optional, Union, BinaryIO, TypeVar, Type, List, Dict

from chipchune._util import read_byte, read_short, read_int, read_str
from .data_types import (
    InsFeatureAbstract, InsFeatureMacro, InsMeta, InstrumentType, InsFeatureName,
    InsFeatureFM, InsFeatureOpr1Macro, InsFeatureOpr2Macro, InsFeatureOpr3Macro, InsFeatureOpr4Macro,
    InsFeatureC64, InsFeatureGB, GBHwSeq, SingleMacro, InsFeatureAmiga, InsFeatureOPLDrums, InsFeatureSNES,
    GainMode, InsFeatureN163, InsFeatureFDS, InsFeatureWaveSynth, _InsFeaturePointerAbstract, InsFeatureSampleList,
    InsFeatureWaveList, InsFeatureMultiPCM, InsFeatureSoundUnit, InsFeatureES5506, InsFeatureX1010, GenericADSR,
    InsFeatureDPCMMap, InsFeaturePowerNoise, InsFeatureSID2
)
from .enums import (
    _FurInsImportType, MacroCode, OpMacroCode, MacroItem, MacroType, GBHwCommand,
    SNESSusMode, WaveFX, ESFilterMode, MacroSize
)

FILE_MAGIC_STR = b'-Furnace instr.-'
DEV127_FILE_MAGIC_STR = b'FINS'

EMBED_MAGIC_STR = b'INST'
DEV127_EMBED_MAGIC_STR = b'INS2'

T_MACRO = TypeVar('T_MACRO', bound=InsFeatureMacro)  # T_MACRO must be subclass of InsFeatureMacro
T_POINTERS = TypeVar('T_POINTERS', bound=_InsFeaturePointerAbstract)


class FurnaceInstrument:
    def __init__(self, file_name: Optional[str] = None, protocol_version: Optional[int] = 1) -> None:
        """
        Creates or opens a new Furnace instrument as a Python object.

        :param file_name: (Optional)
            If specified, then it will parse a file as a FurnaceInstrument. If file name (str) is
            given, it will load that file.

            Defaults to None.

        :param protocol_version: (Optional)
            If specified, it will determine which format the instrument is to be serialized (exported)
            to. It is ignored if loading up a file.

            Defaults to 2 (dev127+ ins. format)
        """
        self.file_name: Optional[str] = None
        """
        Original file name, if the object was initialized with one.
        """
        self.protocol_version: Optional[int] = protocol_version
        """
        Instrument file "protocol" version. Currently:
        - 0: The "unified" instrument format up to Furnace version 126.
        - 1: The new "featural" instrument format introduced in version 127.
        """
        self.features: List[InsFeatureAbstract] = []
        """
        List of features, regardless of protocol version.
        """
        self.meta: InsMeta = InsMeta()
        """
        Instrument metadata.
        """

        # self.wavetables: list[] = []
        # self.samples: list[] = []

        self.__map_to_fn = {
            b'NA': self.__load_na_block,
            b'FM': self.__load_fm_block,
            b'MA': self.__load_ma_block,
            b'64': self.__load_c64_block,
            b'GB': self.__load_gb_block,
            b'SM': self.__load_sm_block,
            b'O1': self.__load_o1_block,
            b'O2': self.__load_o2_block,
            b'O3': self.__load_o3_block,
            b'O4': self.__load_o4_block,
            b'LD': self.__load_ld_block,
            b'SN': self.__load_sn_block,
            b'N1': self.__load_n1_block,
            b'FD': self.__load_fd_block,
            b'WS': self.__load_ws_block,
            b'SL': self.__load_sl_block,
            b'WL': self.__load_wl_block,
            b'MP': self.__load_mp_block,
            b'SU': self.__load_su_block,
            b'ES': self.__load_es_block,
            b'X1': self.__load_x1_block,
            b'NE': self.__load_ne_block,
            # TODO: No documentation?
            b'EF': self.__load_ef_block,
            b'PN': self.__load_pn_block,
            b'S2': self.__load_s2_block,
        }

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
                return self.load_from_stream(f, _FurInsImportType.FORMAT_0_FILE)
            elif detect_magic[:len(DEV127_FILE_MAGIC_STR)] == DEV127_FILE_MAGIC_STR:
                return self.load_from_stream(f, _FurInsImportType.FORMAT_1_FILE)
            else:  # uncompressed for sure
                raise ValueError('No recognized file type magic')

    def load_from_bytes(self, data: bytes, import_as: Union[int, _FurInsImportType]) -> None:
        """
        Load an instrument from a series of bytes.

        :param data: Bytes
        :param import_as: int
            see :method:`FurnaceInstrument.load_from_stream`

        """
        return self.load_from_stream(
            BytesIO(data),
            import_as
        )

    def load_from_stream(self, stream: BinaryIO, import_as: Union[int, _FurInsImportType]) -> None:
        """
        Load a module from an **uncompressed** stream.

        :param stream: File-like object containing the uncompressed module.
        :param import_as: int
            - 0 = old format instrument file
            - 1 = old format, embedded in module
            - 2 = new format instrument file
            - 3 = new format, embedded in module
        """
        if import_as == _FurInsImportType.FORMAT_0_FILE:
            if stream.read(len(FILE_MAGIC_STR)) != FILE_MAGIC_STR:
                raise ValueError('Bad magic value for a format 1 file')
            self.protocol_version = 0
            self.meta.version = read_short(stream)
            read_short(stream)  # reserved
            ins_data_ptr = read_int(stream)
            num_waves = read_short(stream)
            num_samples = read_short(stream)
            read_int(stream)  # reserved

            # these don't exist for format 1 instrs.
            self.__wavetable_ptr = [
                read_int(stream) for _ in range(num_waves)
            ]
            self.__sample_ptr = [
                read_int(stream) for _ in range(num_samples)
            ]

            stream.seek(ins_data_ptr)
            self.__load_format_0_embed(stream)
            # TODO: load wavetables and samples

        elif import_as == _FurInsImportType.FORMAT_0_EMBED:
            self.protocol_version = 0
            return self.__load_format_0_embed(stream)

        elif import_as == _FurInsImportType.FORMAT_1_FILE:
            if stream.read(len(DEV127_FILE_MAGIC_STR)) != DEV127_FILE_MAGIC_STR:
                raise ValueError('Bad magic value for a format 1 file')
            self.protocol_version = 1
            self.__load_format_1(stream)
            # TODO: load wavetables and samples

        elif import_as == _FurInsImportType.FORMAT_1_EMBED:
            if stream.read(len(DEV127_EMBED_MAGIC_STR)) != DEV127_EMBED_MAGIC_STR:
                raise ValueError('Bad magic value for a format 1 embed')
            self.protocol_version = 1
            ins_data = BytesIO(stream.read(read_int(stream)))
            return self.__load_format_1(ins_data)

        else:
            raise ValueError('Invalid import type')

    def __str__(self) -> str:
        return '<Furnace instrument "%s", type %s>' % (
            self.get_name(), self.meta.type
        )

    def __load_format_1(self, stream: BinaryIO) -> None:
        # skip headers and magic
        self.meta.version = read_short(stream)
        self.meta.type = InstrumentType(read_short(stream))
        self.features.clear()

        # add all the features
        feat = self.__read_format_1_feature(stream)
        while isinstance(feat, InsFeatureAbstract):
            self.features.append(feat)
            feat = self.__read_format_1_feature(stream)

    def __read_format_1_feature(self, stream: BinaryIO) -> Optional[object]:  # subclass InsFeatureAbstract
        code = stream.read(2)
        if code == b'EN' or code == b'':  # eof
            return None

        len_block = read_short(stream)
        feature_block = BytesIO(stream.read(len_block))

        # if this fails it might be a malformed file
        return self.__map_to_fn[code](feature_block)

    def get_name(self) -> str:
        """
        Shortcut to fetch the instrument name.

        :return: Instrument name
        """
        name = ''
        for i in self.features:
            if isinstance(i, InsFeatureName):
                name = i  # InsFeatureName also subclasses 'str' so it's fine
        return name

    # format 1 features

    def __load_na_block(self, stream: BytesIO) -> InsFeatureName:
        return InsFeatureName(
            read_str(stream)
        )

    def __load_fm_block(self, stream: BytesIO) -> InsFeatureFM:
        fm = InsFeatureFM()

        # read base data
        data = [read_byte(stream) for _ in range(4)]

        current = data.pop(0)
        ops = current & 0b1111
        fm.op_list[0].enable = bool(current & 16)
        fm.op_list[1].enable = bool(current & 32)
        fm.op_list[2].enable = bool(current & 64)
        fm.op_list[3].enable = bool(current & 128)

        current = data.pop(0)
        fm.alg = (current >> 4) & 0b111
        fm.fb = current & 0b111

        current = data.pop(0)
        fm.fms2 = (current >> 5) & 0b111
        fm.ams = (current >> 3) & 0b11
        fm.fms = current & 0b111

        current = data.pop(0)
        fm.ams2 = (current >> 6) & 0b11
        if current & 32:
            fm.ops = 4
        else:
            fm.ops = 2
        fm.opll_preset = current & 31

        # read operators
        for op in range(ops):
            data = [read_byte(stream) for _ in range(8)]

            current = data.pop(0)
            fm.op_list[op].ksr = bool(current & 128)
            fm.op_list[op].dt = (current >> 4) & 7
            fm.op_list[op].mult = current & 15

            current = data.pop(0)
            fm.op_list[op].sus = bool(current & 128)
            fm.op_list[op].tl = current & 127

            current = data.pop(0)
            fm.op_list[op].rs = (current >> 6) & 3
            fm.op_list[op].vib = bool(current & 32)
            fm.op_list[op].ar = current & 31

            current = data.pop(0)
            fm.op_list[op].am = bool(current & 128)
            fm.op_list[op].ksl = (current >> 5) & 3
            fm.op_list[op].dr = current & 31

            current = data.pop(0)
            fm.op_list[op].egt = bool(current & 128)
            fm.op_list[op].kvs = (current >> 5) & 3
            fm.op_list[op].d2r = current & 31

            current = data.pop(0)
            fm.op_list[op].sl = (current >> 4) & 15
            fm.op_list[op].rr = current & 15

            current = data.pop(0)
            fm.op_list[op].dvb = (current >> 4) & 15
            fm.op_list[op].ssg_env = current & 15

            current = data.pop(0)
            fm.op_list[op].dam = (current >> 5) & 7
            fm.op_list[op].dt2 = (current >> 3) & 3
            fm.op_list[op].ws = current & 7

        return fm

    def __common_ma_block(self, stream: BytesIO, macro_class: Type[T_MACRO]) -> T_MACRO:
        ma = macro_class()
        ma.macros.clear()
        read_short(stream)  # header size

        target_code: Union[MacroCode, OpMacroCode]

        if macro_class in [InsFeatureOpr1Macro,
                           InsFeatureOpr2Macro,
                           InsFeatureOpr3Macro,
                           InsFeatureOpr4Macro]:
            target_code = OpMacroCode(read_byte(stream))
        else:
            target_code = MacroCode(read_byte(stream))

        while target_code != MacroCode.STOP:
            new_macro = SingleMacro(kind=target_code)

            length = read_byte(stream)
            loop = read_byte(stream)
            release = read_byte(stream)

            new_macro.mode = read_byte(stream)
            flags = read_byte(stream)

            word_size = MacroSize(flags >> 6 & 0b11)  # type: ignore
            new_macro.type = MacroType(flags >> 1 & 0b11)
            new_macro.open = bool(flags & 1)
            new_macro.delay = read_byte(stream)
            new_macro.speed = read_byte(stream)

            # adsr and lfo will simply be kept as a list
            macro_content: List[Union[int, MacroItem]] = [
                int.from_bytes(
                    stream.read(word_size.num_bytes),
                    byteorder='little',
                    signed=word_size.signed
                )
                for _ in range(length)
            ]

            if loop != 0xff:  # hard limit in new macro
                macro_content.insert(loop, MacroItem.LOOP)

            if release != 0xff:  # ^
                macro_content.insert(release, MacroItem.RELEASE)

            new_macro.data = macro_content

            ma.macros.append(new_macro)

            if macro_class in [InsFeatureOpr1Macro,
                               InsFeatureOpr2Macro,
                               InsFeatureOpr3Macro,
                               InsFeatureOpr4Macro]:
                target_code = OpMacroCode(read_byte(stream))
            else:
                target_code = MacroCode(read_byte(stream))

        return ma

    def __load_ma_block(self, stream: BytesIO) -> InsFeatureMacro:
        return self.__common_ma_block(stream, InsFeatureMacro)

    def __load_o1_block(self, stream: BytesIO) -> InsFeatureOpr1Macro:
        return self.__common_ma_block(stream, InsFeatureOpr1Macro)

    def __load_o2_block(self, stream: BytesIO) -> InsFeatureOpr2Macro:
        return self.__common_ma_block(stream, InsFeatureOpr2Macro)

    def __load_o3_block(self, stream: BytesIO) -> InsFeatureOpr3Macro:
        return self.__common_ma_block(stream, InsFeatureOpr3Macro)

    def __load_o4_block(self, stream: BytesIO) -> InsFeatureOpr4Macro:
        return self.__common_ma_block(stream, InsFeatureOpr4Macro)

    def __load_c64_block(self, stream: BytesIO) -> InsFeatureC64:
        c64 = InsFeatureC64()

        data = [read_byte(stream) for _ in range(4)]

        current = data.pop(0)
        c64.duty_is_abs = bool((current >> 7) & 1)
        c64.init_filter = bool((current >> 6) & 1)
        c64.vol_is_cutoff = bool((current >> 5) & 1)
        c64.to_filter = bool((current >> 4) & 1)
        c64.noise_on = bool((current >> 3) & 1)
        c64.pulse_on = bool((current >> 2) & 1)
        c64.saw_on = bool((current >> 1) & 1)
        c64.tri_on = bool(current & 1)

        current = data.pop(0)
        c64.osc_sync = bool((current >> 7) & 1)
        c64.ring_mod = bool((current >> 6) & 1)
        c64.no_test = bool((current >> 5) & 1)
        c64.filter_is_abs = bool((current >> 4) & 1)
        c64.ch3_off = bool((current >> 3) & 1)
        c64.bp = bool((current >> 2) & 1)
        c64.hp = bool((current >> 1) & 1)
        c64.lp = bool(current & 1)

        current = data.pop(0)
        c64.envelope.a = (current >> 4) & 0b1111
        c64.envelope.d = current & 0b1111

        current = data.pop(0)
        c64.envelope.s = (current >> 4) & 0b1111
        c64.envelope.r = current & 0b1111

        c64.duty = read_short(stream)

        c_r = read_short(stream)
        c64.cut = c_r & 0b11111111111
        c64.res = (c_r >> 12) & 0b1111

        return c64

    def __load_gb_block(self, stream: BytesIO) -> InsFeatureGB:
        gb = InsFeatureGB()

        data = [read_byte(stream) for _ in range(4)]

        current = data.pop(0)
        gb.env_vol = current & 0b1111
        gb.env_dir = (current >> 4) & 1
        gb.env_len = (current >> 5) & 0b111

        gb.sound_len = data.pop(0)

        current = data.pop(0)
        gb.soft_env = bool(current & 1)
        gb.always_init = bool((current >> 1) & 1)

        hw_seq_len = data.pop(0)
        for i in range(hw_seq_len):
            seq_entry = GBHwSeq(
                GBHwCommand(read_byte(stream))
            )
            seq_entry.data = [
                read_byte(stream),
                read_byte(stream)
            ]
            gb.hw_seq.append(seq_entry)

        return gb

    def __load_sm_block(self, stream: BytesIO) -> InsFeatureAmiga:
        sm = InsFeatureAmiga()

        sm.init_sample = read_short(stream)

        current = read_byte(stream)
        sm.use_wave = bool((current >> 2) & 1)
        sm.use_sample = bool((current >> 1) & 1)
        sm.use_note_map = bool(current & 1)

        sm.wave_len = read_byte(stream)

        if sm.use_note_map:
            for i in range(len(sm.sample_map)):
                sm.sample_map[i].freq = read_short(stream)
                sm.sample_map[i].sample_index = read_short(stream)

        return sm

    def __load_ld_block(self, stream: BytesIO) -> InsFeatureOPLDrums:
        return InsFeatureOPLDrums(
            fixed_drums=bool(read_byte(stream) & 1),
            kick_freq=read_short(stream),
            snare_hat_freq=read_short(stream),
            tom_top_freq=read_short(stream)
        )

    def __load_sn_block(self, stream: BytesIO) -> InsFeatureSNES:
        sn = InsFeatureSNES()

        data = [read_byte(stream) for _ in range(4)]

        current = data.pop(0)
        sn.envelope.d = (current >> 4) & 0b111
        sn.envelope.a = current & 0b1111

        current = data.pop(0)
        sn.envelope.s = (current >> 5) & 0b111
        sn.envelope.r = current & 0b11111

        current = data.pop(0)
        sn.use_env = bool((current >> 4) & 1)
        sn.sus = SNESSusMode((current >> 3) & 1)

        gain_mode = current & 0b111
        if current < 4:
            gain_mode = 0
        sn.gain_mode = GainMode(gain_mode)

        sn.gain = data.pop(0)

        if self.meta.version >= 131:
            d2s = read_byte(stream)
            sn.sus = SNESSusMode((d2s >> 5 & 0b11))
            sn.d2 = d2s & 31

        return sn

    def __load_n1_block(self, stream: BytesIO) -> InsFeatureN163:
        return InsFeatureN163(
            wave=read_int(stream),
            wave_pos=read_byte(stream),
            wave_len=read_byte(stream),
            wave_mode=read_byte(stream)
        )

    def __load_fd_block(self, stream: BytesIO) -> InsFeatureFDS:
        fd = InsFeatureFDS(
            mod_speed=read_int(stream),
            mod_depth=read_int(stream),
            init_table_with_first_wave=bool(read_byte(stream))
        )
        for i in range(32):
            fd.mod_table[i] = read_byte(stream)
        return fd

    def __load_ws_block(self, stream: BytesIO) -> InsFeatureWaveSynth:
        return InsFeatureWaveSynth(
            wave_indices=[
                read_int(stream), read_int(stream)
            ],
            rate_divider=read_byte(stream),
            effect=WaveFX(read_byte(stream)),
            enabled=bool(read_byte(stream) & 1),
            global_effect=bool(read_byte(stream) & 1),
            speed=read_byte(stream),
            params=[
                read_byte(stream), read_byte(stream),
                read_byte(stream), read_byte(stream)
            ]
        )

    def __common_pointers_block(self, stream: BytesIO, ptr_class: Type[T_POINTERS]) -> T_POINTERS:
        pt = ptr_class()
        num_entries = read_byte(stream)

        for _ in range(num_entries):
            pt.pointers[read_byte(stream)] = -1

        for i in pt.pointers:
            pt.pointers[i] = read_int(stream)

        return pt

    def __load_sl_block(self, stream: BytesIO) -> InsFeatureSampleList:
        return self.__common_pointers_block(stream, InsFeatureSampleList)

    def __load_wl_block(self, stream: BytesIO) -> InsFeatureWaveList:
        return self.__common_pointers_block(stream, InsFeatureWaveList)

    def __load_mp_block(self, stream: BytesIO) -> InsFeatureMultiPCM:
        return InsFeatureMultiPCM(
            ar=read_byte(stream),
            d1r=read_byte(stream),
            dl=read_byte(stream),
            d2r=read_byte(stream),
            rr=read_byte(stream),
            rc=read_byte(stream),
            lfo=read_byte(stream),
            vib=read_byte(stream),
            am=read_byte(stream),
        )

    def __load_su_block(self, stream: BytesIO) -> InsFeatureSoundUnit:
        return InsFeatureSoundUnit(
            switch_roles=bool(read_byte(stream))
        )

    def __load_es_block(self, stream: BytesIO) -> InsFeatureES5506:
        return InsFeatureES5506(
            filter_mode=ESFilterMode(read_byte(stream)),
            k1=read_short(stream),
            k2=read_short(stream),
            env_count=read_short(stream),
            left_volume_ramp=read_byte(stream),
            right_volume_ramp=read_byte(stream),
            k1_ramp=read_byte(stream),
            k2_ramp=read_byte(stream),
            k1_slow=read_byte(stream),
            k2_slow=read_byte(stream)
        )

    def __load_x1_block(self, stream: BytesIO) -> InsFeatureX1010:
        return InsFeatureX1010(
            bank_slot=read_int(stream)
        )

    def __load_ne_block(self, stream: BytesIO) -> InsFeatureDPCMMap:
        sm = InsFeatureDPCMMap()

        sm.use_map = bool(read_byte(stream) & 1)

        if sm.use_map:
            for i in range(len(sm.sample_map)):
                sm.sample_map[i].pitch = read_byte(stream)
                sm.sample_map[i].delta = read_byte(stream)

        return sm

    # TODO: No documentation?
    def __load_ef_block(self, stream: BytesIO): # -> InsFeatureESFM:
        pass

    def __load_pn_block(self, stream: BytesIO) -> InsFeaturePowerNoise:
        return InsFeaturePowerNoise(
            octave=read_byte(stream)
        )

    def __load_s2_block(self, stream: BytesIO) -> InsFeatureSID2:
        current_byte = read_byte(stream)
        return InsFeatureSID2(
            volume=current_byte & 0b1111,
            wave_mix=(current_byte >> 4) & 0b11,
            noise_mode=(current_byte >> 6) & 0b11
        )
    
    # format 0; also used for file because it includes the "INST" header too

    def __load_format_0_embed(self, stream: BinaryIO) -> None:
        # load format 0 as a series of format 1 feature blocks

        # aux function...
        def add_to_macro_data(macro: List[Union[int, MacroItem]],
                              loop: Optional[int] = 0xffffffff,
                              release: Optional[int] = 0xffffffff,
                              data: Optional[List[int]] = None) -> None:
            if data is not None:
                macro.extend(data)
            if loop is not None and loop != 0xffffffff:  # old macros have a 4-byte length
                macro.insert(loop, MacroItem.LOOP)
            if release is not None and release != 0xffffffff:
                macro.insert(release, MacroItem.RELEASE)

        # we check the header here
        if stream.read(len(EMBED_MAGIC_STR)) != EMBED_MAGIC_STR:
            raise RuntimeError('Bad magic value for a format 0 embed')

        blk_size = read_int(stream)
        if blk_size > 0:
            ins_data = BytesIO(stream.read(blk_size))
        else:
            ins_data = stream

        self.meta.version = read_short(ins_data)  # overwrites the file header version
        self.meta.type = InstrumentType(read_byte(ins_data))

        read_byte(ins_data)

        # read all features in one go!
        self.features.clear()

        # name, insert immediately
        self.features.append(
            InsFeatureName(read_str(ins_data))
        )

        # fm
        if True:
            fm = InsFeatureFM(
                alg=read_byte(ins_data),
                fb=read_byte(ins_data),
                fms=read_byte(ins_data),
                ams=read_byte(ins_data),
                ops=read_byte(ins_data),
                opll_preset=read_byte(ins_data)
            )
            read_short(ins_data)
            for i in range(4):
                fm.op_list[i].am = bool(read_byte(ins_data))
                fm.op_list[i].ar = read_byte(ins_data)
                fm.op_list[i].dr = read_byte(ins_data)
                fm.op_list[i].mult = read_byte(ins_data)
                fm.op_list[i].rr = read_byte(ins_data)
                fm.op_list[i].sl = read_byte(ins_data)
                fm.op_list[i].tl = read_byte(ins_data)
                fm.op_list[i].dt2 = read_byte(ins_data)
                fm.op_list[i].rs = read_byte(ins_data)
                fm.op_list[i].dt = read_byte(ins_data)
                fm.op_list[i].d2r = read_byte(ins_data)
                fm.op_list[i].ssg_env = read_byte(ins_data)
                fm.op_list[i].dam = read_byte(ins_data)
                fm.op_list[i].dvb = read_byte(ins_data)
                fm.op_list[i].egt = bool(read_byte(ins_data))
                fm.op_list[i].ksl = read_byte(ins_data)
                fm.op_list[i].sus = bool(read_byte(ins_data))
                fm.op_list[i].vib = bool(read_byte(ins_data))
                fm.op_list[i].ws = read_byte(ins_data)
                fm.op_list[i].ksr = bool(read_byte(ins_data))
                en = read_byte(ins_data)
                if self.meta.version >= 114:
                    fm.op_list[i].enable = bool(en)
                kvs = read_byte(ins_data)
                if self.meta.version >= 115:
                    fm.op_list[i].kvs = kvs
                ins_data.read(10)
            self.features.append(fm)

        # gameboy
        if True:
            gb = InsFeatureGB(
                env_vol=read_byte(ins_data),
                env_dir=read_byte(ins_data),
                env_len=read_byte(ins_data),
                sound_len=read_byte(ins_data)
            )
            self.features.append(gb)

        # c64
        if True:
            c64 = InsFeatureC64(
                tri_on=bool(read_byte(ins_data)),
                saw_on=bool(read_byte(ins_data)),
                pulse_on=bool(read_byte(ins_data)),
                noise_on=bool(read_byte(ins_data)),
                duty=read_short(ins_data),
                ring_mod=read_byte(ins_data),
                osc_sync=read_byte(ins_data),
                to_filter=bool(read_byte(ins_data)),
                init_filter=bool(read_byte(ins_data)),
                vol_is_cutoff=bool(read_byte(ins_data)),
                res=read_byte(ins_data),
                lp=bool(read_byte(ins_data)),
                bp=bool(read_byte(ins_data)),
                hp=bool(read_byte(ins_data)),
                ch3_off=bool(read_byte(ins_data)),
                cut=read_short(ins_data),
                duty_is_abs=bool(read_byte(ins_data)),
                filter_is_abs=bool(read_byte(ins_data))
            )
            c64.envelope = GenericADSR(
                a=read_byte(ins_data),
                d=read_byte(ins_data),
                s=read_byte(ins_data),
                r=read_byte(ins_data),
            )
            self.features.append(c64)

        # amiga
        if True:
            amiga = InsFeatureAmiga(
                init_sample=read_short(ins_data)
            )

            wave = read_byte(ins_data)
            wavelen = read_byte(ins_data)
            if self.meta.version >= 82:
                amiga.use_wave = bool(wave)
                amiga.wave_len = wavelen

            for _ in range(12):
                read_byte(ins_data)  # reserved

            self.features.append(amiga)

        # standard
        if True:
            mac = InsFeatureMacro()

            vol_mac = SingleMacro(kind=MacroCode.VOL)
            arp_mac = SingleMacro(kind=MacroCode.ARP)
            duty_mac = SingleMacro(kind=MacroCode.DUTY)
            wave_mac = SingleMacro(kind=MacroCode.WAVE)

            vol_mac.data.clear()
            arp_mac.data.clear()
            duty_mac.data.clear()
            wave_mac.data.clear()

            mac_list: List[SingleMacro] = [vol_mac, arp_mac, duty_mac, wave_mac]
            mac.macros = mac_list

            vol_mac_len = read_int(ins_data)
            arp_mac_len = read_int(ins_data)
            duty_mac_len = read_int(ins_data)
            wave_mac_len = read_int(ins_data)

            if self.meta.version >= 17:
                pitch_mac = SingleMacro(kind=MacroCode.PITCH)
                x1_mac = SingleMacro(kind=MacroCode.EX1)
                x2_mac = SingleMacro(kind=MacroCode.EX2)
                x3_mac = SingleMacro(kind=MacroCode.EX3)

                pitch_mac.data.clear()
                x1_mac.data.clear()
                x2_mac.data.clear()
                x3_mac.data.clear()

                mac_list.extend([pitch_mac, x1_mac, x2_mac, x3_mac])

                pitch_mac_len = read_int(ins_data)
                x1_mac_len = read_int(ins_data)
                x2_mac_len = read_int(ins_data)
                x3_mac_len = read_int(ins_data)

            vol_mac_loop = read_int(ins_data)
            arp_mac_loop = read_int(ins_data)
            duty_mac_loop = read_int(ins_data)
            wave_mac_loop = read_int(ins_data)

            if self.meta.version >= 17:
                pitch_mac_loop = read_int(ins_data)
                x1_mac_loop = read_int(ins_data)
                x2_mac_loop = read_int(ins_data)
                x3_mac_loop = read_int(ins_data)

            arp_mac_mode = read_byte(ins_data)
            old_vol_height = read_byte(ins_data)
            old_duty_height = read_byte(ins_data)

            read_byte(ins_data)

            add_to_macro_data(vol_mac.data,
                              loop=vol_mac_loop,
                              release=None,
                              data=[read_int(ins_data) for _ in range(vol_mac_len)])

            add_to_macro_data(arp_mac.data,
                              loop=arp_mac_loop,
                              release=None,
                              data=[read_int(ins_data) for _ in range(arp_mac_len)])

            add_to_macro_data(duty_mac.data,
                              loop=duty_mac_loop,
                              release=None,
                              data=[read_int(ins_data) for _ in range(duty_mac_len)])

            add_to_macro_data(wave_mac.data,
                              loop=wave_mac_loop,
                              release=None,
                              data=[read_int(ins_data) for _ in range(wave_mac_len)])

            # adjust values
            if self.meta.version < 31:
                if arp_mac_mode == 0:
                    for j in range(len(arp_mac.data)):
                        if isinstance(arp_mac.data[j], int):
                            arp_mac.data[j] -= 12
            if self.meta.version < 87:
                if c64.vol_is_cutoff and not c64.filter_is_abs:
                    for j in range(len(vol_mac.data)):
                        if isinstance(vol_mac.data[j], int):
                            vol_mac.data[j] -= 18
                if c64.duty_is_abs:  # TODO
                    for j in range(len(duty_mac.data)):
                        if isinstance(duty_mac.data[j], int):
                            duty_mac.data[j] -= 12
            if self.meta.version < 112:
                if arp_mac_mode == 1: # fixed arp!
                    for i in range(len(arp_mac.data)):
                        if isinstance(arp_mac.data[i], int):
                            arp_mac.data[i] |= (1 << 30)
                    if len(arp_mac.data) > 0:
                        if arp_mac_loop != 0xffffffff:
                            if arp_mac_loop == arp_mac_len+1:
                                arp_mac.data[-1] = 0
                                arp_mac.data.append(MacroItem.LOOP)
                            elif arp_mac_loop == arp_mac_len:
                                arp_mac.data.append(0)
                    else:
                        arp_mac.data.append(0)

            # read more macros
            if self.meta.version >= 17:
                add_to_macro_data(pitch_mac.data,
                                  loop=pitch_mac_loop,
                                  release=None,
                                  data=[read_int(ins_data) for _ in range(pitch_mac_len)])

                add_to_macro_data(x1_mac.data,
                                  loop=x1_mac_loop,
                                  release=None,
                                  data=[read_int(ins_data) for _ in range(x1_mac_len)])

                add_to_macro_data(x2_mac.data,
                                  loop=x2_mac_loop,
                                  release=None,
                                  data=[read_int(ins_data) for _ in range(x2_mac_len)])

                add_to_macro_data(x3_mac.data,
                                  loop=x3_mac_loop,
                                  release=None,
                                  data=[read_int(ins_data) for _ in range(x3_mac_len)])
            else:
                if self.meta.type == InstrumentType.STANDARD:
                    if old_vol_height == 31:
                        self.meta.type = InstrumentType.PCE
                    elif old_duty_height == 31:
                        self.meta.type = InstrumentType.SSG

            self.features.append(mac)

        # fm macros
        if True:
            if self.meta.version >= 29:
                alg_mac = SingleMacro(kind=MacroCode.ALG)
                fb_mac = SingleMacro(kind=MacroCode.FB)
                fms_mac = SingleMacro(kind=MacroCode.FMS)
                ams_mac = SingleMacro(kind=MacroCode.AMS)
                mac_list.extend([alg_mac, fb_mac, fms_mac, ams_mac])

                alg_mac.data.clear()
                fb_mac.data.clear()
                fms_mac.data.clear()
                ams_mac.data.clear()

                alg_mac_len = read_int(ins_data)
                fb_mac_len = read_int(ins_data)
                fms_mac_len = read_int(ins_data)
                ams_mac_len = read_int(ins_data)

                alg_mac_loop = read_int(ins_data)
                fb_mac_loop = read_int(ins_data)
                fms_mac_loop = read_int(ins_data)
                ams_mac_loop = read_int(ins_data)

                vol_mac.open = bool(read_byte(ins_data))
                arp_mac.open = bool(read_byte(ins_data))
                duty_mac.open = bool(read_byte(ins_data))
                wave_mac.open = bool(read_byte(ins_data))
                pitch_mac.open = bool(read_byte(ins_data))
                x1_mac.open = bool(read_byte(ins_data))
                x2_mac.open = bool(read_byte(ins_data))
                x3_mac.open = bool(read_byte(ins_data))

                alg_mac.open = bool(read_byte(ins_data))
                fb_mac.open = bool(read_byte(ins_data))
                fms_mac.open = bool(read_byte(ins_data))
                ams_mac.open = bool(read_byte(ins_data))

                add_to_macro_data(alg_mac.data,
                                  loop=alg_mac_loop,
                                  release=None,
                                  data=[read_int(ins_data) for _ in range(alg_mac_len)])

                add_to_macro_data(fb_mac.data,
                                  loop=fb_mac_loop,
                                  release=None,
                                  data=[read_int(ins_data) for _ in range(fb_mac_len)])

                add_to_macro_data(fms_mac.data,
                                  loop=fms_mac_loop,
                                  release=None,
                                  data=[read_int(ins_data) for _ in range(fms_mac_len)])

                add_to_macro_data(ams_mac.data,
                                  loop=ams_mac_loop,
                                  release=None,
                                  data=[read_int(ins_data) for _ in range(ams_mac_len)])

        # fm op macros
        if True:
            if self.meta.version >= 29:
                new_ops: Dict[int, InsFeatureMacro] = {}  # actual ops

                ops_types: Dict[int, Type[InsFeatureMacro]] = {  # classes
                    0: InsFeatureOpr1Macro,
                    1: InsFeatureOpr2Macro,
                    2: InsFeatureOpr3Macro,
                    3: InsFeatureOpr4Macro,
                }

                ops: Dict[int, Dict[str, Union[int, bool]]] = {  # params
                    0: {},
                    1: {},
                    2: {},
                    3: {}
                }

                for opi in ops:
                    ops[opi]["am_mac_len"] = read_int(ins_data)
                    ops[opi]["ar_mac_len"] = read_int(ins_data)
                    ops[opi]["dr_mac_len"] = read_int(ins_data)
                    ops[opi]["mult_mac_len"] = read_int(ins_data)
                    ops[opi]["rr_mac_len"] = read_int(ins_data)
                    ops[opi]["sl_mac_len"] = read_int(ins_data)
                    ops[opi]["tl_mac_len"] = read_int(ins_data)
                    ops[opi]["dt2_mac_len"] = read_int(ins_data)
                    ops[opi]["rs_mac_len"] = read_int(ins_data)
                    ops[opi]["dt_mac_len"] = read_int(ins_data)
                    ops[opi]["d2r_mac_len"] = read_int(ins_data)
                    ops[opi]["ssg_mac_len"] = read_int(ins_data)

                    ops[opi]["am_mac_loop"] = read_int(ins_data)
                    ops[opi]["ar_mac_loop"] = read_int(ins_data)
                    ops[opi]["dr_mac_loop"] = read_int(ins_data)
                    ops[opi]["mult_mac_loop"] = read_int(ins_data)
                    ops[opi]["rr_mac_loop"] = read_int(ins_data)
                    ops[opi]["sl_mac_loop"] = read_int(ins_data)
                    ops[opi]["tl_mac_loop"] = read_int(ins_data)
                    ops[opi]["dt2_mac_loop"] = read_int(ins_data)
                    ops[opi]["rs_mac_loop"] = read_int(ins_data)
                    ops[opi]["dt_mac_loop"] = read_int(ins_data)
                    ops[opi]["d2r_mac_loop"] = read_int(ins_data)
                    ops[opi]["ssg_mac_loop"] = read_int(ins_data)

                    ops[opi]["am_mac_open"] = read_byte(ins_data)
                    ops[opi]["ar_mac_open"] = read_byte(ins_data)
                    ops[opi]["dr_mac_open"] = read_byte(ins_data)
                    ops[opi]["mult_mac_open"] = read_byte(ins_data)
                    ops[opi]["rr_mac_open"] = read_byte(ins_data)
                    ops[opi]["sl_mac_open"] = read_byte(ins_data)
                    ops[opi]["tl_mac_open"] = read_byte(ins_data)
                    ops[opi]["dt2_mac_open"] = read_byte(ins_data)
                    ops[opi]["rs_mac_open"] = read_byte(ins_data)
                    ops[opi]["dt_mac_open"] = read_byte(ins_data)
                    ops[opi]["d2r_mac_open"] = read_byte(ins_data)
                    ops[opi]["ssg_mac_open"] = read_byte(ins_data)

                for opi in ops:
                    new_op = ops_types[opi]()
                    new_op.macros = []

                    am_mac = SingleMacro(kind=OpMacroCode.AM)
                    am_mac.open = bool(ops[opi]["am_mac_open"])
                    am_mac.data.clear()
                    add_to_macro_data(am_mac.data,
                                      loop=ops[opi]["am_mac_loop"],
                                      release=None,
                                      data=[read_int(ins_data) for _ in range(ops[opi]["am_mac_len"])])

                    ar_mac = SingleMacro(kind=OpMacroCode.AR)
                    ar_mac.open = bool(ops[opi]["ar_mac_open"])
                    ar_mac.data.clear()
                    add_to_macro_data(ar_mac.data,
                                      loop=ops[opi]["ar_mac_loop"],
                                      release=None,
                                      data=[read_int(ins_data) for _ in range(ops[opi]["ar_mac_len"])])

                    dr_mac = SingleMacro(kind=OpMacroCode.DR)
                    dr_mac.open = bool(ops[opi]["dr_mac_open"])
                    dr_mac.data.clear()
                    add_to_macro_data(dr_mac.data,
                                      loop=ops[opi]["dr_mac_loop"],
                                      release=None,
                                      data=[read_int(ins_data) for _ in range(ops[opi]["dr_mac_len"])])

                    mult_mac = SingleMacro(kind=OpMacroCode.MULT)
                    mult_mac.open = bool(ops[opi]["mult_mac_open"])
                    mult_mac.data.clear()
                    add_to_macro_data(mult_mac.data,
                                      loop=ops[opi]["mult_mac_loop"],
                                      release=None,
                                      data=[read_int(ins_data) for _ in range(ops[opi]["mult_mac_len"])])

                    rr_mac = SingleMacro(kind=OpMacroCode.RR)
                    rr_mac.open = bool(ops[opi]["rr_mac_open"])
                    rr_mac.data.clear()
                    add_to_macro_data(rr_mac.data,
                                      loop=ops[opi]["rr_mac_loop"],
                                      release=None,
                                      data=[read_int(ins_data) for _ in range(ops[opi]["rr_mac_len"])])

                    sl_mac = SingleMacro(kind=OpMacroCode.SL)
                    sl_mac.open = bool(ops[opi]["sl_mac_open"])
                    sl_mac.data.clear()
                    add_to_macro_data(sl_mac.data,
                                      loop=ops[opi]["sl_mac_loop"],
                                      release=None,
                                      data=[read_int(ins_data) for _ in range(ops[opi]["sl_mac_len"])])

                    tl_mac = SingleMacro(kind=OpMacroCode.TL)
                    tl_mac.open = bool(ops[opi]["tl_mac_open"])
                    tl_mac.data.clear()
                    add_to_macro_data(tl_mac.data,
                                      loop=ops[opi]["tl_mac_loop"],
                                      release=None,
                                      data=[read_int(ins_data) for _ in range(ops[opi]["tl_mac_len"])])

                    dt2_mac = SingleMacro(kind=OpMacroCode.DT2)
                    dt2_mac.open = bool(ops[opi]["dt2_mac_open"])
                    dt2_mac.data.clear()
                    add_to_macro_data(dt2_mac.data,
                                      loop=ops[opi]["dt2_mac_loop"],
                                      release=None,
                                      data=[read_int(ins_data) for _ in range(ops[opi]["dt2_mac_len"])])

                    rs_mac = SingleMacro(kind=OpMacroCode.RS)
                    rs_mac.open = bool(ops[opi]["rs_mac_open"])
                    rs_mac.data.clear()
                    add_to_macro_data(rs_mac.data,
                                      loop=ops[opi]["rs_mac_loop"],
                                      release=None,
                                      data=[read_int(ins_data) for _ in range(ops[opi]["rs_mac_len"])])

                    dt_mac = SingleMacro(kind=OpMacroCode.DT)
                    dt_mac.open = bool(ops[opi]["dt_mac_open"])
                    dt_mac.data.clear()
                    add_to_macro_data(dt_mac.data,
                                      loop=ops[opi]["dt_mac_loop"],
                                      release=None,
                                      data=[read_int(ins_data) for _ in range(ops[opi]["dt_mac_len"])])

                    d2r_mac = SingleMacro(kind=OpMacroCode.D2R)
                    d2r_mac.open = bool(ops[opi]["d2r_mac_open"])
                    d2r_mac.data.clear()
                    add_to_macro_data(d2r_mac.data,
                                      loop=ops[opi]["d2r_mac_loop"],
                                      release=None,
                                      data=[read_int(ins_data) for _ in range(ops[opi]["d2r_mac_len"])])

                    ssg_mac = SingleMacro(kind=OpMacroCode.SSG_EG)
                    ssg_mac.open = bool(ops[opi]["ssg_mac_open"])
                    ssg_mac.data.clear()
                    add_to_macro_data(ssg_mac.data,
                                      loop=ops[opi]["ssg_mac_loop"],
                                      release=None,
                                      data=[read_int(ins_data) for _ in range(ops[opi]["ssg_mac_len"])])

                    new_op.macros.extend([
                        am_mac, ar_mac, dr_mac, mult_mac, rr_mac,
                        sl_mac, tl_mac, dt2_mac, rs_mac, dt_mac,
                        d2r_mac, ssg_mac
                    ])  # must be in order!!

                    new_ops[opi] = new_op

        # release points
        if True:
            if self.meta.version >= 44:
                add_to_macro_data(vol_mac.data, None, read_int(ins_data), None)
                add_to_macro_data(arp_mac.data, None, read_int(ins_data), None)
                add_to_macro_data(duty_mac.data, None, read_int(ins_data), None)
                add_to_macro_data(wave_mac.data, None, read_int(ins_data), None)
                add_to_macro_data(pitch_mac.data, None, read_int(ins_data), None)
                add_to_macro_data(x1_mac.data, None, read_int(ins_data), None)
                add_to_macro_data(x2_mac.data, None, read_int(ins_data), None)
                add_to_macro_data(x3_mac.data, None, read_int(ins_data), None)
                add_to_macro_data(alg_mac.data, None, read_int(ins_data), None)
                add_to_macro_data(fb_mac.data, None, read_int(ins_data), None)
                add_to_macro_data(fms_mac.data, None, read_int(ins_data), None)
                add_to_macro_data(ams_mac.data, None, read_int(ins_data), None)

                for opi in new_ops:
                    for i in range(12):
                        add_to_macro_data(new_ops[opi].macros[i].data, None, read_int(ins_data), None)

        # extended op macros
        if True:
            if self.meta.version >= 61:
                for op in new_ops:
                    dam_mac = SingleMacro(kind=OpMacroCode.DAM)
                    dvb_mac = SingleMacro(kind=OpMacroCode.DVB)
                    egt_mac = SingleMacro(kind=OpMacroCode.EGT)
                    ksl_mac = SingleMacro(kind=OpMacroCode.KSL)
                    sus_mac = SingleMacro(kind=OpMacroCode.SUS)
                    vib_mac = SingleMacro(kind=OpMacroCode.VIB)
                    ws_mac = SingleMacro(kind=OpMacroCode.WS)
                    ksr_mac = SingleMacro(kind=OpMacroCode.KSR)

                    dam_mac_len = read_int(ins_data)
                    dvb_mac_len = read_int(ins_data)
                    egt_mac_len = read_int(ins_data)
                    ksl_mac_len = read_int(ins_data)
                    sus_mac_len = read_int(ins_data)
                    vib_mac_len = read_int(ins_data)
                    ws_mac_len = read_int(ins_data)
                    ksr_mac_len = read_int(ins_data)

                    dam_mac_loop = read_int(ins_data)
                    dvb_mac_loop = read_int(ins_data)
                    egt_mac_loop = read_int(ins_data)
                    ksl_mac_loop = read_int(ins_data)
                    sus_mac_loop = read_int(ins_data)
                    vib_mac_loop = read_int(ins_data)
                    ws_mac_loop = read_int(ins_data)
                    ksr_mac_loop = read_int(ins_data)

                    dam_mac_rel = read_int(ins_data)
                    dvb_mac_rel = read_int(ins_data)
                    egt_mac_rel = read_int(ins_data)
                    ksl_mac_rel = read_int(ins_data)
                    sus_mac_rel = read_int(ins_data)
                    vib_mac_rel = read_int(ins_data)
                    ws_mac_rel = read_int(ins_data)
                    ksr_mac_rel = read_int(ins_data)

                    dam_mac.open = bool(read_byte(ins_data))
                    dvb_mac.open = bool(read_byte(ins_data))
                    egt_mac.open = bool(read_byte(ins_data))
                    ksl_mac.open = bool(read_byte(ins_data))
                    sus_mac.open = bool(read_byte(ins_data))
                    vib_mac.open = bool(read_byte(ins_data))
                    ws_mac.open = bool(read_byte(ins_data))
                    ksr_mac.open = bool(read_byte(ins_data))

                    dam_mac.data.clear()
                    dvb_mac.data.clear()
                    egt_mac.data.clear()
                    ksl_mac.data.clear()
                    sus_mac.data.clear()
                    vib_mac.data.clear()
                    ws_mac.data.clear()
                    ksr_mac.data.clear()

                    add_to_macro_data(dam_mac.data, dam_mac_loop, dam_mac_rel, [
                        read_byte(ins_data) for _ in range(dam_mac_len)
                    ])
                    add_to_macro_data(dvb_mac.data, dvb_mac_loop, dvb_mac_rel, [
                        read_byte(ins_data) for _ in range(dvb_mac_len)
                    ])
                    add_to_macro_data(egt_mac.data, egt_mac_loop, egt_mac_rel, [
                        read_byte(ins_data) for _ in range(egt_mac_len)
                    ])
                    add_to_macro_data(ksl_mac.data, ksl_mac_loop, ksl_mac_rel, [
                        read_byte(ins_data) for _ in range(ksl_mac_len)
                    ])
                    add_to_macro_data(sus_mac.data, sus_mac_loop, sus_mac_rel, [
                        read_byte(ins_data) for _ in range(sus_mac_len)
                    ])
                    add_to_macro_data(vib_mac.data, vib_mac_loop, vib_mac_rel, [
                        read_byte(ins_data) for _ in range(vib_mac_len)
                    ])
                    add_to_macro_data(ws_mac.data, ws_mac_loop, ws_mac_rel, [
                        read_byte(ins_data) for _ in range(ws_mac_len)
                    ])
                    add_to_macro_data(ksr_mac.data, ksr_mac_loop, ksr_mac_rel, [
                        read_byte(ins_data) for _ in range(ksr_mac_len)
                    ])

                    new_ops[op].macros.extend([
                        dam_mac, dvb_mac, egt_mac, ksl_mac, sus_mac, vib_mac,
                        ws_mac, ksr_mac
                    ])

        # opl drum data
        if True:
            if self.meta.version >= 63:
                opl_drum = InsFeatureOPLDrums(
                    fixed_drums = bool(read_byte(ins_data))
                )
                read_byte(ins_data)
                opl_drum.kick_freq = read_short(ins_data)
                opl_drum.snare_hat_freq = read_short(ins_data)
                opl_drum.tom_top_freq = read_short(ins_data)
                self.features.append(opl_drum)

        # clear macros
        if True:
            if self.meta.version < 63 and self.meta.type == InstrumentType.PCE:
                duty_mac.data.clear()
            if self.meta.version < 70 and self.meta.type == InstrumentType.FM_OPLL:
                wave_mac.data.clear()

        # sample map
        if True:
            if self.meta.version >= 67:
                note_map = InsFeatureAmiga()
                note_map.use_note_map = bool(read_byte(ins_data))
                if note_map.use_note_map:
                    for i in range(len(note_map.sample_map)):
                        note_map.sample_map[i].freq = read_int(ins_data)
                    for i in range(len(note_map.sample_map)):
                        note_map.sample_map[i].sample_index = read_short(ins_data)
                self.features.append(note_map)

        # n163
        if True:
            if self.meta.version >= 73:
                n163 = InsFeatureN163(
                    wave=read_int(ins_data),
                    wave_pos=read_byte(ins_data),
                    wave_len=read_byte(ins_data),
                    wave_mode=read_byte(ins_data)
                )
                read_byte(ins_data)  # reserved
                self.features.append(n163)

        # moar macroes
        if True:
            if self.meta.version >= 76:
                pan_l_mac = SingleMacro(kind=MacroCode.PAN_L)
                pan_r_mac = SingleMacro(kind=MacroCode.PAN_R)
                phase_res_mac = SingleMacro(kind=MacroCode.PHASE_RESET)
                x4_mac = SingleMacro(kind=MacroCode.EX4)
                x5_mac = SingleMacro(kind=MacroCode.EX5)
                x6_mac = SingleMacro(kind=MacroCode.EX6)
                x7_mac = SingleMacro(kind=MacroCode.EX7)
                x8_mac = SingleMacro(kind=MacroCode.EX8)

                pan_l_mac.data.clear()
                pan_r_mac.data.clear()
                phase_res_mac.data.clear()
                x4_mac.data.clear()
                x5_mac.data.clear()
                x6_mac.data.clear()
                x7_mac.data.clear()
                x8_mac.data.clear()

                pan_l_mac_len = read_int(ins_data)
                pan_r_mac_len = read_int(ins_data)
                phase_res_mac_len = read_int(ins_data)
                x4_mac_len = read_int(ins_data)
                x5_mac_len = read_int(ins_data)
                x6_mac_len = read_int(ins_data)
                x7_mac_len = read_int(ins_data)
                x8_mac_len = read_int(ins_data)

                pan_l_mac_loop = read_int(ins_data)
                pan_r_mac_loop = read_int(ins_data)
                phase_res_mac_loop = read_int(ins_data)
                x4_mac_loop = read_int(ins_data)
                x5_mac_loop = read_int(ins_data)
                x6_mac_loop = read_int(ins_data)
                x7_mac_loop = read_int(ins_data)
                x8_mac_loop = read_int(ins_data)

                pan_l_mac_rel = read_int(ins_data)
                pan_r_mac_rel = read_int(ins_data)
                phase_res_mac_rel = read_int(ins_data)
                x4_mac_rel = read_int(ins_data)
                x5_mac_rel = read_int(ins_data)
                x6_mac_rel = read_int(ins_data)
                x7_mac_rel = read_int(ins_data)
                x8_mac_rel = read_int(ins_data)

                pan_l_mac.open = bool(read_byte(ins_data))
                pan_r_mac.open = bool(read_byte(ins_data))
                phase_res_mac.open = bool(read_byte(ins_data))
                x4_mac.open = bool(read_byte(ins_data))
                x5_mac.open = bool(read_byte(ins_data))
                x6_mac.open = bool(read_byte(ins_data))
                x7_mac.open = bool(read_byte(ins_data))
                x8_mac.open = bool(read_byte(ins_data))

                add_to_macro_data(pan_l_mac.data, pan_l_mac_loop, pan_l_mac_rel, [
                    read_int(ins_data) for _ in range(pan_l_mac_len)
                ])
                add_to_macro_data(pan_r_mac.data, pan_r_mac_loop, pan_r_mac_rel, [
                    read_int(ins_data) for _ in range(pan_r_mac_len)
                ])
                add_to_macro_data(phase_res_mac.data, phase_res_mac_loop, phase_res_mac_rel, [
                    read_int(ins_data) for _ in range(phase_res_mac_len)
                ])
                add_to_macro_data(x4_mac.data, x4_mac_loop, x4_mac_rel, [
                    read_int(ins_data) for _ in range(x4_mac_len)
                ])
                add_to_macro_data(x5_mac.data, x5_mac_loop, x5_mac_rel, [
                    read_int(ins_data) for _ in range(x5_mac_len)
                ])
                add_to_macro_data(x6_mac.data, x6_mac_loop, x6_mac_rel, [
                    read_int(ins_data) for _ in range(x6_mac_len)
                ])
                add_to_macro_data(x7_mac.data, x7_mac_loop, x7_mac_rel, [
                    read_int(ins_data) for _ in range(x7_mac_len)
                ])
                add_to_macro_data(x8_mac.data, x8_mac_loop, x8_mac_rel, [
                    read_int(ins_data) for _ in range(x8_mac_len)
                ])

                mac_list.extend([
                    pan_l_mac, pan_r_mac, phase_res_mac, x4_mac,
                    x5_mac, x6_mac, x7_mac, x8_mac
                ])

        # fds
        if True:
            if self.meta.version >= 76:
                fds = InsFeatureFDS(
                    mod_speed=read_int(ins_data),
                    mod_depth=read_int(ins_data),
                    init_table_with_first_wave=bool(read_byte(ins_data))
                )
                read_byte(ins_data)  # reserved
                read_byte(ins_data)
                read_byte(ins_data)
                fds.mod_table = [read_byte(ins_data) for _ in range(32)]
                self.features.append(fds)

        # opz
        if True:
            if self.meta.version >= 77:
                fm.fms2 = read_byte(ins_data)
                fm.ams2 = read_byte(ins_data)

        # wave synth
        if True:
            if self.meta.version >= 79:
                ws = InsFeatureWaveSynth(
                    wave_indices=[read_int(ins_data), read_int(ins_data)],
                    rate_divider=read_byte(ins_data),
                    effect=WaveFX(read_byte(ins_data)),
                    enabled=bool(read_byte(ins_data)),
                    global_effect=bool(read_byte(ins_data)),
                    speed=read_byte(ins_data),
                    params=[read_byte(ins_data) for _ in range(4)]
                )
                self.features.append(ws)

        # macro moads
        if True:
            if self.meta.version >= 84:
                vol_mac.mode = read_byte(ins_data)
                duty_mac.mode = read_byte(ins_data)
                wave_mac.mode = read_byte(ins_data)
                pitch_mac.mode = read_byte(ins_data)
                x1_mac.mode = read_byte(ins_data)
                x2_mac.mode = read_byte(ins_data)
                x3_mac.mode = read_byte(ins_data)
                alg_mac.mode = read_byte(ins_data)
                fb_mac.mode = read_byte(ins_data)
                fms_mac.mode = read_byte(ins_data)
                ams_mac.mode = read_byte(ins_data)
                pan_l_mac.mode = read_byte(ins_data)
                pan_r_mac.mode = read_byte(ins_data)
                phase_res_mac.mode = read_byte(ins_data)
                x4_mac.mode = read_byte(ins_data)
                x5_mac.mode = read_byte(ins_data)
                x6_mac.mode = read_byte(ins_data)
                x7_mac.mode = read_byte(ins_data)
                x8_mac.mode = read_byte(ins_data)

        # c64 no test
        if True:
            if self.meta.version >= 89:
                c64.no_test = bool(read_byte(ins_data))

        # multipcm
        if True:
            if self.meta.version >= 93:
                mp = InsFeatureMultiPCM(
                    ar=read_byte(ins_data),
                    d1r=read_byte(ins_data),
                    dl=read_byte(ins_data),
                    d2r=read_byte(ins_data),
                    rr=read_byte(ins_data),
                    rc=read_byte(ins_data),
                    lfo=read_byte(ins_data),
                    vib=read_byte(ins_data),
                    am=read_byte(ins_data)
                )
                for _ in range(23):  # reserved
                    read_byte(ins_data)
                self.features.append(mp)

        # sound unit
        if True:
            if self.meta.version >= 104:
                amiga.use_sample = bool(read_byte(ins_data))
                su = InsFeatureSoundUnit(
                    switch_roles=bool(read_byte(ins_data))
                )
                self.features.append(su)

        # gb hw seq
        if True:
            if self.meta.version >= 105:
                gb_hwseq_len = read_byte(ins_data)
                gb.hw_seq.clear()
                for i in range(gb_hwseq_len):
                    gb.hw_seq.append(
                        GBHwSeq(
                            command=GBHwCommand(read_byte(ins_data)),
                            data=[read_byte(ins_data), read_byte(ins_data)]
                        )
                    )

        # additional gb
        if True:
            if self.meta.version >= 106:
                gb.soft_env = bool(read_byte(ins_data))
                gb.always_init = bool(read_byte(ins_data))

        # es5506
        if True:
            if self.meta.version >= 107:
                es = InsFeatureES5506(
                    filter_mode=ESFilterMode(read_byte(ins_data)),
                    k1=read_short(ins_data),
                    k2=read_short(ins_data),
                    env_count=read_short(ins_data),
                    left_volume_ramp=read_byte(ins_data),
                    right_volume_ramp=read_byte(ins_data),
                    k1_ramp=read_byte(ins_data),
                    k2_ramp=read_byte(ins_data),
                    k1_slow=read_byte(ins_data),
                    k2_slow=read_byte(ins_data)
                )
                self.features.append(es)

        # snes
        if True:
            if self.meta.version >= 109:
                snes = InsFeatureSNES()
                snes.use_env = bool(read_byte(ins_data))
                if self.meta.version >= 118:
                    snes.gain_mode = GainMode(read_byte(ins_data))
                    snes.gain = read_byte(ins_data)
                else:
                    read_byte(ins_data)
                    read_byte(ins_data)
                snes.envelope.a = read_byte(ins_data)
                snes.envelope.d = read_byte(ins_data)
                snes_env_s = read_byte(ins_data)
                snes.envelope.s = snes_env_s & 0b111
                snes.envelope.r = read_byte(ins_data)
                snes.sus = SNESSusMode((snes_env_s >> 3) & 1)  # ???
                self.features.append(snes)

        # macro speed delay
        if True:
            if self.meta.version >= 111:
                vol_mac.speed = read_byte(ins_data)
                arp_mac.speed = read_byte(ins_data)
                duty_mac.speed = read_byte(ins_data)
                wave_mac.speed = read_byte(ins_data)
                pitch_mac.speed = read_byte(ins_data)
                x1_mac.speed = read_byte(ins_data)
                x2_mac.speed = read_byte(ins_data)
                x3_mac.speed = read_byte(ins_data)
                alg_mac.speed = read_byte(ins_data)
                fb_mac.speed = read_byte(ins_data)
                fms_mac.speed = read_byte(ins_data)
                ams_mac.speed = read_byte(ins_data)
                pan_l_mac.speed = read_byte(ins_data)
                pan_r_mac.speed = read_byte(ins_data)
                phase_res_mac.speed = read_byte(ins_data)
                x4_mac.speed = read_byte(ins_data)
                x5_mac.speed = read_byte(ins_data)
                x6_mac.speed = read_byte(ins_data)
                x7_mac.speed = read_byte(ins_data)
                x8_mac.speed = read_byte(ins_data)

                vol_mac.delay = read_byte(ins_data)
                arp_mac.delay = read_byte(ins_data)
                duty_mac.delay = read_byte(ins_data)
                wave_mac.delay = read_byte(ins_data)
                pitch_mac.delay = read_byte(ins_data)
                x1_mac.delay = read_byte(ins_data)
                x2_mac.delay = read_byte(ins_data)
                x3_mac.delay = read_byte(ins_data)
                alg_mac.delay = read_byte(ins_data)
                fb_mac.delay = read_byte(ins_data)
                fms_mac.delay = read_byte(ins_data)
                ams_mac.delay = read_byte(ins_data)
                pan_l_mac.delay = read_byte(ins_data)
                pan_r_mac.delay = read_byte(ins_data)
                phase_res_mac.delay = read_byte(ins_data)
                x4_mac.delay = read_byte(ins_data)
                x5_mac.delay = read_byte(ins_data)
                x6_mac.delay = read_byte(ins_data)
                x7_mac.delay = read_byte(ins_data)
                x8_mac.delay = read_byte(ins_data)

                for op in ops:
                    for i in range(20):
                        new_ops[op].macros[i].speed = read_byte(ins_data)
                    for i in range(20):
                        new_ops[op].macros[i].delay = read_byte(ins_data)

        # old arp mac format
        if True:
            if self.meta.version < 112:
                if arp_mac.mode != 0:
                    arp_mac.mode = 0
                    for i in range(len(arp_mac.data)):
                        if isinstance(arp_mac.data[i], int):
                            arp_mac.data[i] ^= 0x40000000

        # add ops macros at the end
        if True:
            if self.meta.version >= 29:
                for _, op_contents in new_ops.items():
                    self.features.append(op_contents)
