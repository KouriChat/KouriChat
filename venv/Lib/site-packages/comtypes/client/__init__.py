"""comtypes.client - High level client level COM support package."""

################################################################
#
# TODO:
#
# - refactor some code into modules
#
################################################################

import ctypes
import logging
import os
import sys
from typing import Any, overload, TypeVar, TYPE_CHECKING
from typing import Optional, Type, Union as _UnionT

import comtypes
from comtypes.hresult import *
from comtypes import automation, CoClass, GUID, IUnknown, typeinfo
import comtypes.client.dynamic
from comtypes.client._constants import Constants
from comtypes.client._events import GetEvents, ShowEvents, PumpEvents
from comtypes.client._generate import GetModule
from comtypes.client._code_cache import _find_gen_dir

if TYPE_CHECKING:
    from comtypes import hints  # type: ignore

gen_dir = _find_gen_dir()
import comtypes.gen

### for testing
##gen_dir = None

_T_IUnknown = TypeVar("_T_IUnknown", bound=IUnknown)
logger = logging.getLogger(__name__)


def wrap_outparam(punk: Any) -> Any:
    logger.debug("wrap_outparam(%s)", punk)
    if not punk:
        return None
    if punk.__com_interface__ == automation.IDispatch:
        return GetBestInterface(punk)
    return punk


def GetBestInterface(punk: Any) -> Any:
    """Try to QueryInterface a COM pointer to the 'most useful'
    interface.

    Get type information for the provided object, either via
    IDispatch.GetTypeInfo(), or via IProvideClassInfo.GetClassInfo().
    Generate a wrapper module for the typelib, and QI for the
    interface found.
    """
    if not punk:  # NULL COM pointer
        return punk  # or should we return None?
    # find the typelib and the interface name
    logger.debug("GetBestInterface(%s)", punk)
    try:
        try:
            pci = punk.QueryInterface(typeinfo.IProvideClassInfo)
            logger.debug("Does implement IProvideClassInfo")
        except comtypes.COMError:
            # Some COM objects support IProvideClassInfo2, but not IProvideClassInfo.
            # These objects are broken, but we support them anyway.
            logger.debug(
                "Does NOT implement IProvideClassInfo, trying IProvideClassInfo2"
            )
            pci = punk.QueryInterface(typeinfo.IProvideClassInfo2)
            logger.debug("Does implement IProvideClassInfo2")
        tinfo = pci.GetClassInfo()  # TypeInfo for the CoClass
        # find the interface marked as default
        ta = tinfo.GetTypeAttr()
        for index in range(ta.cImplTypes):
            if tinfo.GetImplTypeFlags(index) == 1:
                break
        else:
            if ta.cImplTypes != 1:
                # Hm, should we use dynamic now?
                raise TypeError("No default interface found")
            # Only one interface implemented, use that (even if
            # not marked as default).
            index = 0
        href = tinfo.GetRefTypeOfImplType(index)
        tinfo = tinfo.GetRefTypeInfo(href)
    except comtypes.COMError:
        logger.debug("Does NOT implement IProvideClassInfo/IProvideClassInfo2")
        try:
            pdisp = punk.QueryInterface(automation.IDispatch)
        except comtypes.COMError:
            logger.debug("No Dispatch interface: %s", punk)
            return punk
        try:
            tinfo = pdisp.GetTypeInfo(0)
        except comtypes.COMError:
            pdisp = comtypes.client.dynamic.Dispatch(pdisp)
            logger.debug("IDispatch.GetTypeInfo(0) failed: %s" % pdisp)
            return pdisp
    typeattr = tinfo.GetTypeAttr()
    logger.debug("Default interface is %s", typeattr.guid)
    try:
        punk.QueryInterface(comtypes.IUnknown, typeattr.guid)
    except comtypes.COMError:
        logger.debug("Does not implement default interface, returning dynamic object")
        return comtypes.client.dynamic.Dispatch(punk)

    itf_name = tinfo.GetDocumentation(-1)[0]  # interface name
    tlib = tinfo.GetContainingTypeLib()[0]  # typelib

    # import the wrapper, generating it on demand
    mod = GetModule(tlib)
    # Python interface class
    interface = getattr(mod, itf_name)
    logger.debug("Implements default interface from typeinfo %s", interface)
    # QI for this interface
    # XXX
    # What to do if this fails?
    # In the following example the engine.Eval() call returns
    # such an object.
    #
    # engine = CreateObject("MsScriptControl.ScriptControl")
    # engine.Language = "JScript"
    # engine.Eval("[1, 2, 3]")
    #
    # Could the above code, as an optimization, check that QI works,
    # *before* generating the wrapper module?
    result = punk.QueryInterface(interface)
    logger.debug("Final result is %s", result)
    return result


