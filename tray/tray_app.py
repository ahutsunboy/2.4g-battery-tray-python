"""
tray_app.py — 2.4G 无线外设电量托盘（主程序）

纯 Python 标准库 + ctypes 调用 Win32 / GDI / HID，无任何第三方依赖。
常驻内存约 25~30 MB。

交互：
  * 鼠标移到托盘图标 → 提示里只有「设备名 + 电量」
  * 左键单击          → 弹出电量卡片；再次单击或点击别处自动收起
  * 右键单击          → 开机自启 / 低电量提醒 / 查看日志 / 退出
  * 电量跌破阈值      → 弹一条 Windows 系统通知（点它也能打开卡片）

用法：  pythonw tray_app.py
"""

import ctypes
import ctypes.wintypes as wt
import gc
import json
import os
import sys
import threading
import time

LOG_PATH = os.path.join(os.environ.get("TEMP", "."), "2.4g_battery_tray.log")


def _ensure_streams():
    """pythonw 下没有控制台，把 stdout/stderr 接到日志文件，便于排错"""
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        # 新建文件时先写 UTF-8 BOM，避免记事本等工具按 GBK 打开导致中文乱码
        try:
            empty = os.path.getsize(LOG_PATH) == 0
        except OSError:
            empty = True
        stream = open(LOG_PATH, "a", encoding="utf-8-sig" if empty else "utf-8",
                      buffering=1, errors="replace")
    except OSError:
        stream = open(os.devnull, "w")
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream


_ensure_streams()

import battery_hid as bh
import wsgui as ui

# --------------------------------------------------------------- 常量
WM_TRAY = ui.WM_APP + 1
WM_CLICK_OUTSIDE = ui.WM_APP + 2
# 工作线程 → 主循环：有设备跌破电量阈值，等主循环播报。
# 必须是 +3：+1 / +2 已被托盘回调与「点外部收起」占用，撞号会互相劫持消息
WM_LOW_BATTERY = ui.WM_APP + 3
WM_KEYDOWN = 0x0100
VK_ESCAPE = 0x1B
MENU_AUTOSTART = 1002
MENU_EXIT = 1003
MENU_LOG = 1004
MENU_LOWALERT = 1005

NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP = 0x01, 0x02, 0x04
NIF_INFO = 0x10
# 气泡图标：0 无 / 1 信息 / 2 警告 / 3 错误。低电量用警告，系统会配一张黄色感叹号
NIIF_NONE, NIIF_INFO, NIIF_WARNING, NIIF_ERROR = 0x00, 0x01, 0x02, 0x03
# 用户点了通知本体（不是那个叉）。legacy 模式下从回调消息的 lParam 低 16 位送来；
# 同一批还有 0x0402/0x0403/0x0404（显示/消失/超时），都不需要处理
NIN_BALLOONUSERCLICK = 0x0405
MF_STRING, MF_CHECKED, MF_SEPARATOR, MF_GRAYED = 0x0000, 0x0008, 0x0800, 0x0001
TPM_RIGHTBUTTON = 0x0002
# 必须带 TPM_RETURNCMD：否则 TrackPopupMenu 只返回 TRUE/FALSE，
# 选中的菜单项 id 会改由 WM_COMMAND 送出（本程序不处理该消息），菜单等于点了没反应
TPM_RETURNCMD = 0x0100
TPM_NONOTIFY = 0x0080
SW_HIDE, SW_SHOW = 0, 5
SM_CXSMICON = 49
TE_LEAVE = 0x00000002
HWND_TOPMOST = -1
SWP_SHOWWINDOW = 0x0040
SPI_GETWORKAREA = 0x0030

#: 键盘这类「可主动查询」的设备，每 10 分钟问一次
QUERY_INTERVAL = 600
#: 鼠标这类「只会主动播报」的设备，阻塞等待一帧的最长时间（毫秒）
LISTEN_MS = 8000
#: 设备重新枚举的间隔（插拔、换接收器）
SCAN_INTERVAL = 60

#: 低电量提醒的默认阈值与迟滞上限，可在 settings.json 里改
LOW_THRESHOLD = 20          # 跌破（含等于）这个值就提醒
LOW_REARM = 25              # 回到这个值以上才算重新武装，再次跌破才再提醒
SETTINGS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "settings.json")

NULL_BRUSH = 5
NULL_PEN = 8


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("hWnd", wt.HWND), ("uID", wt.UINT),
                ("uFlags", wt.UINT), ("uCallbackMessage", wt.UINT),
                ("hIcon", wt.HICON), ("szTip", wt.WCHAR * 128),
                ("dwState", wt.DWORD), ("dwStateMask", wt.DWORD),
                ("szInfo", wt.WCHAR * 256), ("uVersion", wt.UINT),
                ("szInfoTitle", wt.WCHAR * 64), ("dwInfoFlags", wt.DWORD),
                ("guidItem", ui.GUID), ("hBalloonIcon", wt.HICON)]


class TRACKMOUSEEVENT(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("dwFlags", wt.DWORD),
                ("hwndTrack", wt.HWND), ("dwHoverTime", wt.DWORD)]


ui.shell32.Shell_NotifyIconW.argtypes = [wt.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
ui.shell32.Shell_NotifyIconW.restype = wt.BOOL
ui.user32.SetWindowRgn.argtypes = [wt.HWND, wt.HANDLE, wt.BOOL]
ui.gdi32.CreateRoundRectRgn.argtypes = [ctypes.c_int] * 6
ui.gdi32.CreateRoundRectRgn.restype = ui.HANDLE32
ui.user32.DestroyWindow.argtypes = [wt.HWND]
ui.user32.RegisterWindowMessageW.argtypes = [wt.LPCWSTR]
ui.user32.RegisterWindowMessageW.restype = wt.UINT
ui.user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, wt.UINT]
ui.user32.SetWindowPos.restype = wt.BOOL
ui.user32.TrackMouseEvent.argtypes = [ctypes.POINTER(TRACKMOUSEEVENT)]
ui.user32.SystemParametersInfoW.argtypes = [wt.UINT, wt.UINT, ctypes.c_void_p, wt.UINT]
ui.user32.SystemParametersInfoW.restype = wt.BOOL
ui.gdi32.GetStockObject.argtypes = [ctypes.c_int]
ui.gdi32.GetStockObject.restype = ui.HANDLE32
ui.kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.LPCWSTR]
ui.kernel32.CreateMutexW.restype = wt.HANDLE

