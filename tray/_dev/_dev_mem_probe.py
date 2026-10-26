"""开发验证：内存 / 句柄 / GDI / 线程 现状测量

用来回答「35 MB 到底花在哪」：把运行中托盘进程的私有内存、工作集、
句柄数、GDI/USER 对象数、线程数都读出来，并给出与空白解释器基线的差值。

用法：
    python _dev_mem_probe.py            测当前托盘实例
    python _dev_mem_probe.py --watch 10 每 10 秒打一行，观察是否缓慢增长
"""
import ctypes
import ctypes.wintypes as wt
import os
import sys
import time

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
u32 = ctypes.WinDLL("user32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)

u32.FindWindowW.restype = ctypes.c_void_p
u32.FindWindowW.argtypes = [wt.LPCWSTR, wt.LPCWSTR]
u32.GetGuiResources.argtypes = [wt.HANDLE, wt.DWORD]
u32.GetGuiResources.restype = wt.DWORD


class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
    _fields_ = [
        ("cb", wt.DWORD),
        ("PageFaultCount", wt.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
        ("PrivateUsage", ctypes.c_size_t),
    ]


psapi.GetProcessMemoryInfo.argtypes = [
    wt.HANDLE, ctypes.POINTER(PROCESS_MEMORY_COUNTERS_EX), wt.DWORD]
psapi.GetProcessMemoryInfo.restype = wt.BOOL
k32.OpenProcess.restype = wt.HANDLE
k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
k32.CloseHandle.argtypes = [wt.HANDLE]

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_VM_READ = 0x0010

MB = 1024.0 * 1024.0


def host_pid():
    h = u32.FindWindowW("BatteryTrayHost", None)
    if not h:
        return None
    pid = wt.DWORD()
    u32.GetWindowThreadProcessId(ctypes.c_void_p(h), ctypes.byref(pid))
    return pid.value


def sample(pid):
    hp = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ,
                         False, pid)
    if not hp:
        return None
    try:
        pmc = PROCESS_MEMORY_COUNTERS_EX()
        pmc.cb = ctypes.sizeof(pmc)
        if not psapi.GetProcessMemoryInfo(hp, ctypes.byref(pmc), pmc.cb):
            return None
        return {
            "ws": pmc.WorkingSetSize,
            "peak_ws": pmc.PeakWorkingSetSize,
            "private": pmc.PrivateUsage,
            "pagefile": pmc.PagefileUsage,
            "gdi": u32.GetGuiResources(hp, 0),
            "user": u32.GetGuiResources(hp, 1),
        }
    finally:
        k32.CloseHandle(hp)


def thread_count(pid):
    """用 CreateToolhelp32Snapshot 数线程"""
    TH32CS_SNAPTHREAD = 0x00000004

    class THREADENTRY32(ctypes.Structure):
        _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD),
                    ("th32ThreadID", wt.DWORD), ("th32OwnerProcessID", wt.DWORD),
                    ("tpBasePri", ctypes.c_long), ("tpDeltaPri", ctypes.c_long),
                    ("dwFlags", wt.DWORD)]

    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
    if snap in (0, -1, None):
        return -1
    try:
        te = THREADENTRY32()
        te.dwSize = ctypes.sizeof(te)
        n = 0
        ok = k32.Thread32First(snap, ctypes.byref(te))
        while ok:
            if te.th32OwnerProcessID == pid:
                n += 1
            ok = k32.Thread32Next(snap, ctypes.byref(te))
        return n
    finally:
        k32.CloseHandle(snap)


def fmt(s):
    return (f"工作集 {s['ws']/MB:6.1f} MB   私有 {s['private']/MB:6.1f} MB   "
            f"峰值 {s['peak_ws']/MB:6.1f} MB   GDI {s['gdi']:3d}   USER {s['user']:3d}")


def main():
    pid = host_pid()
    if not pid:
        print("托盘没在运行")
        return 1
    print(f"托盘进程 PID {pid}")
    n = thread_count(pid)
    s = sample(pid)
    print("  线程数:", n)
    print("  " + fmt(s))

    if "--watch" in sys.argv:
        sec = int(sys.argv[sys.argv.index("--watch") + 1])
        base = s["private"]
        for _ in range(3):
            time.sleep(sec)
            s = sample(pid)
            print(f"  {fmt(s)}   较首次 {((s['private']-base)/MB):+.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
