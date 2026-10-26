"""开发验证：真实鼠标点击菜单第 N 项，确认命令 id 能正确返回并执行。

用法：python _dev_menu_click.py [项序号，从 0 开始]
      0=开机自动启动  1=低电量提醒  2=查看日志  3=退出
仅用于开发期验证。
"""
import ctypes
import sys
import time

u = ctypes.WinDLL("user32", use_last_error=True)
u.FindWindowW.restype = ctypes.c_void_p
u.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
u.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                           ctypes.c_size_t, ctypes.c_size_t]
u.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
u.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]

idx = int(sys.argv[1]) if len(sys.argv) > 1 else 0

u.SetProcessDPIAware()
host = u.FindWindowW("BatteryTrayHost", None)
if not host:
    raise SystemExit("宿主窗口没找到")

u.PostMessageW(host, 0x8001, 0, 0x0205)   # 右键
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
row = (bottom - top) // 6                  # 6 行（4 项 + 1 个分隔符 + 边距）
x = left + 40
y = top + row * idx + row // 2
print(f"菜单 rect={tuple(r)}  点击第 {idx} 项 @({x},{y})")

u.SetCursorPos(x, y)
time.sleep(0.12)
u.mouse_event(0x0002, 0, 0, 0, 0)          # LEFTDOWN
time.sleep(0.05)
u.mouse_event(0x0004, 0, 0, 0, 0)          # LEFTUP
time.sleep(1.0)
print("菜单已收起 =", not bool(u.FindWindowW("#32768", None)))
print("宿主仍存活 =", bool(u.FindWindowW("BatteryTrayHost", None)))
