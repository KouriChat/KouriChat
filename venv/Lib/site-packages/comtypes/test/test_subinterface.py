import unittest, sys
from comtypes import IUnknown, GUID
from ctypes import *


def test_main():
    from test import test_support

    test_support.run_unittest(Test)


class Test(unittest.TestCase):
    def test_subinterface(self):
        class ISub(IUnknown):
            pass

    def test_subclass(self):
        class X(c_void_p):
            pass