# --------------------------------------------------------------- 配色
# 取自 UI/电量.png + UI/设备图标.png：白底、深灰大字、亮绿胶囊进度条
C_BG = ui.rgb(0xFF, 0xFF, 0xFF)
C_BORDER = ui.rgb(0xEC, 0xEA, 0xEF)
C_TITLE = ui.rgb(0x30, 0x31, 0x3A)
C_NAME = ui.rgb(0x4C, 0x50, 0x5B)
C_UNIT = ui.rgb(0xA9, 0xA6, 0xAE)
C_META = ui.rgb(0xAF, 0xB2, 0xBA)
C_FOOT = ui.rgb(0xBC, 0xBF, 0xC6)
C_TRACK = ui.rgb(0xF1, 0xEF, 0xF2)
C_ICONBG = ui.rgb(0xF4, 0xF9, 0xFE)
C_DIV = ui.rgb(0xEF, 0xED, 0xF1)
C_GOOD = ui.rgb(0x7F, 0xFF, 0x62)
C_WARN = ui.rgb(0xFF, 0xB0, 0x20)
C_BAD = ui.rgb(0xFF, 0x5A, 0x5A)
C_OFF = ui.rgb(0xC9, 0xCC, 0xD2)

# 鼠标接收器约 48 秒才推一帧，超过这个秒数就说明数据明显陈旧了
STALE_SECONDS = 300


def _log_err(msg):
    """模块级日志（pythonw 下 stdout 已接到日志文件）"""
    try:
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)
    except Exception:
        pass


def _dump_exc(tag=""):
    """打印当前异常。

    traceback 故意**不在顶层 import**：它会连锁拉起 linecache → tokenize → re，
    实测多占约 1 MB 常驻内存，而这个程序正常运行时永远走不到异常分支。
    放在这里按需导入，只在真出错时才付出这份代价。
    """
    try:
        import traceback
        if tag:
            _log_err(tag)
        traceback.print_exc()
    except Exception:
        pass


def _clamp_int(value, default, lo, hi):
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def autostart_script(run_dir=None):
    """生成开机自启 .vbs 的字节内容。

    这里踩过三个坑，都别再改回去：

    1. **引号**。VBScript 字符串里的引号写成两个。以前是手拼 `\"\"\"a\"\" \"\"\"b\"\"\"`，
       引号数凑成 11（奇数），解析到行尾字符串还没闭合 → 开机弹窗
       「语句未结束 / 800A0401」。现在先把整条命令行拼好，再把每个 `"` 翻倍，
       结构清晰且不会数错。
    2. **换行**。文本模式写文件时 `\\n` 会被再翻译成 `\\r\\n`，而我们写的本来就是
       `\\r\\n`，于是落盘成了 `\\r\\r\\n`——行号被算翻倍，报错指向根本不存在的第 5 行。
       所以必须用二进制模式写入。
    3. **编码**。路径里有中文，用 UTF-16（带 BOM）写，不依赖系统 ANSI 代码页。
       Windows Script Host 认 BOM，cscript / wscript 都能正常执行。
    """
    if run_dir is None:
        run_dir = os.path.dirname(os.path.abspath(__file__))
    exe = sys.executable
    pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if not os.path.exists(pyw):
        pyw = exe
    target = os.path.join(run_dir, "tray_app.py")
    cmdline = f'"{pyw}" "{target}"'
    lines = [
        'Set sh = CreateObject("WScript.Shell")',
        'sh.CurrentDirectory = "' + run_dir.replace('"', '""') + '"',
        'sh.Run "' + cmdline.replace('"', '""') + '", 0, False',
    ]
    return ("\r\n".join(lines) + "\r\n").encode("utf-16")


class Settings:
    """settings.json 的读写

    设计要点：
      * 文件不存在 / JSON 坏了 / 编码不对 → 一律退回默认值，绝不影响启动
      * threshold 与 rearm 都做区间钳制，且强制 rearm > threshold，
        否则「回升到 rearm 才重新武装」永远不成立，会变成无限重弹
      * 写入走 tmp + os.replace 原子替换，并保留文件里我们不认识的字段
      * mtime 变了才重读，实现「手改配置免重启」
    """

    def __init__(self, path=SETTINGS_PATH):
        self.path = path
        self.raw = {}
        self.enabled = True
        self.threshold = LOW_THRESHOLD
        self.rearm = LOW_REARM
        self.trim_ws = True          # 空闲时把工作集还给系统
        self.trim_after = 120        # 静默多少秒后修剪
        self._mtime = None
        self.load()

    def load(self):
        raw = {}
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                raw = data
        except FileNotFoundError:
            pass
        except Exception as exc:
            _log_err(f"settings.json 读取失败，使用默认值: {exc}")
        self.raw = raw
        lb = raw.get("low_battery")
        if not isinstance(lb, dict):
            lb = {}
        self.enabled = bool(lb.get("enabled", True))
        self.threshold = _clamp_int(lb.get("threshold"), LOW_THRESHOLD, 5, 95)
        lo = self.threshold + 1
        self.rearm = _clamp_int(lb.get("rearm"), max(LOW_REARM, lo), lo, 100)
        mem = raw.get("memory")
        if not isinstance(mem, dict):
            mem = {}
        self.trim_ws = bool(mem.get("trim_working_set", True))
        self.trim_after = _clamp_int(mem.get("idle_seconds"), 120, 30, 3600)
        try:
            self._mtime = os.path.getmtime(self.path)
        except OSError:
            self._mtime = None

    def reload_if_changed(self):
        """手改文件后免重启。重读失败时 _mtime 不动，不会把内存值冲掉"""
        try:
            m = os.path.getmtime(self.path)
        except OSError:
            return
        if m != self._mtime:
            self.load()

    def save(self):
        data = dict(self.raw) if isinstance(self.raw, dict) else {}
        lb = data.get("low_battery")
        lb = dict(lb) if isinstance(lb, dict) else {}
        lb.update({"enabled": bool(self.enabled),
                   "threshold": int(self.threshold),
                   "rearm": int(self.rearm)})
        mem = data.get("memory")
        mem = dict(mem) if isinstance(mem, dict) else {}
        mem.update({"trim_working_set": bool(self.trim_ws),
                    "idle_seconds": int(self.trim_after)})
        data.setdefault("version", 1)
        data["low_battery"] = lb
        data["memory"] = mem
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.write("\n")
            os.replace(tmp, self.path)
            self.raw = data
            self._mtime = os.path.getmtime(self.path)
            return True
        except OSError as exc:
            # 只读目录 / 杀软占着文件：只影响持久化，本次运行照常生效
            _log_err(f"settings.json 写入失败，仅本次运行生效: {exc}")
            try:
                os.remove(tmp)
            except OSError:
                pass
            return False


