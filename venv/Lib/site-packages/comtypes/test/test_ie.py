import unittest as ut
from ctypes import Structure, c_long, c_uint, c_ulong

from comtypes.client import CreateObject, GetEvents


def setUpModule():
    raise ut.SkipTest(
        "External test dependencies like this seem bad.  Find a different built-in "
        "win32 API to use."
    )


class EventSink:
    def __init__(self):
        self._events = []

    # some DWebBrowserEvents
    def OnVisible(self, this, *args):
        # print "OnVisible", args
        self._events.append("OnVisible")

    def BeforeNavigate(self, this, *args):
        # print "BeforeNavigate", args
        self._events.append("BeforeNavigate")

    def NavigateComplete(self, this, *args):
        # print "NavigateComplete", args
        self._events.append("NavigateComplete")

    # some DWebBrowserEvents2
    def BeforeNavigate2(self, this, *args):
        # print "BeforeNavigate2", args
        self._events.append("BeforeNavigate2")

    def NavigateComplete2(self, this, *args):
        # print "NavigateComplete2", args
        self._events.append("NavigateComplete2")

    def DocumentComplete(self, this, *args):
        # print "DocumentComplete", args
        self._events.append("DocumentComplete")


class POINT(Structure):
    _fields_ = [("x", c_long), ("y", c_long)]


class MSG(Structure):
    _fields_ = [
        ("hWnd", c_ulong),
        ("message", c_uint),
        ("wParam", c_ulong),
        ("lParam", c_ulong),
        ("time", c_ulong),
        ("pt", POINT),
    ]


def PumpWaitingMessages():
    from ctypes import byref, windll

    user32 = windll.user32
    msg = MSG()
    PM_REMOVE = 0x0001
    while user32.PeekMessageA(byref(msg), 0, 0, 0, PM_REMOVE):
        user32.TranslateMessage(byref(msg))
        user32.DispatchMessageA(byref(msg))


class Test(ut.TestCase):
    def tearDown(self):
        import gc

        gc.collect()
        import time

        time.sleep(2)

    def test_default_eventinterface(self):
        sink = EventSink()
        ie = CreateObject("InternetExplorer.Application")
        conn = GetEvents(ie, sink=sink)
        ie.Visible = True
        ie.Navigate2(URL="http://docs.python.org/", Flags=0)
        import time

        for i in range(50):
            PumpWaitingMessages()
            time.sleep(0.1)
        ie.Visible = False
        ie.Quit()

        self.assertEqual(
            sink._events,
            [
                "OnVisible",
                "BeforeNavigate2",
                "NavigateComplete2",
                "DocumentComplete",
                "OnVisible",
            ],
        )

        del ie
        del conn

    def test_nondefault_eventinterface(self):
        sink = EventSink()
        ie = CreateObject("InternetExplorer.Application")
        import comtypes.gen.SHDocVw as mod

        conn = GetEvents(ie, sink, interface=mod.DWebBrowserEvents)

        ie.Visible = True
        ie.Navigate2(Flags=0, URL="http://docs.python.org/")
        import time

        for i in range(50):
            PumpWaitingMessages()
            time.sleep(0.1)
        ie.Visible = False
        ie.Quit()

        self.assertEqual(sink._events, ["BeforeNavigate", "NavigateComplete"])
        del ie


if __name__ == "__main__":
    ut.main()
