import unittest
from comtypes.automation import IDispatch
from comtypes.client import CreateObject, GetModule
from comtypes.client.lazybind import Dispatch

# create the typelib wrapper and import it
GetModule("scrrun.dll")
from comtypes.gen.Scripting import IDictionary


class Test(unittest.TestCase):
    def setUp(self):
        self.d = CreateObject("Scripting.Dictionary", dynamic=True)

    def tearDown(self):
        del self.d

    def test_type(self):
        self.assertTrue(isinstance(self.d, Dispatch))

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

    def test_reference_passing(self):
        d = self.d

        # Check reference passing
        d["self"] = d
        d[0] = "something nontrivial"
        dself = d["self"]
        dself[1] = "something else nontrivial"
        self.assertEqual(d, dself)
        self.assertEqual(d[0], "something nontrivial")
        self.assertEqual(dself[0], d[0])
        self.assertEqual(d[1], "something else nontrivial")
        self.assertEqual(dself[1], d[1])

    def test_query_interface(self):
        d = self.d
        d.CompareMode = 42
        d.Item["foo"] = 1
        d.Item["bar"] = "spam foo"
        d.Item["baz"] = 3.14

        # This should cast the underlying com object to an IDispatch
        d2 = d.QueryInterface(IDispatch)
        # Which can be cast to the non-dynamic type
        d3 = d2.QueryInterface(IDictionary)
        self.assertEqual(d3.CompareMode, 42)
        self.assertEqual(d3.Item["foo"], 1)
        self.assertEqual(d3.Item["bar"], "spam foo")
        self.assertEqual(d3.Item["baz"], 3.14)

    def test_named_property_no_length(self):
        self.assertRaises(TypeError, len, self.d.Item)

    def test_named_property_not_iterable(self):
        self.assertRaises(TypeError, list, self.d.Item)

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


if __name__ == "__main__":
    unittest.main()
