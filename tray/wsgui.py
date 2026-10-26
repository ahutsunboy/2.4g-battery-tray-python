"""
wsgui.py — 极简 Win32 界面工具集（纯 ctypes / GDI，无第三方依赖）

提供：
  * 高 DPI 适配
  * 抗锯齿图标栅格化 → HICON
  * 无边框圆角面板窗口（WM_PAINT + GDI 绘制）
  * 简易字体 / 颜色封装
"""

import ctypes
import ctypes.wintypes as wt
import math

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)

#: GDI / USER 句柄在 x64 上是 32 位值，系统返回时高 32 位未定义。
#: 用 c_void_p 读会把符号扩展位一起读进来，得到一个非法句柄，
#: 之后所有 API 都静默失败（AlphaBlend 报 87、SelectObject 不生效）。
#: 因此所有返回句柄的函数统一按 32 位无符号整数读取。
HANDLE32 = ctypes.c_uint32


WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_PAINT = 0x000F
WM_TIMER = 0x0113
WM_ACTIVATE = 0x0006
WM_LBUTTONUP = 0x0202
WM_MOUSEMOVE = 0x0200
WM_RBUTTONUP = 0x0205
WM_MOUSELEAVE = 0x02A3
WM_APP = 0x8000
WM_ERASEBKGND = 0x0014

WS_POPUP = 0x80000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008
WS_EX_NOACTIVATE = 0x08000000
CS_DROPSHADOW = 0x00020000
DT_SINGLELINE = 0x20
DT_LEFT = 0x0000
DT_RIGHT = 0x0002
DT_CENTER = 0x0001
DT_VCENTER = 0x0004
DT_BOTTOM = 0x0008
DT_NOPREFIX = 0x0800
TRANSPARENT = 1
NULL_BRUSH = 5
PS_SOLID = 0
FW_SEMIBOLD = 600
FW_NORMAL = 400
FW_BOLD = 700
SB_HORZ = 0


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("style", wt.UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON), ("hCursor", wt.HANDLE),
                ("hbrBackground", wt.HBRUSH), ("lpszMenuName", wt.LPCWSTR),
                ("lpszClassName", wt.LPCWSTR), ("hIconSm", wt.HICON)]


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD),
                ("Data4", ctypes.c_ubyte * 8)]


class PAINTSTRUCT(ctypes.Structure):
    _fields_ = [("hdc", wt.HDC), ("fErase", wt.BOOL), ("rcPaint", wt.RECT),
                ("fRestore", wt.BOOL), ("fIncUpdate", wt.BOOL),
                ("rgbReserved", ctypes.c_ubyte * 32)]


class ICONINFO(ctypes.Structure):
    _fields_ = [("fIcon", wt.BOOL), ("xHotspot", wt.DWORD), ("yHotspot", wt.DWORD),
                ("hbmMask", wt.HBITMAP), ("hbmColor", wt.HBITMAP)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", ctypes.c_long),
                ("biHeight", ctypes.c_long), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wt.DWORD),
                ("biClrImportant", wt.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]


# ----------------------------------------------------------------- 函数签名
user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
user32.RegisterClassExW.restype = wt.WORD
user32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   wt.HWND, wt.HMENU, wt.HINSTANCE, ctypes.c_void_p]
user32.CreateWindowExW.restype = wt.HWND
user32.BeginPaint.argtypes = [wt.HWND, ctypes.POINTER(PAINTSTRUCT)]
user32.BeginPaint.restype = wt.HDC
user32.EndPaint.argtypes = [wt.HWND, ctypes.POINTER(PAINTSTRUCT)]
user32.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT]
user32.TranslateMessage.argtypes = [ctypes.POINTER(wt.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wt.MSG)]
user32.DispatchMessageW.restype = LRESULT
user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.SetTimer.argtypes = [wt.HWND, ctypes.c_size_t, wt.UINT, ctypes.c_void_p]
user32.KillTimer.argtypes = [wt.HWND, ctypes.c_size_t]
user32.InvalidateRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT), wt.BOOL]
user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
user32.SetForegroundWindow.argtypes = [wt.HWND]
user32.SetForegroundWindow.restype = wt.BOOL
user32.ShowWindow.restype = wt.BOOL
user32.GetSystemMetrics.restype = ctypes.c_int
user32.GetCursorPos.restype = wt.BOOL
user32.InvalidateRect.restype = wt.BOOL
user32.GetCursorPos.argtypes = [ctypes.POINTER(wt.POINT)]
user32.SetFocus.argtypes = [wt.HWND]
user32.DrawTextW.argtypes = [wt.HDC, wt.LPCWSTR, ctypes.c_int, ctypes.POINTER(wt.RECT), wt.UINT]
user32.FillRect.argtypes = [wt.HDC, ctypes.POINTER(wt.RECT), wt.HBRUSH]
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.SetProcessDPIAware.restype = wt.BOOL
user32.TrackMouseEvent.argtypes = [ctypes.c_void_p]
user32.CreatePopupMenu.restype = wt.HMENU
user32.AppendMenuW.argtypes = [wt.HMENU, wt.UINT, ctypes.c_size_t, wt.LPCWSTR]
user32.TrackPopupMenu.argtypes = [wt.HMENU, wt.UINT, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_int, wt.HWND, ctypes.c_void_p]
user32.DestroyMenu.argtypes = [wt.HMENU]
user32.SetMenuDefaultItem.argtypes = [wt.HMENU, wt.UINT, wt.UINT]

