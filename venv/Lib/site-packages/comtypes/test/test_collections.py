import unittest
from comtypes.client import CreateObject
from ctypes import ArgumentError

from comtypes.test.find_memleak import find_memleak


class Test(unittest.TestCase):
    def test_IEnumVARIANT(self):
        # The XP firewall manager.
        fwmgr = CreateObject("HNetCfg.FwMgr")
        # apps has a _NewEnum property that implements IEnumVARIANT
        services = fwmgr.LocalPolicy.CurrentProfile.Services

        self.assertEqual(services.Count, len(services))

        cv = iter(services)

        names = [p.Name for p in cv]
        self.assertEqual(len(services), len(names))

        # The iterator is consumed now:
        self.assertEqual([p.Name for p in cv], [])

        # But we can reset it:
        cv.Reset()
        self.assertEqual([p.Name for p in cv], names)

        # Reset, then skip:
        cv.Reset()
        cv.Skip(3)
        self.assertEqual([p.Name for p in cv], names[3:])

        # Reset, then skip:
        cv.Reset()
        cv.Skip(300)
        self.assertEqual([p.Name for p in cv], names[300:])

        # Hm, do we want to allow random access to the iterator?
        # Should the iterator support __getitem__ ???
        self.assertEqual(cv[0].Name, names[0])
        self.assertEqual(cv[0].Name, names[0])
        self.assertEqual(cv[0].Name, names[0])

        if len(names) > 1:
            self.assertEqual(cv[1].Name, names[1])
            self.assertEqual(cv[1].Name, names[1])
            self.assertEqual(cv[1].Name, names[1])

        # We can now call Next(celt) with celt != 1, the call always returns a
        # list:
        cv.Reset()
        self.assertEqual(names[:3], [p.Name for p in cv.Next(3)])

        # calling Next(0) makes no sense, but should work anyway:
        self.assertEqual(cv.Next(0), [])

        cv.Reset()
        self.assertEqual(len(cv.Next(len(names) * 2)), len(names))

        # slicing is not (yet?) supported
        cv.Reset()
        self.assertRaises(ArgumentError, lambda: cv[:])

    @unittest.skip("This test takes a long time.  Do we need it? Can it be rewritten?")
    def test_leaks_1(self):
        # The XP firewall manager.
        fwmgr = CreateObject("HNetCfg.FwMgr")
        # apps has a _NewEnum property that implements IEnumVARIANT
        apps = fwmgr.LocalPolicy.CurrentProfile.AuthorizedApplications

        def doit():
            for item in iter(apps):
                item.ProcessImageFileName

        bytes = find_memleak(doit, (20, 20))
        self.assertFalse(bytes, f"Leaks {bytes} bytes")

    @unittest.skip("This test takes a long time.  Do we need it? Can it be rewritten?")
    def test_leaks_2(self):
        # The XP firewall manager.
        fwmgr = CreateObject("HNetCfg.FwMgr")
        # apps has a _NewEnum property that implements IEnumVARIANT
        apps = fwmgr.LocalPolicy.CurrentProfile.AuthorizedApplications

        def doit():
            iter(apps).Next(99)

        bytes = find_memleak(doit, (20, 20))
        self.assertFalse(bytes, f"Leaks {bytes} bytes")

    @unittest.skip("This test takes a long time.  Do we need it? Can it be rewritten?")
    def test_leaks_3(self):
        # The XP firewall manager.
        fwmgr = CreateObject("HNetCfg.FwMgr")
        # apps has a _NewEnum property that implements IEnumVARIANT
        apps = fwmgr.LocalPolicy.CurrentProfile.AuthorizedApplications

        def doit():
            for i in range(2):
                for what in iter(apps):
                    pass

        bytes = find_memleak(doit, (20, 20))
        self.assertFalse(bytes, f"Leaks {bytes} bytes")


class TestCollectionInterface(unittest.TestCase):
    """Test the early-bound collection interface."""

    def setUp(self):
        self.d = CreateObject("Scripting.Dictionary", dynamic=False)

    def tearDown(self):
        del self.d

    def assertAccessInterface(self, d):
        """Asserts access via indexing and named property"""
        self.assertEqual(d.CompareMode, 42)
        self.assertEqual(d["foo"], 1)
        self.assertEqual(d.Item["foo"], d["foo"])
        self.assertEqual(d.Item("foo"), d["foo"])
        self.assertEqual(d["bar"], "spam foo")
        self.assertEqual(d.Item("bar"), "spam foo")
        self.assertEqual(d["baz"], 3.14)
        self.assertEqual(d.Item("baz"), d["baz"])
        self.assertIsNone(d["asdlfkj"])
        self.assertIsNone(d.Item["asdlfkj"])
        self.assertIsNone(d.Item("asdlfkj"))

        items = iter(d)
        self.assertEqual(items[0], "foo")
        self.assertEqual(items[1], "bar")
        self.assertEqual(items[2], "baz")
        self.assertEqual(items[3], "asdlfkj")

    def test_index_setter(self):
        d = self.d
        d.CompareMode = 42
        d["foo"] = 1
        d["bar"] = "spam foo"
        d["baz"] = 3.14
        self.assertAccessInterface(d)

    def test_named_property_setter(self):
        d = self.d
        d.CompareMode = 42
        d.Item["foo"] = 1
        d.Item["bar"] = "spam foo"
        d.Item["baz"] = 3.14
        self.assertAccessInterface(d)

    def test_named_property_no_length(self):
        self.assertRaises(TypeError, len, self.d.Item)

    def test_named_property_not_iterable(self):
        self.assertRaises(TypeError, list, self.d.Item)


if __name__ == "__main__":
    unittest.main()
