import logging
import queue
from _ctypes import COMError, CopyComPointer
from ctypes import (
    POINTER,
    FormatError,
    Structure,
    byref,
    c_long,
    c_void_p,
    oledll,
    pointer,
    windll,
)
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    ClassVar,
    Dict,
    List,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
)
from typing import Union as _UnionT

from comtypes import GUID, IPersist, IUnknown, hresult
from comtypes._vtbl import _MethodFinder, create_dispimpl, create_vtbl_mapping
from comtypes.errorinfo import ISupportErrorInfo
from comtypes.typeinfo import IProvideClassInfo, IProvideClassInfo2, ITypeInfo

if TYPE_CHECKING:
    from ctypes import _CArgObject, _Pointer

    from comtypes import hints  # type: ignore

logger = logging.getLogger(__name__)
_debug = logger.debug

################################################################
# COM object implementation

# so we don't have to import comtypes.automation
DISPATCH_METHOD = 1
DISPATCH_PROPERTYGET = 2
DISPATCH_PROPERTYPUT = 4
DISPATCH_PROPERTYPUTREF = 8

################################################################

try:
    _InterlockedIncrement = windll.kernel32.InterlockedIncrement
    _InterlockedDecrement = windll.kernel32.InterlockedDecrement
except AttributeError:
    import threading

    _lock = threading.Lock()
    _acquire = _lock.acquire
    _release = _lock.release
    # win 64 doesn't have these functions

    def _InterlockedIncrement(ob: c_long) -> int:
        _acquire()
        refcnt = ob.value + 1
        ob.value = refcnt
        _release()
        return refcnt

    def _InterlockedDecrement(ob: c_long) -> int:
        _acquire()
        refcnt = ob.value - 1
        ob.value = refcnt
        _release()
        return refcnt

else:
    _InterlockedIncrement.argtypes = [POINTER(c_long)]
    _InterlockedDecrement.argtypes = [POINTER(c_long)]
    _InterlockedIncrement.restype = c_long
    _InterlockedDecrement.restype = c_long


class LocalServer(object):
    _queue: Optional[queue.Queue] = None

    def run(self, classobjects: Sequence["hints.localserver.ClassFactory"]) -> None:
        # Use windll instead of oledll so that we don't get an
        # exception on a FAILED hresult:
        hr = windll.ole32.CoInitialize(None)
        if hresult.RPC_E_CHANGED_MODE == hr:
            # we're running in MTA: no message pump needed
            _debug("Server running in MTA")
            self.run_mta()
        else:
            # we're running in STA: need a message pump
            _debug("Server running in STA")
            if hr >= 0:
                # we need a matching CoUninitialize() call for a successful
                # CoInitialize().
                windll.ole32.CoUninitialize()
            self.run_sta()

        for obj in classobjects:
            obj._revoke_class()

    def run_sta(self) -> None:
        from comtypes import messageloop

        messageloop.run()

    def run_mta(self) -> None:
        self._queue = queue.Queue()
        self._queue.get()

    def Lock(self) -> None:
        oledll.ole32.CoAddRefServerProcess()

    def Unlock(self) -> None:
        rc = oledll.ole32.CoReleaseServerProcess()
        if rc == 0:
            if self._queue:
                self._queue.put(42)
            else:
                windll.user32.PostQuitMessage(0)


class InprocServer(object):
    def __init__(self) -> None:
        self.locks = c_long(0)

    def Lock(self) -> None:
        _InterlockedIncrement(self.locks)

    def Unlock(self) -> None:
        _InterlockedDecrement(self.locks)

    def DllCanUnloadNow(self) -> int:
        if self.locks.value:
            return hresult.S_FALSE
        if COMObject._instances_:
            return hresult.S_FALSE
        return hresult.S_OK


_T_IUnknown = TypeVar("_T_IUnknown", bound=IUnknown)


