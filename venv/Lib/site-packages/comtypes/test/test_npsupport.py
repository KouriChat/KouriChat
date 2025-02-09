import datetime
import functools
import importlib
import inspect
import unittest
from ctypes import c_long, c_double, pointer, POINTER
from decimal import Decimal

import comtypes._npsupport
from comtypes import IUnknown
from comtypes._safearray import SafeArrayGetVartype
from comtypes.automation import (
    BSTR,
    VT_BSTR,
    VT_DATE,
    VT_I4,
    _midlSAFEARRAY,
    VARIANT,
    VT_VARIANT,
    VARIANT_BOOL,
)
from comtypes.safearray import safearray_as_ndarray

try:
    import numpy
except ImportError:
    numpy = None


def setUpModule():
    """Only run the module if we can import numpy."""
    if numpy is None:
        raise unittest.SkipTest("Skipping test_npsupport as numpy not installed.")


def get_ndarray(sa):
    """Get an array from a safe array type"""
    with safearray_as_ndarray:
        return sa[0]


def com_refcnt(o):
    """Return the COM refcount of an interface pointer"""
    import gc

    gc.collect()
    gc.collect()
    o.AddRef()
    return o.Release()


def enabled_disabled(disabled_error):
    """Decorator for testing which will replace the original test method with
    two new methods in the same local frame, one will be called where npsupport
    is enabled, the other where it is disabled. For the disabled version, it is
    expected that disabled_error will be raised by the function.
    """
    frame_locals = inspect.currentframe().f_back.f_locals

    def decorator_enabled_disabled(func):
        @functools.wraps(func)
        def call_enabled(self):
            from comtypes import npsupport

            npsupport.enable()
            func(self)

        @functools.wraps(func)
        def call_disabled(self):
            from comtypes import npsupport

            if npsupport.enabled:
                raise EnvironmentError(
                    "Expected numpy interop not to be enabled but it is."
                )
            with self.assertRaises(disabled_error):
                func(self)

        frame_locals[func.__name__ + "_enabled"] = call_enabled
        frame_locals[func.__name__ + "_disabled"] = call_disabled

    return decorator_enabled_disabled


