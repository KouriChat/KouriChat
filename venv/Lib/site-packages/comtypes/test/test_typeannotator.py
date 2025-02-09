import unittest

from comtypes.tools import typedesc
from comtypes.tools.codegenerator import typeannotator
from comtypes.tools.tlbparser import (
    BSTR_type,
    HRESULT_type,
    VARIANT_type,
    VARIANT_BOOL_type,
    void_type,
)


iunknown_type = typedesc.ComInterface(
    "IUnknown", None, "{00000000-0000-0000-C000-000000000046}", ["hidden"], None
)
idispatch_type = typedesc.ComInterface(
    "IDispatch",
    iunknown_type,
    "{00020400-0000-0000-C000-000000000046}",
    ["restricted"],
    None,
)


class Test_AvoidUsingKeywords(unittest.TestCase):
    def _create_typedesc_disp_interface(self) -> typedesc.DispInterface:
        guid = "{00000000-0000-0000-0000-000000000000}"
        itf = typedesc.DispInterface("IDispDerived", idispatch_type, guid, [], None)
        ham = typedesc.DispProperty(0, "ham", BSTR_type, ["readonly"], None)
        bacon = typedesc.DispMethod(
            472, 1, "bacon", VARIANT_BOOL_type, ["hidden"], None
        )
        bacon.add_argument(VARIANT_type, "and", ["in"], None)
        bacon.add_argument(VARIANT_type, "foo", ["in"], None)
        get_spam = typedesc.DispMethod(6, 2, "spam", VARIANT_type, ["propget"], None)
        get_spam.add_argument(VARIANT_type, "arg1", ["in", "optional"], None)
        put_spam = typedesc.DispMethod(6, 4, "spam", void_type, ["propput"], None)
        put_spam.add_argument(VARIANT_type, "arg1", ["in", "optional"], None)
        put_spam.add_argument(VARIANT_type, "arg2", ["in"], None)
        except_ = typedesc.DispProperty(1, "except", BSTR_type, ["readonly"], None)
        raise_ = typedesc.DispMethod(
            474, 1, "raise", VARIANT_BOOL_type, ["hidden"], None
        )
        raise_.add_argument(VARIANT_type, "foo", ["in"], None)
        raise_.add_argument(VARIANT_type, "bar", ["in", "optional"], None)
        get_def = typedesc.DispMethod(8, 2, "def", VARIANT_type, ["propget"], None)
        get_def.add_argument(VARIANT_type, "arg1", ["in", "optional"], None)
        put_def = typedesc.DispMethod(8, 4, "def", void_type, ["propput"], None)
        put_def.add_argument(VARIANT_type, "arg1", ["in", "optional"], None)
        put_def.add_argument(VARIANT_type, "arg2", ["in"], None)
        for m in [ham, bacon, get_spam, put_spam, except_, raise_, get_def, put_def]:
            itf.add_member(m)
        return itf

    def test_disp_interface(self):
        itf = self._create_typedesc_disp_interface()
        expected = (
            "        @property  # dispprop\n"
            "        def ham(self) -> hints.Incomplete: ...\n"
            "        pass  # @property  # dispprop\n"
            "        pass  # avoid using a keyword for def except(self) -> hints.Incomplete: ...\n"  # noqa
            "        def bacon(self, *args: hints.Any, **kwargs: hints.Any) -> hints.Incomplete: ...\n"  # noqa
            "        def _get_spam(self, arg1: hints.Incomplete = ...) -> hints.Incomplete: ...\n"  # noqa
            "        def _set_spam(self, arg1: hints.Incomplete = ..., **kwargs: hints.Any) -> hints.Incomplete: ...\n"  # noqa
            "        spam = hints.named_property('spam', _get_spam, _set_spam)\n"
            "        pass  # avoid using a keyword for def raise(self, foo: hints.Incomplete, bar: hints.Incomplete = ...) -> hints.Incomplete: ...\n"  # noqa
            "        def _get_def(self, arg1: hints.Incomplete = ...) -> hints.Incomplete: ...\n"  # noqa
            "        def _set_def(self, arg1: hints.Incomplete = ..., **kwargs: hints.Any) -> hints.Incomplete: ...\n"  # noqa
            "        pass  # avoid using a keyword for def = hints.named_property('def', _get_def, _set_def)"  # noqa
        )
        self.assertEqual(
            expected, typeannotator.DispInterfaceMembersAnnotator(itf).generate()
        )

    def _create_typedesc_com_interface(self) -> typedesc.ComInterface:
        guid = "{00000000-0000-0000-0000-000000000000}"
        itf = typedesc.ComInterface(
            "IUnkDerived", iunknown_type, guid, ["hidden"], None
        )
        spam = typedesc.ComMethod(
            2, 1610678269, "spam", HRESULT_type, ["propget"], None
        )
        get_ham = typedesc.ComMethod(
            2, 1610678270, "ham", HRESULT_type, ["propget"], None
        )
        put_ham = typedesc.ComMethod(
            4, 1610678270, "ham", HRESULT_type, ["propput"], None
        )
        bacon = typedesc.ComMethod(1, 1610678271, "bacon", HRESULT_type, [], None)
        bacon.add_argument(VARIANT_type, "foo", ["in"], None)
        bacon.add_argument(VARIANT_type, "or", ["in"], None)
        global_ = typedesc.ComMethod(
            2, 1610678272, "global", HRESULT_type, ["propget"], None
        )
        get_class = typedesc.ComMethod(
            2, 1610678273, "class", HRESULT_type, ["propget"], None
        )
        put_class = typedesc.ComMethod(
            4, 1610678273, "class", HRESULT_type, ["propput"], None
        )
        pass_ = typedesc.ComMethod(1, 1610678274, "pass", HRESULT_type, [], None)
        pass_.add_argument(VARIANT_type, "foo", ["in"], None)
        pass_.add_argument(VARIANT_type, "bar", ["in", "optional"], None)
        members = [spam, get_ham, put_ham, bacon, global_, get_class, put_class, pass_]
        itf.extend_members(members)
        return itf

    def test_com_interface(self):
        itf = self._create_typedesc_com_interface()
        expected = (
            "        def _get_spam(self) -> hints.Hresult: ...\n"
            "        spam = hints.normal_property(_get_spam)\n"
            "        def _get_ham(self) -> hints.Hresult: ...\n"
            "        def _set_ham(self) -> hints.Hresult: ...\n"
            "        ham = hints.normal_property(_get_ham, _set_ham)\n"
            "        def bacon(self, *args: hints.Any, **kwargs: hints.Any) -> hints.Hresult: ...\n"  # noqa
            "        def _get_global(self) -> hints.Hresult: ...\n"
            "        pass  # avoid using a keyword for global = hints.normal_property(_get_global)\n"  # noqa
            "        def _get_class(self) -> hints.Hresult: ...\n"
            "        def _set_class(self) -> hints.Hresult: ...\n"
            "        pass  # avoid using a keyword for class = hints.normal_property(_get_class, _set_class)\n"  # noqa
            "        pass  # avoid using a keyword for def pass(self, foo: hints.Incomplete, bar: hints.Incomplete = ...) -> hints.Hresult: ..."  # noqa
        )
        self.assertEqual(
            expected, typeannotator.ComInterfaceMembersAnnotator(itf).generate()
        )
