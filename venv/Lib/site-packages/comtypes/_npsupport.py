"""Consolidation of numpy support utilities."""

import sys

is_64bits = sys.maxsize > 2**32


class Interop:
    """Class encapsulating all the functionality necessary to allow interop of
    comtypes with numpy. Needs to be enabled with the "enable()" method.
    """

    def __init__(self):
        self.enabled = False
        self.VARIANT_dtype = None
        self.typecodes = {}
        self.datetime64 = None
        self.com_null_date64 = None

    def _make_variant_dtype(self):
        """Create a dtype for VARIANT. This requires support for Unions, which
        is available in numpy version 1.7 or greater.

        This does not support the decimal type.

        Returns None if the dtype cannot be created.
        """
        if not self.enabled:
            return None
        # pointer typecode
        ptr_typecode = "<u8" if is_64bits else "<u4"

        _tagBRECORD_format = [
            ("pvRecord", ptr_typecode),
            ("pRecInfo", ptr_typecode),
        ]

        # overlapping typecodes only allowed in numpy version 1.7 or greater
        U_VARIANT_format = dict(
            names=[
                "VT_BOOL",
                "VT_I1",
                "VT_I2",
                "VT_I4",
                "VT_I8",
                "VT_INT",
                "VT_UI1",
                "VT_UI2",
                "VT_UI4",
                "VT_UI8",
                "VT_UINT",
                "VT_R4",
                "VT_R8",
                "VT_CY",
                "c_wchar_p",
                "c_void_p",
                "pparray",
                "bstrVal",
                "_tagBRECORD",
            ],
            formats=[
                "<i2",
                "<i1",
                "<i2",
                "<i4",
                "<i8",
                "<i4",
                "<u1",
                "<u2",
                "<u4",
                "<u8",
                "<u4",
                "<f4",
                "<f8",
                "<i8",
                ptr_typecode,
                ptr_typecode,
                ptr_typecode,
                ptr_typecode,
                _tagBRECORD_format,
            ],
            offsets=[0] * 19,  # This is what makes it a union
        )

        tagVARIANT_format = [
            ("vt", "<u2"),
            ("wReserved1", "<u2"),
            ("wReserved2", "<u2"),
            ("wReserved3", "<u2"),
            ("_", U_VARIANT_format),
        ]

        return self.numpy.dtype(tagVARIANT_format)

    def _check_ctypeslib_typecodes(self):
        if not self.enabled:
            return {}
        import numpy as np
        from numpy import ctypeslib

        try:
            from numpy.ctypeslib import _typecodes
        except ImportError:
            from numpy.ctypeslib import as_ctypes_type

            dtypes_to_ctypes = {}

            for tp in set(np.sctypeDict.values()):
                try:
                    ctype_for = as_ctypes_type(tp)
                    dtypes_to_ctypes[np.dtype(tp).str] = ctype_for
                except NotImplementedError:
                    continue
            ctypeslib._typecodes = dtypes_to_ctypes
        return ctypeslib._typecodes

    def isndarray(self, value):
        """Check if a value is an ndarray.

        This cannot succeed if numpy is not available.

        """
        if not self.enabled:
            if hasattr(value, "__array_interface__"):
                raise ValueError(
                    (
                        "Argument {0} appears to be a numpy.ndarray, but "
                        "comtypes numpy support has not been enabled. Please "
                        "try calling comtypes.npsupport.enable_numpy_interop()"
                        " before passing ndarrays as parameters."
                    ).format(value)
                )
            return False

        return isinstance(value, self.numpy.ndarray)

    def isdatetime64(self, value):
        """Check if a value is a datetime64.

        This cannot succeed if datetime64 is not available.

        """
        if not self.enabled:
            return False
        return isinstance(value, self.numpy.datetime64)

    @property
    def numpy(self):
        """The numpy package."""
        if self.enabled:
            import numpy

            return numpy
        raise ImportError(
            "In comtypes>=1.2.0 numpy interop must be explicitly enabled with "
            "comtypes.npsupport.enable_numpy_interop before attempting to use "
            "numpy features."
        )

    def enable(self):
        """Enables numpy/comtypes interop."""
        # don't do this twice
        if self.enabled:
            return
        # first we have to be able to import numpy
        import numpy

        # if that succeeded we can be enabled
        self.enabled = True
        self.VARIANT_dtype = self._make_variant_dtype()
        self.typecodes = self._check_ctypeslib_typecodes()
        self.com_null_date64 = self.numpy.datetime64("1899-12-30T00:00:00", "ns")


interop = Interop()

__all__ = ["interop"]
