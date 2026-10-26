"""验证「左键单击切换卡片」与真实渲染效果

用法： python _dev_toggle_test.py
前提：tray_app.py 已在同一进程外运行（由调用方启动）
"""
import ctypes
import ctypes.wintypes as wt
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _dev_shot import capture

u = ctypes.WinDLL("user32", use_last_error=True)
u.FindWindowW.restype = ctypes.c_void_p
u.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
u.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t,
                           ctypes.c_size_t]
u.IsWindowVisible.argtypes = [ctypes.c_void_p]
u.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))

WM_TRAY = 0x8000 + 1
WM_LBUTTONUP = 0x0202


def click():
    host = u.FindWindowW("BatteryTrayHost", None)
    u.PostMessageW(host, WM_TRAY, 0, WM_LBUTTONUP)
    time.sleep(0.45)


def visible():
    p = u.FindWindowW("BatteryTrayPanel", None)
    return p, bool(u.IsWindowVisible(p))


if __name__ == "__main__":
    host = u.FindWindowW("BatteryTrayHost", None)
    print("host =", hex(host or 0))
    if not host:
        raise SystemExit("主程序没在运行")

    p, v0 = visible()
    print("初始可见 =", v0)

    click()
    p, v1 = visible()
    print("第 1 次点击后可见 =", v1)

    click()
    p, v2 = visible()
    print("第 2 次点击后可见 =", v2)

    click()
    p, v3 = visible()
    print("第 3 次点击后可见 =", v3)

    if v3:
        r = (ctypes.c_long * 4)()
        u.GetWindowRect(p, ctypes.byref(r))
        l, t, rr, b = r
        print("panel rect =", (l, t, rr, b))
        print(capture("live_v2.png", (max(0, l - 24), max(0, t - 24), rr + 24, b + 24)))

    print("toggle 结论:", "OK" if (v1 and not v2 and v3) else "异常")