class NumpySupportTestCase(unittest.TestCase):
    def setUp(self):
        # we reload the module in between tests to disable the previously
        # enabled interop functionality
        importlib.reload(comtypes._npsupport)
        comtypes.npsupport = comtypes._npsupport.interop

    @enabled_disabled(disabled_error=ImportError)
    def test_not_imported_imported(self):
        np = comtypes.npsupport.numpy
        self.assertEqual(np, numpy)

    def test_nested_contexts(self):
        t = _midlSAFEARRAY(BSTR)
        sa = t.from_param(["a", "b", "c"])

        first = sa[0]
        with safearray_as_ndarray:
            second = sa[0]
            with safearray_as_ndarray:
                third = sa[0]
            fourth = sa[0]
        fifth = sa[0]

        self.assertTrue(isinstance(first, tuple))
        self.assertTrue(isinstance(second, numpy.ndarray))
        self.assertTrue(isinstance(third, numpy.ndarray))
        self.assertTrue(isinstance(fourth, numpy.ndarray))
        self.assertTrue(isinstance(fifth, tuple))

    @unittest.skip(
        "Skipping because numpy cannot currently create an array of variants "
        "because it doesn't recognise the VARIANT_BOOL typecode 'v'."
    )
    def test_datetime64_ndarray(self):
        comtypes.npsupport.enable()
        dates = numpy.array(
            [
                numpy.datetime64("2000-01-01T05:30:00", "s"),
                numpy.datetime64("1800-01-01T05:30:00", "ms"),
                numpy.datetime64("2014-03-07T00:12:56", "us"),
                numpy.datetime64("2000-01-01T12:34:56", "ns"),
            ]
        )

        t = _midlSAFEARRAY(VARIANT)
        sa = t.from_param(dates)
        arr = get_ndarray(sa).astype(dates.dtype)
        self.assertTrue((dates == arr).all())

    @unittest.skip(
        "This fails with a 'library not registered' error.  Need to figure "
        "out how to register TestComServerLib (without admin if possible)."
    )
    def test_UDT_ndarray(self):
        from comtypes.gen.TestComServerLib import MYCOLOR

        t = _midlSAFEARRAY(MYCOLOR)
        self.assertTrue(t is _midlSAFEARRAY(MYCOLOR))

        sa = t.from_param([MYCOLOR(0, 0, 0), MYCOLOR(1, 2, 3)])
        arr = get_ndarray(sa)

        self.assertTrue(isinstance(arr, numpy.ndarray))
        # The conversion code allows numpy to choose the dtype of
        # structured data.  This dtype is structured under numpy 1.5, 1.7 and
        # 1.8, and object in 1.6. Instead of assuming either of these, check
        # the array contents based on the chosen type.
        if arr.dtype is numpy.dtype(object):
            data = [(x.red, x.green, x.blue) for x in arr]
        else:
            float_dtype = numpy.dtype("float64")
            self.assertIs(arr.dtype[0], float_dtype)
            self.assertIs(arr.dtype[1], float_dtype)
            self.assertIs(arr.dtype[2], float_dtype)
            data = [tuple(x) for x in arr]
        self.assertEqual(data, [(0.0, 0.0, 0.0), (1.0, 2.0, 3.0)])

    def test_VT_BOOL_ndarray(self):
        t = _midlSAFEARRAY(VARIANT_BOOL)

        sa = t.from_param([True, False, True, False])
        arr = get_ndarray(sa)
        self.assertEqual(numpy.dtype(numpy.bool_), arr.dtype)
        self.assertTrue(isinstance(arr, numpy.ndarray))
        self.assertTrue((arr == (True, False, True, False)).all())

    def test_VT_BSTR_ndarray(self):
        t = _midlSAFEARRAY(BSTR)

        sa = t.from_param(["a", "b", "c"])
        arr = get_ndarray(sa)

        self.assertTrue(isinstance(arr, numpy.ndarray))
        self.assertEqual(numpy.dtype("<U1"), arr.dtype)
        self.assertTrue((arr == ("a", "b", "c")).all())
        self.assertEqual(SafeArrayGetVartype(sa), VT_BSTR)

    @enabled_disabled(disabled_error=ValueError)
    def test_VT_I4_ndarray(self):
        t = _midlSAFEARRAY(c_long)

        in_arr = numpy.array([11, 22, 33])
        sa = t.from_param(in_arr)

        arr = get_ndarray(sa)

        self.assertTrue(isinstance(arr, numpy.ndarray))
        self.assertEqual(numpy.dtype(int), arr.dtype)
        self.assertTrue((arr == in_arr).all())
        self.assertEqual(SafeArrayGetVartype(sa), VT_I4)

    @enabled_disabled(disabled_error=ValueError)
    def test_array(self):
        t = _midlSAFEARRAY(c_double)
        pat = pointer(t())

        pat[0] = numpy.zeros(32, dtype=float)
        arr = get_ndarray(pat[0])
        self.assertTrue(isinstance(arr, numpy.ndarray))
        self.assertEqual(numpy.dtype(float), arr.dtype)
        self.assertTrue((arr == (0.0,) * 32).all())

        data = ((1.0, 2.0, 3.0), (4.0, 5.0, 6.0), (7.0, 8.0, 9.0))
        a = numpy.array(data, dtype=float)
        pat[0] = a
        arr = get_ndarray(pat[0])
        self.assertTrue(isinstance(arr, numpy.ndarray))
        self.assertEqual(numpy.dtype(float), arr.dtype)
        self.assertTrue((arr == data).all())

        data = ((1.0, 2.0), (3.0, 4.0), (5.0, 6.0))
        a = numpy.array(data, dtype=float, order="F")
        pat[0] = a
        arr = get_ndarray(pat[0])
        self.assertTrue(isinstance(arr, numpy.ndarray))
        self.assertEqual(numpy.dtype(float), arr.dtype)
        self.assertEqual(pat[0][0], data)

    @unittest.skip(
        "Skipping because creating an ndarray from ctypes pointer to c_void_p "
        "is not currently supported."
    )
    def test_VT_UNKNOWN_multi_ndarray(self):
        a = _midlSAFEARRAY(POINTER(IUnknown))
        t = _midlSAFEARRAY(POINTER(IUnknown))
        self.assertTrue(a is t)

        from comtypes.typeinfo import CreateTypeLib

        # will never be saved to disk
        punk = CreateTypeLib("spam").QueryInterface(IUnknown)

        # initial refcount
        initial = com_refcnt(punk)

        # This should increase the refcount by 4
        sa = t.from_param((punk,) * 4)
        self.assertEqual(initial + 4, com_refcnt(punk))

        # Unpacking the array must not change the refcount, and must
        # return an equal object. Creating an ndarray may change the
        # refcount.
        arr = get_ndarray(sa)
        self.assertTrue(isinstance(arr, numpy.ndarray))
        self.assertEqual(numpy.dtype(object), arr.dtype)
        self.assertTrue((arr == (punk,) * 4).all())
        self.assertEqual(initial + 8, com_refcnt(punk))

        del arr
        self.assertEqual(initial + 4, com_refcnt(punk))

        del sa
        self.assertEqual(initial, com_refcnt(punk))

        # This should increase the refcount by 2
        sa = t.from_param((punk, None, punk, None))
        self.assertEqual(initial + 2, com_refcnt(punk))

        null = POINTER(IUnknown)()
        arr = get_ndarray(sa)
        self.assertTrue(isinstance(arr, numpy.ndarray))
        self.assertEqual(numpy.dtype(object), arr.dtype)
        self.assertTrue((arr == (punk, null, punk, null)).all())

        del sa
        del arr
        self.assertEqual(initial, com_refcnt(punk))

    @unittest.skip(
        "Skipping because numpy cannot currently create an array of variants "
        "because it doesn't recognise the VARIANT_BOOL typecode 'v'."
    )
    def test_VT_VARIANT_ndarray(self):
        comtypes.npsupport.enable()
        t = _midlSAFEARRAY(VARIANT)

        now = datetime.datetime.now()
        inarr = numpy.array(
            [11, "22", "33", 44.0, None, True, now, Decimal("3.14")]
        ).reshape(2, 4)
        sa = t.from_param(inarr)
        arr = get_ndarray(sa)
        self.assertEqual(numpy.dtype(object), arr.dtype)
        self.assertTrue(isinstance(arr, numpy.ndarray))
        self.assertTrue((arr == inarr).all())
        self.assertEqual(SafeArrayGetVartype(sa), VT_VARIANT)


