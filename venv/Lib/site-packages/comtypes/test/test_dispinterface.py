import os
import unittest

import comtypes.test.TestDispServer
from comtypes.server.register import register, unregister

try:
    from win32com.client import Dispatch
    from win32com.client.gencache import EnsureDispatch

    IMPORT_PYWIN32_FAILED = False
except ImportError:
    IMPORT_PYWIN32_FAILED = True


def setUpModule():
    try:
        register(comtypes.test.TestDispServer.TestDispServer)
    except WindowsError as e:
        if e.winerror != 5:  # [Error 5] Access is denied
            raise e
        raise unittest.SkipTest(
            "This test requires the tests to be run as admin since it tries to "
            "register the test COM server."
        )


def tearDownModule():
    unregister(comtypes.test.TestDispServer.TestDispServer)


@unittest.skipIf(IMPORT_PYWIN32_FAILED, "This depends on 'pywin32'.")
class Test_win32com(unittest.TestCase):
    @unittest.skip(
        "It likely fails due to bugs in `GenerateChildFromTypeLibSpec` "
        "or `GetModuleForCLSID`."
    )
    def test_win32com_ensure_dispatch(self):
        # EnsureDispatch is case-sensitive
        d = EnsureDispatch("TestDispServerLib.TestDispServer")

        self.assertEqual(d.eval("3.14"), 3.14)
        self.assertEqual(d.eval("1 + 2"), 3)
        self.assertEqual(d.eval("[1 + 2, 'foo', None]"), (3, "foo", None))

        self.assertEqual(d.eval2("3.14"), 3.14)
        self.assertEqual(d.eval2("1 + 2"), 3)
        self.assertEqual(d.eval2("[1 + 2, 'foo', None]"), (3, "foo", None))

        d.eval(
            "__import__('comtypes.client').client.CreateObject('Scripting.Dictionary')"
        )

        server_id = d.eval("id(self)")
        self.assertEqual(d.id, server_id)

        self.assertEqual(d.name, "spam, spam, spam")

        d.SetName("foo bar")
        self.assertEqual(d.name, "foo bar")

        d.name = "blah"
        self.assertEqual(d.name, "blah")

    def test_win32com_dynamic_dispatch(self):
        # dynamic Dispatch is case-IN-sensitive
        d = Dispatch("TestDispServerLib.TestDispServer")

        self.assertEqual(d.eval("3.14"), 3.14)
        self.assertEqual(d.eval("1 + 2"), 3)
        self.assertEqual(d.eval("[1 + 2, 'foo', None]"), (3, "foo", None))

        self.assertEqual(d.eval2("3.14"), 3.14)
        self.assertEqual(d.eval2("1 + 2"), 3)
        self.assertEqual(d.eval2("[1 + 2, 'foo', None]"), (3, "foo", None))

        d.eval(
            "__import__('comtypes.client').client.CreateObject('Scripting.Dictionary')"
        )

        self.assertEqual(d.EVAL("3.14"), 3.14)
        self.assertEqual(d.EVAL("1 + 2"), 3)
        self.assertEqual(d.EVAL("[1 + 2, 'foo', None]"), (3, "foo", None))

        self.assertEqual(d.EVAL2("3.14"), 3.14)
        self.assertEqual(d.EVAL2("1 + 2"), 3)
        self.assertEqual(d.EVAL2("[1 + 2, 'foo', None]"), (3, "foo", None))

        server_id = d.eval("id(self)")
        self.assertEqual(d.id, server_id)
        self.assertEqual(d.ID, server_id)

        self.assertEqual(d.Name, "spam, spam, spam")
        self.assertEqual(d.nAME, "spam, spam, spam")

        d.SetName("foo bar")
        self.assertEqual(d.Name, "foo bar")

        # fails.  Why?
        # d.name = "blah"
        # self.assertEqual(d.Name, "blah")


class Test_comtypes(unittest.TestCase):
    def test_comtypes(self):
        from comtypes.client import CreateObject

        d = CreateObject("TestDispServerLib.TestDispServer")

        self.assertEqual(d.eval("3.14"), 3.14)
        self.assertEqual(d.eval("1 + 2"), 3)
        self.assertEqual(d.eval("[1 + 2, 'foo', None]"), (3, "foo", None))

        self.assertEqual(d.eval2("3.14"), 3.14)
        self.assertEqual(d.eval2("1 + 2"), 3)
        self.assertEqual(d.eval2("[1 + 2, 'foo', None]"), (3, "foo", None))

        d.eval(
            "__import__('comtypes.client').client.CreateObject('Scripting.Dictionary')"
        )

        self.assertEqual(d.EVAL("3.14"), 3.14)
        self.assertEqual(d.EVAL("1 + 2"), 3)
        self.assertEqual(d.EVAL("[1 + 2, 'foo', None]"), (3, "foo", None))

        self.assertEqual(d.EVAL2("3.14"), 3.14)
        self.assertEqual(d.EVAL2("1 + 2"), 3)
        self.assertEqual(d.EVAL2("[1 + 2, 'foo', None]"), (3, "foo", None))

        server_id = d.eval("id(self)")
        self.assertEqual(d.id, server_id)
        self.assertEqual(d.ID, server_id)

        self.assertEqual(d.Name, "spam, spam, spam")
        self.assertEqual(d.nAME, "spam, spam, spam")

        d.SetName("foo bar")
        self.assertEqual(d.Name, "foo bar")

        d.name = "blah"
        self.assertEqual(d.Name, "blah")


@unittest.skip("This raises 'ClassFactory cannot supply requested class'. Why?")
class Test_jscript(unittest.TestCase):
    def test_withjscript(self):
        jscript = os.path.join(os.path.dirname(__file__), "test_jscript.js")
        errcode = os.system("cscript -nologo %s" % jscript)
        self.assertEqual(errcode, 0)


if __name__ == "__main__":
    unittest.main()
