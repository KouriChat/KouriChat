# https://learn.microsoft.com/en-us/windows/win32/api/unknwn/

import logging
import sys
from ctypes import HRESULT, POINTER, byref, c_ulong, c_void_p
from typing import TYPE_CHECKING, ClassVar, List, Optional, Type, TypeVar

from comtypes import GUID, _ole32_nohresult, com_interface_registry
from comtypes._memberspec import STDMETHOD, ComMemberGenerator, DispMemberGenerator
from comtypes._post_coinit import _cominterface_meta_patcher as _meta_patch
from comtypes._post_coinit.instancemethod import instancemethod

if TYPE_CHECKING:
    from comtypes._memberspec import _ComMemberSpec, _DispMemberSpec

logger = logging.getLogger(__name__)


def _shutdown(
    func=_ole32_nohresult.CoUninitialize,
    _debug=logger.debug,
    _exc_clear=getattr(sys, "exc_clear", lambda: None),
):
    # Make sure no COM pointers stay in exception frames.
    _exc_clear()
    # Sometimes, CoUninitialize, running at Python shutdown,
    # raises an exception.  We suppress this when __debug__ is
    # False.
    _debug("Calling CoUninitialize()")
    if __debug__:
        func()
    else:
        try:
            func()
        except WindowsError:
            pass
    # Set the flag which means that calling obj.Release() is no longer
    # needed.
    if _cominterface_meta is not None:
        _cominterface_meta._com_shutting_down = True
    _debug("CoUninitialize() done.")


################################################################
# The metaclasses...


