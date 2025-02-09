import time
import unittest

import comtypes
import comtypes.client
import comtypes.test

try:
    # pass Word libUUID
    comtypes.client.GetModule(("{00020905-0000-0000-C000-000000000046}",))
    IMPORT_FAILED = False
except (ImportError, OSError):
    IMPORT_FAILED = True


################################################################
#
# TODO:
#
# It seems bad that only external test like this
# can verify the behavior of `comtypes` implementation.
# Find a different built-in win32 API to use.
#
################################################################


@unittest.skipIf(IMPORT_FAILED, "This depends on Word.")
class Test(unittest.TestCase):
    def setUp(self):
        try:
            comtypes.client.GetActiveObject("Word.Application")
        except WindowsError:
            pass
        else:
            # seems word is running, we cannot test this.
            self.fail("MSWord is running, cannot test")
        # create a WORD instance
        self.w1 = comtypes.client.CreateObject("Word.Application")

    def tearDown(self):
        if hasattr(self, "w1"):
            self.w1.Quit()
            del self.w1

    def test(self):
        # connect to the running instance
        w1 = self.w1
        w2 = comtypes.client.GetActiveObject("Word.Application")

        # check if they are referring to the same object
        self.assertEqual(
            w1.QueryInterface(comtypes.IUnknown), w2.QueryInterface(comtypes.IUnknown)
        )

        w1.Quit()
        del self.w1

        time.sleep(1)

        with self.assertRaises(comtypes.COMError) as arc:
            w2.Visible

        err = arc.exception
        variables = err.hresult, err.text, err.details
        self.assertEqual(variables, err.args)
        with self.assertRaises(WindowsError):
            comtypes.client.GetActiveObject("Word.Application")


if __name__ == "__main__":
    unittest.main()
