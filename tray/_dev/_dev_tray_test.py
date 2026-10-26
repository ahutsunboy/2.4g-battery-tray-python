import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ctypes
import ctypes.wintypes as wt
import time

import tray_app
import _dev_shot as shot
import wsgui as ui

shell32 = ui.shell32
shell32.Shell_NotifyIconGetRect.argtypes = [ctypes.POINTER(tray_app.NOTIFYICONDATAW),
                                            ctypes.POINTER(wt.RECT)]
shell32.Shell_NotifyIconGetRect.restype = ctypes.c_long

app = tray_app.BatteryTray()
app.build()
time.sleep(0.6)
app._refresh_tray()
time.sleep(0.6)

nid = tray_app.NOTIFYICONDATAW()
nid.cbSize = ctypes.sizeof(tray_app.NOTIFYICONDATAW)
nid.hWnd = app.hwnd_tray
nid.uID = 1
rc = wt.RECT()
hr = shell32.Shell_NotifyIconGetRect(ctypes.byref(nid), ctypes.byref(rc))
print("Shell_NotifyIconGetRect hr=0x%08X rect=(%d,%d,%d,%d)"
      % (hr & 0xFFFFFFFF, rc.left, rc.top, rc.right, rc.bottom))

if hr == 0 and rc.right > rc.left:
    pad = 26
    box = (max(rc.left - pad, 0), max(rc.top - pad, 0),
           rc.right + pad, rc.bottom + pad)
    print("capture", box)
    shot.capture("tray_area.png", box)
print("tray_added =", app.tray_added)
app._quit()
time.sleep(0.2)
print("done")
