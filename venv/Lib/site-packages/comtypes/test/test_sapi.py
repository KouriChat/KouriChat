# http://www.microsoft.com/technet/scriptcenter/funzone/games/sapi.mspx
# ../gen/_C866CA3A_32F7_11D2_9602_00C04F8EE628_0_5_0
# http://thread.gmane.org/gmane.comp.python.ctypes.user/1485

import os, unittest, tempfile
from comtypes.client import CreateObject


class Test(unittest.TestCase):
    def test(self, dynamic=False):
        engine = CreateObject("SAPI.SpVoice", dynamic=dynamic)
        stream = CreateObject("SAPI.SpFileStream", dynamic=dynamic)
        from comtypes.gen import SpeechLib

        fd, fname = tempfile.mkstemp(suffix=".wav")
        os.close(fd)

        stream.Open(fname, SpeechLib.SSFMCreateForWrite)

        # engine.AudioStream is a propputref property
        engine.AudioOutputStream = stream
        self.assertEqual(engine.AudioOutputStream, stream)
        engine.speak("Hello, World", 0)
        stream.Close()
        filesize = os.stat(fname).st_size
        self.assertTrue(filesize > 100, "filesize only %d bytes" % filesize)
        os.unlink(fname)

    def test_dyndisp(self):
        return self.test(dynamic=True)


if __name__ == "__main__":
    unittest.main()
