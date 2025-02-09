from ctypes import c_char_p, c_int, c_short, c_wchar_p
from ctypes import POINTER
from ctypes import byref, create_string_buffer, create_unicode_buffer
from ctypes.wintypes import DWORD, WIN32_FIND_DATAA, WIN32_FIND_DATAW, MAX_PATH
from typing import Tuple, TYPE_CHECKING, Literal

from comtypes import IUnknown, GUID, COMMETHOD, HRESULT, CoClass


if TYPE_CHECKING:
    from comtypes import hints  # type: ignore


# for GetPath
SLGP_SHORTPATH = 0x1
SLGP_UNCPRIORITY = 0x2
SLGP_RAWPATH = 0x4

# for SetShowCmd, GetShowCmd
SW_SHOWNORMAL = 0x01
SW_SHOWMAXIMIZED = 0x03
SW_SHOWMINNOACTIVE = 0x07

# for Resolve
SLR_INVOKE_MSI = 0x0080
SLR_NOLINKINFO = 0x0040
SLR_NO_UI = 0x0001
SLR_NOUPDATE = 0x0008
SLR_NOSEARCH = 0x0010
SLR_NOTRACK = 0x0020
SLR_UPDATE = 0x0004

# for Hotkey
HOTKEYF_ALT = 0x04
HOTKEYF_CONTROL = 0x02
HOTKEYF_EXT = 0x08
HOTKEYF_SHIFT = 0x01

# fake these...
ITEMIDLIST = c_int
LPITEMIDLIST = LPCITEMIDLIST = POINTER(ITEMIDLIST)