class _cominterface_meta(type):
    """Metaclass for COM interfaces.  Automatically creates high level
    methods from COMMETHOD lists.
    """

    _case_insensitive_: bool
    _iid_: GUID
    _methods_: List["_ComMemberSpec"]
    _disp_methods_: List["_DispMemberSpec"]

    # This flag is set to True by the atexit handler which calls
    # CoUninitialize.
    _com_shutting_down = False

    # Creates also a POINTER type for the newly created class.
    def __new__(cls, name, bases, namespace):
        methods = namespace.pop("_methods_", None)
        dispmethods = namespace.pop("_disp_methods_", None)
        self = type.__new__(cls, name, bases, namespace)

        if methods is not None:
            self._methods_ = methods
        if dispmethods is not None:
            self._disp_methods_ = dispmethods

        # ` _compointer_meta` is a subclass inherited from `_cominterface_meta`.
        # `_compointer_base` uses `_compointer_meta` as its metaclass.
        # In other words, when the `__new__` method of this metaclass is called,
        # `_compointer_base` type or an subclass of it might be created and assigned
        # to `self`.
        if bases == (c_void_p,):
            # `self` is the `_compointer_base` type.
            # On some versions of Python, `_compointer_base` is not yet available in
            # the accessible namespace at this point in its initialization, and
            # referencing it could raise a `NameError`.
            # This metaclass is intended to be used only as a base class for defining
            # the `_compointer_meta` or as the metaclass for the `IUnknown`, so the
            # situation where the `bases` parameter is `(c_void_p,)` is limited to when
            # the `_compointer_meta` is specified as the metaclass of the
            # `_compointer_base`.
            # Prevent specifying the metaclass type instance in the `bases` parameter
            # when instantiating it, as this would lead to infinite recursion.
            return self
        if issubclass(self, _compointer_base):
            # `self` is a `POINTER(interface)` type.
            # Prevent creating/registering a pointer to a pointer (to a pointer...),
            # which would lead to infinite recursion.
            # Depending on a version or revision of Python, this may be essential.
            return self

        # If we sublass a COM interface, for example:
        #
        # class IDispatch(IUnknown):
        #     ....
        #
        # then we need to make sure that POINTER(IDispatch) is a
        # subclass of POINTER(IUnknown) because of the way ctypes
        # typechecks work.
        if bases == (object,):
            # `self` is the `IUnknown` type.
            _ptr_bases = (self, _compointer_base)
        else:
            # `self` is an interface type derived from `IUnknown`.
            _ptr_bases = (self, POINTER(bases[0]))

        # The interface 'self' is used as a mixin.
        # HACK: Could `type(_compointer_base)` be replaced with `_compointer_meta`?
        # `type(klass)` returns its metaclass.
        # Since this specification, `type(_compointer_base)` will return the
        # `_compointer_meta` type as per the class definition.
        # The reason for this implementation might be a remnant of the differences in
        # how metaclasses work between Python 3.x and Python 2.x.
        # If there are no problems with the versions of Python that `comtypes`
        # supports, this replacement could make the process flow easier to understand.
        p = type(_compointer_base)(
            f"POINTER({self.__name__})",
            _ptr_bases,
            {"__com_interface__": self, "_needs_com_addref_": None},
        )

        from ctypes import _pointer_type_cache  # type: ignore

        _pointer_type_cache[self] = p

        if self._case_insensitive_:
            _meta_patch.case_insensitive(p)
        _meta_patch.reference_fix(POINTER(p))  # type: ignore

        return self

    def __setattr__(self, name, value):
        if name == "_methods_":
            # XXX I'm no longer sure why the code generator generates
            # "_methods_ = []" in the interface definition, and later
            # overrides this by "Interface._methods_ = [...]
            # assert self.__dict__.get("_methods_", None) is None
            self._make_methods(value)
            self._make_specials()
        elif name == "_disp_methods_":
            assert self.__dict__.get("_disp_methods_", None) is None
            self._make_dispmethods(value)
            self._make_specials()
        type.__setattr__(self, name, value)

    def _make_specials(self):
        # This call installs methods that forward the Python protocols
        # to COM protocols.

        def has_name(name):
            # Determine whether a property or method named 'name'
            # exists
            if self._case_insensitive_:
                return name.lower() in self.__map_case__
            return hasattr(self, name)

        # XXX These special methods should be generated by the code generator.
        if has_name("Count"):
            _meta_patch.sized(self)
        if has_name("Item"):
            _meta_patch.callable_and_subscriptable(self)
        if has_name("_NewEnum"):
            _meta_patch.iterator(self)

    def _make_case_insensitive(self):
        # The __map_case__ dictionary maps lower case names to the
        # names in the original spelling to enable case insensitive
        # method and attribute access.
        try:
            self.__dict__["__map_case__"]
        except KeyError:
            d = {}
            d.update(getattr(self, "__map_case__", {}))
            self.__map_case__ = d

    def _make_dispmethods(self, methods: List["_DispMemberSpec"]) -> None:
        if self._case_insensitive_:
            self._make_case_insensitive()
        # create dispinterface methods and properties on the interface 'self'
        member_gen = DispMemberGenerator(self.__name__)
        for m in methods:
            member_gen.add(m)
        for name, func_or_prop, is_prop in member_gen.items():
            setattr(self, name, func_or_prop)
            # COM is case insensitive.
            # For a method, this is the real name.  For a property,
            # this is the name WITHOUT the _set_ or _get_ prefix.
            if self._case_insensitive_:
                self.__map_case__[name.lower()] = name
                if is_prop:
                    self.__map_case__[name[5:].lower()] = name[5:]
        for name, accessor in member_gen.properties():
            setattr(self, name, accessor)
            # COM is case insensitive
            if self._case_insensitive_:
                self.__map_case__[name.lower()] = name

    def __get_baseinterface_methodcount(self):
        "Return the number of com methods in the base interfaces"
        result = 0
        for itf in self.mro()[1:-1]:
            if "_methods_" in vars(itf):
                result += len(vars(itf)["_methods_"])
            else:
                raise TypeError(f"baseinterface '{itf.__name__}' has no _methods_")
        return result

    def _make_methods(self, methods: List["_ComMemberSpec"]) -> None:
        if self._case_insensitive_:
            self._make_case_insensitive()
        # register com interface. we insist on an _iid_ in THIS class!
        try:
            iid = self.__dict__["_iid_"]
        except KeyError:
            raise AttributeError("this class must define an _iid_")
        else:
            com_interface_registry[str(iid)] = self
        # create members
        vtbl_offset = self.__get_baseinterface_methodcount()
        member_gen = ComMemberGenerator(self.__name__, vtbl_offset, self._iid_)
        # create private low level, and public high level methods
        for m in methods:
            member_gen.add(m)
        for name, func, raw_func, is_prop in member_gen.methods():
            raw_mth = instancemethod(raw_func, None, self)
            setattr(self, f"_{self.__name__}__com_{name}", raw_mth)
            mth = instancemethod(func, None, self)
            if not is_prop:
                # We install the method in the class, except when it's a property.
                # And we make sure we don't overwrite a property that's already present.
                mthname = name if not hasattr(self, name) else f"_{name}"
                setattr(self, mthname, mth)
            # For a method, this is the real name.
            # For a property, this is the name WITHOUT the _set_ or _get_ prefix.
            if self._case_insensitive_:
                self.__map_case__[name.lower()] = name
                if is_prop:
                    self.__map_case__[name[5:].lower()] = name[5:]
        # create public properties / attribute accessors
        for name, accessor in member_gen.properties():
            # Again, we should not overwrite class attributes that are already present.
            propname = name if not hasattr(self, name) else f"_{name}"
            setattr(self, propname, accessor)
            # COM is case insensitive
            if self._case_insensitive_:
                self.__map_case__[name.lower()] = name


################################################################


# will not work if we change the order of the two base classes!
class _compointer_meta(type(c_void_p), _cominterface_meta):
    """metaclass for COM interface pointer classes"""

    pass  # no functionality, but needed to avoid a metaclass conflict


