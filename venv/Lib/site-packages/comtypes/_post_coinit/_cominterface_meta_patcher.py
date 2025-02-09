import types
from _ctypes import COMError
from typing import Type

from comtypes import patcher


_all_slice = slice(None, None, None)


def case_insensitive(p: Type) -> None:
    @patcher.Patch(p)
    class CaseInsensitive(object):
        # case insensitive attributes for COM methods and properties
        def __getattr__(self, name):
            """Implement case insensitive access to methods and properties"""
            try:
                fixed_name = self.__map_case__[name.lower()]
            except KeyError:
                raise AttributeError(name)  # Should we use exception-chaining?
            if fixed_name != name:  # prevent unbounded recursion
                return getattr(self, fixed_name)
            raise AttributeError(name)

        # __setattr__ is pretty heavy-weight, because it is called for
        # EVERY attribute assignment.  Settings a non-com attribute
        # through this function takes 8.6 usec, while without this
        # function it takes 0.7 sec - 12 times slower.
        #
        # How much faster would this be if implemented in C?
        def __setattr__(self, name, value):
            """Implement case insensitive access to methods and properties"""
            object.__setattr__(self, self.__map_case__.get(name.lower(), name), value)


def reference_fix(pp: Type) -> None:
    @patcher.Patch(pp)
    class ReferenceFix(object):
        def __setitem__(self, index, value):
            # We override the __setitem__ method of the
            # POINTER(POINTER(interface)) type, so that the COM
            # reference count is managed correctly.
            #
            # This is so that we can implement COM methods that have to
            # return COM pointers more easily and consistent.  Instead of
            # using CopyComPointer in the method implementation, we can
            # simply do:
            #
            # def GetTypeInfo(self, this, ..., pptinfo):
            #     if not pptinfo: return E_POINTER
            #     pptinfo[0] = a_com_interface_pointer
            #     return S_OK
            if index != 0:
                # CopyComPointer, which is in _ctypes, does only
                # handle an index of 0.  This code does what
                # CopyComPointer should do if index != 0.
                if bool(value):
                    value.AddRef()
                super(pp, self).__setitem__(index, value)  # type: ignore
                return
            from _ctypes import CopyComPointer

            CopyComPointer(value, self)  # type: ignore


def sized(itf: Type) -> None:
    @patcher.Patch(itf)
    class _(object):
        def __len__(self):
            "Return the the 'self.Count' property."
            return self.Count


def callable_and_subscriptable(itf: Type) -> None:
    @patcher.Patch(itf)
    class _(object):
        # 'Item' is the 'default' value.  Make it available by
        # calling the instance (Not sure this makes sense, but
        # win32com does this also).
        def __call__(self, *args, **kw):
            "Return 'self.Item(*args, **kw)'"
            return self.Item(*args, **kw)

        # does this make sense? It seems that all standard typelibs I've
        # seen so far that support .Item also support ._NewEnum
        @patcher.no_replace
        def __getitem__(self, index):
            "Return 'self.Item(index)'"
            # Handle tuples and all-slice
            if isinstance(index, tuple):
                args = index
            elif index == _all_slice:
                args = ()
            else:
                args = (index,)

            try:
                result = self.Item(*args)
            except COMError as err:
                (hresult, text, details) = err.args
                if hresult == -2147352565:  # DISP_E_BADINDEX
                    raise IndexError("invalid index")
                else:
                    raise

            # Note that result may be NULL COM pointer. There is no way
            # to interpret this properly, so it is returned as-is.

            # Hm, should we call __ctypes_from_outparam__ on the
            # result?
            return result

        @patcher.no_replace
        def __setitem__(self, index, value):
            "Attempt 'self.Item[index] = value'"
            try:
                self.Item[index] = value
            except COMError as err:
                (hresult, text, details) = err.args
                if hresult == -2147352565:  # DISP_E_BADINDEX
                    raise IndexError("invalid index")
                else:
                    raise
            except TypeError:
                msg = f"{type(self)!r} object does not support item assignment"
                raise TypeError(msg)


def iterator(itf: Type) -> None:
    @patcher.Patch(itf)
    class _(object):
        def __iter__(self):
            "Return an iterator over the _NewEnum collection."
            # This method returns a pointer to _some_ _NewEnum interface.
            # It relies on the fact that the code generator creates next()
            # methods for them automatically.
            #
            # Better would maybe to return an object that
            # implements the Python iterator protocol, and
            # forwards the calls to the COM interface.
            enum = self._NewEnum
            if isinstance(enum, types.MethodType):
                # _NewEnum should be a propget property, with dispid -4.
                #
                # Sometimes, however, it is a method.
                enum = enum()
            if hasattr(enum, "Next"):
                return enum
            # _NewEnum returns an IUnknown pointer, QueryInterface() it to
            # IEnumVARIANT
            from comtypes.automation import IEnumVARIANT

            return enum.QueryInterface(IEnumVARIANT)
