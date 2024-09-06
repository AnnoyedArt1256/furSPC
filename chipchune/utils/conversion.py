from chipchune.furnace.module import FurnacePattern
from chipchune.interchange.enums import InterNote
from chipchune.interchange.furnace import furnace_note_to_internote
from typing import Union, List, Tuple
from dataclasses import dataclass, field

@dataclass
class SequenceEntry:
    """
    A representation of a row in note-length format. Such a format is commonly
    used across different sound engines and sequenced data.

    A pattern can be turned into a list of SequenceEntries, which should be easier
    to convert into a format of your choice.
    """
    note: InterNote
    length: int
    volume: int
    """
    Tracker-defined volume; although this should be -1 for undefined values.
    """
    octave: int
    """
    Tracker-defined octave; although this should be -1 for undefined values.
    """
    instrument: int
    """
    Tracker-defined instrument number; although this should be -1 for undefined values.
    """
    effects: List[Tuple[int, int]] = field(default_factory=list)
    """
    Tracker-defined effects list; if undefined, this should be empty.
    """

def pattern_to_sequence(pattern: Union[FurnacePattern, None]) -> List[SequenceEntry]:
    """
    Interface to convert a pattern from tracker rows to a "sequence", which is
    really a list of SequenceEntries.

    :param pattern:
        A pattern object. Supported types at the moment: `FurnacePattern`.
        Anything outside of the supported types will throw a `TypeError`.
    """
    if isinstance(pattern, FurnacePattern):
        return furnace_pattern_to_sequence(pattern)
    else:
        raise TypeError("Invalid pattern type; must be one of: FurnacePattern")

def furnace_pattern_to_sequence(pattern: FurnacePattern) -> List[SequenceEntry]:
    converted: List[SequenceEntry] = []
    last_volume = -1
    for i in pattern.data:
        note = furnace_note_to_internote(i.note)
        effects = i.effects
        volume = i.volume
        instrument = i.instrument

        if effects == [(65535, 65535)]:
            effects = []
        
        if volume == 65535:
            volume = last_volume
        else:
            last_volume = volume
        
        if instrument == 65535:
            instrument = -1
        
        if note == InterNote.__:
            if len(converted) == 0:
                converted.append(
                    SequenceEntry(
                        note=InterNote.__,
                        length=1,
                        volume=volume,
                        octave=i.octave,
                        instrument=instrument,
                        effects=effects,
                    )
                )
            else:
                converted[-1].length += 1
        else:
            converted.append(
                SequenceEntry(
                    note=note,
                    length=1,
                    volume=volume,
                    octave=i.octave,
                    instrument=instrument,
                    effects=effects,
                )
            )
    return converted
