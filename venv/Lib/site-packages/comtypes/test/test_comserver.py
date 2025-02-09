import doctest
import unittest
from ctypes import pointer
from typing import Any

import comtypes.test.TestComServer
from comtypes import BSTR
from comtypes.automation import VARIANT, _midlSAFEARRAY
from comtypes.client import CreateObject
from comtypes.server.register import register, unregister
from comtypes.test.find_memleak import find_memleak

try:
    from win32com.client import Dispatch

    IMPORT_PYWIN32_FAILED = False
except ImportError:
    IMPORT_PYWIN32_FAILED = True


def setUpModule():
    try:
        register(comtypes.test.TestComServer.TestComServer)
    except WindowsError as e:
        if e.winerror != 5:  # [Error 5] Access is denied
            raise e
        raise unittest.SkipTest(
            "This test requires the tests to be run as admin since it tries to "
            "register the test COM server."
        )


def tearDownModule():
    unregister(comtypes.test.TestComServer.TestComServer)


class BaseServerTest(object):
    def create_object(self) -> Any: ...

    def _find_memleak(self, func):
        bytes = find_memleak(func)
        self.assertFalse(bytes, f"Leaks {bytes} bytes")  # type: ignore

    def test_mixedinout(self):
        o = self.create_object()
        self.assertEqual(o.MixedInOut(2, 4), (3, 5))  # type: ignore

    def test_getname(self):
        # This tests a tricky bug, introduced with this patch:
        # http://www.python.org/sf/1643874
        #
        # Returning a BSTR as an [out] parameter from a server
        # implementation must transfer the ownership to the caller.
        # When this is not done, the BSTR instance is SysFreeString'd
        # too early, and the memory is reused.
        obj = self.create_object()
        pb = pointer(BSTR())
        # Get the BSTR from the server:
        obj._ITestComServer__com__get_name(pb)
        # Retrieve the value, but keep the pointer to the BSTR alive:
        name = pb[0]
        # Create sme BSTR's to reuse the memory in case it has been freed:
        for i in range(10):
            BSTR("f" * len(name))
        # Make sure the pointer is still valid:
        self.assertEqual(pb[0], name)  # type: ignore

    def test_get_id(self):
        obj = self.create_object()
        self._find_memleak(lambda: obj.id)

    def test_get_name(self):
        obj = self.create_object()
        self._find_memleak(lambda: obj.name)

    def test_set_name(self):
        obj = self.create_object()

        def func():
            obj.name = "abcde"

        self._find_memleak(func)

    def test_SetName(self):
        obj = self.create_object()

        def func():
            obj.SetName("abcde")

        self._find_memleak(func)

    def test_eval(self):
        obj = self.create_object()

        def func():
            return obj.eval("(1, 2, 3)")

        self.assertEqual(func(), (1, 2, 3))  # type: ignore
        self._find_memleak(func)

    def test_get_typeinfo(self):
        obj = self.create_object()

        def func():
            obj.GetTypeInfo(0)
            obj.GetTypeInfoCount()
            obj.QueryInterface(comtypes.IUnknown)

        self._find_memleak(func)


class TestInproc(BaseServerTest, unittest.TestCase):
    def create_object(self):
        return CreateObject(
            "TestComServerLib.TestComServer", clsctx=comtypes.CLSCTX_INPROC_SERVER
        )


class TestLocalServer(BaseServerTest, unittest.TestCase):
    def create_object(self):
        return CreateObject(
            "TestComServerLib.TestComServer", clsctx=comtypes.CLSCTX_LOCAL_SERVER
        )

    @unittest.skip("This fails. Why?")
    def test_get_typeinfo(self):
        # Calling `GetTypeInfo` occurs;
        # OSError: exception: access violation reading 0x0000000000000000
        pass


@unittest.skipIf(IMPORT_PYWIN32_FAILED, "This depends on 'pywin32'.")
class TestInproc_win32com(BaseServerTest, unittest.TestCase):
    def create_object(self):
        return Dispatch("TestComServerLib.TestComServer")

    # These tests make no sense with win32com, override to disable them:
    @unittest.skip("This test make no sense with win32com.")
    def test_get_typeinfo(self):
        pass

    @unittest.skip("This test make no sense with win32com.")
    def test_getname(self):
        pass

    @unittest.skip("This test make no sense with win32com.")
    def test_mixedinout(self):
        # Not sure about this; it raise 'Invalid Number of parameters'
        # Is mixed [in], [out] args not compatible with IDispatch???
        pass


@unittest.skipIf(IMPORT_PYWIN32_FAILED, "This depends on 'pywin32'.")
class TestLocalServer_win32com(BaseServerTest, unittest.TestCase):
    def create_object(self):
        return Dispatch(
            "TestComServerLib.TestComServer", clsctx=comtypes.CLSCTX_LOCAL_SERVER
        )

    # These tests are skipped for the same reason as `TestInproc_win32com`.
    @unittest.skip("This test make no sense with win32com.")
    def test_get_typeinfo(self):
        pass

    @unittest.skip("This test make no sense with win32com.")
    def test_getname(self):
        pass

    @unittest.skip("This test make no sense with win32com.")
    def test_mixedinout(self):
        pass


