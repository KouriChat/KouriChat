import unittest

from comtypes.client import GetModule

iem = GetModule("shdocvw.dll")


class TestCase(unittest.TestCase):
    def test(self):
        from comtypes.client import GetModule

        iem = GetModule("shdocvw.dll")

        # IDispatch(IUnknown)
        # IWebBrowser(IDispatch)
        # IWebBrowserApp(IWebBrowser)
        # IWebBrowser2(IWebBrowserApp)

        # print iem.IWebBrowser2.mro()

        self.assertTrue(issubclass(iem.IWebBrowser2, iem.IWebBrowserApp))
        self.assertTrue(issubclass(iem.IWebBrowserApp, iem.IWebBrowser))

        # print sorted(iem.IWebBrowser.__map_case__.keys())
        # print "=" * 42
        # print sorted(iem.IWebBrowserApp.__map_case__.keys())
        # print "=" * 42
        # print sorted(iem.IWebBrowser2.__map_case__.keys())
        # print "=" * 42

        # names in the base class __map_case__ must also appear in the
        # subclass.
        for name in iem.IWebBrowser.__map_case__:
            self.assertTrue(name in iem.IWebBrowserApp.__map_case__, f"{name} missing")
            self.assertTrue(name in iem.IWebBrowser2.__map_case__, f"{name} missing")

        for name in iem.IWebBrowserApp.__map_case__:
            self.assertTrue(name in iem.IWebBrowser2.__map_case__, f"{name} missing")


if __name__ == "__main__":
    unittest.main()
