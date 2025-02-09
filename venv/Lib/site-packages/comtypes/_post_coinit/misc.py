from ctypes import c_ulong, c_ushort, c_void_p, c_wchar_p, HRESULT, Structure
from ctypes import byref, cast, _Pointer, POINTER, pointer

# fmt: off
from typing import (  # noqa
    Any, overload, TYPE_CHECKING, TypeVar,
    # instead of `builtins`. see PEP585
    Type,
    # instead of `collections.abc`. see PEP585
    Callable,
    # instead of `A | B` and `None | A`. see PEP604
    Optional,
)
# fmt: on
if TYPE_CHECKING:
    from comtypes import hints as hints  # noqa  # type: ignore

from comtypes import GUID
from comtypes import CLSCTX_SERVER, CLSCTX_LOCAL_SERVER, CLSCTX_REMOTE_SERVER
from comtypes import _ole32, oledll, DWORD
from comtypes._memberspec import COMMETHOD
from comtypes._post_coinit.unknwn import IUnknown


def _is_object(obj):
    """This function determines if the argument is a COM object.  It
    is used in several places to determine whether propputref or
    propput setters have to be used."""
    from comtypes.automation import VARIANT

    # A COM pointer is an 'Object'
    if isinstance(obj, POINTER(IUnknown)):
        return True
    # A COM pointer in a VARIANT is an 'Object', too
    elif isinstance(obj, VARIANT) and isinstance(obj.value, POINTER(IUnknown)):
        return True
    # It may be a dynamic dispatch object.
    return hasattr(obj, "_comobj")


_T_IUnknown = TypeVar("_T_IUnknown", bound=IUnknown)


################################################################
# IPersist is a trivial interface, which allows to ask an object about
# its clsid.
class IPersist(IUnknown):
    _iid_ = GUID("{0000010C-0000-0000-C000-000000000046}")
    _idlflags_ = []
    _methods_ = [
        COMMETHOD([], HRESULT, "GetClassID", (["out"], POINTER(GUID), "pClassID")),
    ]
    if TYPE_CHECKING:
        # Should this be "normal" method that calls `self._GetClassID`?
        def GetClassID(self) -> GUID:
            """Returns the CLSID that uniquely represents an object class that
            defines the code that can manipulate the object's data.
            """
            ...


class IServiceProvider(IUnknown):
    _iid_ = GUID("{6D5140C1-7436-11CE-8034-00AA006009FA}")
    _QueryService: Callable[[Any, Any, Any], int]

    # Overridden QueryService to make it nicer to use (passing it an
    # interface and it returns a pointer to that interface)
    def QueryService(
        self, serviceIID: GUID, interface: Type[_T_IUnknown]
    ) -> _T_IUnknown:
        p = POINTER(interface)()
        self._QueryService(byref(serviceIID), byref(interface._iid_), byref(p))
        return p  # type: ignore

    _methods_ = [
        COMMETHOD(
            [],
            HRESULT,
            "QueryService",
            (["in"], POINTER(GUID), "guidService"),
            (["in"], POINTER(GUID), "riid"),
            (["in"], POINTER(c_void_p), "ppvObject"),
        )
    ]


################################################################


@overload
def CoGetObject(displayname: str, interface: None) -> IUnknown: ...
@overload
def CoGetObject(displayname: str, interface: Type[_T_IUnknown]) -> _T_IUnknown: ...
def CoGetObject(displayname: str, interface: Optional[Type[IUnknown]]) -> IUnknown:
    """Convert a displayname to a moniker, then bind and return the object
    identified by the moniker."""
    if interface is None:
        interface = IUnknown
    punk = POINTER(interface)()
    # Do we need a way to specify the BIND_OPTS parameter?
    _ole32.CoGetObject(str(displayname), None, byref(interface._iid_), byref(punk))
    return punk  # type: ignore


_pUnkOuter = Type["_Pointer[IUnknown]"]


