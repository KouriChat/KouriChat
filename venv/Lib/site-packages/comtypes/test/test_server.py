import os
import unittest

import comtypes.client
import comtypes.typeinfo

# Force module to raise.
raise unittest.SkipTest("This test module cannot run as-is.  Investigate why")


class TypeLib(object):
    """This class collects IDL code fragments and eventually writes
    them into a .IDL file.  The compile() method compiles the IDL file
    into a typelibrary and registers it.  A function is also
    registered with atexit that will unregister the typelib at program
    exit.
    """

    def __init__(self, lib):
        self.lib = lib
        self.interfaces = []
        self.coclasses = []

    def interface(self, header):
        itf = Interface(header)
        self.interfaces.append(itf)
        return itf

    def coclass(self, definition):
        self.coclasses.append(definition)

    def __str__(self):
        header = (
            """import "oaidl.idl";
                    import "ocidl.idl";
                    %s {"""
            % self.lib
        )
        body = "\n".join([str(itf) for itf in self.interfaces])
        footer = "\n".join(self.coclasses) + "}"
        return "\n".join((header, body, footer))

    def compile(self):
        """Compile and register the typelib"""
        code = str(self)
        curdir = os.path.dirname(__file__)
        idl_path = os.path.join(curdir, "mylib.idl")
        tlb_path = os.path.join(curdir, "mylib.tlb")
        if not os.path.isfile(idl_path) or open(idl_path, "r").read() != code:
            open(idl_path, "w").write(code)
            os.system(
                r'call "%%VS71COMNTOOLS%%vsvars32.bat" && '
                r"midl /nologo %s /tlb %s" % (idl_path, tlb_path)
            )
        # Register the typelib...
        tlib = comtypes.typeinfo.LoadTypeLib(tlb_path)
        # create the wrapper module...
        comtypes.client.GetModule(tlb_path)
        # Unregister the typelib at interpreter exit...
        attr = tlib.GetLibAttr()
        guid, major, minor = attr.guid, attr.wMajorVerNum, attr.wMinorVerNum
        ##        atexit.register(comtypes.typeinfo.UnRegisterTypeLib,
        ##                        guid, major, minor)
        return tlb_path


class Interface(object):
    def __init__(self, header):
        self.header = header
        self.code = ""

    def add(self, text):
        self.code += text + "\n"
        return self

    def __str__(self):
        return self.header + " {\n" + self.code + "}\n"


################################################################
import comtypes
from comtypes.client import wrap

tlb = TypeLib("[uuid(f4f74946-4546-44bd-a073-9ea6f9fe78cb)] library TestLib")

itf = tlb.interface(
    """[object,
                        oleautomation,
                        dual,
                        uuid(ed978f5f-cc45-4fcc-a7a6-751ffa8dfedd)]
                        interface IMyInterface : IDispatch"""
)

outgoing = tlb.interface(
    """[object,
                                oleautomation,
                                dual,
                                uuid(f7c48a90-64ea-4bb8-abf1-b3a3aa996848)]
                                interface IMyEventInterface : IDispatch"""
)

tlb.coclass(
    """
[uuid(fa9de8f4-20de-45fc-b079-648572428817)]
coclass MyServer {
    [default] interface IMyInterface;
    [default, source] interface IMyEventInterface;
};
"""
)

# The purpose of the MyServer class is to locate three separate code
# section snippets closely together:
#
# 1. The IDL method definition for a COM interface method
# 2. The Python implementation of the COM method
# 3. The unittest(s) for the COM method.
#
from comtypes.server.connectionpoints import ConnectableObjectMixin


