import unittest
from ctypes import POINTER
import comtypes
from comtypes.client import CreateObject, GetModule

GetModule("oleacc.dll")
from comtypes.gen.Accessibility import IAccessible


@unittest.skip(
    "This IE test is not working.  We need to move it to using some other win32 API."
)
class TestCase(unittest.TestCase):
    def setUp(self):
        self.ie = CreateObject("InternetExplorer.application")

    def tearDown(self):
        self.ie.Quit()
        del self.ie

    def test(self):
        ie = self.ie
        ie.navigate2("about:blank", 0)
        sp = ie.Document.Body.QueryInterface(comtypes.IServiceProvider)
        pacc = sp.QueryService(IAccessible._iid_, IAccessible)
        self.assertEqual(type(pacc), POINTER(IAccessible))


if __name__ == "__main__":
    unittest.main()
