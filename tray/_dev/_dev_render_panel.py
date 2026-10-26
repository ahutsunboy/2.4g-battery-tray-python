import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ctypes
import ctypes.wintypes as wt
import struct
import sys
import zlib

import wsgui as ui

ui.gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
ui.gdi32.CreateCompatibleDC.restype = wt.HDC
ui.gdi32.CreateCompatibleBitmap.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int]
ui.gdi32.CreateCompatibleBitmap.restype = wt.HBITMAP
ui.gdi32.GetDIBits.argtypes = [wt.HDC, wt.HBITMAP, wt.UINT, wt.UINT,
                               ctypes.c_void_p, ctypes.POINTER(ui.BITMAPINFO), wt.UINT]
ui.gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
ui.gdi32.SetViewportOrgEx.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
ui.gdi32.SetViewportOrgEx.restype = wt.BOOL
ui.user32.GetDC.argtypes = [wt.HWND]
ui.user32.GetDC.restype = wt.HDC
ui.user32.FillRect.argtypes = [wt.HDC, ctypes.POINTER(wt.RECT), wt.HBRUSH]
ui.gdi32.CreateSolidBrush.argtypes = [wt.COLORREF]
ui.gdi32.CreateSolidBrush.restype = wt.HBRUSH


def chunk(tag, data):
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def write_png(path, w, h, raw_bgra, bg=(0xF3, 0xF4, 0xF6)):
    rows = []
    for y in range(h):
        row = bytearray([0])
        for x in range(w):
            i = (y * w + x) * 4
            b, g, r = raw_bgra[i], raw_bgra[i + 1], raw_bgra[i + 2]
            row += bytes((r, g, b))
        rows.append(bytes(row))
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(b"".join(rows), 6))
           + chunk(b"IEND", b""))
    open(path, "wb").write(png)


class FakeDriver:
    class Info:
        id = "258A:0138"
    info = Info()
    key = "mchose"
    label = "迈从鼠标"


class FakeState:
    def __init__(self, name, label, pct, age=0, charging=False, online=True,
                 note="", kind="mouse"):
        self.name = name
        self.label = label
        self.kind = kind
        self.battery = pct
        self.charging = charging
        self.online = online
        self.note = note
        self.updated = None if age is None else __import__("time").time() - age
        self.driver = FakeDriver()

    def snapshot(self):
        return {"name": self.name, "label": self.label, "kind": self.kind,
                "vidpid": "258A:0138",
                "battery": self.battery, "charging": self.charging,
                "online": self.online, "raw": "", "note": self.note,
                "updated_ts": self.updated}


def main():
    import tray_app

    app = tray_app.BatteryTray()
    app._create_resources()
    app.states = [
        FakeState("狼蛛 FN75 键盘", "Compx 键盘", 100, age=3, kind="kbd"),
        FakeState("迈从 G3 鼠标", "迈从鼠标", 46, age=134, kind="mouse"),
    ]
    w, h, *_ = app._panel_layout()
    pad = 24
    W, H = w + pad * 2, h + pad * 2

    hdc_screen = ui.user32.GetDC(None)
    mem = ui.gdi32.CreateCompatibleDC(hdc_screen)
    bmp = ui.gdi32.CreateCompatibleBitmap(hdc_screen, W, H)
    ui.gdi32.SelectObject(mem, bmp)

    # 背景（模拟桌面）
    rect = wt.RECT(0, 0, W, H)
    ui.user32.FillRect(mem, ctypes.byref(rect), ui.gdi32.CreateSolidBrush(ui.rgb(0xEC, 0xEE, 0xF2)))

    # 偏移绘制面板
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
    write_png(sys.argv[1] if len(sys.argv) > 1 else "panel_off.png", W, H, buf.raw)
    print("ok", W, H)


if __name__ == "__main__":
    main()
