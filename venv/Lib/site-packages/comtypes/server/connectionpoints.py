from ctypes import *
from comtypes import IUnknown, COMObject, COMError
from comtypes.hresult import *
from comtypes.typeinfo import LoadRegTypeLib
from comtypes.connectionpoints import IConnectionPoint
from comtypes.automation import IDispatch

import logging

logger = logging.getLogger(__name__)

__all__ = ["ConnectableObjectMixin"]


class ConnectionPointImpl(COMObject):
    """This object implements a connectionpoint"""

    _com_interfaces_ = [IConnectionPoint]

    def __init__(self, sink_interface, sink_typeinfo):
        super(ConnectionPointImpl, self).__init__()
        self._connections = {}
        self._cookie = 0
        self._sink_interface = sink_interface
        self._typeinfo = sink_typeinfo

    # per MSDN, all interface methods *must* be implemented, E_NOTIMPL
    # is no allowed return value

    def IConnectionPoint_Advise(self, this, pUnk, pdwCookie):
        if not pUnk or not pdwCookie:
            return E_POINTER
        logger.debug("Advise")
        try:
            ptr = pUnk.QueryInterface(self._sink_interface)
        except COMError:
            return CONNECT_E_CANNOTCONNECT
        pdwCookie[0] = self._cookie = self._cookie + 1
        self._connections[self._cookie] = ptr
        return S_OK

    def IConnectionPoint_Unadvise(self, this, dwCookie):
        logger.debug("Unadvise %s", dwCookie)
        try:
            del self._connections[dwCookie]
        except KeyError:
            return CONNECT_E_NOCONNECTION
        return S_OK

    def IConnectionPoint_GetConnectionPointContainer(self, this, ppCPC):
        return E_NOTIMPL

    def IConnectionPoint_GetConnectionInterface(self, this, pIID):
        return E_NOTIMPL

    def _call_sinks(self, name, *args, **kw):
        results = []
        logger.debug("_call_sinks(%s, %s, *%s, **%s)", self, name, args, kw)
        # Is it an IDispatch derived interface?  Then, events have to be delivered
        # via Invoke calls (even if it is a dual interface).
        if hasattr(self._sink_interface, "Invoke"):
            # for better performance, we could cache the dispids.
            dispid = self._typeinfo.GetIDsOfNames(name)[0]
            for key, p in self._connections.items():
                try:
                    result = p.Invoke(dispid, *args, **kw)
                except COMError as details:
                    if details.hresult == -2147023174:
                        logger.warning(
                            "_call_sinks(%s, %s, *%s, **%s) failed; removing connection",
                            self,
                            name,
                            args,
                            kw,
                            exc_info=True,
                        )
                        try:
                            del self._connections[key]
                        except KeyError:
                            pass  # connection already gone
                    else:
                        logger.warning(
                            "_call_sinks(%s, %s, *%s, **%s)",
                            self,
                            name,
                            args,
                            kw,
                            exc_info=True,
                        )
                else:
                    results.append(result)
        else:
            for p in self._connections.values():
                try:
                    result = getattr(p, name)(*args, **kw)
                except COMError as details:
                    if details.hresult == -2147023174:
                        logger.warning(
                            "_call_sinks(%s, %s, *%s, **%s) failed; removing connection",
                            self,
                            name,
                            args,
                            kw,
                            exc_info=True,
                        )
                        del self._connections[key]
                    else:
                        logger.warning(
                            "_call_sinks(%s, %s, *%s, **%s)",
                            self,
                            name,
                            args,
                            kw,
                            exc_info=True,
                        )
                else:
                    results.append(result)
        return results


class ConnectableObjectMixin(object):
    """Mixin which implements IConnectionPointContainer.

    Call Fire_Event(interface, methodname, *args, **kw) to fire an
    event.  <interface> can either be the source interface, or an
    integer index into the _outgoing_interfaces_ list.
    """

    def __init__(self):
        super(ConnectableObjectMixin, self).__init__()
        self.__connections = {}

        tlib = LoadRegTypeLib(*self._reg_typelib_)
        for itf in self._outgoing_interfaces_:
            typeinfo = tlib.GetTypeInfoOfGuid(itf._iid_)
            self.__connections[itf] = ConnectionPointImpl(itf, typeinfo)

    def IConnectionPointContainer_EnumConnectionPoints(self, this, ppEnum):
        # according to MSDN, E_NOTIMPL is specificially disallowed
        # because, without typeinfo, there's no way for the caller to
        # find out.
        return E_NOTIMPL

    def IConnectionPointContainer_FindConnectionPoint(self, this, refiid, ppcp):
        iid = refiid[0]
        logger.debug("FindConnectionPoint %s", iid)
        if not ppcp:
            return E_POINTER
        for itf in self._outgoing_interfaces_:
            if itf._iid_ == iid:
                # 'byref' will not work in this case, since the QueryInterface
                # method implementation is called on Python directly. There's
                # no C layer between which will convert the second parameter
                # from byref() to pointer().
                conn = self.__connections[itf]
                result = conn.IUnknown_QueryInterface(
                    None, pointer(IConnectionPoint._iid_), ppcp
                )
                logger.debug("connectionpoint found, QI() -> %s", result)
                return result
        logger.debug("No connectionpoint found")
        return CONNECT_E_NOCONNECTION

    def Fire_Event(self, itf, name, *args, **kw):
        # Fire event 'name' with arguments *args and **kw.
        # Accepts either an interface index or an interface as first argument.
        # Returns a list of results.
        logger.debug("Fire_Event(%s, %s, *%s, **%s)", itf, name, args, kw)
        if isinstance(itf, int):
            itf = self._outgoing_interfaces_[itf]
        return self.__connections[itf]._call_sinks(name, *args, **kw)
