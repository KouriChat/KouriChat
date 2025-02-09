"""comtypes.GUID module"""

from ctypes import oledll, windll
from ctypes import byref, c_wchar_p, Structure
from ctypes.wintypes import BYTE, WORD, DWORD
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from comtypes import hints  # type: ignore


def binary(obj: "GUID") -> bytes:
    return bytes(obj)


_ole32 = oledll.ole32

_StringFromCLSID = _ole32.StringFromCLSID
_CoTaskMemFree = windll.ole32.CoTaskMemFree
_ProgIDFromCLSID = _ole32.ProgIDFromCLSID
_CLSIDFromString = _ole32.CLSIDFromString
_CLSIDFromProgID = _ole32.CLSIDFromProgID
_CoCreateGuid = _ole32.CoCreateGuid

# Note: Comparing GUID instances by comparing their buffers
# is slightly faster than using ole32.IsEqualGUID.


class GUID(Structure):
    """Globally unique identifier structure."""

    _fields_ = [("Data1", DWORD), ("Data2", WORD), ("Data3", WORD), ("Data4", BYTE * 8)]

    def __init__(self, name=None):
        if name is not None:
            _CLSIDFromString(str(name), byref(self))

    def __repr__(self):
        return f'GUID("{str(self)}")'

    def __str__(self) -> str:
        p = c_wchar_p()
        _StringFromCLSID(byref(self), byref(p))
        result = p.value
        _CoTaskMemFree(p)
        # stringified `GUID_null` would be '{00000000-0000-0000-0000-000000000000}'
        # Should we do `assert result is not None`?
        return result  # type: ignore

    def __bool__(self) -> bool:
        return self != GUID_null

    def __eq__(self, other) -> bool:
        return isinstance(other, GUID) and binary(self) == binary(other)

    def __hash__(self) -> int:
        # We make GUID instances hashable, although they are mutable.
        return hash(binary(self))

    def copy(self) -> "GUID":
        return GUID(str(self))

    @classmethod
    def from_progid(cls, progid: Any) -> "hints.Self":
        """Get guid from progid, ..."""
        if hasattr(progid, "_reg_clsid_"):
            progid = progid._reg_clsid_
        if isinstance(progid, cls):
            return progid
        elif isinstance(progid, str):
            if progid.startswith("{"):
                return cls(progid)
            inst = cls()
            _CLSIDFromProgID(str(progid), byref(inst))
            return inst
        else:
            raise TypeError(f"Cannot construct guid from {progid!r}")

    def as_progid(self) -> str:
        """Convert a GUID into a progid"""
        progid = c_wchar_p()
        _ProgIDFromCLSID(byref(self), byref(progid))
        result = progid.value
        _CoTaskMemFree(progid)
        # Should we do `assert result is not None`?
        return result  # type: ignore

    @classmethod
    def create_new(cls) -> "hints.Self":
        """Create a brand new guid"""
        guid = cls()
        _CoCreateGuid(byref(guid))
        return guid


GUID_null = GUID()

__all__ = ["GUID"]
