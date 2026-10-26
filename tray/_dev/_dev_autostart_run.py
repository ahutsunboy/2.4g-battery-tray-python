"""开发验证：真正跑一遍 Startup 里的自启 .vbs，确认不再弹「语句未结束」

做法跟开机时一致：让 shell 按 .vbs 关联打开它（等同双击），然后观察
  * 托盘隐藏宿主窗口 BatteryTrayHost 是否出现 -> 脚本执行成功
  * 是否冒出「Windows Script Host」错误对话框 -> 语法仍然是坏的

注意：脚本里用 pythonw 启动，托盘已在跑时会被单实例 mutex 挡掉，
     所以本测试只判断「脚本本身能不能被解析执行」，不判断是否重复启动。

用法：python _dev_autostart_run.py
"""
import ctypes
import ctypes.wintypes as wt
import os
import sys
import time

VBS = os.path.join(
    os.environ.get("APPDATA", ""),
    r"Microsoft\Windows\Start Menu\Programs\Startup\2.4G电量托盘.vbs")

user32 = ctypes.WinDLL("user32")
user32.FindWindowW.restype = ctypes.c_void_p
user32.FindWindowW.argtypes = [wt.LPCWSTR, wt.LPCWSTR]

WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, wt.LPARAM]
user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]


def error_dialogs():
    """枚举顶层窗口，找 WSH 的错误框（类名 #32770，标题 Windows Script Host）"""
    found = []

    def cb(hwnd, _):
        cls = ctypes.create_unicode_buffer(256)
        txt = ctypes.create_unicode_buffer(512)
        user32.GetClassNameW(hwnd, cls, 256)
        user32.GetWindowTextW(hwnd, txt, 512)
        if cls.value == "#32770" and "Script Host" in txt.value:
            found.append((hwnd, txt.value))
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return found


def main():
    vbs = sys.argv[1] if len(sys.argv) > 1 else VBS
    if not os.path.exists(vbs):
        print(f"[NG] 自启文件不存在: {vbs}")
        return 1
    print(f"自启文件: {vbs}  ({os.path.getsize(vbs)} 字节)")

    host_before = user32.FindWindowW("BatteryTrayHost", None)
    print(f"执行前托盘窗口: {hex(host_before or 0)}")

    # 把已有的错误框先清掉，避免误判
    for hwnd, title in error_dialogs():
        user32.PostMessageW(hwnd, 0x0010, 0, 0)      # WM_CLOSE

    print("按 .vbs 关联打开（等同双击）...")
    os.startfile(vbs)

    ok = False
    dlg = None
    for _ in range(60):                              # 最多等 18 秒
        time.sleep(0.3)
        d = error_dialogs()
        if d:
            dlg = d[0]
            break
        if user32.FindWindowW("BatteryTrayHost", None):
            ok = True
            break

    if dlg:
        print(f"[NG] 仍然弹出脚本错误框: {dlg[1]}  hwnd={hex(dlg[0])}")
        return 1
    if ok:
        print("[OK] 脚本被正常解析执行，托盘窗口已出现，没有报错框")
        return 0
    print("[??] 18 秒内既没看到托盘窗口也没看到错误框，请手动双击确认")
    return 2


if __name__ == "__main__":
    sys.exit(main())
