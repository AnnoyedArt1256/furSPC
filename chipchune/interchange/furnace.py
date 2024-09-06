from chipchune.furnace.enums import Note as FurnaceNote
from chipchune.interchange.enums import InterNote

def furnace_note_to_internote(note: FurnaceNote) -> InterNote:
    """
    Convert a Furnace note into an InterNote.

    Raises:
    - Exception: If the supplied note is out of range.
    """
    if note == FurnaceNote.__: return InterNote.__
    elif note == FurnaceNote.C_: return InterNote.C_
    elif note == FurnaceNote.Cs: return InterNote.Cs
    elif note == FurnaceNote.D_: return InterNote.D_
    elif note == FurnaceNote.Ds: return InterNote.Ds
    elif note == FurnaceNote.E_: return InterNote.E_
    elif note == FurnaceNote.F_: return InterNote.F_
    elif note == FurnaceNote.Fs: return InterNote.Fs
    elif note == FurnaceNote.G_: return InterNote.G_
    elif note == FurnaceNote.Gs: return InterNote.Gs
    elif note == FurnaceNote.A_: return InterNote.A_
    elif note == FurnaceNote.As: return InterNote.As
    elif note == FurnaceNote.B_: return InterNote.B_
    elif note == FurnaceNote.OFF: return InterNote.Off
    elif note == FurnaceNote.OFF_REL: return InterNote.OffRel
    elif note == FurnaceNote.REL: return InterNote.Rel
    else:
        raise Exception("Invalid note value %s" % note)

def internote_to_furnace_note(note: InterNote) -> FurnaceNote:
    """
    Convert an InterNote into a Furnace note. If the equivalent
    value is unable to be determined, a blank note `__` is returned.
    """
    if note == InterNote.__: return FurnaceNote.__
    elif note == InterNote.C_: return FurnaceNote.C_
    elif note == InterNote.Cs: return FurnaceNote.Cs
    elif note == InterNote.D_: return FurnaceNote.D_
    elif note == InterNote.Ds: return FurnaceNote.Ds
    elif note == InterNote.E_: return FurnaceNote.E_
    elif note == InterNote.F_: return FurnaceNote.F_
    elif note == InterNote.Fs: return FurnaceNote.Fs
    elif note == InterNote.G_: return FurnaceNote.G_
    elif note == InterNote.Gs: return FurnaceNote.Gs
    elif note == InterNote.A_: return FurnaceNote.A_
    elif note == InterNote.As: return FurnaceNote.As
    elif note == InterNote.B_: return FurnaceNote.B_
    elif note == InterNote.Off: return FurnaceNote.OFF
    elif note == InterNote.OffRel: return FurnaceNote.OFF_REL
    elif note == InterNote.Rel: return FurnaceNote.REL
    else:
        return FurnaceNote.__