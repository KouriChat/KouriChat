import unittest
from ctypes import POINTER
from comtypes.automation import IDispatch
from comtypes.client import CreateObject
from comtypes import GUID

##from test import test_support
##from comtypes.unittests import support

try:
    GUID.from_progid("MSScriptControl.ScriptControl")
    CreateObject("MSScriptControl.ScriptControl")
except WindowsError:
    # doesn't exist on Windows CE or in 64-bit.
    pass
else:

    class Test(unittest.TestCase):
        def test_jscript(self):
            engine = CreateObject("MSScriptControl.ScriptControl")
            engine.Language = "JScript"
            # strange.
            #
            # engine.Eval returns a VARIANT containing a dispatch pointer.
            #
            # The dispatch pointer exposes this typeinfo (the number of
            # dispproperties varies, depending on the length of the list we pass
            # to Eval):
            #
            # class JScriptTypeInfo(comtypes.gen._00020430_0000_0000_C000_000000000046_0_2_0.IDispatch):
            #    'JScript Type Info'
            #    _iid_ = GUID('{C59C6B12-F6C1-11CF-8835-00A0C911E8B2}')
            #    _idlflags_ = []
            #    _methods_ = []
            # JScriptTypeInfo._disp_methods_ = [
            #    DISPPROPERTY([dispid(9522932)], VARIANT, '0'),
            #    DISPPROPERTY([dispid(9522976)], VARIANT, '1'),
            # ]
            #
            # Although the exact interface members vary, the guid stays
            # the same. Don't think that's allowed by COM standards - is
            # this a bug in the MSScriptControl?
            #
            # What's even more strange is that the returned dispatch
            # pointer can't be QI'd for this interface!  So it seems the
            # typeinfo is really a temporary thing.

            res = engine.Eval("[1, 2, 3, 4]")._comobj

            # comtypes.client works around this bug, by not trying to
            # high-level wrap the dispatch pointer because QI for the real
            # interface fails.
            self.assertEqual(type(res), POINTER(IDispatch))

            tinfo_1 = engine.Eval("[1, 2, 3]")._comobj.GetTypeInfo(0)
            tinfo_2 = engine.Eval("[1, 2, 3, 4]")._comobj.GetTypeInfo(0)
            tinfo_3 = engine.Eval("[1, 2, 3, 4, 5]")._comobj.GetTypeInfo(0)

            self.assertEqual(tinfo_1.GetTypeAttr().cVars, 3)
            self.assertEqual(tinfo_2.GetTypeAttr().cVars, 4)
            self.assertEqual(tinfo_3.GetTypeAttr().cVars, 5)

            # These tests simply describe the current behaviour ;-)
            self.assertEqual(tinfo_1.GetTypeAttr().guid, tinfo_1.GetTypeAttr().guid)

            ## print (res[0], res[1], res[2])
            ## print len(res)

            engine.Reset()


if __name__ == "__main__":
    unittest.main()
