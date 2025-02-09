# comtypes version numbers follow semver (http://semver.org/) and PEP 440
__version__ = "1.4.9"

try:
    from _ctypes import COMError  # noqa
except ImportError as e:
    msg = "\n".join(
        (
            "COM technology not available (maybe it's the wrong platform).",
            "Note that COM is only supported on Windows.",
            "For more details, please check: "
            "https://learn.microsoft.com/en-us/windows/win32/com",
        )
    )
    raise ImportError(msg) from e

import atexit

# HACK: Workaround for projects that depend on this package
# There should be several projects around the world that depend on this package
# and indirectly reference the symbols of `ctypes` from `comtypes`.
# If we remove the wildcard import from `ctypes`, they might break. So it is
# left in the following line.
from ctypes import *  # noqa
from ctypes import HRESULT  # noqa
from ctypes import _Pointer, _SimpleCData  # noqa
from ctypes import c_int, c_ulong, oledll, windll
from ctypes.wintypes import DWORD  # noqa
import logging
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ctypes import _CData  # only in `typeshed`, private in runtime
    from comtypes import hints as hints  # noqa  # type: ignore
else:
    _CData = _SimpleCData.__mro__[:-1][-1]

from comtypes.GUID import GUID
from comtypes import patcher  # noqa
from comtypes._npsupport import interop as npsupport  # noqa
from comtypes._tlib_version_checker import _check_version  # noqa

_all_slice = slice(None, None, None)


class NullHandler(logging.Handler):
    """A Handler that does nothing."""

    def emit(self, record):
        pass


logger = logging.getLogger(__name__)

# Add a NULL handler to the comtypes logger.  This prevents getting a
# message like this:
#    No handlers could be found for logger "comtypes"
# when logging is not configured and logger.error() is called.
logger.addHandler(NullHandler())


class ReturnHRESULT(Exception):
    """ReturnHRESULT(hresult, text)

    Return a hresult code from a COM method implementation
    without logging an error.
    """


# class IDLWarning(UserWarning):
#    "Warn about questionable type information"

_GUID = GUID
IID = GUID

wireHWND = c_ulong

################################################################
# About COM apartments:
# http://blogs.msdn.com/larryosterman/archive/2004/04/28/122240.aspx
################################################################

################################################################
# constants for object creation
CLSCTX_INPROC_SERVER = 1
CLSCTX_INPROC_HANDLER = 2
CLSCTX_LOCAL_SERVER = 4

CLSCTX_INPROC = 3
CLSCTX_SERVER = 5
CLSCTX_ALL = 7

CLSCTX_INPROC_SERVER16 = 8
CLSCTX_REMOTE_SERVER = 16
CLSCTX_INPROC_HANDLER16 = 32
CLSCTX_RESERVED1 = 64
CLSCTX_RESERVED2 = 128
CLSCTX_RESERVED3 = 256
CLSCTX_RESERVED4 = 512
CLSCTX_NO_CODE_DOWNLOAD = 1024
CLSCTX_RESERVED5 = 2048
CLSCTX_NO_CUSTOM_MARSHAL = 4096
CLSCTX_ENABLE_CODE_DOWNLOAD = 8192
CLSCTX_NO_FAILURE_LOG = 16384
CLSCTX_DISABLE_AAA = 32768
CLSCTX_ENABLE_AAA = 65536
CLSCTX_FROM_DEFAULT_CONTEXT = 131072

tagCLSCTX = c_int  # enum
CLSCTX = tagCLSCTX

# Constants for security setups
SEC_WINNT_AUTH_IDENTITY_UNICODE = 0x2
RPC_C_AUTHN_WINNT = 10
RPC_C_AUTHZ_NONE = 0
RPC_C_AUTHN_LEVEL_CONNECT = 2
RPC_C_IMP_LEVEL_IMPERSONATE = 3
EOAC_NONE = 0


################################################################
# Initialization and shutdown
_ole32 = oledll.ole32
_ole32_nohresult = windll.ole32  # use this for functions that don't return a HRESULT

COINIT_MULTITHREADED = 0x0
COINIT_APARTMENTTHREADED = 0x2
COINIT_DISABLE_OLE1DDE = 0x4
COINIT_SPEED_OVER_MEMORY = 0x8


def CoInitialize():
    return CoInitializeEx(COINIT_APARTMENTTHREADED)


def CoInitializeEx(flags=None):
    if flags is None:
        flags = getattr(sys, "coinit_flags", COINIT_APARTMENTTHREADED)
    logger.debug("CoInitializeEx(None, %s)", flags)
    _ole32.CoInitializeEx(None, flags)


# COM is initialized automatically for the thread that imports this
# module for the first time.  sys.coinit_flags is passed as parameter
# to CoInitializeEx, if defined, otherwise COINIT_APARTMENTTHREADED
# (COINIT_MULTITHREADED on Windows CE) is used.
#
# A shutdown function is registered with atexit, so that
# CoUninitialize is called when Python is shut down.
CoInitializeEx()


# We need to have CoUninitialize for multithreaded model where we have
# to initialize and uninitialize COM for every new thread (except main)
# in which we are using COM
def CoUninitialize():
    logger.debug("CoUninitialize()")
    _ole32_nohresult.CoUninitialize()


