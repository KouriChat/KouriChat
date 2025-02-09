import unittest as ut
from ctypes import HRESULT, POINTER, Structure, c_int, c_ulong, c_wchar_p, pointer
from typing import TYPE_CHECKING, Any, Callable, List, NamedTuple, Tuple, Type
from unittest.mock import MagicMock

import comtypes
from comtypes._memberspec import _fix_inout_args
from comtypes.client import IUnknown

if TYPE_CHECKING:
    from comtypes._memberspec import _ArgSpecElmType

WSTRING = c_wchar_p


class Test_RealWorldExamples(ut.TestCase):
    def test_IUrlHistoryStg(self):
        class Mock_STATURL(Structure):
            _fields_ = []

        spec = comtypes.COMMETHOD(
            [],
            HRESULT,
            "QueryUrl",
            (["in"], WSTRING, "pocsUrl"),
            (["in"], c_ulong, "dwFlags"),
            (["in", "out"], POINTER(Mock_STATURL), "lpSTATURL"),
        )
        orig = MagicMock()
        orig.return_value = MagicMock(spec=Mock_STATURL, name="lpSTATURL")
        fixed = _fix_inout_args(orig, spec.argtypes, spec.paramflags)

        self_ = MagicMock(name="Self")
        pocs_url = "ghi"
        dw_flags = 8
        lp_staturl = Mock_STATURL()
        ret_val = fixed(self_, pocs_url, dw_flags, lp_staturl)

        # Here we encounter a quirk of _fix_inout_args:
        #
        # When the function has only one return value,
        #   _fix_inout_args will call __ctypes_from_outparam__ on the return value of the function.
        # When there is more than one return value,
        #   _fix_inout_args will call __ctypes_from_outparam__ on the input inout parameters.
        #
        # This may be a bug, but due to backwards compatibility we won't change it
        # unless someone can demonstrate that it causes problems.

        orig.assert_called_once_with(self_, pocs_url, dw_flags, lp_staturl)

        # Not too happy about using underscore attributes, but I didn't find a cleaner way
        self.assertEqual(ret_val._mock_new_name, "()")
        ret_val_parent = ret_val._mock_new_parent
        self.assertEqual(ret_val_parent._mock_new_name, "__ctypes_from_outparam__")
        self.assertIs(ret_val_parent._mock_new_parent, orig.return_value)

        # TODO Alternative:
        self.assertEqual(
            ret_val._extract_mock_name(), "lpSTATURL.__ctypes_from_outparam__()"
        )

    def test_IMoniker(self):
        # memberspec of IMoniker.Reduce
        spec = comtypes.COMMETHOD(
            [],
            HRESULT,
            "Reduce",
            (["in"], POINTER(IUnknown), "pbc"),
            (["in"], c_ulong, "dwReduceHowFar"),
            (["in", "out"], POINTER(POINTER(IUnknown)), "ppmkToLeft"),
            (["out"], POINTER(POINTER(IUnknown)), "ppmkReduced"),
        )
        orig = MagicMock()
        ppmk_reduced = MagicMock(spec=POINTER(IUnknown), name="ppmkReduced")
        orig.return_value = (..., ppmk_reduced)
        fixed = _fix_inout_args(orig, spec.argtypes, spec.paramflags)

        self_ = MagicMock(name="Self")
        pbc = POINTER(IUnknown)()
        dw_reduce_how_far = 15
        ppmk_to_left = POINTER(IUnknown)()
        ret_val = fixed(self_, pbc, dw_reduce_how_far, ppmk_to_left)

        orig.assert_called_once()
        # (orig_0th, orig_1st, orig_2nd, orig_3rd, orig_4th), orig_kw = orig.call_args

        self.assertEqual(orig.call_args[1], {})
        self.assertTupleEqual(
            orig.call_args[0], (self_, pbc, dw_reduce_how_far, ppmk_to_left)
        )
        self.assertListEqual(ret_val, [ppmk_to_left, ppmk_reduced])

    def test_IPin(self):
        spec = comtypes.COMMETHOD(
            [],
            HRESULT,
            "QueryInternalConnections",
            (["out"], POINTER(POINTER(IUnknown)), "apPin"),  # IPin
            (["in", "out"], POINTER(c_ulong), "nPin"),
        )
        orig = MagicMock()
        apPin = MagicMock(spec=POINTER(IUnknown), name="apPin")
        orig.return_value = (apPin, ...)
        fixed = _fix_inout_args(orig, spec.argtypes, spec.paramflags)

        self_ = MagicMock(name="Self")
        # test passing in a pointer of the right type
        n_pin = pointer(c_ulong(26))
        ret_val = fixed(self_, n_pin)

        orig.assert_called_once_with(self_, n_pin)
        self.assertEqual(orig.call_args[1], {})
        self.assertListEqual(ret_val, [apPin, n_pin])

    def test_IMFAttributes(self):
        self_ = MagicMock(name="Self")
        # a memberspec of `MSVidCtlLib.IMFAttributes`
        # Notably, for the first parameters, neither 'in' nor 'out' is specified.
        # For compatibility with legacy code this should be treated as 'in'.
        spec = comtypes.COMMETHOD(
            [],
            HRESULT,
            "GetItemType",
            ([], POINTER(comtypes.GUID), "guidKey"),
            (["out"], POINTER(c_int), "pType"),
        )
        orig = MagicMock(__name__="orig")
        guidKey = comtypes.GUID("{00000000-0000-0000-0000-000000000000}")
        pType = 4
        orig.return_value = pType
        fixed = _fix_inout_args(orig, spec.argtypes, spec.paramflags)
        ret_val = fixed(self_, guidKey)

        orig.assert_called_once_with(self_, guidKey)
        self.assertEqual(ret_val, pType)