class _compointer_base(c_void_p, metaclass=_compointer_meta):
    "base class for COM interface pointer classes"

    def __del__(self, _debug=logger.debug):
        "Release the COM refcount we own."
        if self:
            # comtypes calls CoUninitialize() when the atexit handlers
            # runs.  CoUninitialize() cleans up the COM objects that
            # are still alive. Python COM pointers may still be
            # present but we can no longer call Release() on them -
            # this may give a protection fault.  So we need the
            # _com_shutting_down flag.
            #
            if not type(self)._com_shutting_down:
                _debug("Release %s", self)
                self.Release()  # type: ignore

    def __eq__(self, other):
        if not isinstance(other, _compointer_base):
            return False
        # get the value property of the c_void_p baseclass, this is the pointer value
        return (
            super(_compointer_base, self).value == super(_compointer_base, other).value
        )

    def __hash__(self):
        """Return the hash value of the pointer."""
        # hash the pointer values
        return hash(super(_compointer_base, self).value)

    # redefine the .value property; return the object itself.
    def __get_value(self):
        return self

    value = property(__get_value, doc="""Return self.""")

    def __repr__(self):
        ptr = super(_compointer_base, self).value
        return f"<{self.__class__.__name__} ptr=0x{ptr or 0:x} at {id(self):x}>"

    # This fixes the problem when there are multiple python interface types
    # wrapping the same COM interface.  This could happen because some interfaces
    # are contained in multiple typelibs.
    #
    # It also allows to pass a CoClass instance to an api
    # expecting a COM interface.
    @classmethod
    def from_param(cls, value):
        """Convert 'value' into a COM pointer to the interface.

        This method accepts a COM pointer, or a CoClass instance
        which is QueryInterface()d."""
        if value is None:
            return None
        # CLF: 2013-01-18
        # A default value of 0, meaning null, can pass through to here.
        if value == 0:
            return None
        if isinstance(value, cls):
            return value
        # multiple python interface types for the same COM interface.
        # Do we need more checks here?
        if cls._iid_ == getattr(value, "_iid_", None):
            return value
        # Accept an CoClass instance which exposes the interface required.
        try:
            table = value._com_pointers_
        except AttributeError:
            pass
        else:
            try:
                # a kind of QueryInterface
                return table[cls._iid_]
            except KeyError:
                raise TypeError(f"Interface {cls._iid_} not supported")
        return value.QueryInterface(cls.__com_interface__)  # type: ignore


################################################################
# IUnknown, the root of all evil...

_T_IUnknown = TypeVar("_T_IUnknown", bound="IUnknown")

if TYPE_CHECKING:

    class _IUnknown_Base(c_void_p, metaclass=_cominterface_meta):  # type: ignore
        """This is workaround to avoid false-positive of static type checking.

        `IUnknown` behaves as a ctypes type, and `POINTER` can take it.
        This behavior is defined by some metaclasses in runtime.

        In runtime, this symbol in the namespace is just alias for
        `builtins.object`.
        """

        ...

else:
    _IUnknown_Base = object


class IUnknown(_IUnknown_Base, metaclass=_cominterface_meta):
    """The most basic COM interface.

    Each subclasses of IUnknown must define these class attributes:

    _iid_ - a GUID instance defining the identifier of this interface

    _methods_ - a list of methods for this interface.

    The _methods_ list must in VTable order.  Methods are specified
    with STDMETHOD or COMMETHOD calls.
    """

    _case_insensitive_: ClassVar[bool] = False
    _iid_: ClassVar[GUID] = GUID("{00000000-0000-0000-C000-000000000046}")
    _methods_: ClassVar[List["_ComMemberSpec"]] = [
        STDMETHOD(HRESULT, "QueryInterface", [POINTER(GUID), POINTER(c_void_p)]),
        STDMETHOD(c_ulong, "AddRef"),
        STDMETHOD(c_ulong, "Release"),
    ]

    # NOTE: Why not `QueryInterface(T) -> _Pointer[T]`?
    # Any static type checkers is not able to provide members of `T` from `_Pointer[T]`,
    # regardless of the pointer is able to access members of contents in runtime.
    # And if `isinstance(p, POINTER(T))` is `True`, then `isinstance(p, T)` is also `True`.
    # So returning `T` is not a lie, and good way to know what members the class has.
    def QueryInterface(
        self, interface: Type[_T_IUnknown], iid: Optional[GUID] = None
    ) -> _T_IUnknown:
        """QueryInterface(interface) -> instance"""
        p = POINTER(interface)()
        if iid is None:
            iid = interface._iid_
        self.__com_QueryInterface(byref(iid), byref(p))  # type: ignore
        clsid = self.__dict__.get("__clsid")
        if clsid is not None:
            p.__dict__["__clsid"] = clsid
        return p  # type: ignore

    # these are only so that they get a docstring.
    # XXX There should be other ways to install a docstring.
    def AddRef(self) -> int:
        """Increase the internal refcount by one and return it."""
        return self.__com_AddRef()  # type: ignore

    def Release(self) -> int:
        """Decrease the internal refcount by one and return it."""
        return self.__com_Release()  # type: ignore


################################################################