@overload
def CoCreateInstance(
    clsid: GUID,
    interface: None = None,
    clsctx: Optional[int] = None,
    punkouter: Optional[_pUnkOuter] = None,
) -> IUnknown: ...
@overload
def CoCreateInstance(
    clsid: GUID,
    interface: Type[_T_IUnknown],
    clsctx: Optional[int] = None,
    punkouter: Optional[_pUnkOuter] = None,
) -> _T_IUnknown: ...
def CoCreateInstance(
    clsid: GUID,
    interface: Optional[Type[IUnknown]] = None,
    clsctx: Optional[int] = None,
    punkouter: Optional[_pUnkOuter] = None,
) -> IUnknown:
    """The basic windows api to create a COM class object and return a
    pointer to an interface.
    """
    if clsctx is None:
        clsctx = CLSCTX_SERVER
    if interface is None:
        interface = IUnknown
    p = POINTER(interface)()
    iid = interface._iid_
    _ole32.CoCreateInstance(byref(clsid), punkouter, clsctx, byref(iid), byref(p))
    return p  # type: ignore


if TYPE_CHECKING:

    @overload
    def CoGetClassObject(
        clsid: GUID,
        clsctx: Optional[int] = None,
        pServerInfo: "Optional[COSERVERINFO]" = None,
        interface: None = None,
    ) -> hints.IClassFactory: ...
    @overload
    def CoGetClassObject(
        clsid: GUID,
        clsctx: Optional[int] = None,
        pServerInfo: "Optional[COSERVERINFO]" = None,
        interface: Type[_T_IUnknown] = hints.IClassFactory,
    ) -> _T_IUnknown: ...


def CoGetClassObject(clsid, clsctx=None, pServerInfo=None, interface=None):
    # type: (GUID, Optional[int], Optional[COSERVERINFO], Optional[Type[IUnknown]]) -> IUnknown
    if clsctx is None:
        clsctx = CLSCTX_SERVER
    if interface is None:
        import comtypes.server

        interface = comtypes.server.IClassFactory
    p = POINTER(interface)()
    _CoGetClassObject(clsid, clsctx, pServerInfo, interface._iid_, byref(p))
    return p  # type: ignore


@overload
def GetActiveObject(clsid: GUID, interface: None = None) -> IUnknown: ...
@overload
def GetActiveObject(clsid: GUID, interface: Type[_T_IUnknown]) -> _T_IUnknown: ...
def GetActiveObject(
    clsid: GUID, interface: Optional[Type[IUnknown]] = None
) -> IUnknown:
    """Retrieves a pointer to a running object"""
    p = POINTER(IUnknown)()
    oledll.oleaut32.GetActiveObject(byref(clsid), None, byref(p))
    if interface is not None:
        p = p.QueryInterface(interface)  # type: ignore
    return p  # type: ignore


class MULTI_QI(Structure):
    _fields_ = [("pIID", POINTER(GUID)), ("pItf", POINTER(c_void_p)), ("hr", HRESULT)]
    if TYPE_CHECKING:
        pIID: GUID
        pItf: _Pointer[c_void_p]
        hr: HRESULT


class _COAUTHIDENTITY(Structure):
    _fields_ = [
        ("User", POINTER(c_ushort)),
        ("UserLength", c_ulong),
        ("Domain", POINTER(c_ushort)),
        ("DomainLength", c_ulong),
        ("Password", POINTER(c_ushort)),
        ("PasswordLength", c_ulong),
        ("Flags", c_ulong),
    ]


COAUTHIDENTITY = _COAUTHIDENTITY


class _COAUTHINFO(Structure):
    _fields_ = [
        ("dwAuthnSvc", c_ulong),
        ("dwAuthzSvc", c_ulong),
        ("pwszServerPrincName", c_wchar_p),
        ("dwAuthnLevel", c_ulong),
        ("dwImpersonationLevel", c_ulong),
        ("pAuthIdentityData", POINTER(_COAUTHIDENTITY)),
        ("dwCapabilities", c_ulong),
    ]


COAUTHINFO = _COAUTHINFO


class _COSERVERINFO(Structure):
    _fields_ = [
        ("dwReserved1", c_ulong),
        ("pwszName", c_wchar_p),
        ("pAuthInfo", POINTER(_COAUTHINFO)),
        ("dwReserved2", c_ulong),
    ]
    if TYPE_CHECKING:
        dwReserved1: int
        pwszName: Optional[str]
        pAuthInfo: _COAUTHINFO
        dwReserved2: int


