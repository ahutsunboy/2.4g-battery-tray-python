"""开发验证：右键菜单弹出 + 选择菜单项是否真正生效（注意 0 会切换开机自启）。

需要主程序已在同一会话中运行。仅用于开发期验证，不参与正式运行。
"""
import ctypes
import time

u = ctypes.WinDLL("user32", use_last_error=True)
u.FindWindowW.restype = ctypes.c_void_p
u.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
u.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                           ctypes.c_size_t, ctypes.c_size_t]
u.IsWindow.argtypes = [ctypes.c_void_p]

VK_DOWN, VK_RETURN = 0x28, 0x0D
WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101

host = u.FindWindowW("BatteryTrayHost", None)
print("host =", hex(host or 0))
if not host:
    raise SystemExit("宿主窗口没找到")

# 1) 右键 → 弹出菜单
u.PostMessageW(host, 0x8001, 0, 0x0205)
menu = 0
for _ in range(20):
    time.sleep(0.05)
    menu = u.FindWindowW("#32768", None)
    if menu:
        break
print("弹出菜单窗口 =", hex(menu or 0), "→ 菜单已弹出" if menu else "→ 未弹出")
if not menu:
    raise SystemExit("菜单没弹出")

# 2) 选择第一项（开机自动启动）
for msg in (WM_KEYDOWN, WM_KEYUP):
    u.PostMessageW(menu, msg, VK_DOWN, 0)
for msg in (WM_KEYDOWN, WM_KEYUP):
    u.PostMessageW(menu, msg, VK_RETURN, 0)
time.sleep(0.8)
print("菜单已收起 =", not bool(u.IsWindow(menu)))
print("宿主仍存活 =", bool(u.IsWindow(host)))