class NumpyVariantTest(unittest.TestCase):
    def setUp(self):
        # we reload the module in between tests to disable the previously
        # enabled interop functionality
        importlib.reload(comtypes._npsupport)
        comtypes.npsupport = comtypes._npsupport.interop

    @enabled_disabled(disabled_error=ValueError)
    def test_double(self):
        for dtype in ("float32", "float64"):
            # because of FLOAT rounding errors, whi will only work for
            # certain values!
            a = numpy.array([1.0, 2.0, 3.0, 4.5], dtype=dtype)
            v = VARIANT()
            v.value = a
            self.assertTrue((v.value == a).all())

    @enabled_disabled(disabled_error=ValueError)
    def test_int(self):
        for dtype in (
            "int8",
            "int16",
            "int32",
            "int64",
            "uint8",
            "uint16",
            "uint32",
            "uint64",
        ):
            a = numpy.array((1, 1, 1, 1), dtype=dtype)
            v = VARIANT()
            v.value = a
            self.assertTrue((v.value == a).all())

    @enabled_disabled(disabled_error=ValueError)
    def test_datetime64(self):
        dates = [
            numpy.datetime64("2000-01-01T05:30:00", "s"),
            numpy.datetime64("1800-01-01T05:30:00", "ms"),
            numpy.datetime64("2000-01-01T12:34:56", "us"),
        ]

        for date in dates:
            v = VARIANT()
            v.value = date
            self.assertEqual(v.vt, VT_DATE)
            self.assertEqual(v.value, date.astype(datetime.datetime))

    @unittest.skip(
        "Skipping because numpy cannot currently create an array of variants "
        "because it doesn't recognise the VARIANT_BOOL typecode 'v'."
    )
    def test_mixed(self):
        comtypes.npsupport.enable()
        now = datetime.datetime.now()
        a = numpy.array([11, "22", None, True, now, Decimal("3.14")]).reshape(2, 3)
        v = VARIANT()
        v.value = a
        self.assertTrue((v.value == a).all())


if __name__ == "__main__":
    unittest.main()