class VariantTest(unittest.TestCase):
    def test_UDT(self):
        from comtypes.gen.TestComServerLib import MYCOLOR

        v = VARIANT(MYCOLOR(red=1.0, green=2.0, blue=3.0))
        value = v.value
        self.assertEqual(1.0, value.red)  # type: ignore
        self.assertEqual(2.0, value.green)  # type: ignore
        self.assertEqual(3.0, value.blue)  # type: ignore

        def func():
            v = VARIANT(MYCOLOR(red=1.0, green=2.0, blue=3.0))
            return v.value

        bytes = find_memleak(func)
        self.assertFalse(bytes, f"Leaks {bytes} bytes")  # type: ignore


class SafeArrayTest(unittest.TestCase):
    def test_UDT(self):
        from comtypes.gen.TestComServerLib import MYCOLOR

        t = _midlSAFEARRAY(MYCOLOR)
        self.assertTrue(t is _midlSAFEARRAY(MYCOLOR))

        sa = t.from_param([MYCOLOR(0, 0, 0), MYCOLOR(1, 2, 3)])

        self.assertEqual(
            [(x.red, x.green, x.blue) for x in sa[0]],
            [(0.0, 0.0, 0.0), (1.0, 2.0, 3.0)],
        )

        def doit():
            t.from_param([MYCOLOR(0, 0, 0), MYCOLOR(1, 2, 3)])

        bytes = find_memleak(doit)
        self.assertFalse(bytes, f"Leaks {bytes} bytes")  # type: ignore


class PropPutRefTest(unittest.TestCase):
    def doit(self, dynamic: bool):
        d = CreateObject("Scripting.Dictionary", dynamic=dynamic)
        s = CreateObject("TestComServerLib.TestComServer", dynamic=dynamic)
        s.name = "the value"

        # This calls propputref, since we assign an Object
        d.Item["object"] = s
        # This calls propput, since we assing a Value
        d.Item["value"] = s.name

        self.assertEqual(d.Item["object"], s)
        self.assertEqual(d.Item["object"].name, "the value")
        self.assertEqual(d.Item["value"], "the value")

        # Changing the default property of the object
        s.name = "foo bar"
        self.assertEqual(d.Item["object"], s)
        self.assertEqual(d.Item["object"].name, "foo bar")
        self.assertEqual(d.Item["value"], "the value")

        # This also calls propputref since we assign an Object
        d.Item["var"] = VARIANT(s)
        self.assertEqual(d.Item["var"], s)

    def test_earlybind(self):
        self.doit(dynamic=False)

    def test_latebind(self):
        self.doit(dynamic=True)


class TestEvents(unittest.TestCase):
    def test(self):
        import comtypes.test.test_comserver

        doctest.testmod(
            comtypes.test.test_comserver, verbose=False, optionflags=doctest.ELLIPSIS
        )


class ShowEventsExamples:
    # The following functions are never called, they only contain doctests:

    def ShowEventsFloat(self):
        """
        >>> from comtypes.client import CreateObject, ShowEvents
        >>>
        >>> o = CreateObject("TestComServerLib.TestComServer")
        >>> con = ShowEvents(o)
        # event found: ITestComServerEvents_EvalStarted
        # event found: ITestComServerEvents_EvalCompleted
        >>> result = o.eval("10. / 4")
        Event ITestComServerEvents_EvalStarted(None, '10. / 4')
        Event ITestComServerEvents_EvalCompleted(None, '10. / 4', VARIANT(vt=0x5, 2.5))
        >>> result
        2.5
        >>>
        """

    # # The following test, if enabled, works but the testsuit
    # # crashes elsewhere.  Is there s problem with SAFEARRAYs?

    # def Fails(self):
    #     """
    #     >>> from comtypes.client import CreateObject, ShowEvents
    #     >>>
    #     >>> o = CreateObject("TestComServerLib.TestComServer")
    #     >>> con = ShowEvents(o)
    #     # event found: ITestComServerEvents_EvalStarted
    #     # event found: ITestComServerEvents_EvalCompleted
    #     >>> result = o.eval("['32'] * 2")
    #     Event ITestComServerEvents_EvalStarted(None, u"['32'] * 2")
    #     Event ITestComServerEvents_EvalCompleted(None, u"['32'] * 2", VARIANT(vt=0x200c, (u'32', u'32')))
    #     >>> result
    #     (u'32', u'32')
    #     >>>
    #     """

    def GetEvents(self):
        """
        >>> from comtypes.client import CreateObject, GetEvents
        >>>
        >>> o =  CreateObject("TestComServerLib.TestComServer")
        >>> class EventHandler(object):
        ...     def EvalStarted(self, this, what):
        ...         print("EvalStarted: %s" % what)
        ...         return 0
        ...     def EvalCompleted(self, this, what, result):
        ...         print("EvalCompleted: %s = %s" % (what, result.value))
        ...         return 0
        ...
        >>>
        >>> con = GetEvents(o, EventHandler())
        >>> o.eval("2 + 3")
        EvalStarted: 2 + 3
        EvalCompleted: 2 + 3 = 5
        5
        >>> del con
        >>> o.eval("3 + 2")
        5
        >>>
        """


if __name__ == "__main__":
    unittest.main()
