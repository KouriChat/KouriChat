# comtypes._meta helper module
from ctypes import POINTER, c_void_p, cast
import comtypes

################################################################
# metaclass for CoClass (in comtypes/__init__.py)


def _wrap_coclass(self):
    # We are an IUnknown pointer, represented as a c_void_p instance,
    # but we really want this interface:
    itf = self._com_interfaces_[0]
    punk = cast(self, POINTER(itf))
    result = punk.QueryInterface(itf)
    result.__dict__["__clsid"] = str(self._reg_clsid_)
    return result


def _coclass_from_param(cls, obj):
    if isinstance(obj, (cls._com_interfaces_[0], cls)):
        return obj
    raise TypeError(obj)


#
# The mro() of a POINTER(App) type, where class App is a subclass of CoClass:
#
#  POINTER(App)
#   App
#    CoClass
#     c_void_p
#      _SimpleCData
#       _CData
#        object


class _coclass_meta(type):
    # metaclass for CoClass
    #
    # When a CoClass subclass is created, create a POINTER(...) type
    # for that class, with bases <coclass> and c_void_p.  Also, the
    # POINTER(...) type gets a __ctypes_from_outparam__ method which
    # will QueryInterface for the default interface: the first one on
    # the coclass' _com_interfaces_ list.
    def __new__(cls, name, bases, namespace):
        self = type.__new__(cls, name, bases, namespace)
        if bases == (object,):
            # HACK: Could this conditional branch be removed since it is never reached?
            # Since definition is `class CoClass(COMObject, metaclass=_coclass_meta)`,
            # the `bases` parameter passed to the `_coclass_meta.__new__` would be
            # `(COMObject,)`.
            # Moreover, since the `COMObject` derives from `object` and does not specify
            # a metaclass, `(object,)` will not be passed as the `bases` parameter
            # to the `_coclass_meta.__new__`.
            # The reason for this implementation might be a remnant of the differences
            # in how metaclasses work between Python 3.x and Python 2.x.
            # If there are no problems with the versions of Python that `comtypes`
            # supports, this removal could make the process flow easier to understand.
            return self
        # XXX We should insist that a _reg_clsid_ is present.
        if "_reg_clsid_" in namespace:
            clsid = namespace["_reg_clsid_"]
            comtypes.com_coclass_registry[str(clsid)] = self

        # `_coclass_pointer_meta` is a subclass inherited from `_coclass_meta`.
        # In other words, when the `__new__` method of this metaclass is called, an
        # instance of `_coclass_pointer_meta` might be created and assigned to `self`.
        if isinstance(self, _coclass_pointer_meta):
            # `self` is the `_coclass_pointer_meta` type or a `POINTER(coclass)` type.
            # Prevent creating/registering a pointer to a pointer (to a pointer...),
            # or specifying the metaclass type instance in the `bases` parameter when
            # instantiating it, which would lead to infinite recursion.
            # Depending on a version or revision of Python, this may be essential.
            return self

        PTR = _coclass_pointer_meta(
            f"POINTER({self.__name__})",
            (self, c_void_p),
            {
                "__ctypes_from_outparam__": _wrap_coclass,
                "from_param": classmethod(_coclass_from_param),
            },
        )
        from ctypes import _pointer_type_cache  # type: ignore

        _pointer_type_cache[self] = PTR

        return self


# will not work if we change the order of the two base classes!
class _coclass_pointer_meta(type(c_void_p), _coclass_meta):
    # metaclass for CoClass pointer

    pass  # no functionality, but needed to avoid a metaclass conflict