# 显式声明句柄签名：x64 下不声明时 ctypes 按 c_int 传参，
# 一旦 HWND 数值超过 2^31 就会被截断（表现为窗口操作静默失效）
user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, ctypes.c_size_t, ctypes.c_size_t]
user32.PostMessageW.restype = wt.BOOL
user32.SendMessageW.argtypes = [wt.HWND, wt.UINT, ctypes.c_size_t, ctypes.c_size_t]
user32.SendMessageW.restype = LRESULT
user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wt.UINT]
user32.SetWindowPos.restype = wt.BOOL
user32.SetWindowRgn.argtypes = [wt.HWND, wt.HRGN, wt.BOOL]
user32.SetWindowRgn.restype = ctypes.c_int
user32.DestroyWindow.argtypes = [wt.HWND]
user32.DestroyWindow.restype = wt.BOOL
user32.GetForegroundWindow.restype = wt.HWND
user32.AttachThreadInput.argtypes = [wt.DWORD, wt.DWORD, wt.BOOL]
user32.AttachThreadInput.restype = wt.BOOL
user32.BringWindowToTop.argtypes = [wt.HWND]
user32.BringWindowToTop.restype = wt.BOOL
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.c_void_p]
user32.GetWindowThreadProcessId.restype = wt.DWORD
kernel32.GetCurrentThreadId.restype = wt.DWORD
#: 不声明 restype 时 ctypes 按 c_int 读，x64 下模块基址会被截断成负数，
#: 再拿去当 HINSTANCE 用就成了非法句柄（SetWindowsHookExW 报 err=126）。
kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
kernel32.GetModuleHandleW.restype = wt.HINSTANCE
kernel32.GetCurrentProcess.restype = wt.HANDLE
kernel32.SetProcessWorkingSetSize.argtypes = [wt.HANDLE, ctypes.c_size_t,
                                              ctypes.c_size_t]
kernel32.SetProcessWorkingSetSize.restype = wt.BOOL


def trim_working_set():
    """把本进程闲置的物理页面还给系统。

    调用后任务管理器里的「内存」会立刻掉到几 MB。**注意这不等于真的省了内存**：
    私有提交量（PrivateUsage）一点没变，只是把暂时不碰的页面踢出了工作集，
    下次用到时靠缺页再调回来（首次打开面板可能多花几十毫秒）。
    托盘常驻程序普遍这么做，收益是它长期不占着物理内存。
    """
    try:
        return bool(kernel32.SetProcessWorkingSetSize(
            kernel32.GetCurrentProcess(), ctypes.c_size_t(-1), ctypes.c_size_t(-1)))
    except Exception:
        return False


def _fix_handle_restypes():
    """把返回 GDI/USER 句柄的函数统一改成 32 位无符号读取"""
    fns = (
        gdi32.CreateSolidBrush, gdi32.CreatePen, gdi32.CreateFontW,
        gdi32.SelectObject, gdi32.GetStockObject, gdi32.CreateCompatibleDC,
        gdi32.CreateCompatibleBitmap, gdi32.CreateDIBSection, gdi32.CreateBitmap,
        gdi32.CreateRoundRectRgn,
        user32.CreateWindowExW, user32.BeginPaint, user32.CreatePopupMenu,
        user32.LoadCursorW, user32.CreateIconIndirect, user32.GetDC,
        user32.GetForegroundWindow,
    )
    for fn in fns:
        try:
            fn.restype = HANDLE32
        except AttributeError:
            pass



