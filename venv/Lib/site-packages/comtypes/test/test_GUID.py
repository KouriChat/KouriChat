import unittest
from comtypes import GUID


class Test(unittest.TestCase):
    def test_GUID_null(self):
        self.assertEqual(GUID(), GUID())
        self.assertEqual(
            str(GUID()),
            "{00000000-0000-0000-0000-000000000000}",
        )

    def test_dunder_eq(self):
        self.assertEqual(
            GUID("{00000000-0000-0000-C000-000000000046}"),
            GUID("{00000000-0000-0000-C000-000000000046}"),
        )

    def test_duner_str(self):
        self.assertEqual(
            str(GUID("{0002DF01-0000-0000-C000-000000000046}")),
            "{0002DF01-0000-0000-C000-000000000046}",
        )

    def test_dunder_repr(self):
        self.assertEqual(
            repr(GUID("{0002DF01-0000-0000-C000-000000000046}")),
            'GUID("{0002DF01-0000-0000-C000-000000000046}")',
        )

    def test_invalid_constructor_arg(self):
        self.assertRaises(WindowsError, GUID, "abc")

    def test_from_progid(self):
        self.assertEqual(
            GUID.from_progid("Scripting.FileSystemObject"),
            GUID("{0D43FE01-F093-11CF-8940-00A0C9054228}"),
        )
        self.assertRaises(WindowsError, GUID.from_progid, "abc")

    def test_as_progid(self):
        self.assertEqual(
            GUID("{0D43FE01-F093-11CF-8940-00A0C9054228}").as_progid(),
            "Scripting.FileSystemObject",
        )
        self.assertRaises(
            WindowsError,
            lambda guid: guid.as_progid(),
            GUID("{00000000-0000-0000-C000-000000000046}"),
        )

    def test_create_new(self):
        self.assertNotEqual(GUID.create_new(), GUID.create_new())


if __name__ == "__main__":
    unittest.main()
