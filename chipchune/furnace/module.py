import re
import zlib
from io import BytesIO, BufferedReader
from typing import BinaryIO, Optional, Literal, Union, Dict, List

from chipchune._util import read_byte, read_short, read_int, read_float, read_str
from .data_types import (
    ModuleMeta, ChipList, ModuleCompatFlags, SubSong, PatchBay, ChannelDisplayInfo,
    InputPatchBayEntry, OutputPatchBayEntry, ChipInfo, FurnacePattern, FurnaceRow
)
from .enums import (
    ChipType, LinearPitch, InputPortSet, OutputPortSet, LoopModality,
    DelayBehavior, JumpTreatment, _FurInsImportType, _FurWavetableImportType, Note
)
from .instrument import FurnaceInstrument
from .wavetable import FurnaceWavetable
from .sample import FurnaceSample

MAGIC_STR = b'-Furnace module-'
MAX_CHIPS = 32


class FurnaceModule:
    """
    Represents a Furnace .fur file.

    When possible, instrument objects etc. will use the latest format as its internal
    representation. For example, old instruments will internally be converted into the
    "new" instrument-feature-list format.
    """

    def __init__(self, file_name_or_stream: Optional[Union[BufferedReader, str]] = None) -> None:
        """
        Creates or opens a new Furnace module as a Python object.

        :param file_name_or_stream: (Optional)
            If specified, then it will parse a file as a FurnaceModule. If file name (str) is
            given, it will load that file. If a stream (BufferedReader) instead is given,
            it will parse it from the stream.

            Defaults to None.
        """
        self.file_name: Optional[str] = None
        """
        Original file name, if the object was initialized with one.
        """
        self.meta: ModuleMeta = ModuleMeta()
        """
        Metadata concerning the module.
        """
        self.chips: ChipList = ChipList()
        """
        List of chips used in the module.
        """
        self.compat_flags: ModuleCompatFlags = ModuleCompatFlags()
        """
        Compat flags settings within the module.
        """
        self.subsongs: List[SubSong] = [SubSong()]
        """
        Subsongs contained within the module. Although the first subsong
        and the others are internally stored separately, they're organized
        into a list here for convenience.
        """
        self.patchbay: List[PatchBay] = []
        """
        List of patchbay connections.
        """
        self.instruments: List[FurnaceInstrument] = []
        """
        List of all instruments in the module.
        """
        self.patterns: List[FurnacePattern] = []
        """
        List of all patterns in the module.
        """
        self.wavetables: List[FurnaceWavetable] = []

        self.samples: List[FurnaceWavetable] = []

        if isinstance(file_name_or_stream, BufferedReader):
            self.load_from_stream(file_name_or_stream)
        elif isinstance(file_name_or_stream, str):
            self.load_from_file(file_name_or_stream)

    def load_from_file(self, file_name: Optional[str] = None) -> None:
        """
        Load a module from a file name. The file may either be compressed or uncompressed.

        :param file_name: If not specified, it will grab from self.file_name instead.
        """
        if isinstance(file_name, str):
            self.file_name = file_name
        if self.file_name is None:
            raise RuntimeError('No file name set, either set self.file_name or pass file_name to the function')
        with open(self.file_name, 'rb') as f:
            detect_magic = f.peek(len(MAGIC_STR))[:len(MAGIC_STR)]
            if detect_magic != MAGIC_STR:  # this is probably compressed, so try decompressing it first
                return self.load_from_bytes(
                    zlib.decompress(f.read())
                )
            else:  # uncompressed for sure
                return self.load_from_stream(f)

    @staticmethod
    def decompress_to_file(in_name: str, out_name: str) -> int:
        """
        Simple zlib wrapper. Decompresses a zlib-compressed .fur
        from in_name to out_name. Does not need instantiation.

        :param in_name: input file name
        :param out_name: output file name
        :return: Results of file.write().
        """
        with open(in_name, 'rb') as fi:
            with open(out_name, 'wb') as fo:
                return fo.write(zlib.decompress(fi.read()))

    def load_from_bytes(self, data: bytes) -> None:
        """
        Load a module from a series of bytes.

        :param data: Bytes
        """
        return self.load_from_stream(
            BytesIO(data)
        )

    def load_from_stream(self, stream: BinaryIO) -> None:
        """
        Load a module from an **uncompressed** stream.

        :param stream: File-like object containing the uncompressed module.
        """
        # assumes uncompressed stream
        if stream.read(len(MAGIC_STR)) != MAGIC_STR:
            raise RuntimeError('Bad magic value; this is not a Furnace file or is corrupt')

        # clear defaults
        self.chips.list.clear()
        self.patchbay.clear()
        self.subsongs[0].order.clear()
        self.subsongs[0].speed_pattern.clear()

        self.__read_header(stream)
        self.__init_compat_flags()
        self.__read_info(stream)
        if self.meta.version >= 119:
            self.__read_dev119_chip_flags(stream)
        self.__read_instruments(stream)
        self.__read_wavetables(stream)
        self.__read_samples(stream)
        if self.meta.version >= 95:
            self.__read_subsongs(stream)
        self.__read_patterns(stream)

    def get_num_channels(self) -> int:
        """
        Retrieve the number of total channels in the module.

        :return: Channel sum across all chips.
        """
        num_channels = 0
        for chip in self.chips.list:
            num_channels += chip.type.channels
        return num_channels

    def get_pattern(self, channel: int, index: int, subsong: int=0) -> Optional[FurnacePattern]:
        """
        Gets one pattern object from a module.

        :param channel: Which channel to use (zero-indexed), e.g. to get VRC6
          in a NES+VRC6 module, use `5`.
        :param index: The index of the pattern within the subsong.
        :param subsong: The subsong number.
        :return: FurnacePattern object or None if no such pattern exists.
        """
        try:
            return next(
                filter(lambda x: x.channel==channel and x.index==index and x.subsong==subsong, self.patterns)
            )
        except StopIteration:
            return None

    def __init_compat_flags(self) -> None:
        """
        Initializes appropriate compat flags based on module version
        """
        if self.meta.version < 37:
            self.compat_flags.limit_slides = True
            self.compat_flags.linear_pitch = LinearPitch.ONLY_PITCH_CHANGE
            self.compat_flags.loop_modality = LoopModality.HARD_RESET_CHANNELS
        if self.meta.version < 43:
            self.compat_flags.proper_noise_layout = False
            self.compat_flags.wave_duty_is_volume = False
        if self.meta.version < 45:
            self.compat_flags.reset_macro_on_porta = True
            self.compat_flags.legacy_volume_slides = True
            self.compat_flags.compatible_arpeggio = True
            self.compat_flags.note_off_resets_slides = True
            self.compat_flags.target_resets_slides = True
        if self.meta.version < 46:
            self.compat_flags.arpeggio_inhibits_portamento = True
            self.compat_flags.wack_algorithm_macro = True
        if self.meta.version < 49:
            self.compat_flags.broken_shortcut_slides = True
        if self.meta.version < 50:
            self.compat_flags.ignore_duplicates_slides = False
        if self.meta.version < 62:
            self.compat_flags.stop_portamento_on_note_off = True
        if self.meta.version < 64:
            self.compat_flags.broken_dac_mode = False
        if self.meta.version < 65:
            self.compat_flags.one_tick_cut = False
        if self.meta.version < 66:
            self.compat_flags.instrument_change_allowed_in_porta = False
        if self.meta.version < 69:
            self.compat_flags.reset_note_base_on_arpeggio_stop = False
        if self.meta.version < 71:
            self.compat_flags.no_slides_on_first_tick = False
            self.compat_flags.next_row_reset_arp_pos = False
            self.compat_flags.ignore_jump_at_end = True
        if self.meta.version < 72:
            self.compat_flags.buggy_portamento_after_slide = True
            self.compat_flags.gb_ins_affects_env = False
        if self.meta.version < 78:
            self.compat_flags.shared_extch_state = False
        if self.meta.version < 83:
            self.compat_flags.ignore_outside_dac_mode_change = True
            self.compat_flags.e1e2_takes_priority = False
        if self.meta.version < 84:
            self.compat_flags.new_sega_pcm = False
        if self.meta.version < 85:
            self.compat_flags.weird_fnum_pitch_slides = True
        if self.meta.version < 86:
            self.compat_flags.sn_duty_resets_phase = True
        if self.meta.version < 90:
            self.compat_flags.linear_pitch_macro = False
        if self.meta.version < 97:
            self.compat_flags.old_octave_boundary = True
            self.compat_flags.disable_opn2_dac_volume_control = True  # dev98
        if self.meta.version < 99:
            self.compat_flags.new_volume_scaling = False
            self.compat_flags.volume_macro_lingers = False
            self.compat_flags.broken_out_vol = True
        if self.meta.version < 100:
            self.compat_flags.e1e2_stop_on_same_note = False
        if self.meta.version < 101:
            self.compat_flags.broken_porta_after_arp = True
        if self.meta.version < 108:
            self.compat_flags.sn_no_low_periods = True
        if self.meta.version < 110:
            self.compat_flags.cut_delay_effect_policy = DelayBehavior.BROKEN
        if self.meta.version < 113:
            self.compat_flags.jump_treatment = JumpTreatment.FIRST_JUMP_ONLY
        if self.meta.version < 115:
            self.compat_flags.auto_sys_name = True
        if self.meta.version < 117:
            self.compat_flags.disable_sample_macro = True
        if self.meta.version < 121:
            self.compat_flags.broken_out_vol_2 = False
        if self.meta.version < 130:
            self.compat_flags.old_arp_strategy = True
        if self.meta.version < 138:
            self.compat_flags.broken_porta_during_legato = True
        if self.meta.version < 155:
            self.compat_flags.broken_fm_off = True
        if self.meta.version < 168:
            self.compat_flags.pre_note_no_effect = True
        if self.meta.version < 183:
            self.compat_flags.old_dpcm = True
        if self.meta.version < 184:
            self.compat_flags.reset_arp_phase_on_new_note = False
        if self.meta.version < 188:
            self.compat_flags.ceil_volume_scaling = False
        if self.meta.version < 191:
            self.compat_flags.old_always_set_volume = True
        if self.meta.version < 200:
            self.compat_flags.old_sample_offset = True

    # XXX: update my signature whenever a new compat flag block is added
    def __read_compat_flags(self, stream: BinaryIO, phase: Literal[1, 2, 3]) -> None:
        """
        Reads the set compat flags in the module
        """
        if phase == 1:
            compat_flags_to_skip = 20
            if self.meta.version < 37:
                self.compat_flags.limit_slides = True
                self.compat_flags.linear_pitch = LinearPitch.ONLY_PITCH_CHANGE
                self.compat_flags.loop_modality = LoopModality.HARD_RESET_CHANNELS
            else:  # >= 37
                self.compat_flags.limit_slides = bool(read_byte(stream))
                self.compat_flags.linear_pitch = LinearPitch(read_byte(stream))
                self.compat_flags.loop_modality = LoopModality(read_byte(stream))
                compat_flags_to_skip -= 3

                if self.meta.version >= 43:
                    self.compat_flags.proper_noise_layout = bool(read_byte(stream))
                    self.compat_flags.wave_duty_is_volume = bool(read_byte(stream))
                    compat_flags_to_skip -= 2

                if self.meta.version >= 45:
                    self.compat_flags.reset_macro_on_porta = bool(read_byte(stream))
                    self.compat_flags.legacy_volume_slides = bool(read_byte(stream))
                    self.compat_flags.compatible_arpeggio = bool(read_byte(stream))
                    self.compat_flags.note_off_resets_slides = bool(read_byte(stream))
                    self.compat_flags.target_resets_slides = bool(read_byte(stream))
                    compat_flags_to_skip -= 5

                if self.meta.version >= 47:
                    self.compat_flags.arpeggio_inhibits_portamento = bool(read_byte(stream))
                    self.compat_flags.wack_algorithm_macro = bool(read_byte(stream))
                    compat_flags_to_skip -= 2

                if self.meta.version >= 49:
                    self.compat_flags.broken_shortcut_slides = bool(read_byte(stream))
                    compat_flags_to_skip -= 1

                if self.meta.version >= 50:
                    self.compat_flags.ignore_duplicates_slides = bool(read_byte(stream))
                    compat_flags_to_skip -= 1

                if self.meta.version >= 62:
                    self.compat_flags.stop_portamento_on_note_off = bool(read_byte(stream))
                    self.compat_flags.continuous_vibrato = bool(read_byte(stream))
                    compat_flags_to_skip -= 2

                if self.meta.version >= 64:
                    self.compat_flags.broken_dac_mode = bool(read_byte(stream))
                    compat_flags_to_skip -= 1

                if self.meta.version >= 65:
                    self.compat_flags.one_tick_cut = bool(read_byte(stream))
                    compat_flags_to_skip -= 1

                if self.meta.version >= 66:
                    self.compat_flags.instrument_change_allowed_in_porta = bool(read_byte(stream))
                    compat_flags_to_skip -= 1

                if self.meta.version >= 69:
                    self.compat_flags.reset_note_base_on_arpeggio_stop = bool(read_byte(stream))
                    compat_flags_to_skip -= 1
        elif phase == 2:
            compat_flags_to_skip = 28
            if self.meta.version >= 70:
                self.compat_flags.broken_speed_selection = bool(read_byte(stream))
                compat_flags_to_skip -= 1

                if self.meta.version >= 71:
                    self.compat_flags.no_slides_on_first_tick = bool(read_byte(stream))
                    self.compat_flags.next_row_reset_arp_pos = bool(read_byte(stream))
                    self.compat_flags.ignore_jump_at_end = bool(read_byte(stream))
                    compat_flags_to_skip -= 3

                if self.meta.version >= 72:
                    self.compat_flags.buggy_portamento_after_slide = bool(read_byte(stream))
                    self.compat_flags.gb_ins_affects_env = bool(read_byte(stream))
                    compat_flags_to_skip -= 2

                if self.meta.version >= 78:
                    self.compat_flags.shared_extch_state = bool(read_byte(stream))
                    compat_flags_to_skip -= 1

                if self.meta.version >= 83:
                    self.compat_flags.ignore_outside_dac_mode_change = bool(read_byte(stream))
                    self.compat_flags.e1e2_takes_priority = bool(read_byte(stream))
                    compat_flags_to_skip -= 2

                if self.meta.version >= 84:
                    self.compat_flags.new_sega_pcm = bool(read_byte(stream))
                    compat_flags_to_skip -= 1

                if self.meta.version >= 85:
                    self.compat_flags.weird_fnum_pitch_slides = bool(read_byte(stream))
                    compat_flags_to_skip -= 1

                if self.meta.version >= 86:
                    self.compat_flags.sn_duty_resets_phase = bool(read_byte(stream))
                    compat_flags_to_skip -= 1

                if self.meta.version >= 90:
                    self.compat_flags.linear_pitch_macro = bool(read_byte(stream))
                    compat_flags_to_skip -= 1

                if self.meta.version >= 94:
                    self.compat_flags.pitch_slide_speed_in_linear = read_byte(stream)
                    compat_flags_to_skip -= 1

                if self.meta.version >= 97:
                    self.compat_flags.old_octave_boundary = bool(read_byte(stream))
                    compat_flags_to_skip -= 1

                if self.meta.version >= 98:
                    self.compat_flags.disable_opn2_dac_volume_control = bool(read_byte(stream))
                    compat_flags_to_skip -= 1

                if self.meta.version >= 99:
                    self.compat_flags.new_volume_scaling = bool(read_byte(stream))
                    self.compat_flags.volume_macro_lingers = bool(read_byte(stream))
                    self.compat_flags.broken_out_vol = bool(read_byte(stream))
                    compat_flags_to_skip -= 3

                if self.meta.version >= 100:
                    self.compat_flags.e1e2_stop_on_same_note = bool(read_byte(stream))
                    compat_flags_to_skip -= 1

                if self.meta.version >= 101:
                    self.compat_flags.broken_porta_after_arp = bool(read_byte(stream))
                    compat_flags_to_skip -= 1

                if self.meta.version >= 108:
                    self.compat_flags.sn_no_low_periods = bool(read_byte(stream))
                    compat_flags_to_skip -= 1

                if self.meta.version >= 110:
                    self.compat_flags.cut_delay_effect_policy = DelayBehavior(read_byte(stream))
                    compat_flags_to_skip -= 1

                if self.meta.version >= 113:
                    self.compat_flags.jump_treatment = JumpTreatment(read_byte(stream))
                    compat_flags_to_skip -= 1

                if self.meta.version >= 115:
                    self.compat_flags.auto_sys_name = bool(read_byte(stream))
                    compat_flags_to_skip -= 1

                if self.meta.version >= 117:
                    self.compat_flags.disable_sample_macro = bool(read_byte(stream))
                    compat_flags_to_skip -= 1

                if self.meta.version >= 121:
                    self.compat_flags.broken_out_vol_2 = bool(read_byte(stream))
                    compat_flags_to_skip -= 1

                if self.meta.version >= 130:
                    self.compat_flags.old_arp_strategy = bool(read_byte(stream))
                    compat_flags_to_skip -= 1

        elif phase == 3:
            compat_flags_to_skip = 8
            if self.meta.version >= 138:
                self.compat_flags.broken_porta_during_legato = bool(read_byte(stream))
                compat_flags_to_skip -= 1
            
            if self.meta.version >= 155:
                self.compat_flags.broken_fm_off = bool(read_byte(stream))
                compat_flags_to_skip -= 1
            
            if self.meta.version >= 168:
                self.compat_flags.pre_note_no_effect = bool(read_byte(stream))
                compat_flags_to_skip -= 1
            
            if self.meta.version >= 183:
                self.compat_flags.old_dpcm = bool(read_byte(stream))
                compat_flags_to_skip -= 1
            
            if self.meta.version >= 184:
                self.compat_flags.reset_arp_phase_on_new_note = bool(read_byte(stream))
                compat_flags_to_skip -= 1
            
            if self.meta.version >= 188:
                self.compat_flags.ceil_volume_scaling = bool(read_byte(stream))
                compat_flags_to_skip -= 1
            
            if self.meta.version >= 191:
                self.compat_flags.old_always_set_volume = bool(read_byte(stream))
                compat_flags_to_skip -= 1
        else:
            raise ValueError(
                'Compat flag phase must be in between: 1, 2, 3'
            )
        stream.read(compat_flags_to_skip)

    def __read_dev119_chip_flags(self, stream: BinaryIO) -> None:
        for i in range(len(self.chips.list)):
            # skip if this chip doesn't have flags
            if self.__chip_flag_ptr[i] == 0:
                continue
            stream.seek(self.__chip_flag_ptr[i])

            if stream.read(4) != b'FLAG':
                raise ValueError('No "FLAG" magic')

            # i assume this will grow, you never know
            blk_size = read_int(stream)
            flag_blk = BytesIO(stream.read(blk_size))

            # read entries in FLAG
            for entry in [flag.split('=') for flag in read_str(flag_blk).split()]:
                key = entry[0]
                value = entry[1]
                # cast by regex
                if re.match(r'true', value):
                    self.chips.list[i].flags[key] = True
                elif re.match(r'false', value):
                    self.chips.list[i].flags[key] = False
                elif re.match(r'\d+$', value):
                    self.chips.list[i].flags[key] = int(value)
                elif re.match(r'\d+\.\d+', value):
                    self.chips.list[i].flags[key] = float(value)
                else:  # all other values should be treated as a string
                    self.chips.list[i].flags[key] = value

    @staticmethod
    def __convert_old_chip_flags(chip: ChipType, flag: int) -> Dict[str, Union[bool, int]]:
        """
        Convert pre-v119 binary chip flags to the newer dict-style form.

        :param chip: ChipType
        :param flag: flag value as a 32-bit number
        :return: dictionary containing the flag's equivalent values
        """
        n = {}

        if chip in [ChipType.GENESIS, ChipType.GENESIS_EX]:
            n['clockSel'] = flag & 2147483647  # bits 0-30
            n['ladderEffect'] = bool((flag >> 31) & 1)
        elif chip == ChipType.SMS:
            cs = flag & 0xff03
            if cs > 0x100:
                cs = cs - 252  # 0x100 + 4
            n['clockSel'] = cs
            ct = (flag & 0xcc) // 4
            if ct >= 32:
                ct -= 24
            elif ct >= 16:
                ct -= 12
            n['chipType'] = ct
            n['noPhaseReset'] = flag >> 4
        elif chip == ChipType.GB:
            n['chipType'] = flag & 0b11
            n['noAntiClick'] = bool((flag >> 3) & 1)
        elif chip == ChipType.PCE:
            n['clockSel'] = flag & 1
            n['chipType'] = (flag >> 2) & 1
            n['noAntiClick'] = bool((flag >> 3) & 1)
        elif chip in [ChipType.NES, ChipType.VRC6, ChipType.FDS, ChipType.MMC5]:
            n['clockSel'] = flag & 0b11
        elif chip in [ChipType.C64_8580, ChipType.C64_6581]:
            n['clockSel'] = flag & 0b1111
        elif chip == ChipType.SEGA_ARCADE:
            n['clockSel'] = flag & 0b11111111
        elif chip in [ChipType.NEO_GEO_CD, ChipType.NEO_GEO, ChipType.NEO_GEO_EX,
                      ChipType.NEO_GEO_CD_EX, ChipType.YM2610B, ChipType.YM2610B_EX]:
            n['clockSel'] = flag & 0b11111111
        elif chip == ChipType.AY38910:
            n['clockSel'] = flag & 0b1111
            n['chipType'] = (flag >> 4) & 0b11
            n['stereo'] = bool((flag >> 6) & 1)
            n['halfClock'] = bool((flag >> 7) & 1)
            n['stereoSep'] = (flag >> 8) & 0b11111111
        elif chip == ChipType.AMIGA:
            n['clockSel'] = flag & 1
            n['chipType'] = (flag >> 1) & 1
            n['bypassLimits'] = bool((flag >> 2) & 1)
            n['stereoSep'] = (flag >> 8) & 0b1111111
        elif chip == ChipType.YM2151:
            n['clockSel'] = flag & 0b11111111
        elif chip in [ChipType.YM2612, ChipType.YM2612_EX, ChipType.YM2612_PLUS,
                      ChipType.YM2612_PLUS_EX]:
            n['clockSel'] = flag & 2147483647  # bits 0-30
            n['ladderEffect'] = bool((flag >> 31) & 1)
        elif chip == ChipType.TIA:
            n['clockSel'] = flag & 1
            n['mixingType'] = (flag >> 1) & 0b11
        elif chip == ChipType.VIC20:
            n['clockSel'] = flag & 1
        elif chip == ChipType.SNES:
            n['volScaleL'] = flag & 0b1111111
            n['volScaleR'] = (flag >> 8) & 0b1111111
        elif chip in [ChipType.OPLL, ChipType.OPLL_DRUMS]:
            n['clockSel'] = flag & 0b1111
            n['patchSet'] = flag >> 4  # safe
        elif chip == ChipType.N163:
            n['clockSel'] = flag & 0b1111
            n['channels'] = (flag >> 4) & 0b111
            n['multiplex'] = bool((flag >> 7) & 1)
        elif chip in [ChipType.OPN, ChipType.YM2203_EX]:
            n['clockSel'] = flag & 0b11111
            n['prescale'] = (flag >> 5) & 0b11
        elif chip in [ChipType.OPL, ChipType.OPL_DRUMS, ChipType.OPL2, ChipType.OPL2_DRUMS,
                      ChipType.Y8950, ChipType.Y8950_DRUMS]:
            n['clockSel'] = flag & 0b11111111
        elif chip in [ChipType.OPL3, ChipType.OPL3_DRUMS]:
            n['clockSel'] = flag & 0b11111111
        elif chip == ChipType.PC_SPEAKER:
            n['speakerType'] = flag & 0b11
        elif chip == ChipType.RF5C68:
            n['clockSel'] = flag & 0b1111
            n['chipType'] = flag >> 4  # safe
        elif chip in [ChipType.SAA1099, ChipType.OPZ]:
            n['clockSel'] = flag & 0b11
        elif chip == ChipType.AY8930:
            n['clockSel'] = flag & 0b1111
            n['stereo'] = bool((flag >> 6) & 1)
            n['halfClock'] = bool((flag >> 7) & 1)
            n['stereoSep'] = (flag >> 8) & 0b11111111
        elif chip == ChipType.VRC7:
            n['clockSel'] = flag & 0b11
        elif chip == ChipType.ZX_BEEPER:
            n['clockSel'] = flag & 1
        elif chip in [ChipType.SCC, ChipType.SCC_PLUS]:
            n['clockSel'] = flag & 0b11
        elif chip == ChipType.MSM6295:
            n['clockSel'] = flag & 0b1111111
            n['rateSel'] = bool((flag >> 7) & 1)
        elif chip == ChipType.MSM6258:
            n['clockSel'] = flag & 0b11
        elif chip in [ChipType.OPL4, ChipType.OPL4_DRUMS]:
            n['clockSel'] = flag & 0b11111111
        elif chip == ChipType.SETA:
            n['clockSel'] = flag & 0b1111
            n['stereo'] = bool((flag >> 4) & 1)
        elif chip == ChipType.ES5506:
            n['channels'] = flag & 0b11111
        elif chip == ChipType.TSU:
            n['clockSel'] = flag & 1
            n['echo'] = bool((flag >> 2) & 1)
            n['swapEcho'] = bool((flag >> 3) & 1)
            n['sampleMemSize'] = (flag >> 4) & 1
            n['pdm'] = bool((flag >> 5) & 1)
            n['echoDelay'] = (flag >> 8) & 0b111111
            n['echoFeedback'] = (flag >> 16) & 0b1111
            n['echoResolution'] = (flag >> 20) & 0b1111
            n['echoVol'] = (flag >> 24) & 0b11111111
        elif chip == ChipType.YMZ280B:
            n['clockSel'] = flag & 0b11111111
        elif chip == ChipType.PCM_DAC:
            n['rate'] = (flag & 0b1111111111111111) + 1
            n['outDepth'] = (flag >> 16) & 0b1111
            n['stereo'] = bool((flag >> 20) & 1)
        elif chip == ChipType.QSOUND:
            n['echoDelay'] = flag & 0b1111111111111
            n['echoFeedback'] = (flag >> 16) & 0b11111111
        return n

    def __read_header(self, stream: BinaryIO) -> None:
        # assuming we passed the magic number check
        self.meta.version = read_short(stream)
        stream.read(2)  # RESERVED
        self.__song_info_ptr = read_int(stream)
        stream.read(8)  # RESERVED

    def __read_info(self, stream: BinaryIO) -> None:
        stream.seek(self.__song_info_ptr)
        if stream.read(4) != b'INFO':
            raise ValueError('No "INFO" magic')

        if self.meta.version < 100:  # don't read size prior to 0.6pre1
            stream.read(4)
            info_blk = stream
        else:
            blk_size = read_int(stream)
            info_blk = BytesIO(stream.read(blk_size))

        # info of first subsong
        self.subsongs[0].timing.timebase = (read_byte(info_blk) + 1)
        self.subsongs[0].timing.speed = (
            read_byte(info_blk),
            read_byte(info_blk)
        )
        self.subsongs[0].timing.arp_speed = read_byte(info_blk)
        self.subsongs[0].timing.clock_speed = read_float(info_blk)
        self.subsongs[0].pattern_length = read_short(info_blk)
        len_orders = read_short(info_blk)
        self.subsongs[0].timing.highlight = (
            read_byte(info_blk),
            read_byte(info_blk)
        )

        # global
        num_insts = read_short(info_blk)
        num_waves = read_short(info_blk)
        num_samples = read_short(info_blk)
        num_patterns = read_int(info_blk)

        # fetch chip list
        for chip_id in info_blk.read(MAX_CHIPS):
            if chip_id == 0:
                break  # seek position is after chips here
            self.chips.list.append(
                ChipInfo(ChipType(chip_id))  # type: ignore
            )

        # fetch volume
        for i in range(MAX_CHIPS):
            vol = read_byte(info_blk, True) / 64.0
            if i >= len(self.chips.list):  # cut here
                continue
            self.chips.list[i].volume = vol

        for i in range(MAX_CHIPS):
            pan = read_byte(info_blk, True) / 128.0
            if i >= len(self.chips.list):  # cut here
                continue
            self.chips.list[i].panning = pan

        if self.meta.version >= 119:
            self.__chip_flag_ptr: List[int] = [
                read_int(info_blk) for _ in range(MAX_CHIPS)
            ]
        else:
            for i in range(MAX_CHIPS):
                flag = read_int(info_blk)
                if i < len(self.chips.list):
                    self.chips.list[i].flags.update(
                        self.__convert_old_chip_flags(self.chips.list[i].type, flag)
                    )

        self.meta.name = read_str(info_blk)
        self.meta.author = read_str(info_blk)
        self.meta.tuning = read_float(info_blk)

        # Compat flags, part I
        self.__read_compat_flags(info_blk, 1)

        self.__instrument_ptr = [
            read_int(info_blk) for _ in range(num_insts)
        ]

        self.__wavetable_ptr = [
            read_int(info_blk) for _ in range(num_waves)
        ]

        self.__sample_ptr = [
            read_int(info_blk) for _ in range(num_samples)
        ]

        self.__pattern_ptr = [
            read_int(info_blk) for _ in range(num_patterns)
        ]

        num_channels = self.get_num_channels()

        for channel in range(self.get_num_channels()):
            self.subsongs[0].order[channel] = [
                read_byte(info_blk) for _ in range(len_orders)
            ]

        self.subsongs[0].effect_columns = [
            read_byte(info_blk) for _ in range(num_channels)
        ]

        # set up channels display info
        self.subsongs[0].channel_display = [
            ChannelDisplayInfo() for _ in range(num_channels)
        ]

        for i in range(num_channels):
            self.subsongs[0].channel_display[i].shown = bool(read_byte(info_blk))

        for i in range(num_channels):
            self.subsongs[0].channel_display[i].collapsed = bool(read_byte(info_blk))

        for i in range(num_channels):
            self.subsongs[0].channel_display[i].name = read_str(info_blk)

        for i in range(num_channels):
            self.subsongs[0].channel_display[i].abbreviation = read_str(info_blk)

        self.meta.comment = read_str(info_blk)

        # Master volume
        if self.meta.version >= 59:
            self.chips.master_volume = read_float(info_blk)

        # Compat flags, part II
        if self.meta.version >= 70:
            self.__read_compat_flags(info_blk, 2)
            if self.meta.version >= 96:
                self.subsongs[0].timing.virtual_tempo = (
                    read_short(info_blk), read_short(info_blk)
                )
            else:
                info_blk.read(4)  # reserved in self.meta.version < 96

        # Subsongs
        if self.meta.version >= 95:
            self.subsongs[0].name = read_str(info_blk)
            self.subsongs[0].comment = read_str(info_blk)
            num_extra_subsongs = read_byte(info_blk)
            info_blk.read(3)  # reserved
            self.__subsong_ptr = [
                read_int(info_blk) for _ in range(num_extra_subsongs)
            ]

        # Extra metadata
        if self.meta.version >= 103:
            self.meta.sys_name = read_str(info_blk)
            self.meta.album = read_str(info_blk)
            # TODO: need to take encoding into account
            self.meta.name_jp = read_str(info_blk)
            self.meta.author_jp = read_str(info_blk)
            self.meta.sys_name_jp = read_str(info_blk)
            self.meta.album_jp = read_str(info_blk)

        # New chip mixer and patchbay
        if self.meta.version >= 135:
            for i in range(len(self.chips.list)):
                # new chip volume/panning format takes precedence over the legacy one
                # if you save a .fur with this, legacy and new volume/panning formats
                # have the same value. different values shouldn't be possible
                self.chips.list[i].volume = read_float(info_blk)
                self.chips.list[i].panning = read_float(info_blk)
                self.chips.list[i].surround = read_float(info_blk)
            num_patchbay_connections = read_int(info_blk)
            for _ in range(num_patchbay_connections):
                src = read_short(info_blk)
                dst = read_short(info_blk)
                self.patchbay.append(
                    PatchBay(
                        dest=InputPatchBayEntry(
                            set=InputPortSet(src >> 4),
                            port=src & 0b1111
                        ),
                        source=OutputPatchBayEntry(
                            set=OutputPortSet(dst >> 4),
                            port=dst & 0b1111
                        )
                    )
                )

        if self.meta.version >= 136:
            self.compat_flags.auto_patchbay = bool(read_byte(info_blk))

        # Compat flags, part III
        if self.meta.version >= 138:
            self.__read_compat_flags(info_blk, 3)

        # Speed patterns and grooves
        if self.meta.version >= 139:
            # speed pattern
            len_speed_pattern = read_byte(info_blk)
            if (len_speed_pattern < 0) or (len_speed_pattern > 16):
                raise ValueError('Invalid speed pattern length value')
            self.subsongs[0].speed_pattern = [
                read_byte(info_blk) for _ in range(len_speed_pattern)
            ]
            info_blk.read(16 - len_speed_pattern)  # skip that many bytes, because it's always 0x06

            # groove
            len_groove_list = read_byte(info_blk)
            for _ in range(len_groove_list):
                len_groove = read_byte(info_blk)
                self.subsongs[0].grooves.append([
                    read_byte(info_blk) for _ in range(len_groove)
                ])
                info_blk.read(16 - len_groove)  # TODO: i assume the same as above. i hope i'm right

    def __read_instruments(self, stream: BinaryIO) -> None:
        for i in self.__instrument_ptr:
            if i == 0:
                break
            stream.seek(i)
            new_ins = FurnaceInstrument()
            if self.meta.version < 127:  # i trust this not to screw up
                new_ins.load_from_stream(stream, _FurInsImportType.FORMAT_0_EMBED)
            else:
                new_ins.load_from_stream(stream, _FurInsImportType.FORMAT_1_EMBED)
            self.instruments.append(new_ins)

    def __read_wavetables(self, stream: BinaryIO) -> None:
        for i in self.__wavetable_ptr:
            if i == 0:
                break
            stream.seek(i)
            new_wt = FurnaceWavetable()
            new_wt.load_from_stream(stream, _FurWavetableImportType.EMBED)
            self.wavetables.append(new_wt)

    def __read_samples(self, stream: BinaryIO) -> None:
        for i in self.__sample_ptr:
            if i == 0:
                break
            stream.seek(i)
            new_wt = FurnaceSample()
            new_wt.load_from_stream(stream)
            self.samples.append(new_wt)

    def __read_patterns(self, stream: BinaryIO) -> None:
        for i in self.__pattern_ptr:
            if i == 0:
                break
            stream.seek(i)

            # Old pattern
            if self.meta.version < 157:
                if stream.read(4) != b'PATR':
                    raise ValueError('No "PATR" magic')
                sz = read_int(stream)
                if sz == 0:
                    patr_blk = stream
                else:
                    patr_blk = BytesIO(stream.read(sz))

                new_patr = FurnacePattern()
                new_patr.channel = read_short(patr_blk)
                new_patr.index = read_short(patr_blk)
                new_patr.subsong = read_short(patr_blk)
                if self.meta.version < 95:
                    assert new_patr.subsong == 0
                read_short(patr_blk)  # reserved

                num_rows = self.subsongs[new_patr.subsong].pattern_length

                for _ in range(num_rows):
                    row = FurnaceRow(
                        note=Note(read_short(patr_blk)),
                        octave=read_short(patr_blk),
                        instrument=read_short(patr_blk),
                        volume=read_short(patr_blk)
                    )
                    row.octave += (1 if row.note == Note.C_ else 0)
                    effect_columns = self.subsongs[new_patr.subsong].effect_columns[new_patr.channel]
                    row.effects = [
                        (read_short(patr_blk), read_short(patr_blk)) for _ in range(effect_columns)
                    ]
                    new_patr.data.append(row)

                if self.meta.version >= 51:
                    new_patr.name = read_str(patr_blk)

            # New pattern
            else:
                if stream.read(4) != b'PATN':
                    raise ValueError('No "PATN" magic')
                sz = read_int(stream)
                if sz == 0:
                    patr_blk = stream
                else:
                    patr_blk = BytesIO(stream.read(sz))

                new_patr = FurnacePattern()
                new_patr.subsong = read_byte(patr_blk)
                new_patr.channel = read_byte(patr_blk)
                new_patr.index = read_short(patr_blk)
                new_patr.name = read_str(patr_blk)

                num_rows = self.subsongs[new_patr.subsong].pattern_length
                effect_columns = self.subsongs[new_patr.subsong].effect_columns[new_patr.channel]

                empty_row = lambda: FurnaceRow(Note.__, 0, 0xffff, 0xffff, [(0xffff,0xffff)] * effect_columns)

                row_idx = 0
                while row_idx < num_rows:
                    char = read_byte(patr_blk)
                    # end of pattern
                    if char == 0xff:
                        break
                    # skip N+2 rows
                    if char & 0x80:
                        skip = (char & 0x7f) + 2
                        row_idx += skip
                        for _ in range(skip):
                            new_patr.data.append(empty_row())
                        continue
                    # check if some values present
                    effect_present_list = [False] * 8
                    effect_val_present_list = [False] * 8
                    note_present = bool(char & 0x01)
                    ins_present = bool(char & 0x02)
                    volume_present = bool(char & 0x04)
                    effect_present_list[0] = bool(char & 0x08)
                    effect_val_present_list[0] = bool(char & 0x10)
                    effect_0_3_present = bool(char & 0x20)
                    effect_4_7_present = bool(char & 0x40)
                    if effect_0_3_present:
                        char = read_byte(patr_blk)
                        assert effect_present_list[0] == bool(char & 0x01)
                        assert effect_val_present_list[0] == bool(char & 0x02)
                        effect_present_list[1] = bool(char & 0x04)
                        effect_val_present_list[1] = bool(char & 0x08)
                        effect_present_list[2] = bool(char & 0x10)
                        effect_val_present_list[2] = bool(char & 0x20)
                        effect_present_list[3] = bool(char & 0x40)
                        effect_val_present_list[3] = bool(char & 0x80)
                    if effect_4_7_present:
                        char = read_byte(patr_blk)
                        effect_present_list[4] = bool(char & 0x01)
                        effect_val_present_list[4] = bool(char & 0x02)
                        effect_present_list[5] = bool(char & 0x04)
                        effect_val_present_list[5] = bool(char & 0x08)
                        effect_present_list[6] = bool(char & 0x10)
                        effect_val_present_list[6] = bool(char & 0x20)
                        effect_present_list[7] = bool(char & 0x40)
                        effect_val_present_list[7] = bool(char & 0x80)

                    # actually read present values
                    note, octave = Note(0), 0
                    if note_present:
                        raw_note = read_byte(patr_blk)
                        if raw_note == 180:
                            note = Note.OFF
                        elif raw_note == 181:
                            note = Note.OFF_REL
                        elif raw_note == 182:
                            note = Note.REL
                        else:
                            note = raw_note % 12
                            note = 12 if note == 0 else note
                            note = Note(note)
                            octave = -5 + raw_note // 12

                    ins, volume = 0xffff, 0xffff
                    if ins_present:
                        ins = read_byte(patr_blk)
                    if volume_present:
                        volume = read_byte(patr_blk)

                    row = FurnaceRow(
                        note=note,
                        octave=octave,
                        instrument=ins,
                        volume=volume
                    )

                    row.effects = [(0xffff,0xffff)] * effect_columns
                    for i, fx_presents in enumerate(zip(effect_present_list, effect_val_present_list)):
                        if i >= effect_columns:
                            break
                        fx_cmd, fx_val = 0xffff, 0xffff
                        if fx_presents[0]:
                            fx_cmd = read_byte(patr_blk)
                        if fx_presents[1]:
                            fx_val = read_byte(patr_blk)
                        row.effects[i] = (fx_cmd, fx_val)

                    new_patr.data.append(row)
                    row_idx += 1
                
                # fill the rest of the pattern with EMPTY
                while row_idx < num_rows:
                    new_patr.data.append(empty_row())
                    row_idx += 1

            self.patterns.append(new_patr)

    def __read_subsongs(self, stream: BinaryIO) -> None:
        for i in self.__subsong_ptr:
            if i == 0:
                break
            stream.seek(i)
            if stream.read(4) != b'SONG':
                raise ValueError('No "SONG" magic')
            subsong_blk = BytesIO(stream.read(read_int(stream)))
            new_subsong = SubSong()
            new_subsong.order.clear()
            new_subsong.speed_pattern.clear()

            new_subsong.timing.timebase = read_byte(subsong_blk)
            new_subsong.timing.speed = (
                read_byte(subsong_blk), read_byte(subsong_blk)
            )
            new_subsong.timing.arp_speed = read_byte(subsong_blk)
            new_subsong.timing.clock_speed = read_float(subsong_blk)
            new_subsong.pattern_length = read_short(subsong_blk)
            new_subsong_len_orders = read_short(subsong_blk)
            new_subsong.timing.highlight = (
                read_byte(subsong_blk), read_byte(subsong_blk)
            )
            new_subsong.timing.virtual_tempo = (
                read_short(subsong_blk), read_short(subsong_blk)
            )
            new_subsong.name = read_str(subsong_blk)
            new_subsong.comment = read_str(subsong_blk)

            num_channels = self.get_num_channels()

            for channel in range(self.get_num_channels()):
                new_subsong.order[channel] = [
                    read_byte(subsong_blk) for _ in range(new_subsong_len_orders)
                ]

            new_subsong.effect_columns = [
                read_byte(subsong_blk) for _ in range(num_channels)
            ]

            # set up channels display info
            new_subsong.channel_display = [
                ChannelDisplayInfo() for _ in range(num_channels)
            ]

            for i in range(num_channels):
                new_subsong.channel_display[i].shown = bool(read_byte(subsong_blk))

            for i in range(num_channels):
                new_subsong.channel_display[i].collapsed = bool(read_byte(subsong_blk))

            for i in range(num_channels):
                new_subsong.channel_display[i].name = read_str(subsong_blk)

            for i in range(num_channels):
                new_subsong.channel_display[i].abbreviation = read_str(subsong_blk)

            # Speed patterns and grooves
            if self.meta.version >= 139:
                # speed pattern
                len_speed_pattern = read_byte(subsong_blk)
                if (len_speed_pattern < 0) or (len_speed_pattern > 16):
                    raise ValueError('Invalid speed pattern length value')
                new_subsong.speed_pattern = [
                    read_byte(subsong_blk) for _ in range(len_speed_pattern)
                ]

            self.subsongs.append(new_subsong)

    def __str__(self) -> str:
        return '<Furnace ver. %d module "%s" by %s>' % (
            self.meta.version, self.meta.name, self.meta.author
        )