# backwards compatibility:
wrap = GetBestInterface

# Should we do this for POINTER(IUnknown) also?
ctypes.POINTER(automation.IDispatch).__ctypes_from_outparam__ = wrap_outparam  # type: ignore


################################################################
#
# Object creation
#
@overload
def GetActiveObject(progid: _UnionT[str, CoClass, GUID]) -> Any: ...
@overload
def GetActiveObject(
    progid: _UnionT[str, CoClass, GUID], interface: Type[_T_IUnknown]
) -> _T_IUnknown: ...
def GetActiveObject(
    progid: _UnionT[str, CoClass, GUID],
    interface: Optional[Type[IUnknown]] = None,
    dynamic: bool = False,
) -> Any:
    """Return a pointer to a running COM object that has been
    registered with COM.

    'progid' may be a string like "Excel.Application",
       a string specifying a clsid, a GUID instance, or an object with
       a _clsid_ attribute which should be any of the above.
    'interface' allows to force a certain interface.
    'dynamic=True' will return a dynamic dispatch object.
    """
    clsid = GUID.from_progid(progid)
    if dynamic:
        if interface is not None:
            raise ValueError("interface and dynamic are mutually exclusive")
        interface = automation.IDispatch
    elif interface is None:
        interface = getattr(progid, "_com_interfaces_", [None])[0]
    obj = comtypes.GetActiveObject(clsid, interface=interface)
    if dynamic:
        return comtypes.client.dynamic.Dispatch(obj)
    return _manage(obj, clsid, interface=interface)


def _manage(
    obj: Any, clsid: Optional[GUID], interface: Optional[Type[IUnknown]]
) -> Any:
    obj.__dict__["__clsid"] = str(clsid)
    if interface is None:
        obj = GetBestInterface(obj)
    return obj


if TYPE_CHECKING:

    @overload
    def GetClassObject(
        progid: _UnionT[str, CoClass, GUID],
        clsctx: Optional[int] = None,
        pServerInfo: Optional[comtypes.COSERVERINFO] = None,
        interface: None = None,
    ) -> hints.IClassFactory: ...
    @overload
    def GetClassObject(
        progid: _UnionT[str, CoClass, GUID],
        clsctx: Optional[int] = None,
        pServerInfo: Optional[comtypes.COSERVERINFO] = None,
        interface: Type[_T_IUnknown] = hints.IClassFactory,
    ) -> _T_IUnknown: ...


def GetClassObject(progid, clsctx=None, pServerInfo=None, interface=None):
    # type: (_UnionT[str, CoClass, GUID], Optional[int], Optional[comtypes.COSERVERINFO], Optional[Type[IUnknown]]) -> IUnknown
    """Create and return the class factory for a COM object.

    'clsctx' specifies how to create the object, use the CLSCTX_... constants.
    'pServerInfo', if used, must be a pointer to a comtypes.COSERVERINFO instance
    'interface' may be used to request an interface other than IClassFactory
    """
    clsid = GUID.from_progid(progid)
    return comtypes.CoGetClassObject(clsid, clsctx, pServerInfo, interface)


