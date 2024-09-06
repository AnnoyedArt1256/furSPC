import enum
from chipchune._util import EnumShowNameOnly

class InterNote(EnumShowNameOnly):
    """
    Common note interchange format.
    """
    __ = enum.auto() # Signifies a blank space in tracker
    C_ = enum.auto()
    Cs = enum.auto()
    D_ = enum.auto()
    Ds = enum.auto()
    E_ = enum.auto()
    F_ = enum.auto()
    Fs = enum.auto()
    G_ = enum.auto()
    Gs = enum.auto()
    A_ =  enum.auto()
    As =  enum.auto()
    B_ =  enum.auto()
    Off =  enum.auto()
    OffRel =  enum.auto()
    Rel =  enum.auto()
    Echo =  enum.auto()
