import time
import unittest

from comtypes import COMError
import comtypes.client

try:
    comtypes.client.GetModule(
        ("{00020905-0000-0000-C000-000000000046}",)
    )  # Word libUUID
    from comtypes.gen import Word

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


class _Sink(object):
    def __init__(self):
        self.events = []

    # Word Application Event
    def DocumentChange(self, this, *args):
        self.events.append("DocumentChange")


@unittest.skipIf(IMPORT_FAILED, "This depends on Word.")
class Test(unittest.TestCase):
    def setUp(self):
        # create a word instance
        self.word = comtypes.client.CreateObject("Word.Application")

    def tearDown(self):
        self.word.Quit()
        del self.word

    def test(self):
        word = self.word
        # Get the instance again, and receive events from that
        w2 = comtypes.client.GetActiveObject("Word.Application")
        sink = _Sink()
        conn = comtypes.client.GetEvents(w2, sink=sink)

        word.Visible = 1

        doc = word.Documents.Add()
        wrange = doc.Range()
        for i in range(10):
            wrange.InsertAfter("Hello from comtypes %d\n" % i)

        for i, para in enumerate(doc.Paragraphs):
            f = para.Range.Font
            f.ColorIndex = i + 1
            f.Size = 12 + (2 * i)

        time.sleep(0.5)

        doc.Close(SaveChanges=Word.wdDoNotSaveChanges)

        del word, w2

        time.sleep(0.5)
        conn.disconnect()

        self.assertEqual(sink.events, ["DocumentChange", "DocumentChange"])

    def test_commandbar(self):
        word = self.word
        word.Visible = 1
        tb = word.CommandBars("Standard")
        btn = tb.Controls[1]

        # word does not allow programmatic access, so this does fail
        with self.assertRaises(COMError):
            word.VBE.Events.CommandBarEvents(btn)

        del word


if __name__ == "__main__":
    unittest.main()