@overload
def CreateObject(progid: _UnionT[str, Type[CoClass], GUID]) -> Any: ...
@overload
def CreateObject(
    progid: _UnionT[str, Type[CoClass], GUID],
    clsctx: Optional[int] = None,
    machine: Optional[str] = None,
    interface: Optional[Type[_T_IUnknown]] = None,
    dynamic: bool = ...,
    pServerInfo: Optional[comtypes.COSERVERINFO] = None,
) -> _T_IUnknown: ...
def CreateObject(
    progid: _UnionT[str, Type[CoClass], GUID],  # which object to create
    clsctx: Optional[int] = None,  # how to create the object
    machine: Optional[str] = None,  # where to create the object
    interface: Optional[Type[IUnknown]] = None,  # the interface we want
    dynamic: bool = False,  # use dynamic dispatch
    pServerInfo: Optional[
        comtypes.COSERVERINFO
    ] = None,  # server info struct for remoting
) -> Any:
    """Create a COM object from 'progid', and try to QueryInterface()
    it to the most useful interface, generating typelib support on
    demand.  A pointer to this interface is returned.

    'progid' may be a string like "InternetExplorer.Application",
       a string specifying a clsid, a GUID instance, or an object with
       a _clsid_ attribute which should be any of the above.
    'clsctx' specifies how to create the object, use the CLSCTX_... constants.
    'machine' allows to specify a remote machine to create the object on.
    'interface' allows to force a certain interface
    'dynamic=True' will return a dynamic dispatch object
    'pServerInfo', if used, must be a pointer to a comtypes.COSERVERINFO instance
        This supercedes 'machine'.

    You can also later request to receive events with GetEvents().
    """
    clsid = GUID.from_progid(progid)
    logger.debug("%s -> %s", progid, clsid)
    if dynamic:
        if interface:
            raise ValueError("interface and dynamic are mutually exclusive")
        interface = automation.IDispatch
    elif interface is None:
        interface = getattr(progid, "_com_interfaces_", [None])[0]
    if machine is None and pServerInfo is None:
        logger.debug(
            "CoCreateInstance(%s, clsctx=%s, interface=%s)", clsid, clsctx, interface
        )
        obj = comtypes.CoCreateInstance(clsid, clsctx=clsctx, interface=interface)
    else:
        logger.debug(
            "CoCreateInstanceEx(%s, clsctx=%s, interface=%s, machine=%s,\
                        pServerInfo=%s)",
            clsid,
            clsctx,
            interface,
            machine,
            pServerInfo,
        )
        if machine is not None and pServerInfo is not None:
            msg = "You cannot set both the machine name and server info."
            raise ValueError(msg)
        obj = comtypes.CoCreateInstanceEx(
            clsid,
            clsctx=clsctx,
            interface=interface,
            machine=machine,
            pServerInfo=pServerInfo,
        )
    if dynamic:
        return comtypes.client.dynamic.Dispatch(obj)
    return _manage(obj, clsid, interface=interface)


@overload
def CoGetObject(displayname: str, interface: Type[_T_IUnknown]) -> _T_IUnknown: ...
@overload
def CoGetObject(
    displayname: str, interface: None = None, dynamic: bool = False
) -> Any: ...
def CoGetObject(
    displayname: str,
    interface: Optional[Type[comtypes.IUnknown]] = None,
    dynamic: bool = False,
) -> Any:
    """Create an object by calling CoGetObject(displayname).

    Additional parameters have the same meaning as in CreateObject().
    """
    if dynamic:
        if interface is not None:
            raise ValueError("interface and dynamic are mutually exclusive")
        interface = automation.IDispatch
    punk = comtypes.CoGetObject(displayname, interface)
    if dynamic:
        return comtypes.client.dynamic.Dispatch(punk)
    return _manage(punk, clsid=None, interface=interface)


# fmt: off
__all__ = [
    "CreateObject", "GetActiveObject", "CoGetObject", "GetEvents",
    "ShowEvents", "PumpEvents", "GetModule", "GetClassObject",
]
# fmt: on