class LowBatteryGate:
    """每台设备一个「低电量迟滞状态机」

    为什么需要迟滞：鼠标电量会有 45↔46 这种抖动，阈值附近的 19↔20 抖动
    如果每次都报，会变成反复弹窗。规则是——跌破阈值报一次，之后必须回到
    rearm 以上才重新武装。

    为什么必须看 reading 而不是 DeviceState.battery：设备离线时
    DeviceState.battery 会保留几小时前的旧值，用旧值判断等于反复误报。
    """

    __slots__ = ("cfg", "notified")

    def __init__(self, cfg=None):
        self.cfg = cfg or Settings(path="")
        self.notified = False

    def feed(self, reading):
        """喂一帧读数；返回 True 表示这一帧需要弹通知"""
        if reading is None or not reading.fresh:
            return False            # 缓存复述不算事件（鼠标每 3 秒复述一次）
        if reading.battery is None or reading.online is False:
            return False            # 没读到 / 设备休眠，电量可能是陈旧值
        pct = reading.battery
        if pct >= self.cfg.rearm:
            self.notified = False   # 回升够了，重新武装
            return False
        if pct <= self.cfg.threshold and not self.notified \
                and not reading.charging:
            self.notified = True    # 先记账，避免关掉提醒时反复计
            return bool(self.cfg.enabled)
        return False


def _shell_notify(cmd, nid):
    """薄封装：单元测试里整段替换掉它，就不会真的弹通知"""
    return bool(ui.shell32.Shell_NotifyIconW(cmd, ctypes.byref(nid)))


def rel_time(ts):
    """把时间戳说成人话：刚刚 / 42 秒前 / 3 分钟前"""
    if not ts:
        return ""
    age = max(0, time.time() - ts)
    if age < 10:
        return "刚刚"
    if age < 60:
        return f"{int(age)} 秒前"
    if age < 3600:
        return f"{int(age // 60)} 分钟前"
    if age < 86400:
        return f"{int(age // 3600)} 小时前"
    return f"{int(age // 86400)} 天前"


def bar_color(pct, brush_map):
    if pct is None:
        return brush_map["off"]
    if pct < 20:
        return brush_map["bad"]
    if pct < 45:
        return brush_map["warn"]
    return brush_map["good"]


# --------------------------------------------------------------- 设备状态
class DeviceState:
    #: cfg 必须带默认值：任何漏传的调用点若抛 TypeError，会让 _rescan 整体失败、
    #: 设备列表变成空的，症状是「程序在跑但一台设备都不显示」
    def __init__(self, driver, cfg=None):
        self.driver = driver
        self.key = driver.key + ":" + driver.info.id
        self.label = driver.label
        self.name = driver.name
        self.kind = "kbd" if driver.key.startswith("compx") else "mouse"
        self.battery = None
        self.charging = False
        self.online = None
        self.raw = ""
        self.note = ""
        self.updated = None
        self.error = ""
        self.low = LowBatteryGate(cfg)   # 迟滞状态机，不进 snapshot()

    @property
    def display(self):
        return self.name or self.label

    def apply(self, reading):
        if reading is None:
            return
        if reading.battery is not None:
            self.battery = reading.battery
            # 只有设备真的发了新数据才推进时间戳，缓存值沿用上一次的时间
            if reading.fresh:
                self.updated = time.time()
            self.note = ""
        elif reading.note:
            self.note = reading.note
        self.charging = bool(reading.charging)
        if reading.online is not None:
            self.online = reading.online
        if reading.raw:
            self.raw = reading.raw

    def snapshot(self):
        return {
            "name": self.display, "label": self.label, "kind": self.kind,
            "vidpid": self.driver.info.id,
            "battery": self.battery, "charging": self.charging,
            "online": self.online, "raw": self.raw, "note": self.note,
            "updated_ts": self.updated,
        }