class IShellLinkA(IUnknown):
    _iid_ = GUID("{000214EE-0000-0000-C000-000000000046}")
    _methods_ = [
        COMMETHOD(
            [],
            HRESULT,
            "GetPath",
            (["in", "out"], c_char_p, "pszFile"),
            (["in"], c_int, "cchMaxPath"),
            (["in", "out"], POINTER(WIN32_FIND_DATAA), "pfd"),
            (["in"], DWORD, "fFlags"),
        ),
        COMMETHOD(
            [],
            HRESULT,
            "GetIDList",
            (["retval", "out"], POINTER(LPITEMIDLIST), "ppidl"),
        ),
        COMMETHOD([], HRESULT, "SetIDList", (["in"], LPCITEMIDLIST, "pidl")),
        COMMETHOD(
            [],
            HRESULT,
            "GetDescription",
            (["in", "out"], c_char_p, "pszName"),
            (["in"], c_int, "cchMaxName"),
        ),
        COMMETHOD([], HRESULT, "SetDescription", (["in"], c_char_p, "pszName")),
        COMMETHOD(
            [],
            HRESULT,
            "GetWorkingDirectory",
            (["in", "out"], c_char_p, "pszDir"),
            (["in"], c_int, "cchMaxPath"),
        ),
        COMMETHOD([], HRESULT, "SetWorkingDirectory", (["in"], c_char_p, "pszDir")),
        COMMETHOD(
            [],
            HRESULT,
            "GetArguments",
            (["in", "out"], c_char_p, "pszArgs"),
            (["in"], c_int, "cchMaxPath"),
        ),
        COMMETHOD([], HRESULT, "SetArguments", (["in"], c_char_p, "pszArgs")),
        COMMETHOD(
            ["propget"],
            HRESULT,
            "Hotkey",
            (["retval", "out"], POINTER(c_short), "pwHotkey"),
        ),
        COMMETHOD(["propput"], HRESULT, "Hotkey", (["in"], c_short, "pwHotkey")),
        COMMETHOD(
            ["propget"],
            HRESULT,
            "ShowCmd",
            (["retval", "out"], POINTER(c_int), "piShowCmd"),
        ),
        COMMETHOD(["propput"], HRESULT, "ShowCmd", (["in"], c_int, "piShowCmd")),
        COMMETHOD(
            [],
            HRESULT,
            "GetIconLocation",
            (["in", "out"], c_char_p, "pszIconPath"),
            (["in"], c_int, "cchIconPath"),
            (["in", "out"], POINTER(c_int), "piIcon"),
        ),
        COMMETHOD(
            [],
            HRESULT,
            "SetIconLocation",
            (["in"], c_char_p, "pszIconPath"),
            (["in"], c_int, "iIcon"),
        ),
        COMMETHOD(
            [],
            HRESULT,
            "SetRelativePath",
            (["in"], c_char_p, "pszPathRel"),
            (["in"], DWORD, "dwReserved"),
        ),
        COMMETHOD(
            [], HRESULT, "Resolve", (["in"], c_int, "hwnd"), (["in"], DWORD, "fFlags")
        ),
        COMMETHOD([], HRESULT, "SetPath", (["in"], c_char_p, "pszFile")),
    ]

    if TYPE_CHECKING:

        def GetIDList(self) -> hints.Incomplete: ...
        def SetIDList(self, pidl: hints.Incomplete) -> hints.Incomplete: ...
        def SetDescription(self, pszName: bytes) -> hints.Incomplete: ...
        def SetWorkingDirectory(self, pszDir: bytes) -> hints.Hresult: ...
        def SetArguments(self, pszArgs: bytes) -> hints.Hresult: ...
        @property
        def Hotkey(self) -> int: ...
        @Hotkey.setter
        def Hotkey(self, pwHotkey: int) -> None: ...
        @property
        def ShowCmd(self) -> int: ...
        @ShowCmd.setter
        def ShowCmd(self, piShowCmd: int) -> None: ...
        def SetIconLocation(self, pszIconPath: bytes, iIcon: int) -> hints.Hresult: ...
        def SetRelativePath(
            self, pszPathRel: bytes, dwReserved: Literal[0]
        ) -> hints.Hresult: ...
        def Resolve(self, hwnd: int, fFlags: int) -> hints.Hresult: ...
        def SetPath(self, pszFile: bytes) -> hints.Hresult: ...

    def GetPath(self, flags: int = SLGP_SHORTPATH) -> bytes:
        buf = create_string_buffer(MAX_PATH)
        # We're not interested in WIN32_FIND_DATA
        self.__com_GetPath(buf, MAX_PATH, None, flags)  # type: ignore
        return buf.value

    def GetDescription(self) -> bytes:
        buf = create_string_buffer(1024)
        self.__com_GetDescription(buf, 1024)  # type: ignore
        return buf.value

    def GetWorkingDirectory(self) -> bytes:
        buf = create_string_buffer(MAX_PATH)
        self.__com_GetWorkingDirectory(buf, MAX_PATH)  # type: ignore
        return buf.value

    def GetArguments(self) -> bytes:
        buf = create_string_buffer(1024)
        self.__com_GetArguments(buf, 1024)  # type: ignore
        return buf.value

    def GetIconLocation(self) -> Tuple[bytes, int]:
        iIcon = c_int()
        buf = create_string_buffer(MAX_PATH)
        self.__com_GetIconLocation(buf, MAX_PATH, byref(iIcon))  # type: ignore
        return buf.value, iIcon.value


