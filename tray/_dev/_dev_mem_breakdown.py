"""开发验证：把 33 MB 拆成「解释器 / 各模块 / 运行期对象」三段

做法：分别拉起几个短命进程，等它们稳定后读私有内存，再两两相减。
不启动窗口、不连 HID 的进程只测「导入成本」。

用法：python _dev_mem_breakdown.py
"""
import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TRAY = os.path.dirname(HERE)
PYW = os.environ.get("PROBE_PYW") or sys.executable.replace("python.exe", "pythonw.exe")
if not os.path.exists(PYW):
    PYW = sys.executable

psapi = ctypes.WinDLL("psapi")
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.OpenProcess.restype = wt.HANDLE
k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
k32.CloseHandle.argtypes = [wt.HANDLE]
psapi.GetProcessMemoryInfo.restype = wt.BOOL


class PMC(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
                ("PrivateUsage", ctypes.c_size_t),
                # 显式补齐 cb 里我们其实用 EX 版本大小
                ("_pad", ctypes.c_size_t)]


MB = 1024.0 * 1024.0

VARIANTS = [
    ("空解释器", "import time; time.sleep(30)"),
    ("+ 标准库导入", "import ctypes, ctypes.wintypes, json, os, sys, threading, time, traceback; time.sleep(30)"),
    ("+ battery_hid", "import sys; sys.path.insert(0, r'%s'); import battery_hid; import time; time.sleep(30)" % TRAY),
    ("+ wsgui", "import sys; sys.path.insert(0, r'%s'); import wsgui; import time; time.sleep(30)" % TRAY),
    ("+ tray_app(全量)", "import sys; sys.path.insert(0, r'%s'); import tray_app; import time; time.sleep(30)" % TRAY),
]


def sample(pid):
    hp = k32.OpenProcess(0x1010, False, pid)      # QUERY_LIMITED | VM_READ
    if not hp:
        return None
    try:
        pm = PMC()
        pm.cb = ctypes.sizeof(pm)
        if not psapi.GetProcessMemoryInfo(hp, ctypes.byref(pm), pm.cb):
            return None
        return pm.PrivateUsage, pm.WorkingSetSize
    finally:
        k32.CloseHandle(hp)


def run(code):
    p = subprocess.Popen([PYW, "-c", code], cwd=TRAY,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        best = (0, 0)
        for _ in range(12):                        # 采样 2.4 秒取最大值
            time.sleep(0.2)
            s = sample(p.pid)
            if s and s[0] > best[0]:
                best = s
        return best
    finally:
        p.kill()
        p.wait()


def main():
    print(f"解释器: {PYW}")
    print(f"{'场景':<18}{'私有':>10}{'工作集':>10}{'增量':>10}")
    prev = 0
    rows = []
    for name, code in VARIANTS:
        priv, ws = run(code)
        delta = (priv - prev) / MB if prev else 0
        rows.append((name, priv / MB, ws / MB, delta))
        prev = priv
        print(f"{name:<18}{priv/MB:8.1f} MB{ws/MB:8.1f} MB{delta:+8.1f} MB")

    print()
    tot = rows[-1][1]
    print(f"导入全部模块后: {tot:.1f} MB")
    print(f"其中解释器自身: {rows[0][1]:.1f} MB ({rows[0][1]/tot*100:.0f}%)")
    print(f"本项目模块    : {tot - rows[0][1]:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