################################################################
# global registries.

# allows to find interface classes by guid strings (iid)
com_interface_registry = {}

# allows to find coclasses by guid strings (clsid)
com_coclass_registry = {}


################################################################
# IDL stuff

from comtypes._memberspec import (  # noqa
    COMMETHOD,
    DISPMETHOD,
    DISPPROPERTY,
    STDMETHOD,
    defaultvalue,
    dispid,
    helpstring,
)

################################################################
# IUnknown, the root of all evil...
from comtypes._post_coinit import _shutdown
from comtypes._post_coinit.unknwn import IUnknown  # noqa

atexit.register(_shutdown)

################################################################

from comtypes._post_coinit.bstr import BSTR  # noqa


################################################################
# IPersist is a trivial interface, which allows to ask an object about
# its clsid.
from comtypes._post_coinit.misc import IPersist, IServiceProvider  # noqa


################################################################


from comtypes._post_coinit.instancemethod import instancemethod  # noqa
from comtypes._post_coinit.misc import (  # noqa
    _is_object,
    CoGetObject,
    CoCreateInstance,
    CoGetClassObject,
    GetActiveObject,
    MULTI_QI,
    _COAUTHIDENTITY,
    COAUTHIDENTITY,
    _COAUTHINFO,
    COAUTHINFO,
    _COSERVERINFO,
    COSERVERINFO,
    _CoGetClassObject,
    tagBIND_OPTS,
    BIND_OPTS,
    tagBIND_OPTS2,
    BINDOPTS2,
    _SEC_WINNT_AUTH_IDENTITY,
    SEC_WINNT_AUTH_IDENTITY,
    _SOLE_AUTHENTICATION_INFO,
    SOLE_AUTHENTICATION_INFO,
    _SOLE_AUTHENTICATION_LIST,
    SOLE_AUTHENTICATION_LIST,
    CoCreateInstanceEx,
)


################################################################
from comtypes._comobject import COMObject

# What's a coclass?
# a POINTER to a coclass is allowed as parameter in a function declaration:
# http://msdn.microsoft.com/library/en-us/midl/midl/oleautomation.asp

from comtypes._meta import _coclass_meta


class CoClass(COMObject, metaclass=_coclass_meta):
    pass


################################################################


# fmt: off
__known_symbols__ = [
    "BIND_OPTS", "tagBIND_OPTS", "BINDOPTS2", "tagBIND_OPTS2", "BSTR",
    "_check_version", "CLSCTX", "tagCLSCTX", "CLSCTX_ALL",
    "CLSCTX_DISABLE_AAA", "CLSCTX_ENABLE_AAA", "CLSCTX_ENABLE_CODE_DOWNLOAD",
    "CLSCTX_FROM_DEFAULT_CONTEXT", "CLSCTX_INPROC", "CLSCTX_INPROC_HANDLER",
    "CLSCTX_INPROC_HANDLER16", "CLSCTX_INPROC_SERVER",
    "CLSCTX_INPROC_SERVER16", "CLSCTX_LOCAL_SERVER", "CLSCTX_NO_CODE_DOWNLOAD",
    "CLSCTX_NO_CUSTOM_MARSHAL", "CLSCTX_NO_FAILURE_LOG",
    "CLSCTX_REMOTE_SERVER", "CLSCTX_RESERVED1", "CLSCTX_RESERVED2",
    "CLSCTX_RESERVED3", "CLSCTX_RESERVED4", "CLSCTX_RESERVED5",
    "CLSCTX_SERVER", "_COAUTHIDENTITY", "COAUTHIDENTITY", "_COAUTHINFO",
    "COAUTHINFO", "CoClass", "CoCreateInstance", "CoCreateInstanceEx",
    "_CoGetClassObject", "CoGetClassObject", "CoGetObject",
    "COINIT_APARTMENTTHREADED", "COINIT_DISABLE_OLE1DDE",
    "COINIT_MULTITHREADED", "COINIT_SPEED_OVER_MEMORY", "CoInitialize",
    "CoInitializeEx", "COMError", "COMMETHOD", "COMObject", "_COSERVERINFO",
    "COSERVERINFO", "CoUninitialize", "dispid", "DISPMETHOD", "DISPPROPERTY",
    "DWORD", "EOAC_NONE", "GetActiveObject", "_GUID", "GUID", "helpstring",
    "IID", "IPersist", "IServiceProvider", "IUnknown", "MULTI_QI",
    "ReturnHRESULT", "RPC_C_AUTHN_LEVEL_CONNECT", "RPC_C_AUTHN_WINNT",
    "RPC_C_AUTHZ_NONE", "RPC_C_IMP_LEVEL_IMPERSONATE",
    "_SEC_WINNT_AUTH_IDENTITY", "SEC_WINNT_AUTH_IDENTITY",
    "SEC_WINNT_AUTH_IDENTITY_UNICODE", "_SOLE_AUTHENTICATION_INFO",
    "SOLE_AUTHENTICATION_INFO", "_SOLE_AUTHENTICATION_LIST",
    "SOLE_AUTHENTICATION_LIST", "STDMETHOD", "wireHWND",
]
# fmt: on
