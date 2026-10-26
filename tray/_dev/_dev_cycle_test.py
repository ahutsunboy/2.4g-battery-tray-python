"""面板反复开关 40 次：检查钩子装卸是否泄漏、内存是否稳定"""
import ctypes
import ctypes.wintypes as wt
import time

u = ctypes.WinDLL("user32", use_last_error=True)
k = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)

u.FindWindowW.restype = ctypes.c_void_p
u.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
u.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_size_t]
u.IsWindowVisible.argtypes = [ctypes.c_void_p]
u.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(wt.RECT)]
u.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
u.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(wt.DWORD)]
k.OpenProcess.restype = ctypes.c_void_p
k.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]


class PMC(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t)]


def mem_mb(hwnd):
    pid = wt.DWORD()
    u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = k.OpenProcess(0x0400 | 0x0010, False, pid.value)   # QUERY_INFORMATION | VM_READ
    pmc = PMC()
    pmc.cb = ctypes.sizeof(PMC)
    psapi.GetProcessMemoryInfo(h, ctypes.byref(pmc), pmc.cb)
    k.CloseHandle(h)
    return pmc.WorkingSetSize / 1048576.0, pmc.QuotaPagedPoolUsage / 1024.0


SW, SH = u.GetSystemMetrics(0), u.GetSystemMetrics(1)


def main():
    host = u.FindWindowW("BatteryTrayHost", None)
    panel = u.FindWindowW("BatteryTrayPanel", None)
    if not host:
        print("找不到窗口")
        return 1

    ws0, pool0 = mem_mb(host)
    print(f"起始内存 {ws0:.1f} MB  分页池 {pool0:.0f} KB")

    fails = 0
    N = 40
    for i in range(N):
        if i and i % 15 == 0:
            ws, pool = mem_mb(host)
            print(f"  — 第 {i} 次后：{ws:.1f} MB  分页池 {pool:.0f} KB")
        u.PostMessageW(host, 0x8001, 0, 0x0202)
        time.sleep(0.35)          # 超过 0.3 秒防抖窗口，模拟真实两次点击
        if not u.IsWindowVisible(panel):
            fails += 1
            print(f"  第 {i+1} 次未能显示")
            continue
        r = wt.RECT()
        u.GetWindowRect(panel, ctypes.byref(r))
        # 停在屏幕顶部中央：远离面板、也远离任务栏
        px, py = SW // 2, 12
        if r.left <= px < r.right and r.top <= py < r.bottom:
            px, py = 12, SH // 2
        u.SetCursorPos(px, py)
        time.sleep(0.08)
        u.mouse_event(0x0002, 0, 0, 0, 0)
        time.sleep(0.04)
        u.mouse_event(0x0004, 0, 0, 0, 0)
        time.sleep(0.30)
        if u.IsWindowVisible(panel):
            fails += 1
            print(f"  第 {i+1} 次点击外部未收起")

    ws1, pool1 = mem_mb(host)
    print(f"结束内存 {ws1:.1f} MB  分页池 {pool1:.0f} KB")
    print(f"内存变化 {ws1 - ws0:+.1f} MB   分页池变化 {pool1 - pool0:+.0f} KB")
    print(f"失败次数 {fails}/{N}")
    return 0 if fails == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