class Test_ArgsKwargsCombinations(ut.TestCase):
    def setUp(self):
        # a memberspec of `PortableDeviceApiLib.IPortableDeviceContent`
        spec = comtypes.COMMETHOD(
            [],
            HRESULT,
            "CreateObjectWithPropertiesAndData",
            (["in"], POINTER(IUnknown), "pValues"),  # IPortableDeviceValues
            (["out"], POINTER(POINTER(IUnknown)), "ppData"),  # IStream
            (["in", "out"], POINTER(c_ulong), "pdwOptimalWriteBufferSize"),
            (["in", "out"], POINTER(WSTRING), "ppszCookie"),
        )
        self.orig = MagicMock()
        self.fixed = _fix_inout_args(self.orig, spec.argtypes, spec.paramflags)
        # out and inout argument are dereferenced once before being returned
        self.pp_data = POINTER(IUnknown)()
        self.orig.return_value = (self.pp_data, ..., ...)

    def test_positionals_only(self):
        self_ = MagicMock(name="Self")
        p_val = MagicMock(spec=POINTER(IUnknown))()
        buf_size = 5
        cookie = "abc"
        ret_val = self.fixed(self_, p_val, buf_size, cookie)

        self.assertEqual(ret_val, [self.pp_data, buf_size, cookie])
        self.orig.assert_called_once()
        (orig_0th, orig_1st, orig_2nd, orig_3rd), orig_kw = self.orig.call_args
        self.assertIs(orig_0th, self_)
        self.assertEqual(orig_1st, p_val)
        self.assertIsInstance(orig_2nd, c_ulong)
        self.assertEqual(orig_2nd.value, buf_size)
        self.assertIsInstance(orig_3rd, WSTRING)
        self.assertEqual(orig_3rd.value, cookie)
        self.assertEqual(orig_kw, {})

    def test_keywords_only(self):
        self_ = MagicMock(name="Self")
        p_val = MagicMock(spec=POINTER(IUnknown))()
        buf_size = 4
        cookie = "efg"
        ret_val = self.fixed(
            self_, pValues=p_val, pdwOptimalWriteBufferSize=buf_size, ppszCookie=cookie
        )

        self.assertEqual(ret_val, [self.pp_data, buf_size, cookie])
        self.orig.assert_called_once()
        (orig_0th,), orig_kw = self.orig.call_args
        self.assertIs(orig_0th, self_)
        self.assertEqual(
            set(orig_kw), {"pValues", "pdwOptimalWriteBufferSize", "ppszCookie"}
        )
        self.assertEqual(orig_kw["pValues"], p_val)
        self.assertIsInstance(orig_kw["pdwOptimalWriteBufferSize"], c_ulong)
        self.assertEqual(orig_kw["pdwOptimalWriteBufferSize"].value, buf_size)
        self.assertIsInstance(orig_kw["ppszCookie"], WSTRING)
        self.assertEqual(orig_kw["ppszCookie"].value, cookie)

    def test_mixed_args_1(self):
        self_ = MagicMock(name="Self")
        p_val = MagicMock(spec=POINTER(IUnknown))()
        buf_size = 3
        cookie = "h"
        ret_val = self.fixed(
            self_, p_val, ppszCookie=cookie, pdwOptimalWriteBufferSize=buf_size
        )

        self.assertEqual(ret_val, [self.pp_data, buf_size, cookie])
        self.orig.assert_called_once()
        (orig_0th, orig_1st), orig_kw = self.orig.call_args
        self.assertIs(orig_0th, self_)
        self.assertEqual(orig_1st, p_val)
        self.assertEqual(set(orig_kw), {"pdwOptimalWriteBufferSize", "ppszCookie"})
        self.assertIsInstance(orig_kw["pdwOptimalWriteBufferSize"], c_ulong)
        self.assertEqual(orig_kw["pdwOptimalWriteBufferSize"].value, buf_size)
        self.assertIsInstance(orig_kw["ppszCookie"], WSTRING)
        self.assertEqual(orig_kw["ppszCookie"].value, cookie)

    def test_mixed_args_2(self):
        self_ = MagicMock(name="Self")
        p_val = MagicMock(spec=POINTER(IUnknown))()
        buf_size = 2
        cookie = "ij"
        ret_val = self.fixed(self_, p_val, buf_size, ppszCookie=cookie)

        self.assertEqual(ret_val, [self.pp_data, buf_size, cookie])
        self.orig.assert_called_once()
        (orig_0th, orig_1st, orig_2nd), orig_kw = self.orig.call_args
        self.assertIs(orig_0th, self_)
        self.assertEqual(orig_1st, p_val)
        self.assertEqual(set(orig_kw), {"ppszCookie"})
        self.assertIsInstance(orig_2nd, c_ulong)
        self.assertEqual(orig_2nd.value, buf_size)
        self.assertIsInstance(orig_kw["ppszCookie"], WSTRING)
        self.assertEqual(orig_kw["ppszCookie"].value, cookie)

    def test_omitted_arguments_autogen(self):
        self_ = MagicMock(name="Self")
        p_val = MagicMock(spec=POINTER(IUnknown))()
        ret_val = self.fixed(self_, pValues=p_val)

        self.orig.assert_called_once()
        (orig_0th,), orig_kw = self.orig.call_args
        self.assertEqual(
            set(orig_kw), {"pValues", "pdwOptimalWriteBufferSize", "ppszCookie"}
        )
        self.assertIs(orig_0th, self_)
        self.assertIs(orig_kw["pValues"], p_val)
        self.assertIsInstance(orig_kw["pdwOptimalWriteBufferSize"], c_ulong)
        self.assertEqual(orig_kw["pdwOptimalWriteBufferSize"].value, c_ulong().value)
        self.assertIsInstance(orig_kw["ppszCookie"], WSTRING)
        self.assertEqual(orig_kw["ppszCookie"].value, WSTRING().value)

        self.assertEqual(
            ret_val,
            [
                self.pp_data,
                orig_kw["pdwOptimalWriteBufferSize"].value,
                orig_kw["ppszCookie"].value,
            ],
        )


