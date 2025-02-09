import logging
import queue
import sys
from ctypes import byref, c_ulong, c_void_p, oledll
from typing import TYPE_CHECKING, Any, Literal, Optional, Sequence, Type

import comtypes
from comtypes import hresult
from comtypes.server import IClassFactory

if TYPE_CHECKING:
    from ctypes import _Pointer


logger = logging.getLogger(__name__)
_debug = logger.debug

REGCLS_SINGLEUSE = 0  # class object only generates one instance
REGCLS_MULTIPLEUSE = 1  # same class object genereates multiple inst.
REGCLS_MULTI_SEPARATE = 2  # multiple use, but separate control over each
REGCLS_SUSPENDED = 4  # register it as suspended, will be activated
REGCLS_SURROGATE = 8  # must be used when a surrogate process


def run(classes: Sequence[Type[comtypes.COMObject]]) -> None:
    classobjects = [ClassFactory(cls) for cls in classes]
    comtypes.COMObject.__run_localserver__(classobjects)


class ClassFactory(comtypes.COMObject):
    _com_interfaces_ = [IClassFactory]
    _locks: int = 0
    _queue: Optional[queue.Queue] = None
    regcls: int = REGCLS_MULTIPLEUSE

    def __init__(self, cls: Type[comtypes.COMObject], *args, **kw) -> None:
        super(ClassFactory, self).__init__()
        self._cls = cls
        self._register_class()
        self._args = args
        self._kw = kw

    def IUnknown_AddRef(self, this: Any) -> int:
        return 2

    def IUnknown_Release(self, this: Any) -> int:
        return 1

    def _register_class(self) -> None:
        regcls = getattr(self._cls, "_regcls_", self.regcls)
        cookie = c_ulong()
        ptr = self._com_pointers_[comtypes.IUnknown._iid_]
        clsctx = self._cls._reg_clsctx_
        clsctx &= ~comtypes.CLSCTX_INPROC  # reset the inproc flags
        oledll.ole32.CoRegisterClassObject(
            byref(comtypes.GUID(self._cls._reg_clsid_)),
            ptr,
            clsctx,
            regcls,
            byref(cookie),
        )
        self.cookie = cookie

    def _revoke_class(self) -> None:
        oledll.ole32.CoRevokeClassObject(self.cookie)

    def CreateInstance(
        self,
        this: Any,
        punkOuter: Optional[Type["_Pointer[comtypes.IUnknown]"]],
        riid: "_Pointer[comtypes.GUID]",
        ppv: c_void_p,
    ) -> int:
        _debug("ClassFactory.CreateInstance(%s)", riid[0])
        obj = self._cls(*self._args, **self._kw)
        result = obj.IUnknown_QueryInterface(None, riid, ppv)
        _debug("CreateInstance() -> %s", result)
        return result

    def LockServer(self, this: Any, fLock: bool) -> Literal[0]:
        if fLock:
            comtypes.COMObject.__server__.Lock()
        else:
            comtypes.COMObject.__server__.Unlock()
        return hresult.S_OK