def force_foreground(hwnd):
    """把窗口抢到前台。

    托盘程序是被动响应的后台进程，直接调 SetForegroundWindow 会被系统
    静默拒绝（返回 0）。拿不到前台会导致两个后果：
      1. TrackPopupMenu 的模态循环收不到鼠标点击 —— 右键菜单点了没反应；
      2. 弹出的面板立刻被判定失焦而自动隐藏。
    临时挂到当前前台线程的输入队列上，就能合法地完成切换。
    """
    if not hwnd:
        return False
    fg = user32.GetForegroundWindow()
    tid_fg = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    tid_self = kernel32.GetCurrentThreadId()
    attached = False
    if tid_fg and tid_fg != tid_self:
        attached = bool(user32.AttachThreadInput(tid_fg, tid_self, True))
    try:
        ok = bool(user32.SetForegroundWindow(hwnd))
        user32.BringWindowToTop(hwnd)
        return ok
    finally:
        if attached:
            user32.AttachThreadInput(tid_fg, tid_self, False)


# ---------------------------------------------------------------- 低级鼠标钩子
# 弹出面板要「点别处就收起」。靠 WM_ACTIVATE 不可靠：面板是 WS_POPUP，
# 若没真正拿到激活状态，点其他窗口时根本不会有 WA_INACTIVE 送过来。
# WH_MOUSE_LL 在鼠标按下那一刻就能拿到全局坐标，判断是否落在面板外，
# 这是托盘菜单、开始菜单一直在用的做法。

WH_MOUSE_LL = 14
WM_LBUTTONDOWN = 0x0201
WM_RBUTTONDOWN = 0x0204
WM_MBUTTONDOWN = 0x0207

HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wt.WPARAM, wt.LPARAM)


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", wt.POINT), ("mouseData", wt.DWORD), ("flags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wt.HINSTANCE, wt.DWORD]
user32.SetWindowsHookExW.restype = HANDLE32
user32.UnhookWindowsHookEx.argtypes = [HANDLE32]
user32.UnhookWindowsHookEx.restype = wt.BOOL
user32.CallNextHookEx.argtypes = [HANDLE32, ctypes.c_int, wt.WPARAM, wt.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
user32.GetWindowRect.restype = wt.BOOL


def install_mouse_hook(on_click_outside, hinst=None):
    """装一个低级鼠标钩子；返回 (hook, 回调引用)。

    回调签名 on_click_outside(x, y) -> bool：返回 True 表示这次点击在面板外，
    需要收起面板。调用方必须保存返回的回调引用，否则会被 GC 掉，
    系统调用到已释放的函数指针时整机鼠标都会卡顿。
    """
    def proc(ncode, wparam, lparam):
        if ncode < 0:
            return user32.CallNextHookEx(0, ncode, wparam, lparam)
        try:
            if wparam in (WM_LBUTTONDOWN, WM_RBUTTONDOWN, WM_MBUTTONDOWN):
                info = ctypes.cast(lparam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                on_click_outside(info.pt.x, info.pt.y)
        except Exception:
            pass   # 钩子里绝对不能往外抛异常
        return user32.CallNextHookEx(0, ncode, wparam, lparam)

    ref = HOOKPROC(proc)
    hook = user32.SetWindowsHookExW(WH_MOUSE_LL, ref, hinst, 0)
    if not hook:
        # 低级钩子的回调在进程内执行，hMod 允许为 NULL
        hook = user32.SetWindowsHookExW(WH_MOUSE_LL, ref, None, 0)
    return hook, ref


def uninstall_mouse_hook(hook):
    if hook:
        user32.UnhookWindowsHookEx(hook)

gdi32.CreateSolidBrush.argtypes = [wt.COLORREF]
gdi32.CreateSolidBrush.restype = wt.HBRUSH
gdi32.CreatePen.argtypes = [ctypes.c_int, ctypes.c_int, wt.COLORREF]
gdi32.CreatePen.restype = wt.HPEN
gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
gdi32.SelectObject.restype = wt.HGDIOBJ
gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
gdi32.CreateFontW.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                              ctypes.c_int, wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD,
                              wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, wt.LPCWSTR]
gdi32.CreateFontW.restype = wt.HFONT
gdi32.SetTextColor.argtypes = [wt.HDC, wt.COLORREF]
gdi32.SetBkMode.argtypes = [wt.HDC, ctypes.c_int]
gdi32.RoundRect.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                            ctypes.c_int, ctypes.c_int, ctypes.c_int]
gdi32.RoundRect.restype = wt.BOOL
gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
gdi32.CreateCompatibleDC.restype = wt.HDC
gdi32.DeleteDC.argtypes = [wt.HDC]
gdi32.DeleteDC.restype = wt.BOOL
gdi32.GetTextExtentPoint32W.argtypes = [wt.HDC, wt.LPCWSTR, ctypes.c_int,
                                        ctypes.POINTER(wt.SIZE)]
