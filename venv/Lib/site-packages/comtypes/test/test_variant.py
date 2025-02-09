import datetime
import decimal
import sys
import unittest
from ctypes import (
    POINTER,
    byref,
    c_byte,
    c_char,
    c_double,
    c_float,
    c_int,
    c_int64,
    c_short,
    c_ubyte,
    c_uint,
    c_uint64,
    c_ushort,
    pointer,
)

from comtypes import GUID, IUnknown
from comtypes.automation import (
    DISPPARAMS,
    VARIANT,
    VT_BSTR,
    VT_BYREF,
    VT_CY,
    VT_DATE,
    VT_DECIMAL,
    VT_EMPTY,
    VT_ERROR,
    VT_I1,
    VT_I2,
    VT_I4,
    VT_I8,
    VT_NULL,
    VT_R4,
    VT_R8,
    VT_UI1,
    VT_UI2,
    VT_UI4,
    VT_UI8,
)
from comtypes.test.find_memleak import find_memleak
from comtypes.typeinfo import LoadRegTypeLib


def get_refcnt(comptr):
    # return the COM reference count of a COM interface pointer
    if not comptr:
        return 0
    comptr.AddRef()
    return comptr.Release()


class VariantTestCase(unittest.TestCase):
    def test_constants(self):
        empty = VARIANT.empty
        self.assertEqual(empty.vt, VT_EMPTY)
        self.assertTrue(empty.value is None)

        null = VARIANT.null
        self.assertEqual(null.vt, VT_NULL)
        self.assertTrue(null.value is None)

        missing = VARIANT.missing
        self.assertEqual(missing.vt, VT_ERROR)
        self.assertRaises(NotImplementedError, lambda: missing.value)

    def test_com_refcounts(self):
        # typelib for oleaut32
        tlb = LoadRegTypeLib(GUID("{00020430-0000-0000-C000-000000000046}"), 2, 0, 0)
        rc = get_refcnt(tlb)

        p = tlb.QueryInterface(IUnknown)
        self.assertEqual(get_refcnt(tlb), rc + 1)

        del p
        self.assertEqual(get_refcnt(tlb), rc)

    def test_com_pointers(self):
        # Storing a COM interface pointer in a VARIANT increments the refcount,
        # changing the variant to contain something else decrements it
        tlb = LoadRegTypeLib(GUID("{00020430-0000-0000-C000-000000000046}"), 2, 0, 0)
        rc = get_refcnt(tlb)

        v = VARIANT(tlb)
        self.assertEqual(get_refcnt(tlb), rc + 1)

        p = v.value
        self.assertEqual(get_refcnt(tlb), rc + 2)
        del p
        self.assertEqual(get_refcnt(tlb), rc + 1)

        v.value = None
        self.assertEqual(get_refcnt(tlb), rc)

    def test_null_com_pointers(self):
        p = POINTER(IUnknown)()
        self.assertEqual(get_refcnt(p), 0)

        VARIANT(p)
        self.assertEqual(get_refcnt(p), 0)

    def test_dispparams(self):
        # DISPPARAMS is a complex structure, well worth testing.
        d = DISPPARAMS()
        d.rgvarg = (VARIANT * 3)()
        values = [1, 5, 7]
        for i, v in enumerate(values):
            d.rgvarg[i].value = v
        result = [d.rgvarg[i].value for i in range(3)]
        self.assertEqual(result, values)

    def test_pythonobjects(self):
        if sys.version_info >= (3, 0):
            objects = [None, 42, 3.14, True, False, "abc", "abc", 7]
        else:
            objects = [None, 42, 3.14, True, False, "abc", "abc", 7]
        for x in objects:
            v = VARIANT(x)
            self.assertEqual(x, v.value)

    def test_integers(self):
        v = VARIANT()

        int_type = int if sys.version_info >= (3, 0) else (int, long)

        if hasattr(sys, "maxint"):
            # this test doesn't work in Python 3000
            v.value = sys.maxsize
            self.assertEqual(v.value, sys.maxsize)
            self.assertIsInstance(v.value, int_type)

            v.value += 1
            self.assertEqual(v.value, sys.maxsize + 1)
            self.assertIsInstance(v.value, int_type)

        v.value = 1

        self.assertEqual(v.value, 1)
        self.assertIsInstance(v.value, int_type)

    def test_datetime(self):
        now = datetime.datetime.now()

        v = VARIANT()
        v.value = now
        self.assertEqual(v.vt, VT_DATE)
        self.assertEqual(v.value, now)

    def test_decimal_as_currency(self):
        value = decimal.Decimal("3.14")

        v = VARIANT()
        v.value = value
        self.assertEqual(v.vt, VT_CY)
        self.assertEqual(v.value, value)

    def test_decimal_as_decimal(self):
        v = VARIANT()
        v.vt = VT_DECIMAL
        v.decVal.Lo64 = 1234
        v.decVal.scale = 3
        self.assertEqual(v.value, decimal.Decimal("1.234"))

        v.decVal.sign = 0x80
        self.assertEqual(v.value, decimal.Decimal("-1.234"))

        v.decVal.scale = 28
        self.assertEqual(v.value, decimal.Decimal("-1.234e-25"))

        v.decVal.scale = 12
        v.decVal.Hi32 = 100
        self.assertEqual(v.value, decimal.Decimal("-1844674407.370955162834"))

    @unittest.skip("This test causes python(3?) to crash.")
    def test_BSTR(self):
        v = VARIANT()
        v.value = "abc\x00123\x00"
        self.assertEqual(v.value, "abc\x00123\x00")

        v.value = None
        # manually clear the variant
        v._.VT_I4 = 0

        # NULL pointer BSTR should be handled as empty string
        v.vt = VT_BSTR
        self.assertTrue(v.value in ("", None))

    def test_empty_BSTR(self):
        v = VARIANT()
        v.value = ""
        self.assertEqual(v.vt, VT_BSTR)

    def test_ctypes_in_variant(self):
        v = VARIANT()
        objs = [
            (c_ubyte(3), VT_UI1),
            (c_char(b"x"), VT_UI1),
            (c_byte(3), VT_I1),
            (c_ushort(3), VT_UI2),
            (c_short(3), VT_I2),
            (c_uint(3), VT_UI4),
            (c_uint64(2**64), VT_UI8),
            (c_int(3), VT_I4),
            (c_int64(2**32), VT_I8),
            (c_double(3.14), VT_R8),
            (c_float(3.14), VT_R4),
        ]
        for value, vt in objs:
            v.value = value
            self.assertEqual(v.vt, vt)

    def test_byref(self):
        variable = c_int(42)
        v = VARIANT(byref(variable))
        self.assertEqual(v[0], 42)
        self.assertEqual(v.vt, VT_BYREF | VT_I4)
        variable.value = 96
        self.assertEqual(v[0], 96)

        variable = c_int(42)
        v = VARIANT(pointer(variable))
        self.assertEqual(v[0], 42)
        self.assertEqual(v.vt, VT_BYREF | VT_I4)
        variable.value = 96
        self.assertEqual(v[0], 96)

    def test_repr(self):
        self.assertEqual(repr(VARIANT(c_int(42))), "VARIANT(vt=0x3, 42)")
        self.assertEqual(
            repr(VARIANT(byref(c_int(42)))), "VARIANT(vt=0x4003, byref(42))"
        )
        self.assertEqual(repr(VARIANT.empty), "VARIANT.empty")
        self.assertEqual(repr(VARIANT.null), "VARIANT.null")
        self.assertEqual(repr(VARIANT.missing), "VARIANT.missing")


