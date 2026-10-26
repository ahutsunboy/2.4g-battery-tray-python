"""单独验证低级鼠标钩子的安装 / 卸载 / 重新安装"""
import ctypes
import ctypes.wintypes as wt
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.getcwd()))
import wsgui as ui

hits = []


def on_click(x, y):
    hits.append((x, y))


def click(x, y):
    u = ui.user32
    u.SetCursorPos(x, y)
    time.sleep(0.1)
    u.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.05)
    u.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(0.25)


def main():
    hinst = ui.kernel32.GetModuleHandleW(None)

    for round_no in (1, 2, 3):
        n0 = len(hits)
        hook, ref = ui.install_mouse_hook(on_click, hinst)
        print(f"第 {round_no} 次安装 hook={hook} 成功={bool(hook)}")
        click(600, 400)
        print(f"  点击后回调次数 = {len(hits) - n0}  （应为 1）")
        ui.uninstall_mouse_hook(hook)
        ui.user32.PostMessageW(0, 0, 0, 0)
        click(620, 420)
        print(f"  卸载后回调次数 = {len(hits) - n0 - 1}  （应为 0）")
        time.sleep(0.2)

    print("总回调:", hits)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
