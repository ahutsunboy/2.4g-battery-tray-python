"""开发验证：给正在运行的托盘程序发一次“左键点击”，然后截取屏幕右下角。

不参与正式运行，仅用于确认面板在真实桌面上的渲染效果。
"""
import ctypes
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _dev_shot import capture  # noqa: E402

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.FindWindowW.restype = ctypes.c_void_p
user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
user32.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                ctypes.c_size_t, ctypes.c_size_t]

WM_TRAY = 0x8000 + 1
WM_LBUTTONUP = 0x0202

out = sys.argv[1] if len(sys.argv) > 1 else "live.png"

hwnd = user32.FindWindowW("BatteryTrayHost", None)
if not hwnd:
    print("未找到 BatteryTrayHost 窗口")
    raise SystemExit(1)
print("hwnd =", hex(hwnd))

ok = user32.PostMessageW(hwnd, WM_TRAY, 0, WM_LBUTTONUP)
print("PostMessage =", ok)

# 等面板完成淡入并刷新一次数据
for _ in range(30):
    time.sleep(0.1)
    if user32.FindWindowW("BatteryTrayPanel", None):
        break
time.sleep(1.2)

try:
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    pass
sw = user32.GetSystemMetrics(0)
sh = user32.GetSystemMetrics(1)
print("screen =", sw, sh)
x0 = max(0, sw - 900)
y0 = max(0, sh - 780)
print(capture(out, (x0, y0, sw, sh)), "->", out)
