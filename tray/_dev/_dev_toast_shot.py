"""开发验证：点一次右键菜单的「低电量提醒」，把随之弹出的自检通知截下来。

用来肉眼确认 NIF_INFO 的 toast 真的出现在桌面上（这一步没法自动化断言）。
注意：菜单项是开关，所以截图前要保证当前是「关」，点一下才会变成「开」并弹通知。

用法：python _dev_toast_shot.py [输出文件]
"""
import ctypes
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _dev_shot import capture  # noqa: E402

u = ctypes.WinDLL("user32", use_last_error=True)
u.FindWindowW.restype = ctypes.c_void_p
u.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
u.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                           ctypes.c_size_t, ctypes.c_size_t]
u.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
u.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]

out = sys.argv[1] if len(sys.argv) > 1 else "toast.png"

host = u.FindWindowW("BatteryTrayHost", None)
if not host:
    raise SystemExit("宿主窗口没找到")

u.PostMessageW(host, 0x8001, 0, 0x0205)      # 右键
menu = 0
for _ in range(30):
    time.sleep(0.05)
    menu = u.FindWindowW("#32768", None)
    if menu:
        break
if not menu:
    raise SystemExit("菜单没弹出")

r = (ctypes.c_long * 4)()
u.GetWindowRect(menu, ctypes.byref(r))
left, top, right, bottom = r
row = (bottom - top) // 6                   # 与 _dev_menu_click.py 同一套算法
x, y = left + 40, top + row * 1 + row // 2  # 第 1 项 = 低电量提醒
u.SetCursorPos(x, y)
time.sleep(0.12)
u.mouse_event(0x0002, 0, 0, 0, 0)
time.sleep(0.05)
u.mouse_event(0x0004, 0, 0, 0, 0)

time.sleep(0.7)                             # 等 toast 动画起来
try:
    u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    pass
sw, sh = u.GetSystemMetrics(0), u.GetSystemMetrics(1)
box = (max(0, sw - 620), max(0, sh - 300), sw, max(0, sh - 10))
print(capture(out, box), "->", out, " 区域:", box)