gdi32.GetTextExtentPoint32W.restype = wt.BOOL

msimg32 = ctypes.WinDLL("msimg32", use_last_error=True)


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]


msimg32.AlphaBlend.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                               ctypes.c_int, wt.HDC, ctypes.c_int, ctypes.c_int,
                               ctypes.c_int, ctypes.c_int,
                               ctypes.POINTER(BLENDFUNCTION)]
msimg32.AlphaBlend.restype = wt.BOOL

AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01


def text_size(hdc, text, font):
    """量出文字在指定字体下的像素宽高（够排版用，不带 DT_ 标志）"""
    old = gdi32.SelectObject(hdc, font)
    try:
        sz = wt.SIZE()
        gdi32.GetTextExtentPoint32W(hdc, text, len(text), ctypes.byref(sz))
        return sz.cx, sz.cy
    finally:
        gdi32.SelectObject(hdc, old)


def rgb(r, g, b):
    return wt.COLORREF(r | (g << 8) | (b << 16))


def dpi_scale():
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2
    except Exception:
        try:
            user32.SetProcessDpiAwareness(2)
        except Exception:
            user32.SetProcessDPIAware()
    try:
        d = user32.GetDpiForSystem()
        if d:
            return d / 96.0
    except Exception:
        pass
    try:
        hdc = user32.GetDC(None)
        d = gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
        user32.ReleaseDC(None, hdc)
        return d / 96.0
    except Exception:
        return 1.0


# ----------------------------------------------------------------- 图标栅格化
def _round_rect_mask(w, h, x0, y0, x1, y1, r):
    """返回 (x,y)->bool 的圆角矩形覆盖判定（浮点边界）"""
    def inside(px, py):
        if px < x0 or px > x1 or py < y0 or py > y1:
            return False
        cx = min(max(px, x0 + r), x1 - r)
        cy = min(max(py, y0 + r), y1 - r)
        dx, dy = px - cx, py - cy
        return dx * dx + dy * dy <= r * r
    return inside