COSERVERINFO = _COSERVERINFO
_CoGetClassObject = _ole32.CoGetClassObject
_CoGetClassObject.argtypes = [
    POINTER(GUID),
    DWORD,
    POINTER(COSERVERINFO),
    POINTER(GUID),
    POINTER(c_void_p),
]


class tagBIND_OPTS(Structure):
    _fields_ = [
        ("cbStruct", c_ulong),
        ("grfFlags", c_ulong),
        ("grfMode", c_ulong),
        ("dwTickCountDeadline", c_ulong),
    ]


# XXX Add __init__ which sets cbStruct?
BIND_OPTS = tagBIND_OPTS


class tagBIND_OPTS2(Structure):
    _fields_ = [
        ("cbStruct", c_ulong),
        ("grfFlags", c_ulong),
        ("grfMode", c_ulong),
        ("dwTickCountDeadline", c_ulong),
        ("dwTrackFlags", c_ulong),
        ("dwClassContext", c_ulong),
        ("locale", c_ulong),
        ("pServerInfo", POINTER(_COSERVERINFO)),
    ]


# XXX Add __init__ which sets cbStruct?
BINDOPTS2 = tagBIND_OPTS2


# Structures for security setups
#########################################
class _SEC_WINNT_AUTH_IDENTITY(Structure):
    _fields_ = [
        ("User", POINTER(c_ushort)),
        ("UserLength", c_ulong),
        ("Domain", POINTER(c_ushort)),
        ("DomainLength", c_ulong),
        ("Password", POINTER(c_ushort)),
        ("PasswordLength", c_ulong),
        ("Flags", c_ulong),
    ]


SEC_WINNT_AUTH_IDENTITY = _SEC_WINNT_AUTH_IDENTITY


class _SOLE_AUTHENTICATION_INFO(Structure):
    _fields_ = [
        ("dwAuthnSvc", c_ulong),
        ("dwAuthzSvc", c_ulong),
        ("pAuthInfo", POINTER(_SEC_WINNT_AUTH_IDENTITY)),
    ]


SOLE_AUTHENTICATION_INFO = _SOLE_AUTHENTICATION_INFO


class _SOLE_AUTHENTICATION_LIST(Structure):
    _fields_ = [
        ("cAuthInfo", c_ulong),
        ("pAuthInfo", POINTER(_SOLE_AUTHENTICATION_INFO)),
    ]


SOLE_AUTHENTICATION_LIST = _SOLE_AUTHENTICATION_LIST


@overload
def CoCreateInstanceEx(
    clsid: GUID,
    interface: None = None,
    clsctx: Optional[int] = None,
    machine: Optional[str] = None,
    pServerInfo: Optional[COSERVERINFO] = None,
) -> IUnknown: ...
@overload
def CoCreateInstanceEx(
    clsid: GUID,
    interface: Type[_T_IUnknown],
    clsctx: Optional[int] = None,
    machine: Optional[str] = None,
    pServerInfo: Optional[COSERVERINFO] = None,
) -> _T_IUnknown: ...
def CoCreateInstanceEx(
    clsid: GUID,
    interface: Optional[Type[IUnknown]] = None,
    clsctx: Optional[int] = None,
    machine: Optional[str] = None,
    pServerInfo: Optional[COSERVERINFO] = None,
) -> IUnknown:
    """The basic windows api to create a COM class object and return a
    pointer to an interface, possibly on another machine.

    Passing both "machine" and "pServerInfo" results in a ValueError.

    """
    if clsctx is None:
        clsctx = CLSCTX_LOCAL_SERVER | CLSCTX_REMOTE_SERVER

    if pServerInfo is not None:
        if machine is not None:
            msg = "Can not specify both machine name and server info"
            raise ValueError(msg)
    elif machine is not None:
        serverinfo = COSERVERINFO()
        serverinfo.pwszName = machine
        pServerInfo = byref(serverinfo)  # type: ignore

    if interface is None:
        interface = IUnknown
    multiqi = MULTI_QI()
    multiqi.pIID = pointer(interface._iid_)  # type: ignore
    _ole32.CoCreateInstanceEx(
        byref(clsid), None, clsctx, pServerInfo, 1, byref(multiqi)
    )
    return cast(multiqi.pItf, POINTER(interface))  # type: ignore