class ArrayTest(unittest.TestCase):
    def test_double(self):
        import array

        for typecode in "df":
            # because of FLOAT rounding errors, whi will only work for
            # certain values!
            a = array.array(typecode, (1.0, 2.0, 3.0, 4.5))
            v = VARIANT()
            v.value = a
            self.assertEqual(v.value, (1.0, 2.0, 3.0, 4.5))

    def test_int(self):
        import array

        for typecode in "bhiBHIlL":
            a = array.array(typecode, (1, 1, 1, 1))
            v = VARIANT()
            v.value = a
            self.assertEqual(v.value, (1, 1, 1, 1))


################################################################
def run_test(rep, msg, func=None, previous={}, results={}):
    # items = [None] * rep
    if func is None:
        locals = sys._getframe(1).f_locals
        func = eval("lambda: %s" % msg, locals)
    items = range(rep)
    from time import clock

    start = clock()
    for i in items:
        func()
        func()
        func()
        func()
        func()
    stop = clock()
    duration = (stop - start) * 1e6 / 5 / rep
    try:
        prev = previous[msg]
    except KeyError:
        print("%40s: %7.1f us" % (msg, duration), file=sys.stderr)
        delta = 0.0
    else:
        delta = duration / prev * 100.0
        print(
            "%40s: %7.1f us, time = %5.1f%%" % (msg, duration, delta), file=sys.stderr
        )
    results[msg] = duration
    return delta


def check_perf(rep=20000):
    from ctypes import c_int, byref
    from comtypes.automation import VARIANT
    import comtypes.automation

    print(comtypes.automation)
    variable = c_int()
    by_var = byref(variable)
    ptr_var = pointer(variable)

    if sys.version_info >= (3, 0):
        import pickle
    else:
        import cPickle as pickle
    try:
        previous = pickle.load(open("result.pickle", "rb"))
    except IOError:
        previous = {}

    results = {}

    d = 0.0
    d += run_test(rep, "VARIANT()", previous=previous, results=results)
    d += run_test(rep, "VARIANT(by_var)", previous=previous, results=results)
    d += run_test(rep, "VARIANT(ptr_var)", previous=previous, results=results)
    d += run_test(rep, "VARIANT().value", previous=previous, results=results)
    d += run_test(rep, "VARIANT(None).value", previous=previous, results=results)
    d += run_test(rep, "VARIANT(42).value", previous=previous, results=results)
    d += run_test(rep, "VARIANT(42L).value", previous=previous, results=results)
    d += run_test(rep, "VARIANT(3.14).value", previous=previous, results=results)
    d += run_test(rep, "VARIANT(u'Str').value", previous=previous, results=results)
    d += run_test(rep, "VARIANT('Str').value", previous=previous, results=results)
    d += run_test(rep, "VARIANT((42,)).value", previous=previous, results=results)
    d += run_test(rep, "VARIANT([42,]).value", previous=previous, results=results)

    print("Average duration %.1f%%" % (d / 10))
    # cPickle.dump(results, open("result.pickle", "wb"))


if __name__ == "__main__":
    try:
        unittest.main()
    except SystemExit:
        pass
    import comtypes

    print(
        "Running benchmark with comtypes %s/Python %s ..."
        % (
            comtypes.__version__,
            sys.version.split()[0],
        )
    )
    check_perf()
