import ctypes
import logging
import sys
import winreg
from typing import Any, Literal, Optional, Type

from comtypes import GUID, COMObject, IUnknown, hresult
from comtypes.server import IClassFactory

logger = logging.getLogger(__name__)
_debug = logger.debug
_critical = logger.critical

################################################################


class ClassFactory(COMObject):
    _com_interfaces_ = [IClassFactory]

    def __init__(self, cls: Type[COMObject]) -> None:
        super(ClassFactory, self).__init__()
        self._cls = cls

    def IClassFactory_CreateInstance(
        self,
        this: Any,
        punkOuter: Optional[Type["ctypes._Pointer[IUnknown]"]],
        riid: "ctypes._Pointer[GUID]",
        ppv: ctypes.c_void_p,
    ) -> int:
        _debug("ClassFactory.CreateInstance(%s)", riid[0])
        result = self._cls().IUnknown_QueryInterface(None, riid, ppv)
        _debug("CreateInstance() -> %s", result)
        return result

    def IClassFactory_LockServer(self, this: Any, fLock: bool) -> Literal[0]:
        if fLock:
            COMObject.__server__.Lock()
        else:
            COMObject.__server__.Unlock()
        return hresult.S_OK


# will be set by py2exe boot script 'from outside'
_clsid_to_class = {}


def inproc_find_class(clsid: GUID) -> Type[COMObject]:
    if _clsid_to_class:
        return _clsid_to_class[clsid]

    key = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, f"CLSID\\{clsid}\\InprocServer32")
    try:
        pathdir = winreg.QueryValueEx(key, "PythonPath")[0]
    except:
        _debug("NO path to insert")
    else:
        if not pathdir in sys.path:
            sys.path.insert(0, str(pathdir))
            _debug("insert path %r", pathdir)
        else:
            _debug("Already in path %r", pathdir)
    pythonclass = winreg.QueryValueEx(key, "PythonClass")[0]
    parts = pythonclass.split(".")
    modname = ".".join(parts[:-1])
    classname = parts[-1]
    _debug("modname: %s, classname %s", modname, classname)
    __import__(modname)
    mod = sys.modules[modname]
    result = getattr(mod, classname)
    _debug("Found class %s", result)
    return result


_logging_configured = False


def _setup_logging(clsid: GUID) -> None:
    """Read from the registry, and configure the logging module.

    Currently, the handler (NTDebugHandler) is hardcoded.
    """
    global _logging_configured
    if _logging_configured:
        return
    _logging_configured = True

    try:
        hkey = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"CLSID\%s\Logging" % clsid)
    except WindowsError:
        return
    from comtypes.logutil import NTDebugHandler

    handler = NTDebugHandler()
    try:
        val, typ = winreg.QueryValueEx(hkey, "format")
        formatter = logging.Formatter(val)
    except:
        formatter = logging.Formatter("(Thread %(thread)s):%(levelname)s:%(message)s")
    handler.setFormatter(formatter)
    logging.root.addHandler(handler)
    try:
        values, typ = winreg.QueryValueEx(hkey, "levels")
    except:
        return
    if typ == winreg.REG_SZ:
        values = [values]
    elif typ != winreg.REG_MULTI_SZ:
        # this is an error
        return
    for val in values:
        name, level = val.split("=")
        level = getattr(logging, level)
        logging.getLogger(name).setLevel(level)


def DllGetClassObject(rclsid: int, riid: int, ppv: int) -> int:
    COMObject.__run_inprocserver__()

    iid = GUID.from_address(riid)
    clsid = GUID.from_address(rclsid)

    if not _logging_configured:
        _setup_logging(clsid)

    # This function is directly called by C code, and receives C
    # integers as parameters. rclsid is a pointer to the CLSID for the
    # coclass we want to be created, riid is a pointer to the
    # requested interface.
    try:
        _debug("DllGetClassObject(clsid=%s, iid=%s)", clsid, iid)

        cls = inproc_find_class(clsid)
        if not cls:
            return hresult.CLASS_E_CLASSNOTAVAILABLE

        result = ClassFactory(cls).IUnknown_QueryInterface(
            None, ctypes.pointer(iid), ctypes.c_void_p(ppv)
        )
        _debug("DllGetClassObject() -> %s", result)
        return result
    except Exception:
        _critical("DllGetClassObject", exc_info=True)
        return hresult.E_FAIL


def DllCanUnloadNow() -> Literal[1]:  # S_FALSE
    COMObject.__run_inprocserver__()
    result = COMObject.__server__.DllCanUnloadNow()
    # To avoid a memory leak when PyInitialize()/PyUninitialize() are
    # called several times, we refuse to unload the dll.
    return hresult.S_FALSE
