import ctypes
from typing import Any, Dict, Optional, Set, Type, TypeVar

from comtypes import automation
from comtypes.client import lazybind
from comtypes import COMError, GUID, IUnknown, hresult as hres, _is_object


_T_IUnknown = TypeVar("_T_IUnknown", bound=IUnknown)
# These errors generally mean the property or method exists,
# but can't be used in this context - eg, property instead of a method, etc.
# Used to determine if we have a real error or not.
ERRORS_BAD_CONTEXT = [
    hres.DISP_E_MEMBERNOTFOUND,
    hres.DISP_E_BADPARAMCOUNT,
    hres.DISP_E_PARAMNOTOPTIONAL,
    hres.DISP_E_TYPEMISMATCH,
    hres.E_INVALIDARG,
]


def Dispatch(obj):
    """Wrap an object in a Dispatch instance, exposing methods and properties
    via fully dynamic dispatch.
    """
    if isinstance(obj, _Dispatch):
        return obj
    if isinstance(obj, ctypes.POINTER(automation.IDispatch)):
        try:
            tinfo = obj.GetTypeInfo(0)
        except (COMError, WindowsError):
            return _Dispatch(obj)
        return lazybind.Dispatch(obj, tinfo)
    return obj


class MethodCaller:
    # Wrong name: does not only call methods but also handle
    # property accesses.
    def __init__(self, _id: int, _obj: "_Dispatch") -> None:
        self._id = _id
        self._obj = _obj

    def __call__(self, *args: Any) -> Any:
        return self._obj._comobj.Invoke(self._id, *args)

    def __getitem__(self, *args: Any) -> Any:
        return self._obj._comobj.Invoke(
            self._id, *args, _invkind=automation.DISPATCH_PROPERTYGET
        )

    def __setitem__(self, *args: Any) -> None:
        if _is_object(args[-1]):
            self._obj._comobj.Invoke(
                self._id, *args, _invkind=automation.DISPATCH_PROPERTYPUTREF
            )
        else:
            self._obj._comobj.Invoke(
                self._id, *args, _invkind=automation.DISPATCH_PROPERTYPUT
            )


class _Dispatch(object):
    """Expose methods and properties via fully dynamic dispatch."""

    _comobj: automation.IDispatch
    _ids: Dict[str, int]
    _methods: Set[str]

    def __init__(self, comobj: "ctypes._Pointer[automation.IDispatch]"):
        self.__dict__["_comobj"] = comobj
        # Tiny optimization: trying not to use GetIDsOfNames more than once
        self.__dict__["_ids"] = {}
        self.__dict__["_methods"] = set()

    def __enum(self) -> automation.IEnumVARIANT:
        e: IUnknown = self._comobj.Invoke(-4)  # DISPID_NEWENUM
        return e.QueryInterface(automation.IEnumVARIANT)

    def __hash__(self) -> int:
        return hash(self._comobj)

    def __getitem__(self, index: Any) -> Any:
        enum = self.__enum()
        if index > 0:
            if 0 != enum.Skip(index):
                raise IndexError("index out of range")
        item, fetched = enum.Next(1)
        if not fetched:
            raise IndexError("index out of range")
        return item

    def QueryInterface(
        self, interface: Type[_T_IUnknown], iid: Optional[GUID] = None
    ) -> _T_IUnknown:
        """QueryInterface is forwarded to the real com object."""
        return self._comobj.QueryInterface(interface, iid)

    def _FlagAsMethod(self, *names: str) -> None:
        """Flag these attribute names as being methods.
        Some objects do not correctly differentiate methods and
        properties, leading to problems when calling these methods.

        Specifically, trying to say: ob.SomeFunc()
        may yield an exception "None object is not callable"
        In this case, an attempt to fetch the *property*has worked
        and returned None, rather than indicating it is really a method.
        Calling: ob._FlagAsMethod("SomeFunc")
        should then allow this to work.
        """
        self._methods.update(names)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        # tc = self._comobj.GetTypeInfo(0).QueryInterface(comtypes.typeinfo.ITypeComp)
        # dispid = tc.Bind(name)[1].memid
        dispid = self._ids.get(name)
        if not dispid:
            dispid = self._comobj.GetIDsOfNames(name)[0]
            self._ids[name] = dispid

        if name in self._methods:
            result = MethodCaller(dispid, self)
            self.__dict__[name] = result
            return result

        flags = automation.DISPATCH_PROPERTYGET
        try:
            result = self._comobj.Invoke(dispid, _invkind=flags)
        except COMError as err:
            (hresult, _, _) = err.args
            if hresult in ERRORS_BAD_CONTEXT:
                result = MethodCaller(dispid, self)
                self.__dict__[name] = result
            else:
                raise err

        return result

    def __setattr__(self, name: str, value: Any) -> None:
        dispid = self._ids.get(name)
        if not dispid:
            dispid = self._comobj.GetIDsOfNames(name)[0]
            self._ids[name] = dispid
        # Detect whether to use DISPATCH_PROPERTYPUT or
        # DISPATCH_PROPERTYPUTREF
        flags = 8 if _is_object(value) else 4
        return self._comobj.Invoke(dispid, value, _invkind=flags)

    def __iter__(self) -> "_Collection":
        return _Collection(self.__enum())

    # def __setitem__(self, index, value):
    #     self._comobj.Invoke(
    #         -3,
    #         index,
    #         value,
    #         _invkind=automation.DISPATCH_PROPERTYPUT
    #         | automation.DISPATCH_PROPERTYPUTREF,
    #     )


class _Collection(object):
    def __init__(self, enum: automation.IEnumVARIANT):
        self.enum = enum

    def __next__(self) -> Any:
        item, fetched = self.enum.Next(1)
        if fetched:
            return item
        raise StopIteration

    def __iter__(self):
        return self


__all__ = ["Dispatch"]
