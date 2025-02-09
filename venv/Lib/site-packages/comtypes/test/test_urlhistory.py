import unittest, os
from copy import copy
from ctypes import *
from comtypes.client import GetModule, CreateObject
from comtypes.patcher import Patch

# ./urlhist.tlb was downloaded somewhere from the internet (?)

GetModule(os.path.join(os.path.dirname(__file__), "urlhist.tlb"))
from comtypes.gen import urlhistLib


# The pwcsTitle and pwcsUrl fields of the _STATURL structure must be
# freed by the caller.  The only way to do this without patching the
# generated code directly is to monkey-patch the
# _STATURL.__ctypes_from_outparam__ method like this.
@Patch(urlhistLib._STATURL)
class _(object):
    def __ctypes_from_outparam__(self):
        from comtypes.util import cast_field

        result = type(self)()
        for n, _ in self._fields_:
            setattr(result, n, getattr(self, n))
        url, title = self.pwcsUrl, self.pwcsTitle
        windll.ole32.CoTaskMemFree(cast_field(self, "pwcsUrl", c_void_p))
        windll.ole32.CoTaskMemFree(cast_field(self, "pwcsTitle", c_void_p))
        return result


from comtypes.test.find_memleak import find_memleak


class Test(unittest.TestCase):
    def check_leaks(self, func):
        bytes = find_memleak(func, (5, 10))
        self.assertFalse(bytes, "Leaks %d bytes" % bytes)

    @unittest.skip(
        "This fails with: `TypeError: iter() returned non-iterator of type 'POINTER(IEnumSTATURL)'`"
    )
    def test_creation(self):
        hist = CreateObject(urlhistLib.UrlHistory)
        for x in hist.EnumURLS():
            x.pwcsUrl, x.pwcsTitle
            # print (x.pwcsUrl, x.pwcsTitle)
            # print x

        def doit():
            for x in hist.EnumURLs():
                pass

        doit()
        self.check_leaks(doit)


if __name__ == "__main__":
    unittest.main()
