"""验证「点面板外自动收起」。

用真实的鼠标输入（mouse_event）产生低级鼠标事件，确保走的是
WH_MOUSE_LL 钩子的真实路径，而不是 PostMessage 模拟。

注意：面板的弹出位置跟随光标，点击会移动光标，所以每次点击前
都要重新读一次面板矩形，不能用缓存坐标。
"""
import ctypes
import ctypes.wintypes as wt
import time

u = ctypes.WinDLL("user32", use_last_error=True)
u.FindWindowW.restype = ctypes.c_void_p
u.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
u.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_size_t]
u.IsWindowVisible.argtypes = [ctypes.c_void_p]
u.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(wt.RECT)]
u.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]

SW, SH = u.GetSystemMetrics(0), u.GetSystemMetrics(1)


def rect_of(panel):
    r = wt.RECT()
    u.GetWindowRect(panel, ctypes.byref(r))
    return r


def inside(r, x, y):
    return r.left <= x < r.right and r.top <= y < r.bottom


def pick_outside(r):
    """挑一个明确在面板外的屏幕点（优先屏幕四角方向，避开面板）"""
    for x, y in ((SW // 2, 30), (30, SH // 2), (SW // 2, SH // 2),
                 (SW - 40, SH // 2), (SW // 2, SH - 60)):
        if not inside(r, x, y):
            return x, y
    return SW // 2, 30


def click(x, y):
    u.SetCursorPos(int(x), int(y))
    time.sleep(0.15)
    u.mouse_event(0x0002, 0, 0, 0, 0)   # LEFTDOWN
    time.sleep(0.06)
    u.mouse_event(0x0004, 0, 0, 0, 0)   # LEFTUP
    time.sleep(0.40)


def main():
    host = u.FindWindowW("BatteryTrayHost", None)
    panel = u.FindWindowW("BatteryTrayPanel", None)
    if not host or not panel:
        print("找不到窗口", hex(host or 0), hex(panel or 0))
        return 1

    ok = True

    # --- 1. 弹出 ---
    u.PostMessageW(host, 0x8001, 0, 0x0202)
    time.sleep(0.6)
    vis = bool(u.IsWindowVisible(panel))
    r = rect_of(panel)
    print("1. 左键点击托盘 → 显示:", vis, " 矩形:", (r.left, r.top, r.right, r.bottom))
    ok &= vis

    # --- 2. 点面板内部，应保持显示 ---
    click((r.left + r.right) // 2, (r.top + r.bottom) // 2)
    vis = bool(u.IsWindowVisible(panel))
    print("2. 点击面板内部 → 仍显示:", vis)
    ok &= vis

    # --- 3. 点面板外，应收起 ---
    ox, oy = pick_outside(rect_of(panel))
    click(ox, oy)
    vis = bool(u.IsWindowVisible(panel))
    print(f"3. 点击面板外 ({ox},{oy}) → 已收起:", not vis)
    ok &= not vis

    # --- 4. 再次点击托盘，应能重新打开 ---
    time.sleep(0.4)
    u.PostMessageW(host, 0x8001, 0, 0x0202)
    time.sleep(0.6)
    vis = bool(u.IsWindowVisible(panel))
    print("4. 再点托盘 → 重新显示:", vis)
    ok &= vis

    # --- 5. 重新打开后再点外部，仍应收起（验证钩子被重新装上） ---
    ox, oy = pick_outside(rect_of(panel))
    click(ox, oy)
    vis = bool(u.IsWindowVisible(panel))
    print(f"5. 重开后点击外部 ({ox},{oy}) → 已收起:", not vis)
    ok &= not vis

    # --- 6. 已收起时点别处不应再把面板弄出来 ---
    click(ox, oy)
    vis = bool(u.IsWindowVisible(panel))
    print("6. 收起状态下再点别处 → 保持收起:", not vis)
    ok &= not vis

    # --- 7. 时间窗：钩子刚收起时紧跟的托盘 UP 事件不能又打开 ---
    time.sleep(0.4)
    u.PostMessageW(host, 0x8001, 0, 0x0202)
    time.sleep(0.6)
    ox, oy = pick_outside(rect_of(panel))
    u.SetCursorPos(ox, oy)
    time.sleep(0.1)
    u.mouse_event(0x0002, 0, 0, 0, 0)          # 按下 → 钩子收起
    u.PostMessageW(host, 0x8001, 0, 0x0202)    # 同一次点击的 UP 事件紧接着到达
    u.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(0.4)
    vis = bool(u.IsWindowVisible(panel))
    print("7. 收起后紧跟的托盘 UP → 不重新弹出:", not vis)
    ok &= not vis

    # --- 8. Esc 关闭 ---
    time.sleep(0.4)
    u.PostMessageW(host, 0x8001, 0, 0x0202)
    time.sleep(0.5)
    u.PostMessageW(panel, 0x0100, 0x1B, 0)     # WM_KEYDOWN / VK_ESCAPE
    time.sleep(0.35)
    vis = bool(u.IsWindowVisible(panel))
    print("8. 显示时按 Esc → 已收起:", not vis)
    ok &= not vis

    print("=== 全部通过 ===" if ok else "=== 有失败项 ===")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
