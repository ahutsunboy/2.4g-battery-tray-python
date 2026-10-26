"""离屏渲染面板的几种状态，用来调版式（不依赖真实设备）"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ctypes
import ctypes.wintypes as wt

import wsgui as ui
from _dev_render_panel import FakeState, write_png

ui.gdi32.CreateCompatibleBitmap.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int]
ui.gdi32.CreateCompatibleBitmap.restype = ui.HANDLE32
ui.gdi32.GetDIBits.argtypes = [wt.HDC, wt.HBITMAP, wt.UINT, wt.UINT,
                               ctypes.c_void_p, ctypes.POINTER(ui.BITMAPINFO), wt.UINT]
ui.gdi32.SetViewportOrgEx.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
ui.gdi32.SetViewportOrgEx.restype = wt.BOOL


def render(states, path):
    import tray_app

    app = tray_app.BatteryTray()
    app._create_resources()
    app.states = states
    w, h, *_ = app._panel_layout()
    pad = 22
    W, H = w + pad * 2, h + pad * 2

    hdc_screen = ui.user32.GetDC(None)
    mem = ui.gdi32.CreateCompatibleDC(hdc_screen)
    bmp = ui.gdi32.CreateCompatibleBitmap(hdc_screen, W, H)
    ui.gdi32.SelectObject(mem, bmp)
    rect = wt.RECT(0, 0, W, H)
    ui.user32.FillRect(mem, ctypes.byref(rect),
                       ui.gdi32.CreateSolidBrush(ui.rgb(0xE9, 0xEC, 0xF1)))
    ui.gdi32.SetViewportOrgEx(mem, pad, pad, None)
    app._paint_content(mem, w, h)
    ui.gdi32.SetViewportOrgEx(mem, 0, 0, None)

    bi = ui.BITMAPINFO()
    bi.bmiHeader.biSize = ctypes.sizeof(ui.BITMAPINFOHEADER)
    bi.bmiHeader.biWidth = W
    bi.bmiHeader.biHeight = -H
    bi.bmiHeader.biPlanes = 1
    bi.bmiHeader.biBitCount = 32
    buf = ctypes.create_string_buffer(W * H * 4)
    ui.gdi32.GetDIBits(mem, bmp, 0, H, buf, ctypes.byref(bi), 0)
    write_png(path, W, H, buf.raw)
    print("ok", path, W, H)


if __name__ == "__main__":
    render([
        FakeState("狼蛛 FN75 键盘", "Compx 键盘", 100, age=3, kind="kbd"),
        FakeState("迈从 G3 鼠标", "迈从鼠标", 46, age=134, kind="mouse"),
    ], "state_normal.png")
    render([
        FakeState("狼蛛 FN75 键盘", "Compx 键盘", 76, age=45, kind="kbd"),
        FakeState("迈从 G3 鼠标", "迈从鼠标", 14, age=800, kind="mouse"),
    ], "state_low.png")
    render([], "state_empty.png")
    render([
        FakeState("迈从 G3 鼠标", "迈从鼠标", None, age=None,
                  note="等待状态帧 · 动一下鼠标唤醒", kind="mouse"),
    ], "state_wait.png")
