import unittest as ut


class TestCase(ut.TestCase):
    def test(self):
        from comtypes.automation import DISPPARAMS, VARIANT

        dp = DISPPARAMS()
        dp.rgvarg = (VARIANT * 3)()

        for i in range(3):
            self.assertEqual(dp.rgvarg[i].value, None)

        dp.rgvarg[0].value = 42
        dp.rgvarg[1].value = "spam"
        dp.rgvarg[2].value = "foo"

        # damn, there's still this old bug!

        self.assertEqual(dp.rgvarg[0].value, 42)
        # these fail:
        # self.failUnlessEqual(dp.rgvarg[1].value, "spam")
        # self.failUnlessEqual(dp.rgvarg[2].value, "foo")

    def X_test_2(self):
        # basically the same test as above
        from comtypes.automation import DISPPARAMS, VARIANT

        args = [42, None, "foo"]

        dp = DISPPARAMS()
        dp.rgvarg = (VARIANT * 3)(*list(map(VARIANT, args[::-1])))

        import gc

        gc.collect()

        self.assertEqual(dp.rgvarg[0].value, 42)
        self.assertEqual(dp.rgvarg[1].value, "spam")
        self.assertEqual(dp.rgvarg[2].value, "foo")


if __name__ == "__main__":
    ut.main()