def render_battery_icon(size, percent, charging=False, ss=4):
    """
    生成 size×size 的 BGRA 位图（bytearray），电池图标 + 电量填充
    4 倍超采样抗锯齿
    """
    W = size * ss
    H = size * ss
    acc = [[0.0, [0, 0, 0]] for _ in range(W * H)]  # (alpha, rgb)

    def paint(mask, color):
        for y in range(H):
            for x in range(W):
                if mask(x + 0.5, y + 0.5):
                    i = y * W + x
                    a = acc[i][0]
                    na = 1.0
                    acc[i] = [na, color]

    # 尺寸布局（相对 16px 设计稿）
    u = W / 16.0
    body_x0, body_y0 = 0.9 * u, 3.9 * u
    body_x1, body_y1 = 12.9 * u, 12.1 * u
    nub_x0, nub_y0 = 13.1 * u, 6.3 * u
    nub_x1, nub_y1 = 15.2 * u, 9.7 * u

    outline = (0x6B, 0x72, 0x80)
    track = (0xD1, 0xD5, 0xDB)

    if percent < 20:
        fill = (0xDC, 0x26, 0x26)
    elif percent < 45:
        fill = (0xF5, 0x9E, 0x0B)
    else:
        fill = (0x16, 0xA3, 0x4A)
    if charging:
        fill = (0x25, 0x63, 0xEB)

    # 外框 + 触点
    rr_body = _round_rect_mask(W, H, body_x0, body_y0, body_x1, body_y1, 2.2 * u)
    stroke = 1.15 * u
    inner = _round_rect_mask(W, H, body_x0 + stroke, body_y0 + stroke,
                             body_x1 - stroke, body_y1 - stroke, 1.6 * u)

    def ring(px, py):
        return rr_body(px, py) and not inner(px, py)

    paint(ring, outline)
    paint(_round_rect_mask(W, H, nub_x0, nub_y0, nub_x1, nub_y1, 0.6 * u), outline)

    # 电量填充区
    pad = 1.9 * u
    bx0, bx1 = body_x0 + pad, body_x1 - pad
    by0, by1 = body_y0 + pad, body_y1 - pad
    paint(_round_rect_mask(W, H, bx0, by0, bx1, by1, 1.0 * u), track)
    frac = max(0.0, min(1.0, percent / 100.0))
    if frac > 0.02:
        fx1 = bx0 + (bx1 - bx0) * frac
        paint(_round_rect_mask(W, H, bx0, by0, max(fx1, bx0 + 1.3 * u), by1, 1.0 * u), fill)

    # 充电闪电
    if charging:
        cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
        bolt = [(cx + 0.55 * u, cy - 1.9 * u), (cx - 0.75 * u, cy + 0.35 * u),
                (cx - 0.05 * u, cy + 0.35 * u), (cx - 0.5 * u, cy + 2.0 * u),
                (cx + 0.8 * u, cy - 0.25 * u), (cx + 0.1 * u, cy - 0.25 * u)]

        def in_bolt(px, py):
            inside = False
            j = len(bolt) - 1
            for i in range(len(bolt)):
                xi, yi = bolt[i]
                xj, yj = bolt[j]
                if ((yi > py) != (yj > py)) and \
                        (px < (xj - xi) * (py - yi) / (yj - yi + 1e-9) + xi):
                    inside = not inside
                j = i
            return inside
        paint(in_bolt, (0xFF, 0xFF, 0xFF))

    # 下采样
    out = bytearray(size * size * 4)
    inv = 1.0 / (ss * ss)
    for y in range(size):
        for x in range(size):
            r = g = b = 0
            a = 0
            for sy in range(ss):
                base = ((y * ss + sy) * W) + x * ss
                for sx in range(ss):
                    cell = acc[base + sx]
                    if cell[0]:
                        c = cell[1]
                        r += c[0]
                        g += c[1]
                        b += c[2]
            # 每格统一颜色，alpha 由覆盖面积决定
            paint_count = 0
            for sy in range(ss):
                base = ((y * ss + sy) * W) + x * ss
                for sx in range(ss):
                    if acc[base + sx][0]:
                        paint_count += 1
            if paint_count:
                n = paint_count
                i = (y * size + x) * 4
                out[i] = b // n
                out[i + 1] = g // n
                out[i + 2] = r // n
                out[i + 3] = int(255 * n * inv)
    return out