class IShellLinkW(IUnknown):
    _iid_ = GUID("{000214F9-0000-0000-C000-000000000046}")
    _methods_ = [
        COMMETHOD(
            [],
            HRESULT,
            "GetPath",
            (["in", "out"], c_wchar_p, "pszFile"),
            (["in"], c_int, "cchMaxPath"),
            (["in", "out"], POINTER(WIN32_FIND_DATAW), "pfd"),
            (["in"], DWORD, "fFlags"),
        ),
        COMMETHOD(
            [],
            HRESULT,
            "GetIDList",
            (["retval", "out"], POINTER(LPITEMIDLIST), "ppidl"),
        ),
        COMMETHOD([], HRESULT, "SetIDList", (["in"], LPCITEMIDLIST, "pidl")),
        COMMETHOD(
            [],
            HRESULT,
            "GetDescription",
            (["in", "out"], c_wchar_p, "pszName"),
            (["in"], c_int, "cchMaxName"),
        ),
        COMMETHOD([], HRESULT, "SetDescription", (["in"], c_wchar_p, "pszName")),
        COMMETHOD(
            [],
            HRESULT,
            "GetWorkingDirectory",
            (["in", "out"], c_wchar_p, "pszDir"),
            (["in"], c_int, "cchMaxPath"),
        ),
        COMMETHOD([], HRESULT, "SetWorkingDirectory", (["in"], c_wchar_p, "pszDir")),
        COMMETHOD(
            [],
            HRESULT,
            "GetArguments",
            (["in", "out"], c_wchar_p, "pszArgs"),
            (["in"], c_int, "cchMaxPath"),
        ),
        COMMETHOD([], HRESULT, "SetArguments", (["in"], c_wchar_p, "pszArgs")),
        COMMETHOD(
            ["propget"],
            HRESULT,
            "Hotkey",
            (["retval", "out"], POINTER(c_short), "pwHotkey"),
        ),
        COMMETHOD(["propput"], HRESULT, "Hotkey", (["in"], c_short, "pwHotkey")),
        COMMETHOD(
            ["propget"],
            HRESULT,
            "ShowCmd",
            (["retval", "out"], POINTER(c_int), "piShowCmd"),
        ),
        COMMETHOD(["propput"], HRESULT, "ShowCmd", (["in"], c_int, "piShowCmd")),
        COMMETHOD(
            [],
            HRESULT,
            "GetIconLocation",
            (["in", "out"], c_wchar_p, "pszIconPath"),
            (["in"], c_int, "cchIconPath"),
            (["in", "out"], POINTER(c_int), "piIcon"),
        ),
        COMMETHOD(
            [],
            HRESULT,
            "SetIconLocation",
            (["in"], c_wchar_p, "pszIconPath"),
            (["in"], c_int, "iIcon"),
        ),
        COMMETHOD(
            [],
            HRESULT,
            "SetRelativePath",
            (["in"], c_wchar_p, "pszPathRel"),
            (["in"], DWORD, "dwReserved"),
        ),
        COMMETHOD(
            [], HRESULT, "Resolve", (["in"], c_int, "hwnd"), (["in"], DWORD, "fFlags")
        ),
        COMMETHOD([], HRESULT, "SetPath", (["in"], c_wchar_p, "pszFile")),
    ]

    if TYPE_CHECKING:

        def GetIDList(self) -> hints.Incomplete: ...
        def SetIDList(self, pidl: hints.Incomplete) -> hints.Incomplete: ...
        def SetDescription(self, pszName: str) -> hints.Incomplete: ...
        def SetWorkingDirectory(self, pszDir: str) -> hints.Hresult: ...
        def SetArguments(self, pszArgs: str) -> hints.Hresult: ...
        @property
        def Hotkey(self) -> int: ...
        @Hotkey.setter
        def Hotkey(self, pwHotkey: int) -> None: ...
        @property
        def ShowCmd(self) -> int: ...
        @ShowCmd.setter
        def ShowCmd(self, piShowCmd: int) -> None: ...
        def SetIconLocation(self, pszIconPath: str, iIcon: int) -> hints.Hresult: ...
        def SetRelativePath(
            self, pszPathRel: str, dwReserved: Literal[0]
        ) -> hints.Hresult: ...
        def Resolve(self, hwnd: int, fFlags: int) -> hints.Hresult: ...
        def SetPath(self, pszFile: str) -> hints.Hresult: ...

    def GetPath(self, flags: int = SLGP_SHORTPATH) -> str:
        buf = create_unicode_buffer(MAX_PATH)
        # We're not interested in WIN32_FIND_DATA
        self.__com_GetPath(buf, MAX_PATH, None, flags)  # type: ignore
        return buf.value

    def GetDescription(self) -> str:
        buf = create_unicode_buffer(1024)
        self.__com_GetDescription(buf, 1024)  # type: ignore
        return buf.value

    def GetWorkingDirectory(self) -> str:
        buf = create_unicode_buffer(MAX_PATH)
        self.__com_GetWorkingDirectory(buf, MAX_PATH)  # type: ignore
        return buf.value

    def GetArguments(self) -> str:
        buf = create_unicode_buffer(1024)
        self.__com_GetArguments(buf, 1024)  # type: ignore
        return buf.value

    def GetIconLocation(self) -> Tuple[str, int]:
        iIcon = c_int()
        buf = create_unicode_buffer(MAX_PATH)
        self.__com_GetIconLocation(buf, MAX_PATH, byref(iIcon))  # type: ignore
        return buf.value, iIcon.value


class ShellLink(CoClass):
    """ShellLink class"""

    _reg_clsid_ = GUID("{00021401-0000-0000-C000-000000000046}")
    _idlflags_ = []
    _com_interfaces_ = [IShellLinkW, IShellLinkA]