class MyServer(comtypes.CoClass, ConnectableObjectMixin):
    _reg_typelib_ = ("{f4f74946-4546-44bd-a073-9ea6f9fe78cb}", 0, 0)
    _reg_clsid_ = comtypes.GUID("{fa9de8f4-20de-45fc-b079-648572428817}")

    ################
    # definition
    itf.add(
        """[id(100), propget] HRESULT Name([out, retval] BSTR *pname);
                [id(100), propput] HRESULT Name([in] BSTR name);"""
    )
    # implementation
    Name = "foo"

    # test
    def test_Name(self):
        p = wrap(self.create())
        self.assertEqual((p.Name, p.name, p.nAME), ("foo",) * 3)
        p.NAME = "spam"
        self.assertEqual((p.Name, p.name, p.nAME), ("spam",) * 3)

    ################
    # definition
    itf.add(
        "[id(101)] HRESULT MixedInOut([in] int a, [out] int *b, [in] int c, [out] int *d);"
    )

    # implementation
    def MixedInOut(self, a, c):
        return a + 1, c + 1

    # test
    def test_MixedInOut(self):
        p = wrap(self.create())
        self.assertEqual(p.MixedInOut(1, 2), (2, 3))

    ################
    # definition
    itf.add("[id(102)] HRESULT MultiInOutArgs([in, out] int *pa, [in, out] int *pb);")

    # implementation
    def MultiInOutArgs(self, pa, pb):
        return pa[0] * 3, pb[0] * 4

    # test
    def test_MultiInOutArgs(self):
        p = wrap(self.create())
        self.assertEqual(p.MultiInOutArgs(1, 2), (3, 8))

    ################
    # definition
    itf.add("HRESULT MultiInOutArgs2([in, out] int *pa, [out] int *pb);")
    ##    # implementation
    ##    def MultiInOutArgs2(self, pa):
    ##        return pa[0] * 3, pa[0] * 4
    ##    # test
    ##    def test_MultiInOutArgs2(self):
    ##        p = wrap(self.create())
    ##        self.assertEqual(p.MultiInOutArgs2(42), (126, 168))

    ################
    # definition
    itf.add("HRESULT MultiInOutArgs3([out] int *pa, [out] int *pb);")

    # implementation
    def MultiInOutArgs3(self):
        return 42, 43

    # test
    def test_MultiInOutArgs3(self):
        p = wrap(self.create())
        self.assertEqual(p.MultiInOutArgs3(), (42, 43))

    ################
    # definition
    itf.add("HRESULT MultiInOutArgs4([out] int *pa, [in, out] int *pb);")

    # implementation
    def MultiInOutArgs4(self, pb):
        return pb[0] + 3, pb[0] + 4

    # test
    def test_MultiInOutArgs4(self):
        p = wrap(self.create())
        res = p.MultiInOutArgs4(pb=32)

    ##        print "MultiInOutArgs4", res

    itf.add(
        """HRESULT GetStackTrace([in] ULONG FrameOffset,
                                        [in, out] INT *Frames,
                                        [in] ULONG FramesSize,
                                        [out, optional] ULONG *FramesFilled);"""
    )

    def GetStackTrace(self, this, *args):
        ##        print "GetStackTrace", args
        return 0

    def test_GetStackTrace(self):
        p = wrap(self.create())
        from ctypes import POINTER, c_int, pointer

        frames = (c_int * 5)()
        res = p.GetStackTrace(42, frames, 5)
        ##        print "RES_1", res

        frames = pointer(c_int(5))
        res = p.GetStackTrace(42, frames, 0)

    ##        print "RES_2", res

    # It is unlear to me if this is allowed or not.  Apparently there
    # are typelibs that define such an argument type, but it may be
    # that these are buggy.
    #
    # Point is that SafeArrayCreateEx(VT_VARIANT|VT_BYREF, ..) fails.
    # The MSDN docs for SafeArrayCreate() have a notice that neither
    # VT_ARRAY not VT_BYREF may be set, this notice is missing however
    # for SafeArrayCreateEx().
    #
    # We have this code here to make sure that comtypes can import
    # such a typelib, although calling ths method will fail because
    # such an array cannot be created.
    itf.add("""HRESULT dummy([in] SAFEARRAY(VARIANT *) foo);""")

    # Test events.
    itf.add("""HRESULT DoSomething();""")
    outgoing.add("""[id(103)] HRESULT OnSomething();""")

    # implementation
    def DoSomething(self):
        "Implement the DoSomething method"
        self.Fire_Event(0, "OnSomething")

    # test
    def test_events(self):
        p = wrap(self.create())

        class Handler(object):
            called = 0

            def OnSomething(self, this):
                "Handles the OnSomething event"
                self.called += 1

        handler = Handler()
        ev = comtypes.client.GetEvents(p, handler)
        p.DoSomething()
        self.assertEqual(handler.called, 1)

        class Handler(object):
            called = 0

            def IMyEventInterface_OnSomething(self):
                "Handles the OnSomething event"
                self.called += 1

        handler = Handler()
        ev = comtypes.client.GetEvents(p, handler)
        p.DoSomething()
        self.assertEqual(handler.called, 1)

    # events with out-parameters (these are probably very unlikely...)
    itf.add("""HRESULT DoSomethingElse();""")
    outgoing.add("""[id(104)] HRESULT OnSomethingElse([out, retval] int *px);""")

    def DoSomethingElse(self):
        "Implement the DoSomething method"
        self.Fire_Event(0, "OnSomethingElse")

    def test_DoSomethingElse(self):
        p = wrap(self.create())

        class Handler(object):
            called = 0

            def OnSomethingElse(self):
                "Handles the OnSomething event"
                self.called += 1
                return 42

        handler = Handler()
        ev = comtypes.client.GetEvents(p, handler)
        p.DoSomethingElse()
        self.assertEqual(handler.called, 1)

        class Handler(object):
            called = 0

            def OnSomethingElse(self, this, presult):
                "Handles the OnSomething event"
                self.called += 1
                presult[0] = 42

        handler = Handler()
        ev = comtypes.client.GetEvents(p, handler)
        p.DoSomethingElse()
        self.assertEqual(handler.called, 1)


################################################################

path = tlb.compile()
from comtypes.connectionpoints import IConnectionPointContainer
from comtypes.gen import TestLib
from comtypes.typeinfo import IProvideClassInfo, IProvideClassInfo2

MyServer._com_interfaces_ = [
    TestLib.IMyInterface,
    IProvideClassInfo2,
    IConnectionPointContainer,
]
MyServer._outgoing_interfaces_ = [TestLib.IMyEventInterface]

################################################################


class Test(unittest.TestCase, MyServer):
    def __init__(self, *args):
        unittest.TestCase.__init__(self, *args)
        MyServer.__init__(self)

    def create(self):
        obj = MyServer()
        return obj.QueryInterface(comtypes.IUnknown)


if __name__ == "__main__":
    unittest.main()