class COMObject(object):
    _com_interfaces_: ClassVar[List[Type[IUnknown]]]
    _outgoing_interfaces_: ClassVar[List[Type["hints.IDispatch"]]]
    _instances_: ClassVar[Dict["COMObject", None]] = {}
    _reg_clsid_: ClassVar[GUID]
    _reg_typelib_: ClassVar[Tuple[str, int, int]]
    __typelib: "hints.ITypeLib"
    _com_pointers_: Dict[GUID, "_Pointer[_Pointer[Structure]]"]
    _dispimpl_: Dict[Tuple[int, int], Callable[..., Any]]

    def __new__(cls, *args, **kw):
        self = super(COMObject, cls).__new__(cls)
        if isinstance(self, c_void_p):
            # We build the VTables only for direct instances of
            # CoClass, not for POINTERs to CoClass.
            return self
        if hasattr(self, "_com_interfaces_"):
            self.__prepare_comobject()
        return self

    def __prepare_comobject(self) -> None:
        # When a CoClass instance is created, COM pointers to all
        # interfaces are created.  Also, the CoClass must be kept alive as
        # until the COM reference count drops to zero, even if no Python
        # code keeps a reference to the object.
        #
        # The _com_pointers_ instance variable maps string interface iids
        # to C compatible COM pointers.
        self._com_pointers_ = {}
        # COM refcount starts at zero.
        self._refcnt = c_long(0)

        # Some interfaces have a default implementation in COMObject:
        # - ISupportErrorInfo
        # - IPersist (if the subclass has a _reg_clsid_ attribute)
        # - IProvideClassInfo (if the subclass has a _reg_clsid_ attribute)
        # - IProvideClassInfo2 (if the subclass has a _outgoing_interfaces_
        #   attribute)
        #
        # Add these if they are not listed in _com_interfaces_.
        interfaces = tuple(self._com_interfaces_)
        if ISupportErrorInfo not in interfaces:
            interfaces += (ISupportErrorInfo,)
        if hasattr(self, "_reg_typelib_"):
            from comtypes.typeinfo import LoadRegTypeLib

            self._COMObject__typelib = LoadRegTypeLib(*self._reg_typelib_)
            if hasattr(self, "_reg_clsid_"):
                if IProvideClassInfo not in interfaces:
                    interfaces += (IProvideClassInfo,)
                if (
                    hasattr(self, "_outgoing_interfaces_")
                    and IProvideClassInfo2 not in interfaces
                ):
                    interfaces += (IProvideClassInfo2,)
        if hasattr(self, "_reg_clsid_"):
            if IPersist not in interfaces:
                interfaces += (IPersist,)
        for itf in interfaces[::-1]:
            self.__make_interface_pointer(itf)

    def __make_interface_pointer(self, itf: Type[IUnknown]) -> None:
        finder = self._get_method_finder_(itf)
        iids, vtbl = create_vtbl_mapping(itf, finder)
        for iid in iids:
            self._com_pointers_[iid] = pointer(pointer(vtbl))
        if hasattr(itf, "_disp_methods_"):
            self._dispimpl_ = create_dispimpl(itf, finder)

    def _get_method_finder_(self, itf: Type[IUnknown]) -> _MethodFinder:
        # This method can be overridden to customize how methods are found.
        return _MethodFinder(self)

    ################################################################
    # LocalServer / InprocServer stuff
    __server__: _UnionT[None, InprocServer, LocalServer] = None

    @staticmethod
    def __run_inprocserver__() -> None:
        if COMObject.__server__ is None:
            COMObject.__server__ = InprocServer()
        elif isinstance(COMObject.__server__, InprocServer):
            pass
        else:
            raise RuntimeError("Wrong server type")

    @staticmethod
    def __run_localserver__(
        classobjects: Sequence["hints.localserver.ClassFactory"],
    ) -> None:
        assert COMObject.__server__ is None
        # XXX Decide whether we are in STA or MTA
        server = COMObject.__server__ = LocalServer()
        server.run(classobjects)
        COMObject.__server__ = None

    @staticmethod
    def __keep__(obj: "COMObject") -> None:
        COMObject._instances_[obj] = None
        _debug("%d active COM objects: Added   %r", len(COMObject._instances_), obj)
        if COMObject.__server__:
            COMObject.__server__.Lock()

    @staticmethod
    def __unkeep__(obj: "COMObject") -> None:
        try:
            del COMObject._instances_[obj]
        except AttributeError:
            _debug("? active COM objects: Removed %r", obj)
        else:
            _debug("%d active COM objects: Removed %r", len(COMObject._instances_), obj)
        _debug("Remaining: %s", list(COMObject._instances_.keys()))
        if COMObject.__server__:
            COMObject.__server__.Unlock()

    #
    ################################################################

    #########################################################
    # IUnknown methods implementations
    def IUnknown_AddRef(
        self,
        this: Any,
        __InterlockedIncrement: Callable[[c_long], int] = _InterlockedIncrement,
        _debug=_debug,
    ) -> int:
        result = __InterlockedIncrement(self._refcnt)
        if result == 1:
            self.__keep__(self)
        _debug("%r.AddRef() -> %s", self, result)
        return result

    def _final_release_(self) -> None:
        """This method may be overridden in subclasses
        to free allocated resources or so."""
        pass

    def IUnknown_Release(
        self,
        this: Any,
        __InterlockedDecrement: Callable[[c_long], int] = _InterlockedDecrement,
        _debug=_debug,
    ) -> int:
        # If this is called at COM shutdown, _InterlockedDecrement()
        # must still be available, although module level variables may
        # have been deleted already - so we supply it as default
        # argument.
        result = __InterlockedDecrement(self._refcnt)
        _debug("%r.Release() -> %s", self, result)
        if result == 0:
            self._final_release_()
            self.__unkeep__(self)
            # Hm, why isn't this cleaned up by the cycle gc?
            self._com_pointers_ = {}
        return result

    def IUnknown_QueryInterface(
        self,
        this: Any,
        riid: "_Pointer[GUID]",
        ppvObj: _UnionT[c_void_p, "_CArgObject"],
        _debug=_debug,
    ) -> int:
        # XXX This is probably too slow.
        # riid[0].hashcode() alone takes 33 us!
        iid = riid[0]
        ptr = self._com_pointers_.get(iid, None)
        if ptr is not None:
            # CopyComPointer(src, dst) calls AddRef!
            _debug("%r.QueryInterface(%s) -> S_OK", self, iid)
            return CopyComPointer(ptr, ppvObj)
        _debug("%r.QueryInterface(%s) -> E_NOINTERFACE", self, iid)
        return hresult.E_NOINTERFACE

    def QueryInterface(self, interface: Type[_T_IUnknown]) -> _T_IUnknown:
        "Query the object for an interface pointer"
        # This method is NOT the implementation of
        # IUnknown::QueryInterface, instead it is supposed to be
        # called on an COMObject by user code.  It allows to get COM
        # interface pointers from COMObject instances.
        ptr = self._com_pointers_.get(interface._iid_, None)
        if ptr is None:
            raise COMError(
                hresult.E_NOINTERFACE,
                FormatError(hresult.E_NOINTERFACE),
                (None, None, None, 0, None),
            )
        # CopyComPointer(src, dst) calls AddRef!
        result = POINTER(interface)()
        CopyComPointer(ptr, byref(result))
        return result  # type: ignore

    ################################################################
    # ISupportErrorInfo::InterfaceSupportsErrorInfo implementation
    def ISupportErrorInfo_InterfaceSupportsErrorInfo(
        self, this: Any, riid: "_Pointer[GUID]"
    ) -> int:
        if riid[0] in self._com_pointers_:
            return hresult.S_OK
        return hresult.S_FALSE

    ################################################################
    # IProvideClassInfo::GetClassInfo implementation
    def IProvideClassInfo_GetClassInfo(self) -> ITypeInfo:
        try:
            self.__typelib
        except AttributeError:
            raise WindowsError(hresult.E_NOTIMPL)
        return self.__typelib.GetTypeInfoOfGuid(self._reg_clsid_)

    ################################################################
    # IProvideClassInfo2::GetGUID implementation

    def IProvideClassInfo2_GetGUID(self, dwGuidKind: int) -> GUID:
        # GUIDKIND_DEFAULT_SOURCE_DISP_IID = 1
        if dwGuidKind != 1:
            raise WindowsError(hresult.E_INVALIDARG)
        return self._outgoing_interfaces_[0]._iid_

    ################################################################
    # IDispatch methods
    @property
    def __typeinfo(self):
        # XXX Looks like this better be a static property, set by the
        # code that sets __typelib also...
        iid = self._com_interfaces_[0]._iid_
        return self.__typelib.GetTypeInfoOfGuid(iid)

    def IDispatch_GetTypeInfoCount(self):
        try:
            self.__typelib
        except AttributeError:
            return 0
        else:
            return 1

    def IDispatch_GetTypeInfo(self, this, itinfo, lcid, ptinfo):
        if itinfo != 0:
            return hresult.DISP_E_BADINDEX
        try:
            ptinfo[0] = self.__typeinfo
            return hresult.S_OK
        except AttributeError:
            return hresult.E_NOTIMPL

    def IDispatch_GetIDsOfNames(self, this, riid, rgszNames, cNames, lcid, rgDispId):
        # This call uses windll instead of oledll so that a failed
        # call to DispGetIDsOfNames will return a HRESULT instead of
        # raising an error.
        try:
            tinfo = self.__typeinfo
        except AttributeError:
            return hresult.E_NOTIMPL
        return windll.oleaut32.DispGetIDsOfNames(tinfo, rgszNames, cNames, rgDispId)

    def IDispatch_Invoke(
        self,
        this,
        dispIdMember,
        riid,
        lcid,
        wFlags,
        pDispParams,
        pVarResult,
        pExcepInfo,
        puArgErr,
    ):
        try:
            self._dispimpl_
        except AttributeError:
            try:
                tinfo = self.__typeinfo
            except AttributeError:
                # Hm, we pretend to implement IDispatch, but have no
                # typeinfo, and so cannot fulfill the contract.  Should we
                # better return E_NOTIMPL or DISP_E_MEMBERNOTFOUND?  Some
                # clients call IDispatch_Invoke with 'known' DISPID_...'
                # values, without going through GetIDsOfNames first.
                return hresult.DISP_E_MEMBERNOTFOUND
            # This call uses windll instead of oledll so that a failed
            # call to DispInvoke will return a HRESULT instead of raising
            # an error.
            interface = self._com_interfaces_[0]
            ptr = self._com_pointers_[interface._iid_]
            return windll.oleaut32.DispInvoke(
                ptr,
                tinfo,
                dispIdMember,
                wFlags,
                pDispParams,
                pVarResult,
                pExcepInfo,
                puArgErr,
            )

        try:
            # XXX Hm, wFlags should be considered a SET of flags...
            mth = self._dispimpl_[(dispIdMember, wFlags)]
        except KeyError:
            return hresult.DISP_E_MEMBERNOTFOUND

        # Unpack the parameters: It would be great if we could use the
        # DispGetParam function - but we cannot since it requires that
        # we pass a VARTYPE for each argument and we do not know that.
        #
        # Seems that n arguments have dispids (0, 1, ..., n-1).
        # Unnamed arguments are packed into the DISPPARAMS array in
        # reverse order (starting with the highest dispid), named
        # arguments are packed in the order specified by the
        # rgdispidNamedArgs array.
        #
        params = pDispParams[0]

        if wFlags & (4 | 8):
            # DISPATCH_PROPERTYPUT
            # DISPATCH_PROPERTYPUTREF
            #
            # How are the parameters unpacked for propertyput
            # operations with additional parameters?  Can propput
            # have additional args?
            args = [
                params.rgvarg[i].value for i in reversed(list(range(params.cNamedArgs)))
            ]
            # MSDN: pVarResult is ignored if DISPATCH_PROPERTYPUT or
            # DISPATCH_PROPERTYPUTREF is specified.
            return mth(this, *args)

        else:
            # DISPATCH_METHOD
            # DISPATCH_PROPERTYGET
            # the positions of named arguments
            #
            # 2to3 has problems to translate 'range(...)[::-1]'
            # correctly, so use 'list(range)[::-1]' instead (will be
            # fixed in Python 3.1, probably):
            named_indexes = [
                params.rgdispidNamedArgs[i] for i in range(params.cNamedArgs)
            ]
            # the positions of unnamed arguments
            num_unnamed = params.cArgs - params.cNamedArgs
            unnamed_indexes = list(reversed(list(range(num_unnamed))))
            # It seems that this code calculates the indexes of the
            # parameters in the params.rgvarg array correctly.
            indexes = named_indexes + unnamed_indexes
            args = [params.rgvarg[i].value for i in indexes]

            if pVarResult and getattr(mth, "has_outargs", False):
                args.append(pVarResult)
            return mth(this, *args)

    ################################################################
    # IPersist interface
    def IPersist_GetClassID(self) -> GUID:
        return self._reg_clsid_


__all__ = ["COMObject"]
