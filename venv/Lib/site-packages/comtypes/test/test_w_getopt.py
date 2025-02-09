import unittest

from comtypes.server.w_getopt import GetoptError, w_getopt


class TestCase(unittest.TestCase):
    def test_1(self):
        args = "-embedding spam /RegServer foo /UnregSERVER blabla".split()
        opts, args = w_getopt(args, "regserver unregserver embedding".split())
        self.assertEqual(
            opts, [("embedding", ""), ("regserver", ""), ("unregserver", "")]
        )
        self.assertEqual(args, ["spam", "foo", "blabla"])

    def test_2(self):
        args = "/TLB Hello.Tlb HELLO.idl".split()
        opts, args = w_getopt(args, ["tlb:"])
        self.assertEqual(opts, [("tlb", "Hello.Tlb")])
        self.assertEqual(args, ["HELLO.idl"])

    def test_3(self):
        # Invalid option
        self.assertRaises(
            GetoptError, w_getopt, "/TLIB hello.tlb hello.idl".split(), ["tlb:"]
        )

    def test_4(self):
        # Missing argument
        self.assertRaises(GetoptError, w_getopt, "/TLB".split(), ["tlb:"])