# --------------------------------------------------------------- 主程序
class BatteryTray:
    # 版面尺寸（逻辑像素，绘制时乘以 DPI 缩放）
    PAD = 18
    WIDTH = 352
    HEADER_H = 44
    ROW_H = 100
    FOOTER_H = 34

    def __init__(self):
        self.scale = ui.dpi_scale()
        self.hinst = ui.kernel32.GetModuleHandleW(None)
        self.states = []
        self.lock = threading.RLock()
        self.stop_flag = threading.Event()
        self._last_sig = None
        self._last_tip_state = None
        self.hwnd_tray = None
        self.hwnd_panel = None
        self.tray_added = False
        self.panel_visible = False
        self.last_hide = 0.0
        self.mouse_hook = 0
        self._mouse_hook_ref = None
        self.dirty = True
        self.cfg = Settings()
        #: 待播报的设备 key。由 _poll_loop 在锁内 append、主循环 drain。
        #: 之所以不在主循环里「重新算一遍谁低电量」：主循环拿不到 reading.fresh，
        #: 也分不清「刚跌到 18%」和「几小时前就是 18%」，会误报。
        self._pending_low = []
        self._cfg_check = 0.0
        #: 省内存：长时间无人理会时把工作集还给系统（见 _on_tray_msg 的 WM_TIMER）
        self._last_active = time.time()
        self._trim_at = 0.0
        self._tick = 0
        self.fonts = {}
        self.brushes = {}
        self._icon_cache = {}
        self._wndproc_refs = []
        self.taskbar_created_msg = ui.user32.RegisterWindowMessageW("TaskbarCreated")
        self.autostart_path = os.path.join(
            os.environ.get("APPDATA", ""),
            r"Microsoft\Windows\Start Menu\Programs\Startup\2.4G电量托盘.vbs")

    def _log(self, msg):
        try:
            print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)
        except Exception:
            pass

    # ---------------------------------------------------------- 初始化
    def build(self):
        self._create_resources()
        self._register_classes()
        self.hwnd_tray = ui.user32.CreateWindowExW(
            0, "BatteryTrayHost", "2.4G电量托盘", ui.WS_POPUP,
            0, 0, 0, 0, None, None, self.hinst, None)
        self.hwnd_panel = ui.user32.CreateWindowExW(
            ui.WS_EX_TOOLWINDOW | ui.WS_EX_TOPMOST, "BatteryTrayPanel", "", ui.WS_POPUP,
            0, 0, 10, 10, None, None, self.hinst, None)
        ui.user32.SetTimer(self.hwnd_tray, 1, 800, None)
        self._start_workers()
        self._refresh_tray()
        if os.environ.get("BT_SHOW_PANEL"):
            ui.user32.SetTimer(self.hwnd_tray, 2, 1500, None)

    def _create_resources(self):
        s = self.scale
        specs = {
            "title": (int(13 * s), ui.FW_SEMIBOLD),
            "name": (int(13 * s), ui.FW_SEMIBOLD),
            "pct": (int(26 * s), ui.FW_BOLD),
            "sign": (int(13 * s), ui.FW_BOLD),
            "unit": (int(11.5 * s), ui.FW_NORMAL),
            "meta": (int(10.5 * s), ui.FW_NORMAL),
        }
        for k, (px, weight) in specs.items():
            self.fonts[k] = ui.gdi32.CreateFontW(
                -max(px, 8), 0, 0, 0, weight, 0, 0, 0, 1, 0, 0, 5, 0,
                "Microsoft YaHei UI")
        for k, c in (("bg", C_BG), ("iconbg", C_ICONBG), ("track", C_TRACK),
                     ("good", C_GOOD), ("warn", C_WARN), ("bad", C_BAD),
                     ("off", C_OFF), ("div", C_DIV)):
            self.brushes[k] = ui.gdi32.CreateSolidBrush(c)
        self.pen_border = ui.gdi32.CreatePen(ui.PS_SOLID, 1, C_BORDER)

    # ---------------------------------------------------------- 窗口类
    def _register_classes(self):
        cursor = ui.make_cursor()
        for cls_name, fn in (("BatteryTrayHost", self._on_tray_msg),
                             ("BatteryTrayPanel", self._on_panel_msg)):
            proc = ui.WNDPROC(fn)
            wc = ui.WNDCLASSEXW()
            wc.cbSize = ctypes.sizeof(ui.WNDCLASSEXW)
            wc.style = ui.CS_DROPSHADOW if cls_name.endswith("Panel") else 0
            wc.lpfnWndProc = proc
            self._wndproc_refs.append(proc)  # 防止回调被 GC
            wc.hInstance = self.hinst
            wc.hCursor = cursor
            wc.hbrBackground = None
            wc.lpszClassName = cls_name
            if not ui.user32.RegisterClassExW(ctypes.byref(wc)):
                err = ctypes.get_last_error()
                if err != 1410:  # ERROR_CLASS_ALREADY_EXISTS
                    raise OSError(f"注册窗口类失败: {cls_name} err={err}")

    # ---------------------------------------------------------- 托盘窗口
    def _on_tray_msg(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_CLICK_OUTSIDE:
                if self.panel_visible:
                    self._hide_panel()
                return 0
            if msg == WM_TRAY:
                ev = lparam & 0xFFFF
                if ev == 0x0202:            # WM_LBUTTONUP：单击切换卡片
                    self._toggle_panel()
                elif ev == 0x0205:          # WM_RBUTTONUP
                    self._show_menu()
                elif ev == NIN_BALLOONUSERCLICK:
                    # 点了系统通知：把卡片叫出来（已经在显示就别重复弹）
                    if not self.panel_visible:
                        self._show_panel()
                return 0
            if msg == WM_LOW_BATTERY:
                self._flush_low_alerts()
                return 0
            if msg == ui.WM_TIMER:
                if wparam == 2:  # 调试：启动后自动弹出面板
                    ui.user32.KillTimer(self.hwnd_tray, 2)
                    self._show_panel()
                    return 0
                # 兜底：万一 PostMessage 丢了，这一轮也能把攒下的提醒发出去
                if self._pending_low:
                    self._flush_low_alerts()
                now = time.time()
                if now - self._cfg_check > 5.0:   # 手改 settings.json 免重启
                    self._cfg_check = now
                    self.cfg.reload_if_changed()
                if self.dirty:
                    self.dirty = False
                    self._refresh_tray()
                self._tick += 1
                if self.panel_visible:
                    # 数据没变也要重画：「N 分钟前」这类文案会随时间自己往前走。
                    # 但文案是分钟级的，没必要 0.8 秒重绘一次，4 秒一次肉眼看不出来。
                    if self._tick % 4 == 0:
                        ui.user32.InvalidateRect(self.hwnd_panel, None, True)
                elif self.cfg.trim_ws and now - self._last_active > self.cfg.trim_after \
                        and now - self._trim_at > 60:
                    # 长时间没人碰（面板关着、数据也没变）：把闲置页面还给系统
                    self._trim_at = now
                    if ui.trim_working_set():
                        self._log(f"空闲 {int(now - self._last_active)} 秒，"
                                  f"已把工作集还给系统")
                return 0
            if msg == self.taskbar_created_msg and self.taskbar_created_msg:
                self.tray_added = False
                self._refresh_tray()
                return 0
            if msg == ui.WM_DESTROY:
                ui.user32.PostQuitMessage(0)
                return 0
        except Exception:
            _dump_exc()
        return ui.user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _toggle_panel(self):
        """单击托盘图标：没显示就弹出，已显示就收起

        有一个坑：卡片显着的时候点托盘，钩子会在 LBUTTONDOWN 时先把面板收起，
        等同一次点击的 WM_LBUTTONUP 到达时面板已经隐藏了，看起来像「又打开一次」。
        用 last_hide 做个短时间窗（覆盖一次点击的 DOWN→UP 间隔），
        把这下半次点击当成「关闭」而不是「重新打开」。
        """
        if time.time() - self.last_hide < 0.3:
            return
        if self.panel_visible:
            self._hide_panel()
        else:
            self._show_panel()

    def _show_menu(self):
        self._last_active = time.time()
        menu = ui.user32.CreatePopupMenu()
        auto = os.path.exists(self.autostart_path)
        self.cfg.reload_if_changed()      # 手改过 settings.json 就在这里立刻反映
        ui.user32.AppendMenuW(menu, MF_STRING | (MF_CHECKED if auto else 0),
                              MENU_AUTOSTART, "开机自动启动")
        ui.user32.AppendMenuW(
            menu, MF_STRING | (MF_CHECKED if self.cfg.enabled else 0),
            MENU_LOWALERT, f"低电量提醒（低于 {self.cfg.threshold}%）")
        ui.user32.AppendMenuW(menu, MF_STRING, MENU_LOG, "查看日志")
        ui.user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        ui.user32.AppendMenuW(menu, MF_STRING, MENU_EXIT, "退出")
        # 必须真正拿到前台，否则 TrackPopupMenu 收不到点击（菜单像死的）
        ui.force_foreground(self.hwnd_tray)
        pt = wt.POINT()
        ui.user32.GetCursorPos(ctypes.byref(pt))
        cmd = ui.user32.TrackPopupMenu(
            menu, TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY,
            pt.x, pt.y, 0, self.hwnd_tray, None)
        ui.user32.DestroyMenu(menu)
        # 选中项后补一条 WM_NULL，否则弹出菜单可能不消失
        ui.user32.PostMessageW(self.hwnd_tray, 0x0000, 0, 0)
        if cmd:
            self._handle_menu_command(cmd)

    def _handle_menu_command(self, cmd):
        if cmd == MENU_AUTOSTART:
            self._toggle_autostart()
        elif cmd == MENU_LOWALERT:
            self._toggle_low_alert()
        elif cmd == MENU_LOG:
            self._open_log()
        elif cmd == MENU_EXIT:
            self._quit()

    def _open_log(self):
        """用系统默认的文本工具打开日志（文件已带 BOM，中文不会乱码）"""
        try:
            if not os.path.exists(LOG_PATH):
                open(LOG_PATH, "a", encoding="utf-8-sig").close()
            ui.shell32.ShellExecuteW(None, "open", "notepad.exe",
                                     f'"{LOG_PATH}"', None, 1)
        except Exception:
            _dump_exc()

    def _toggle_autostart(self):
        try:
            if os.path.exists(self.autostart_path):
                os.remove(self.autostart_path)
                self._log("已关闭开机自启")
                return
            os.makedirs(os.path.dirname(self.autostart_path), exist_ok=True)
            with open(self.autostart_path, "wb") as f:
                f.write(autostart_script())
            self._log(f"已开启开机自启 -> {self.autostart_path}")
        except Exception as exc:
            self._log(f"切换开机自启失败: {exc}")
            _dump_exc()

    def _quit(self):
        self.stop_flag.set()
        self._disarm_dismiss()
        self._remove_tray()
        with self.lock:
            for st in self.states:
                try:
                    st.driver.close()
                except Exception:
                    pass
        ui.user32.DestroyWindow(self.hwnd_panel)
        ui.user32.DestroyWindow(self.hwnd_tray)
        ui.user32.PostQuitMessage(0)

    # ---------------------------------------------------------- 工作线程
    def _start_workers(self):
        threading.Thread(target=self._scan_loop, daemon=True).start()

    def _scan_loop(self):
        """定期重新枚举设备，负责插拔 / 换接收器后的恢复"""
        while not self.stop_flag.is_set():
            try:
                self._rescan()
            except Exception:
                _dump_exc()
            timeout = SCAN_INTERVAL if self.states else 8
            self.stop_flag.wait(timeout)

    def _rescan(self):
        try:
            drivers = bh.find_drivers()
        except Exception:
            _dump_exc()
            drivers = []
        with self.lock:
            fresh = []
            for drv in drivers:
                key = drv.key + ":" + drv.info.id
                existing = next((s for s in self.states if s.key == key), None)
                if existing:
                    fresh.append(existing)
                    drv.close()
                else:
                    st = DeviceState(drv, self.cfg)
                    fresh.append(st)
                    threading.Thread(target=self._poll_loop, args=(st,),
                                     daemon=True).start()
            for st in self.states:
                if st not in fresh:
                    try:
                        st.driver.close()
                    except Exception:
                        pass
            self.states = fresh
        sig = tuple(st.driver.info.id for st in fresh)
        if sig != self._last_sig:      # 只在设备集合变化时记一笔，避免刷屏
            self._last_sig = sig
            if fresh:
                self._log("已连接: " + ", ".join(
                    f"{st.display}({st.driver.info.id})" for st in fresh))
            else:
                self._log("未检测到受支持的 2.4G 接收器，稍后重试")
        self.dirty = True

    def _poll_loop(self, st):
        """每条设备一个线程

        键盘（可主动查询）：每 QUERY_INTERVAL 秒问一次。
        鼠标（只能被动接收）：阻塞在一帧上，来了就更新 → 天然实时。
        """
        drv = st.driver
        realtime = drv.key == "mchose"
        while not self.stop_flag.is_set():
            reading = None
            try:
                reading = drv.poll(LISTEN_MS if realtime else 1800)
                st.error = ""
            except Exception as exc:
                st.error = str(exc)
            if reading is not None:
                alert = False
                with self.lock:
                    before = (st.battery, st.online)
                    st.apply(reading)
                    after = (st.battery, st.online)
                    try:
                        # 判定必须在锁内、且在手握这一帧 reading 的线程里做
                        if st.low.feed(reading):
                            alert = True
                            self._pending_low.append(st.key)
                    except Exception:
                        # 提醒逻辑绝不能炸死轮询线程：线程一死这台设备就永久停更
                        _dump_exc()
                if reading.fresh and reading.battery is not None \
                        and reading.battery != before[0]:
                    self._log(f"{st.display}: {reading.battery}%  ({reading.raw})")
                    # 电量真的变了 = 有人在用设备，重置「空闲」计时（省内存修剪用）。
                    # 只认电量变化：60 秒一次的例行重扫会把 dirty 打开，
                    # 若把 dirty 当活跃信号，120 秒的空闲阈值永远达不到。
                    self._last_active = time.time()
                if after != before:
                    self.dirty = True
                if alert:
                    self._log(f"{st.display}: 电量偏低，排队提醒")
                    # 锁外投递（锁内跨线程 PostMessage 是死锁形状）；
                    # 只是「加速信号」，丢了还有 800ms 定时器兜底
                    ui.user32.PostMessageW(self.hwnd_tray, WM_LOW_BATTERY, 0, 0)
                if realtime and not reading.fresh:
                    # 没收到新帧（设备休眠 / 未插好）就别紧贴着重试
                    self.stop_flag.wait(0.5)
            elif realtime:
                self.stop_flag.wait(2.0)
            if not realtime:
                self.stop_flag.wait(QUERY_INTERVAL)

    # ---------------------------------------------------------- 托盘刷新
    def _icon_for(self, pct, charging):
        size = ui.user32.GetSystemMetrics(SM_CXSMICON) or 16
        bucket = None if pct is None else max(0, min(100, int(round(pct / 5.0)) * 5))
        key = (size, bucket, bool(charging))
        if key not in self._icon_cache:
            self._icon_cache[key] = ui.make_hicon(size, bucket or 0, bool(charging))
        return self._icon_cache[key]

    def _refresh_tray(self, force=True):
        with self.lock:
            snaps = [s.snapshot() for s in self.states]
        withbat = [s for s in snaps if s["battery"] is not None]
        if withbat:
            low = min(withbat, key=lambda s: s["battery"])
            icon = self._icon_for(low["battery"], low["charging"])
        else:
            icon = self._icon_for(None, False)
        if snaps:
            # 悬停提示只给「设备名 + 电量」，具体多久前更新留在卡片里看
            tip = "  ·  ".join(
                (f"{s['name']} {s['battery']}%" if s["battery"] is not None
                 else f"{s['name']} --") for s in snaps)
        else:
            tip = "未检测到支持的 2.4G 设备"
        state = (icon, tip[:120])
        if not force and state == self._last_tip_state and self.tray_added:
            return
        self._last_tip_state = state
        self._notify(icon, tip[:120], modify=self.tray_added)

    def _notify(self, hicon, tip, modify=False):
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd_tray
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAY
        nid.hIcon = hicon
        nid.szTip = tip
        ok = ui.shell32.Shell_NotifyIconW(NIM_MODIFY if modify else NIM_ADD,
                                          ctypes.byref(nid))
        if not ok and modify:
            # 图标被资源管理器重建后需要重新添加
            ok = ui.shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))
        self.tray_added = bool(ok)

    def _remove_tray(self):
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd_tray
        nid.uID = 1
        ui.shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))

    # ---------------------------------------------------------- 低电量提醒
    def _flush_low_alerts(self):
        """主循环调用：把排队中的设备合并成一条系统通知

        合并是必要的：两台设备同时掉到阈值以下，弹两条会互相把对方顶掉，
        而且托盘一次只能挂一条气泡。
        """
        with self.lock:
            keys = self._pending_low[:]
            del self._pending_low[:]
            by_key = {st.key: st for st in self.states}
            items = []
            for k in keys:
                st = by_key.get(k)
                # 排队到播报之间设备可能已经被拔掉，静默丢弃
                if st is None or st.battery is None:
                    continue
                items.append((st.display, st.battery))
        if not items:
            return
        title, info = self._toast_text(items)
        self._log("低电量提醒: " + " · ".join(f"{n} {p}%" for n, p in items))
        self._show_toast(title, info)

    @staticmethod
    def _toast_text(items):
        """拼通知文案

        szInfoTitle 是 64 个 wchar、szInfo 是 256 个 wchar。必须切到 63 / 255：
        填满虽然不报错，但字符串没有 NUL 结尾，shell 会继续读后面的字段。
        """
        items = sorted(items, key=lambda it: it[1])       # 最危险的最前面
        head = "、".join(f"{n} 剩余 {p}%" for n, p in items[:2])
        if len(items) > 2:
            head += f"，等 {len(items)} 台设备"
        return "设备电量不足"[:63], f"{head}，建议尽快充电（点击查看详情）"[:255]

    def _show_toast(self, title, info):
        """发一条系统通知

        走 Shell_NotifyIcon(NIM_MODIFY) + NIF_INFO：Win10/11 会把它渲染成原生
        toast 横幅并带提示音，不需要注册 AppUserModelID，也不需要任何第三方库。

        三条不能碰的红线：
          1. uVersion 只能是 0。设成 4（NOTIFYICON_VERSION_4）后回调语义会变成
             「wParam 带坐标、lParam 低字是 NIN_*」，_on_tray_msg 里
             `ev = lparam & 0xFFFF` 的解析全部错位，左键/右键/点外部收起会一起失效。
          2. uFlags 只写 NIF_INFO。不要加 NIF_ICON / NIF_TIP —— 那会顺手覆盖托盘
             图标和悬停文案；也绝不要把 NIF_INFO 加进共用的 _notify()，那条路被
             800ms 定时器驱动，会变成通知风暴。
          3. 字符串切到 63 / 255，保证 NUL 结尾。
        """
        if not self.hwnd_tray:
            return
        if not self.tray_added:
            # 图标不在托盘里时 NIM_MODIFY 必然失败，先补一次 NIM_ADD
            self._refresh_tray(force=True)
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd_tray
        nid.uID = 1
        nid.uFlags = NIF_INFO
        nid.uVersion = 0
        nid.szInfoTitle = title[:63]
        nid.szInfo = str(info).replace("\n", " ")[:255]
        nid.dwInfoFlags = NIIF_WARNING
        ok = _shell_notify(NIM_MODIFY, nid)
        if not ok and self.tray_added:
            # Explorer 重启过 / 图标刚被回收，补一次再试
            self._refresh_tray(force=True)
            ok = _shell_notify(NIM_MODIFY, nid)
        if not ok:
            self._log(f"系统通知发送失败 err={ctypes.get_last_error()}")
        return ok

    def _toggle_low_alert(self):
        self.cfg.enabled = not self.cfg.enabled
        saved = self.cfg.save()
        self._log(f"低电量提醒 → {'开' if self.cfg.enabled else '关'}"
                  + ("" if saved else "（设置没写进磁盘，仅本次运行生效）"))
        if self.cfg.enabled:
            # 顺手当「通知通道通不通」的自检，省得等到真掉到阈值才发现没弹
            self._show_toast("低电量提醒已开启",
                             f"电量低于 {self.cfg.threshold}% 时会提醒你一次")

    # ---------------------------------------------------------- 面板
    def _panel_layout(self):
        s = self.scale
        with self.lock:
            n = max(len(self.states), 1)
        w = int(self.WIDTH * s)
        h = int((self.HEADER_H + n * self.ROW_H + self.FOOTER_H) * s)
        return (w, h, int(self.PAD * s), int(self.HEADER_H * s),
                int(self.ROW_H * s), int(self.FOOTER_H * s))

    def _work_area(self):
        rect = wt.RECT()
        if ui.user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0):
            return rect.left, rect.top, rect.right, rect.bottom
        return (0, 0, ui.user32.GetSystemMetrics(0), ui.user32.GetSystemMetrics(1))

    def _show_panel(self):
        self._last_active = time.time()
        w, h, *_ = self._panel_layout()
        pt = wt.POINT()
        ui.user32.GetCursorPos(ctypes.byref(pt))
        left, top, right, bottom = self._work_area()
        margin = int(8 * self.scale)
        # 贴着托盘图标往上弹，并保证完整落在工作区内
        x = min(max(pt.x - w + int(26 * self.scale), left + margin), right - w - margin)
        y = min(max(pt.y - h - int(12 * self.scale), top + margin), bottom - h - margin)
        ui.user32.SetWindowPos(self.hwnd_panel, HWND_TOPMOST, x, y, w, h, SWP_SHOWWINDOW)
        rgn = ui.gdi32.CreateRoundRectRgn(0, 0, w + 1, h + 1,
                                          int(13 * self.scale), int(13 * self.scale))
        ui.user32.SetWindowRgn(self.hwnd_panel, rgn, True)
        ui.user32.ShowWindow(self.hwnd_panel, SW_SHOW)
        ui.force_foreground(self.hwnd_panel)
        ui.user32.SetFocus(self.hwnd_panel)
        self.panel_visible = True
        self._arm_dismiss()
        ui.user32.InvalidateRect(self.hwnd_panel, None, True)

    def _arm_dismiss(self):
        """面板显示期间挂上鼠标钩子，点面板外任何地方就收起"""
        if self.mouse_hook:
            return
        self.mouse_hook, self._mouse_hook_ref = ui.install_mouse_hook(
            self._on_global_click, self.hinst)
        if not self.mouse_hook:
            self._log(f"鼠标钩子安装失败，退回失焦收起 err={ctypes.get_last_error()}")

    def _on_global_click(self, x, y):
        """钩子回调：只做判断，真正的隐藏在消息循环里执行

        钩子回调运行在系统的鼠标输入路径上，不能在这里直接销毁/隐藏窗口，
        也不能卸载自己（UnhookWindowsHookEx 不允许在自身回调内调用）。
        投递一条自定义消息回到主循环处理即可。
        """
        if not self.panel_visible or not self.hwnd_panel:
            return
        rect = wt.RECT()
        if not ui.user32.GetWindowRect(self.hwnd_panel, ctypes.byref(rect)):
            return
        if rect.left <= x < rect.right and rect.top <= y < rect.bottom:
            return   # 点在面板里，不动
        ui.user32.PostMessageW(self.hwnd_tray, WM_CLICK_OUTSIDE, 0, 0)

    def _disarm_dismiss(self):
        if self.mouse_hook:
            ui.uninstall_mouse_hook(self.mouse_hook)
            self.mouse_hook = 0
            self._mouse_hook_ref = None

    def _hide_panel(self):
        ui.user32.ShowWindow(self.hwnd_panel, SW_HIDE)
        self.panel_visible = False
        self.last_hide = time.time()
        self._last_active = self.last_hide
        self._disarm_dismiss()

    def _on_panel_msg(self, hwnd, msg, wparam, lparam):
        try:
            if msg == ui.WM_PAINT:
                self._paint_panel(hwnd)
                return 0
            if msg == ui.WM_ERASEBKGND:
                return 1
            if msg == ui.WM_ACTIVATE and (wparam & 0xFFFF) == 0:
                # 兜底：能拿到激活态时，切窗口也收起
                self._hide_panel()
                return 0
            if msg == WM_KEYDOWN and wparam == VK_ESCAPE:
                self._hide_panel()
                return 0
        except Exception:
            _dump_exc()
        return ui.user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    # ---------------------------------------------------------- GDI 辅助
    def _fill(self, hdc, brush, x0, y0, x1, y1):
        rect = wt.RECT(int(x0), int(y0), int(x1), int(y1))
        ui.user32.FillRect(hdc, ctypes.byref(rect), brush)

    def _round_fill(self, hdc, brush, x0, y0, x1, y1, r):
        old_brush = ui.gdi32.SelectObject(hdc, brush)
        old_pen = ui.gdi32.SelectObject(hdc, ui.gdi32.GetStockObject(NULL_PEN))
        ui.gdi32.RoundRect(hdc, int(x0), int(y0), int(x1), int(y1),
                           int(r * 2), int(r * 2))
        ui.gdi32.SelectObject(hdc, old_brush)
        ui.gdi32.SelectObject(hdc, old_pen)

    def _round_stroke(self, hdc, pen, x0, y0, x1, y1, r):
        old_pen = ui.gdi32.SelectObject(hdc, pen)
        old_brush = ui.gdi32.SelectObject(hdc, ui.gdi32.GetStockObject(NULL_BRUSH))
        ui.gdi32.RoundRect(hdc, int(x0), int(y0), int(x1), int(y1),
                           int(r * 2), int(r * 2))
        ui.gdi32.SelectObject(hdc, old_brush)
        ui.gdi32.SelectObject(hdc, old_pen)

    def _text(self, hdc, text, font, color, x, y, w, h, align=ui.DT_LEFT):
        old = ui.gdi32.SelectObject(hdc, font)
        ui.gdi32.SetTextColor(hdc, color)
        ui.gdi32.SetBkMode(hdc, ui.TRANSPARENT)
        rect = wt.RECT(int(x), int(y), int(x + w), int(y + h))
        ui.user32.DrawTextW(hdc, text, len(text), ctypes.byref(rect),
                            align | ui.DT_SINGLELINE | ui.DT_NOPREFIX)
        ui.gdi32.SelectObject(hdc, old)

    def _paint_panel(self, hwnd):
        ps = ui.PAINTSTRUCT()
        hdc = ui.user32.BeginPaint(hwnd, ctypes.byref(ps))
        try:
            w, h, *_ = self._panel_layout()
            self._paint_content(hdc, w, h)
        finally:
            ui.user32.EndPaint(hwnd, ctypes.byref(ps))

    def _paint_content(self, hdc, w, h):
        """把面板内容画到任意 HDC 上（窗口绘制与离屏渲染共用）"""
        s = self.scale
        pad = int(self.PAD * s)
        header_h = int(self.HEADER_H * s)
        row_h = int(self.ROW_H * s)
        footer_h = int(self.FOOTER_H * s)

        self._fill(hdc, self.brushes["bg"], 0, 0, w, h)
        self._round_stroke(hdc, self.pen_border, 1, 1, w - 1, h - 1, int(12 * s))

        with self.lock:
            snaps = [st.snapshot() for st in self.states]

        # 标题行
        self._text(hdc, "设备电量", self.fonts["title"], C_TITLE,
                   pad, 0, w - pad * 2 - int(64 * s), header_h, ui.DT_VCENTER)
        if snaps:
            self._text(hdc, f"{len(snaps)} 台设备", self.fonts["meta"], C_META,
                       w - pad - int(64 * s), 0, int(64 * s), header_h,
                       ui.DT_VCENTER | ui.DT_RIGHT)

        # 设备行
        if not snaps:
            block = int(46 * s)
            ey = header_h + (row_h - block) // 2
            self._text(hdc, "未检测到 2.4G 接收器", self.fonts["name"], C_NAME,
                       pad, ey, w - pad * 2, int(24 * s), ui.DT_VCENTER)
            self._text(hdc, "请确认接收器已插好，或该型号尚未适配", self.fonts["meta"],
                       C_META, pad, ey + int(24 * s), w - pad * 2, int(20 * s),
                       ui.DT_VCENTER)
        else:
            y = header_h
            for i, snap in enumerate(snaps):
                self._paint_row(hdc, snap, y, w, row_h)
                if i < len(snaps) - 1:
                    self._fill(hdc, self.brushes["div"], pad + int(56 * s),
                               y + row_h - 1, w - pad, y + row_h)
                y += row_h

        # 底部说明：解释刷新节奏，避免用户误以为鼠标卡住了
        self._text(hdc, "键盘每 10 分钟查询 · 鼠标实时接收", self.fonts["meta"],
                   C_FOOT, pad, h - footer_h, w - pad * 2, footer_h,
                   ui.DT_VCENTER | ui.DT_CENTER)

    def _paint_row(self, hdc, snap, y, w, row_h):
        s = self.scale
        pad = int(self.PAD * s)
        box = int(42 * s)
        tx = pad + box + int(14 * s)
        right = w - pad

        # 图标底衬
        by = y + int(10 * s)
        self._round_fill(hdc, self.brushes["iconbg"], pad, by, pad + box, by + box,
                         int(12 * s))
        isz = int(28 * s)
        ui.device_icon(hdc, snap["kind"], pad + (box - isz) // 2,
                       by + (box - isz) // 2, isz, bg=(0xF4, 0xF9, 0xFE))

        # 设备名
        self._text(hdc, snap["name"], self.fonts["name"], C_NAME,
                   tx, y + int(9 * s), right - tx, int(18 * s), ui.DT_VCENTER)

        # 「80% 电量」——大字左下对齐
        pct = snap["battery"]
        num = str(pct) if pct is not None else "--"
        color = C_TITLE if pct is not None else C_OFF
        py = y + int(27 * s)
        ph = int(35 * s)
        nw, _ = ui.text_size(hdc, num, self.fonts["pct"])
        self._text(hdc, num, self.fonts["pct"], color, tx, py, nw + int(3 * s), ph,
                   ui.DT_BOTTOM)
        sx = tx + nw
        sw, _ = ui.text_size(hdc, "%", self.fonts["sign"])
        self._text(hdc, "%", self.fonts["sign"], color, sx, py, sw + int(4 * s), ph,
                   ui.DT_BOTTOM)
        ux = sx + sw + int(5 * s)
        self._text(hdc, "电量", self.fonts["unit"], C_UNIT, ux, py,
                   max(right - ux, 10), ph, ui.DT_BOTTOM)

        # 胶囊进度条
        bar_y = y + int(66 * s)
        bar_h = int(10 * s)
        self._round_fill(hdc, self.brushes["track"], tx, bar_y, right, bar_y + bar_h,
                         bar_h / 2.0)
        if pct:
            fw = (right - tx) * min(max(pct, 2), 100) / 100.0
            self._round_fill(hdc, bar_color(snap["battery"], self.brushes), tx, bar_y,
                             max(tx + fw, tx + bar_h), bar_y + bar_h, bar_h / 2.0)

        # 更新时间 / 状态
        self._text(hdc, self._meta_line(snap), self.fonts["meta"], C_META,
                   tx, y + int(81 * s), right - tx, int(15 * s), ui.DT_VCENTER)

    def _meta_line(self, snap):
        bits = []
        if snap["charging"]:
            bits.append("充电中")
        if snap["online"] is False:
            bits.append("设备休眠")
        age = (time.time() - snap["updated_ts"]) if snap["updated_ts"] else None
        if snap["updated_ts"]:
            bits.append(rel_time(snap["updated_ts"]) + "更新")
            # 已经判定休眠就够说明了，再叠一句"可能已关机"是重复
            if (age is not None and age > STALE_SECONDS
                    and snap["online"] is not False):
                bits.append("可能已关机")
        elif snap["note"]:
            bits.append(snap["note"])
        if not bits:
            bits.append(snap["label"])
        return " · ".join(bits)

    # ---------------------------------------------------------- 运行
    def run(self):
        self.build()
        # 启动期建的对象（窗口类、字体、笔刷、图标、模块常量）之后基本不再变动。
        # freeze 之后 GC 不再逐轮扫描它们，阈值放宽则进一步减少回收次数 ——
        # 换来的是更低的 CPU 占用和更平的内存曲线（本项目几乎不产生循环引用）。
        try:
            gc.collect()
            gc.freeze()
            gc.set_threshold(5000, 50, 100)
        except Exception:
            pass
        ui.message_loop()


PID_FILE = os.path.join(os.environ.get("TEMP", "."), "2.4g_battery_tray.pid")


def main():
    ctypes.set_last_error(0)
    mutex = ui.kernel32.CreateMutexW(None, False, "2.4G_Battery_Tray_Mutex")
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        return
    try:
        with open(PID_FILE, "w", encoding="ascii") as f:
            f.write(str(os.getpid()))
    except OSError:
        pass
    app = BatteryTray()
    try:
        app.run()
    finally:
        try:
            app._remove_tray()
        except Exception:
            pass
        try:
            os.remove(PID_FILE)
        except OSError:
            pass


if __name__ == "__main__":
    main()
