"""Use Scripting.Dictionary to test the lazybind module."""

import unittest

from comtypes.automation import VARIANT
from comtypes.client import CreateObject
from comtypes.client.lazybind import Dispatch


class Test(unittest.TestCase):
    def test_dict(self):
        d = CreateObject("Scripting.Dictionary", dynamic=True)
        self.assertEqual(type(d), Dispatch)

        # Count is a normal propget, no propput
        self.assertEqual(d.Count, 0)
        self.assertRaises(AttributeError, lambda: setattr(d, "Count", -1))

        # HashVal is a 'named' propget, no propput
        ##d.HashVal

        # Add(Key, Item) -> None
        self.assertEqual(d.Add("one", 1), None)
        self.assertEqual(d.Count, 1)

        # RemoveAll() -> None
        self.assertEqual(d.RemoveAll(), None)
        self.assertEqual(d.Count, 0)

        # CompareMode: propget, propput
        # (Can only be set when dict is empty!)
        self.assertEqual(d.CompareMode, 0)
        d.CompareMode = 1
        self.assertEqual(d.CompareMode, 1)
        d.CompareMode = 0

        # Exists(key) -> bool
        self.assertEqual(d.Exists(42), False)
        d.Add(42, "foo")
        self.assertEqual(d.Exists(42), True)

        # Keys() -> array
        # Items() -> array
        self.assertEqual(d.Keys(), (42,))
        self.assertEqual(d.Items(), ("foo",))
        d.Remove(42)
        self.assertEqual(d.Exists(42), False)
        self.assertEqual(d.Keys(), ())
        self.assertEqual(d.Items(), ())

        # Item[key] : propget
        d.Add(42, "foo")
        self.assertEqual(d.Item[42], "foo")

        d.Add("spam", "bar")
        self.assertEqual(d.Item["spam"], "bar")

        # Item[key] = value: propput, propputref
        d.Item["key"] = "value"
        self.assertEqual(d.Item["key"], "value")
        d.Item[42] = 73, 48
        self.assertEqual(d.Item[42], (73, 48))

        ################################################################
        # part 2, testing propput and propputref

        s = CreateObject("Scripting.Dictionary", dynamic=True)
        s.CompareMode = 42

        # This calls propputref, since we assign an Object
        d.Item["object"] = s
        # This calls propput, since we assing a Value
        d.Item["value"] = s.CompareMode

        a = d.Item["object"]

        self.assertEqual(d.Item["object"], s)
        self.assertEqual(d.Item["object"].CompareMode, 42)
        self.assertEqual(d.Item["value"], 42)

        # Changing a property of the object
        s.CompareMode = 5
        self.assertEqual(d.Item["object"], s)
        self.assertEqual(d.Item["object"].CompareMode, 5)
        self.assertEqual(d.Item["value"], 42)

        # This also calls propputref since we assign an Object
        d.Item["var"] = VARIANT(s)
        self.assertEqual(d.Item["var"], s)

        # iter(d)
        keys = [x for x in d]
        self.assertEqual(d.Keys(), tuple([x for x in d]))

        # d[key] = value
        # d[key] -> value
        d["blah"] = "blarg"
        self.assertEqual(d["blah"], "blarg")
        # d(key) -> value
        self.assertEqual(d("blah"), "blarg")


if __name__ == "__main__":
    unittest.main()