def make_hicon(size, percent, charging=False):
    """把 BGRA 位图包装成 HICON"""
    bgra = render_battery_icon(size, percent, charging)

    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = size
    bmi.bmiHeader.biHeight = -size  # top-down
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = 0  # BI_RGB
    bmi.bmiHeader.biSizeImage = len(bgra)

    bits = ctypes.c_void_p()
    gdi32.CreateDIBSection.argtypes = [wt.HDC, ctypes.POINTER(BITMAPINFO), wt.UINT,
                                       ctypes.POINTER(ctypes.c_void_p), wt.HANDLE, wt.DWORD]
    gdi32.CreateDIBSection.restype = HANDLE32
    hbm = gdi32.CreateDIBSection(None, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
    if not hbm:
        return None
    ctypes.memmove(bits, bytes(bgra), len(bgra))

    # 掩码位图（1bpp，全 0）
    gdi32.CreateBitmap.argtypes = [ctypes.c_int, ctypes.c_int, wt.UINT, wt.UINT, ctypes.c_void_p]
    gdi32.CreateBitmap.restype = HANDLE32
    mask_bits = ctypes.create_string_buffer(((size + 15) // 16) * 2 * size)
    hmasks = gdi32.CreateBitmap(size, size, 1, 1, mask_bits)

    ii = ICONINFO()
    ii.fIcon = True
    ii.hbmMask = hmasks
    ii.hbmColor = hbm
    user32.CreateIconIndirect.argtypes = [ctypes.POINTER(ICONINFO)]
    user32.CreateIconIndirect.restype = HANDLE32
    hicon = user32.CreateIconIndirect(ctypes.byref(ii))
    gdi32.DeleteObject(hbm)
    gdi32.DeleteObject(hmasks)
    return hicon


def make_cursor():
    user32.LoadCursorW.argtypes = [wt.HINSTANCE, ctypes.c_void_p]
    user32.LoadCursorW.restype = HANDLE32
    return user32.LoadCursorW(None, ctypes.c_void_p(32512))  # IDC_ARROW


# ----------------------------------------------------------------- 设备图标
# 图标风格对齐 UI/设备图标.png：灰色线条 + 浅蓝填充，24×24 设计稿
ICON_BLUE = (0x7C, 0xC8, 0xF2)
ICON_GRAY = (0x7E, 0x80, 0x86)


def _rrect_mask(x0, y0, x1, y1, r):
    r = max(0.0, min(r, (x1 - x0) / 2.0, (y1 - y0) / 2.0))

    def inside(px, py):
        if px < x0 or px > x1 or py < y0 or py > y1:
            return False
        cx = min(max(px, x0 + r), x1 - r)
        cy = min(max(py, y0 + r), y1 - r)
        dx, dy = px - cx, py - cy
        return dx * dx + dy * dy <= r * r
    return inside


def _render_shapes(size, painter, ss=4):
    """把 painter(paint, u) 描述的矢量图超采样成预乘 BGRA 位图

    u = 一个设计稿单位对应的像素数（设计稿按 24×24 画）
    """
    W = size * ss
    alpha = [0.0] * (W * W)
    rgb = [None] * (W * W)

    def paint(mask, color):
        cr, cg, cb = color
        for yy in range(W):
            base = yy * W
            fy = yy + 0.5
            for xx in range(W):
                if mask(xx + 0.5, fy):
                    idx = base + xx
                    alpha[idx] = 1.0
                    rgb[idx] = (cr, cg, cb)

    painter(paint, W / 24.0)

    out = bytearray(size * size * 4)
    inv = 1.0 / (ss * ss)
    for y in range(size):
        for x in range(size):
            sa = sr = sg = sb = 0.0
            for sy in range(ss):
                base = (y * ss + sy) * W + x * ss
                for sx in range(ss):
                    a = alpha[base + sx]
                    if a:
                        c = rgb[base + sx]
                        sa += a
                        sr += a * c[0]
                        sg += a * c[1]
                        sb += a * c[2]
            if sa <= 0.0:
                continue
            cov = sa * inv
            i = (y * size + x) * 4
            # AlphaBlend 要求源位图为预乘 alpha
            out[i] = int(sb / sa * cov + 0.5)
            out[i + 1] = int(sg / sa * cov + 0.5)
            out[i + 2] = int(sr / sa * cov + 0.5)
            out[i + 3] = int(cov * 255.0 + 0.5)
    return bytes(out)


def _draw_keyboard(paint, u):
    def rr(x0, y0, x1, y1, r):
        return _rrect_mask(x0 * u, y0 * u, x1 * u, y1 * u, r * u)

    outer = rr(1.6, 6.2, 22.4, 17.8, 2.6)
    inner = rr(3.1, 7.7, 20.9, 16.3, 1.6)

    def ring(px, py):
        return outer(px, py) and not inner(px, py)

    paint(ring, ICON_GRAY)
    for row_y in (9.2, 12.1):
        for i in range(4):
            x0 = 4.7 + i * 4.05
            paint(rr(x0, row_y, x0 + 2.95, row_y + 1.6, 0.45), ICON_BLUE)
    paint(rr(8.4, 14.8, 15.6, 16.15, 0.45), ICON_BLUE)


def _draw_mouse(paint, u):
    def rr(x0, y0, x1, y1, r):
        return _rrect_mask(x0 * u, y0 * u, x1 * u, y1 * u, r * u)

    outer = rr(7.2, 2.6, 16.8, 21.4, 4.4)
    inner = rr(8.7, 4.1, 15.3, 19.9, 2.9)

    def ring(px, py):
        return outer(px, py) and not inner(px, py)

    paint(ring, ICON_GRAY)

    line = rr(8.2, 9.85, 15.8, 10.75, 0.45)
    paint(lambda px, py: line(px, py) and inner(px, py), ICON_GRAY)
    paint(rr(10.95, 5.3, 13.05, 8.6, 1.0), ICON_BLUE)


def _draw_dongle(paint, u):
    def rr(x0, y0, x1, y1, r):
        return _rrect_mask(x0 * u, y0 * u, x1 * u, y1 * u, r * u)

    outer = rr(7.4, 2.4, 16.6, 21.6, 3.0)
    inner = rr(8.9, 3.9, 15.1, 20.1, 2.0)

    def ring(px, py):
        return outer(px, py) and not inner(px, py)

    paint(ring, ICON_GRAY)
    paint(rr(9.6, 4.6, 14.4, 9.4, 0.8), ICON_BLUE)
    paint(rr(10.9, 13.4, 13.1, 15.6, 1.1), ICON_GRAY)


_PAINTERS = {"kbd": _draw_keyboard, "mouse": _draw_mouse, "dongle": _draw_dongle}
_icon_cache = {}


def _flat_bgra(data, w, h):
    """把一段字节做成一幅 32bpp DIB，并返回 (memdc, hbitmap)

    不返回 HDC 而是返回可复用的 DC：图标尺寸固定，一次建好反复贴。
    """
    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = w
    bmi.bmiHeader.biHeight = -h
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = 0
    bmi.bmiHeader.biSizeImage = len(data)

    bits = ctypes.c_void_p()
    gdi32.CreateDIBSection.argtypes = [wt.HDC, ctypes.POINTER(BITMAPINFO), wt.UINT,
                                       ctypes.POINTER(ctypes.c_void_p), wt.HANDLE, wt.DWORD]
    gdi32.CreateDIBSection.restype = HANDLE32
    hbm = gdi32.CreateDIBSection(None, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
    if not hbm:
        return None
    ctypes.memmove(bits, data, len(data))
    memdc = gdi32.CreateCompatibleDC(None)
    gdi32.SelectObject(memdc, hbm)
    return memdc, hbm


def _icon_bitmap(kind, size, bg):
    """返回 (memdc, hbitmap)；同尺寸同类图标只栅格化一次

    bg 是图标将要覆盖的底色。这里直接把「预乘图标 + 底色」算成不透明像素，
    贴图时用 BitBlt 即可 —— 不用 AlphaBlend（本机该 API 对 DIB 源位图
    一律返回 ERROR_INVALID_PARAMETER，见 README 的踩坑记录）。
    """
    key = (kind, size, bg)
    hit = _icon_cache.get(key)
    if hit:
        return hit
    prem = _render_shapes(size, _PAINTERS.get(kind, _draw_dongle))
    br, bgc, bb = bg
    out = bytearray(len(prem))
    for i in range(0, len(prem), 4):
        inv = 255 - prem[i + 3]
        out[i] = min(255, prem[i] + bb * inv // 255)
        out[i + 1] = min(255, prem[i + 1] + bgc * inv // 255)
        out[i + 2] = min(255, prem[i + 2] + br * inv // 255)
        out[i + 3] = 255
    hit = _flat_bgra(bytes(out), size, size)
    _icon_cache[key] = hit
    return hit


def device_icon(hdc, kind, x, y, size, bg=(0xFF, 0xFF, 0xFF)):
    """把设备图标画到 hdc 的 (x, y)，size 为物理像素边长

    bg 必须传图标位置的真实底色，否则边缘会出现一圈杂色。
    """
    size = int(size)
    if size < 8:
        return
    hit = _icon_bitmap(kind, size, bg)
    if not hit:
        return
    gdi32.BitBlt.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                             ctypes.c_int, wt.HDC, ctypes.c_int, ctypes.c_int, wt.DWORD]
    gdi32.BitBlt.restype = wt.BOOL
    gdi32.BitBlt(hdc, int(x), int(y), size, size, hit[0], 0, 0, 0x00CC0020)



def message_loop():
    msg = wt.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))


# 放在最后：前面各处又逐个改过 restype，这里统一收口
_fix_handle_restypes()