class PermutedArgspecTestingParams(NamedTuple):
    argspec: "Tuple[_ArgSpecElmType, _ArgSpecElmType, _ArgSpecElmType, _ArgSpecElmType]"
    args: Tuple[Any, Any, Any]
    orig_ret_val: Tuple[Any, Any, Any]
    fixed_ret_val: List[Any]
    call_args_validators: List[Tuple[Type[Any], Callable[[Any], Any], Any]]


class Test_ArgspecPermutations(ut.TestCase):
    def test_permutations(self):
        for testing_params in self._get_params():
            with self.subTest(testing_params.argspec):
                self_ = MagicMock(name="Self")
                orig = MagicMock(return_value=testing_params.orig_ret_val)
                spec = comtypes.COMMETHOD([], HRESULT, "foo", *testing_params.argspec)
                fixed = _fix_inout_args(orig, spec.argtypes, spec.paramflags)
                ret_val = fixed(self_, *testing_params.args)

                self.assertEqual(ret_val, testing_params.fixed_ret_val)
                orig.assert_called_once()
                (orig_0th, *orig_call_args), orig_kw = orig.call_args
                self.assertEqual(orig_kw, {})
                self.assertIs(orig_0th, self_)
                for (typ, f, val), orig in zip(
                    testing_params.call_args_validators, orig_call_args
                ):
                    self.assertIsInstance(orig, typ)
                    self.assertEqual(f(orig), val)

    def _get_params(self) -> List[PermutedArgspecTestingParams]:
        in_ = MagicMock(spec=POINTER(IUnknown))()
        out = POINTER(IUnknown)()
        inout1 = 5
        inout2 = "abc"
        IN_ARGSPEC = (["in"], POINTER(comtypes.IUnknown), "in")
        OUT_ARGSPEC = (["out"], POINTER(POINTER(comtypes.IUnknown)), "out")
        INOUT1_ARGSPEC = (["in", "out"], POINTER(c_ulong), "inout1")
        INOUT2_ARGSPEC = (["in", "out"], POINTER(WSTRING), "inout2")
        IN_VALIDATOR = (MagicMock, lambda x: x, in_)
        INOUT1_VALIDATOR = (c_ulong, lambda x: x.value, inout1)
        INOUT2_VALIDATOR = (WSTRING, lambda x: x.value, inout2)
        return [
            PermutedArgspecTestingParams(
                (IN_ARGSPEC, OUT_ARGSPEC, INOUT1_ARGSPEC, INOUT2_ARGSPEC),
                (in_, inout1, inout2),
                (out, ..., ...),
                [out, inout1, inout2],
                [IN_VALIDATOR, INOUT1_VALIDATOR, INOUT2_VALIDATOR],
            ),
            PermutedArgspecTestingParams(
                (IN_ARGSPEC, OUT_ARGSPEC, INOUT2_ARGSPEC, INOUT1_ARGSPEC),
                (in_, inout2, inout1),
                (out, ..., ...),
                [out, inout2, inout1],
                [IN_VALIDATOR, INOUT2_VALIDATOR, INOUT1_VALIDATOR],
            ),
            PermutedArgspecTestingParams(
                (IN_ARGSPEC, INOUT1_ARGSPEC, OUT_ARGSPEC, INOUT2_ARGSPEC),
                (in_, inout1, inout2),
                (..., out, ...),
                [inout1, out, inout2],
                [IN_VALIDATOR, INOUT1_VALIDATOR, INOUT2_VALIDATOR],
            ),
            PermutedArgspecTestingParams(
                (IN_ARGSPEC, INOUT1_ARGSPEC, INOUT2_ARGSPEC, OUT_ARGSPEC),
                (in_, inout1, inout2),
                (..., ..., out),
                [inout1, inout2, out],
                [IN_VALIDATOR, INOUT1_VALIDATOR, INOUT2_VALIDATOR],
            ),
            PermutedArgspecTestingParams(
                (IN_ARGSPEC, INOUT2_ARGSPEC, OUT_ARGSPEC, INOUT1_ARGSPEC),
                (in_, inout2, inout1),
                (..., out, ...),
                [inout2, out, inout1],
                [IN_VALIDATOR, INOUT2_VALIDATOR, INOUT1_VALIDATOR],
            ),
            PermutedArgspecTestingParams(
                (IN_ARGSPEC, INOUT2_ARGSPEC, INOUT1_ARGSPEC, OUT_ARGSPEC),
                (in_, inout2, inout1),
                (..., ..., out),
                [inout2, inout1, out],
                [IN_VALIDATOR, INOUT2_VALIDATOR, INOUT1_VALIDATOR],
            ),
            PermutedArgspecTestingParams(
                (OUT_ARGSPEC, IN_ARGSPEC, INOUT1_ARGSPEC, INOUT2_ARGSPEC),
                (in_, inout1, inout2),
                (out, ..., ...),
                [out, inout1, inout2],
                [IN_VALIDATOR, INOUT1_VALIDATOR, INOUT2_VALIDATOR],
            ),
            PermutedArgspecTestingParams(
                (OUT_ARGSPEC, IN_ARGSPEC, INOUT2_ARGSPEC, INOUT1_ARGSPEC),
                (in_, inout2, inout1),
                (out, ..., ...),
                [out, inout2, inout1],
                [IN_VALIDATOR, INOUT2_VALIDATOR, INOUT1_VALIDATOR],
            ),
            PermutedArgspecTestingParams(
                (OUT_ARGSPEC, INOUT1_ARGSPEC, IN_ARGSPEC, INOUT2_ARGSPEC),
                (inout1, in_, inout2),
                (out, ..., ...),
                [out, inout1, inout2],
                [INOUT1_VALIDATOR, IN_VALIDATOR, INOUT2_VALIDATOR],
            ),
            PermutedArgspecTestingParams(
                (OUT_ARGSPEC, INOUT1_ARGSPEC, INOUT2_ARGSPEC, IN_ARGSPEC),
                (inout1, inout2, in_),
                (out, ..., ...),
                [out, inout1, inout2],
                [INOUT1_VALIDATOR, INOUT2_VALIDATOR, IN_VALIDATOR],
            ),
            PermutedArgspecTestingParams(
                (OUT_ARGSPEC, INOUT2_ARGSPEC, IN_ARGSPEC, INOUT1_ARGSPEC),
                (inout2, in_, inout1),
                (out, ..., ...),
                [out, inout2, inout1],
                [INOUT2_VALIDATOR, IN_VALIDATOR, INOUT1_VALIDATOR],
            ),
            PermutedArgspecTestingParams(
                (OUT_ARGSPEC, INOUT2_ARGSPEC, INOUT1_ARGSPEC, IN_ARGSPEC),
                (inout2, inout1, in_),
                (out, ..., ...),
                [out, inout2, inout1],
                [INOUT2_VALIDATOR, INOUT1_VALIDATOR, IN_VALIDATOR],
            ),
            PermutedArgspecTestingParams(
                (INOUT1_ARGSPEC, IN_ARGSPEC, OUT_ARGSPEC, INOUT2_ARGSPEC),
                (inout1, in_, inout2),
                (..., out, ...),
                [inout1, out, inout2],
                [INOUT1_VALIDATOR, IN_VALIDATOR, INOUT2_VALIDATOR],
            ),
            PermutedArgspecTestingParams(
                (INOUT1_ARGSPEC, IN_ARGSPEC, INOUT2_ARGSPEC, OUT_ARGSPEC),
                (inout1, in_, inout2),
                (..., ..., out),
                [inout1, inout2, out],
                [INOUT1_VALIDATOR, IN_VALIDATOR, INOUT2_VALIDATOR],
            ),
            PermutedArgspecTestingParams(
                (INOUT1_ARGSPEC, OUT_ARGSPEC, IN_ARGSPEC, INOUT2_ARGSPEC),
                (inout1, in_, inout2),
                (..., out, ...),
                [inout1, out, inout2],
                [INOUT1_VALIDATOR, IN_VALIDATOR, INOUT2_VALIDATOR],
            ),
            PermutedArgspecTestingParams(
                (INOUT1_ARGSPEC, OUT_ARGSPEC, INOUT2_ARGSPEC, IN_ARGSPEC),
                (inout1, inout2, in_),
                (..., out, ...),
                [inout1, out, inout2],
                [INOUT1_VALIDATOR, INOUT2_VALIDATOR, IN_VALIDATOR],
            ),
            PermutedArgspecTestingParams(
                (INOUT1_ARGSPEC, INOUT2_ARGSPEC, IN_ARGSPEC, OUT_ARGSPEC),
                (inout1, inout2, in_),
                (..., ..., out),
                [inout1, inout2, out],
                [INOUT1_VALIDATOR, INOUT2_VALIDATOR, IN_VALIDATOR],
            ),
            PermutedArgspecTestingParams(
                (INOUT1_ARGSPEC, INOUT2_ARGSPEC, OUT_ARGSPEC, IN_ARGSPEC),
                (inout1, inout2, in_),
                (..., ..., out),
                [inout1, inout2, out],
                [INOUT1_VALIDATOR, INOUT2_VALIDATOR, IN_VALIDATOR],
            ),
            PermutedArgspecTestingParams(
                (INOUT2_ARGSPEC, IN_ARGSPEC, OUT_ARGSPEC, INOUT1_ARGSPEC),
                (inout2, in_, inout1),
                (..., out, ...),
                [inout2, out, inout1],
                [INOUT2_VALIDATOR, IN_VALIDATOR, INOUT1_VALIDATOR],
            ),
            PermutedArgspecTestingParams(
                (INOUT2_ARGSPEC, IN_ARGSPEC, INOUT1_ARGSPEC, OUT_ARGSPEC),
                (inout2, in_, inout1),
                (..., ..., out),
                [inout2, inout1, out],
                [INOUT2_VALIDATOR, IN_VALIDATOR, INOUT1_VALIDATOR],
            ),
            PermutedArgspecTestingParams(
                (INOUT2_ARGSPEC, OUT_ARGSPEC, IN_ARGSPEC, INOUT1_ARGSPEC),
                (inout2, in_, inout1),
                (..., out, ...),
                [inout2, out, inout1],
                [INOUT2_VALIDATOR, IN_VALIDATOR, INOUT1_VALIDATOR],
            ),
            PermutedArgspecTestingParams(
                (INOUT2_ARGSPEC, OUT_ARGSPEC, INOUT1_ARGSPEC, IN_ARGSPEC),
                (inout2, inout1, in_),
                (..., out, ...),
                [inout2, out, inout1],
                [INOUT2_VALIDATOR, INOUT1_VALIDATOR, IN_VALIDATOR],
            ),
            PermutedArgspecTestingParams(
                (INOUT2_ARGSPEC, INOUT1_ARGSPEC, IN_ARGSPEC, OUT_ARGSPEC),
                (inout2, inout1, in_),
                (..., ..., out),
                [inout2, inout1, out],
                [INOUT2_VALIDATOR, INOUT1_VALIDATOR, IN_VALIDATOR],
            ),
            PermutedArgspecTestingParams(
                (INOUT2_ARGSPEC, INOUT1_ARGSPEC, OUT_ARGSPEC, IN_ARGSPEC),
                (inout2, inout1, in_),
                (..., ..., out),
                [inout2, inout1, out],
                [INOUT2_VALIDATOR, INOUT1_VALIDATOR, IN_VALIDATOR],
            ),
        ]


class Test_Error(ut.TestCase):
    def test_missing_name_omitted(self):
        self_ = MagicMock(name="Self")
        spec = comtypes.COMMETHOD(
            [],
            HRESULT,
            "Foo",
            (["in", "out"], POINTER(c_ulong)),
        )
        orig = MagicMock()
        fixed = _fix_inout_args(orig, spec.argtypes, spec.paramflags)
        with self.assertRaises(TypeError) as cm:
            fixed(self_)
        self.assertEqual(
            str(cm.exception), "Unnamed inout parameters cannot be omitted"
        )


if __name__ == "__main__":
    ut.main()
