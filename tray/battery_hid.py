"""
battery_hid.py — 2.4G 无线外设电量读取层（纯 ctypes，无第三方依赖）

支持：
  * Compx / 中颖方案键盘（VID 0x3554 等，0xFF02 通道，Report ID 0x13）
  * 迈从 MCHOSE 鼠标（VID 0x258A / PID 0x0138，0xFF02 通道状态帧 Report ID 0x09）

对外接口：
  enumerate_devices()        -> list[DeviceInfo]
  open_driver(DeviceInfo)    -> Driver 实例
"""

import ctypes
import ctypes.wintypes as wt
import json
import os
import time

# --------------------------------------------------------------- 设备友好名
#: 出厂内置的已知型号（VID, PID）→ 显示名
BUILTIN_NAMES = {
    (0x3554, 0xFA09): "狼蛛 FN75 键盘",
    (0x258A, 0x0138): "迈从 G3 鼠标",
}


def _load_user_names():
    """读取同目录下的 devices.json，形如 {"3554:FA09": "我的键盘"}"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "devices.json")
    out = {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for key, name in (data.get("names") or {}).items():
            try:
                vid, pid = key.split(":")
                out[(int(vid, 16), int(pid, 16))] = str(name)
            except ValueError:
                continue
    except FileNotFoundError:
        pass
    except Exception:
        pass
    return out


_USER_NAMES = None


def friendly_name(vid, pid, fallback):
    global _USER_NAMES
    if _USER_NAMES is None:
        _USER_NAMES = _load_user_names()
    return _USER_NAMES.get((vid, pid)) or BUILTIN_NAMES.get((vid, pid)) or fallback

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)
hid = ctypes.WinDLL("hid", use_last_error=True)
setupapi = ctypes.WinDLL("setupapi", use_last_error=True)

GUID_DEVINTERFACE_HID = "{4D1E55B2-F16F-11CF-88CB-001111000030}"

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
FILE_FLAG_OVERLAPPED = 0x40000000
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD),
                ("Data4", ctypes.c_ubyte * 8)]


class HIDD_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Size", wt.ULONG), ("VendorID", wt.USHORT),
                ("ProductID", wt.USHORT), ("VersionNumber", wt.USHORT)]


class HIDP_CAPS(ctypes.Structure):
    _fields_ = [("Usage", wt.USHORT), ("UsagePage", wt.USHORT),
                ("InputReportByteLength", wt.USHORT),
                ("OutputReportByteLength", wt.USHORT),
                ("FeatureReportByteLength", wt.USHORT),
                ("Reserved", wt.USHORT * 17),
                ("NumberLinkCollectionNodes", wt.USHORT),
                ("NumberInputButtonCaps", wt.USHORT), ("NumberInputValueCaps", wt.USHORT),
                ("NumberInputDataIndices", wt.USHORT),
                ("NumberOutputButtonCaps", wt.USHORT), ("NumberOutputValueCaps", wt.USHORT),
                ("NumberOutputDataIndices", wt.USHORT),
                ("NumberFeatureButtonCaps", wt.USHORT), ("NumberFeatureValueCaps", wt.USHORT),
                ("NumberFeatureDataIndices", wt.USHORT)]


class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("InterfaceClassGuid", GUID),
                ("Flags", wt.DWORD), ("Reserved", ctypes.c_void_p)]


class OVERLAPPED(ctypes.Structure):
    _fields_ = [("Internal", ctypes.c_void_p), ("InternalHigh", ctypes.c_void_p),
                ("Offset", wt.DWORD), ("OffsetHigh", wt.DWORD), ("hEvent", wt.HANDLE)]


# ---------------------------------------------------------------- 函数签名
setupapi.SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(GUID), wt.LPCWSTR, wt.HWND, wt.DWORD]
setupapi.SetupDiGetClassDevsW.restype = wt.HANDLE
setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
    wt.HANDLE, ctypes.c_void_p, ctypes.POINTER(GUID), wt.DWORD,
    ctypes.POINTER(SP_DEVICE_INTERFACE_DATA)]
setupapi.SetupDiEnumDeviceInterfaces.restype = wt.BOOL
setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
    wt.HANDLE, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA), ctypes.c_void_p,
    wt.DWORD, ctypes.POINTER(wt.DWORD), ctypes.c_void_p]
setupapi.SetupDiGetDeviceInterfaceDetailW.restype = wt.BOOL
setupapi.SetupDiDestroyDeviceInfoList.argtypes = [wt.HANDLE]

kernel32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p,
                                 wt.DWORD, wt.DWORD, wt.HANDLE]
kernel32.CreateFileW.restype = wt.HANDLE
kernel32.CloseHandle.argtypes = [wt.HANDLE]
kernel32.ReadFile.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.DWORD,
                              ctypes.POINTER(wt.DWORD), ctypes.POINTER(OVERLAPPED)]
kernel32.ReadFile.restype = wt.BOOL
kernel32.WriteFile.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.DWORD,
                               ctypes.POINTER(wt.DWORD), ctypes.POINTER(OVERLAPPED)]
kernel32.WriteFile.restype = wt.BOOL
kernel32.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
kernel32.WaitForSingleObject.restype = wt.DWORD
kernel32.GetOverlappedResult.argtypes = [wt.HANDLE, ctypes.POINTER(OVERLAPPED),
                                         ctypes.POINTER(wt.DWORD), wt.BOOL]
kernel32.GetOverlappedResult.restype = wt.BOOL
kernel32.CancelIoEx.argtypes = [wt.HANDLE, ctypes.POINTER(OVERLAPPED)]
kernel32.CreateEventW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.BOOL, wt.LPCWSTR]
kernel32.CreateEventW.restype = wt.HANDLE
kernel32.ResetEvent.argtypes = [wt.HANDLE]

hid.HidD_GetAttributes.argtypes = [wt.HANDLE, ctypes.POINTER(HIDD_ATTRIBUTES)]
hid.HidD_GetAttributes.restype = wt.BOOL
hid.HidD_GetPreparsedData.argtypes = [wt.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
hid.HidD_GetPreparsedData.restype = wt.BOOL
hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(HIDP_CAPS)]
hid.HidP_GetCaps.restype = ctypes.c_long
hid.HidD_GetProductString.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.ULONG]
hid.HidD_GetProductString.restype = wt.BOOL
hid.HidD_GetManufacturerString.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.ULONG]
hid.HidD_GetManufacturerString.restype = wt.BOOL
hid.HidD_GetFeature.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.ULONG]
hid.HidD_GetFeature.restype = wt.BOOL
hid.HidD_SetFeature.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.ULONG]
hid.HidD_SetFeature.restype = wt.BOOL

WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 258
ERROR_IO_PENDING = 997


# ---------------------------------------------------------------- 设备枚举
class DeviceInfo:
    __slots__ = ("path", "vid", "pid", "version", "usage_page", "usage",
                 "product", "manufacturer", "in_len", "out_len", "feat_len",
                 "collection", "iface")

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))

    @property
    def id(self):
        return f"{self.vid:04X}:{self.pid:04X}"

    def __repr__(self):
        return (f"<DeviceInfo {self.id} page=0x{self.usage_page:04X} "
                f"usage=0x{self.usage:04X} {self.product!r}>")


def _open_path(path, want_write=False):
    access = (GENERIC_READ | GENERIC_WRITE) if want_write else GENERIC_READ
    h = kernel32.CreateFileW(path, access, FILE_SHARE_READ | FILE_SHARE_WRITE,
                             None, OPEN_EXISTING, FILE_FLAG_OVERLAPPED, None)
    if h == INVALID_HANDLE_VALUE or not h:
        return None
    return h


def _hid_string(handle, fn, wchars=256):
    buf = ctypes.create_unicode_buffer(wchars)
    if fn(handle, buf, ctypes.sizeof(buf)):
        return buf.value
    return ""


def enumerate_devices():
    """枚举全部 HID 接口（同一物理设备的每个 collection 各一条）"""
    g = GUID()
    ctypes.windll.ole32.CLSIDFromString(ctypes.c_wchar_p(GUID_DEVINTERFACE_HID), ctypes.byref(g))
    hdev = setupapi.SetupDiGetClassDevsW(ctypes.byref(g), None, None, 0x12)  # PRESENT|DEVICEINTERFACE
    if hdev in (None, 0, INVALID_HANDLE_VALUE):
        return []

    out = []
    idx = 0
    while True:
        did = SP_DEVICE_INTERFACE_DATA()
        did.cbSize = ctypes.sizeof(did)
        if not setupapi.SetupDiEnumDeviceInterfaces(hdev, None, ctypes.byref(g), idx,
                                                    ctypes.byref(did)):
            break
        idx += 1
        req = wt.DWORD(0)
        setupapi.SetupDiGetDeviceInterfaceDetailW(hdev, ctypes.byref(did), None, 0,
                                                  ctypes.byref(req), None)
        if req.value == 0:
            continue
        buf = ctypes.create_string_buffer(req.value)
        ctypes.cast(buf, ctypes.POINTER(wt.DWORD))[0] = 8  # x64 下 cbSize
        if not setupapi.SetupDiGetDeviceInterfaceDetailW(hdev, ctypes.byref(did), buf,
                                                         req.value, ctypes.byref(req), None):
            continue
        path = ctypes.wstring_at(ctypes.addressof(buf) + 4)

        h = _open_path(path, want_write=False)
        if not h:
            h = kernel32.CreateFileW(path, 0, FILE_SHARE_READ | FILE_SHARE_WRITE,
                                     None, OPEN_EXISTING, FILE_FLAG_OVERLAPPED, None)
        if not h or h == INVALID_HANDLE_VALUE:
            continue
        try:
            attr = HIDD_ATTRIBUTES()
            attr.Size = ctypes.sizeof(attr)
            if not hid.HidD_GetAttributes(h, ctypes.byref(attr)):
                continue
            pp = ctypes.c_void_p()
            in_len = out_len = feat_len = 0
            upage = usage = 0
            if hid.HidD_GetPreparsedData(h, ctypes.byref(pp)):
                caps = HIDP_CAPS()
                hid.HidP_GetCaps(pp, ctypes.byref(caps))
                in_len = caps.InputReportByteLength
                out_len = caps.OutputReportByteLength
                feat_len = caps.FeatureReportByteLength
                upage = caps.UsagePage
                usage = caps.Usage
                hid.HidD_FreePreparsedData(pp)
            name = _hid_string(h, hid.HidD_GetProductString) or "未知设备"
            manu = _hid_string(h, hid.HidD_GetManufacturerString)
            coll = path.split("#")[-2] if "#" in path else ""
            out.append(DeviceInfo(path=path, vid=attr.VendorID, pid=attr.ProductID,
                                  version=attr.VersionNumber, usage_page=upage,
                                  usage=usage, product=name, manufacturer=manu,
                                  in_len=in_len, out_len=out_len, feat_len=feat_len,
                                  collection=coll, iface=_iface_of(coll)))
        finally:
            kernel32.CloseHandle(h)
    setupapi.SetupDiDestroyDeviceInfoList(hdev)
    return out


def _iface_of(collection):
    try:
        return int(collection.split("mi_")[1].split("&")[0], 16)
    except Exception:
        return 0


# ---------------------------------------------------------------- 句柄封装
class HidHandle:
    """带超时的 HID 读写封装（overlapped I/O）"""

    def __init__(self, path, want_write=False):
        self.path = path
        self.handle = _open_path(path, want_write=want_write)
        self.writable = self.handle is not None
        if self.handle is None:
            self.handle = kernel32.CreateFileW(path, GENERIC_READ,
                                               FILE_SHARE_READ | FILE_SHARE_WRITE,
                                               None, OPEN_EXISTING,
                                               FILE_FLAG_OVERLAPPED, None)
        if not self.handle or self.handle == INVALID_HANDLE_VALUE:
            raise OSError(f"无法打开 HID 通道: {path}")
        self._event = kernel32.CreateEventW(None, True, False, None)
        self._buf = (ctypes.c_ubyte * 4096)()
        self._ov = OVERLAPPED()
        self._ov.hEvent = self._event

    @property
    def valid(self):
        return bool(self.handle) and self.handle != INVALID_HANDLE_VALUE

    def read(self, size, timeout_ms=200):
        """返回包含 Report ID 的原始字节，超时返回 None"""
        if not self.valid:
            return None
        kernel32.ResetEvent(self._event)
        nread = wt.DWORD(0)
        ok = kernel32.ReadFile(self.handle, self._buf, min(size, 4096),
                               ctypes.byref(nread), ctypes.byref(self._ov))
        if ok:
            return bytes(self._buf[:nread.value])
        if ctypes.get_last_error() != ERROR_IO_PENDING:
            return None
        rc = kernel32.WaitForSingleObject(self._event, timeout_ms)
        if rc != WAIT_OBJECT_0:
            kernel32.CancelIoEx(self.handle, ctypes.byref(self._ov))
            kernel32.WaitForSingleObject(self._event, 50)
            return None
        if not kernel32.GetOverlappedResult(self.handle, ctypes.byref(self._ov),
                                            ctypes.byref(nread), False):
            return None
        return bytes(self._buf[:nread.value])

    def write(self, data):
        """data[0] 必须是 Report ID"""
        kernel32.ResetEvent(self._event)
        buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        written = wt.DWORD(0)
        ok = kernel32.WriteFile(self.handle, buf, len(data),
                                ctypes.byref(written), ctypes.byref(self._ov))
        if not ok:
            if ctypes.get_last_error() != ERROR_IO_PENDING:
                return -1
            rc = kernel32.WaitForSingleObject(self._event, 500)
            if rc != WAIT_OBJECT_0:
                kernel32.CancelIoEx(self.handle, ctypes.byref(self._ov))
                return -1
            kernel32.GetOverlappedResult(self.handle, ctypes.byref(self._ov),
                                         ctypes.byref(written), False)
        return written.value

    def get_feature(self, report_id, size):
        buf = (ctypes.c_ubyte * size)()
        buf[0] = report_id
        if hid.HidD_GetFeature(self.handle, buf, size):
            return bytes(buf)
        return None

    def set_feature(self, data):
        buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        return bool(hid.HidD_SetFeature(self.handle, buf, len(data)))

    def close(self):
        if self.valid:
            kernel32.CloseHandle(self.handle)
            self.handle = None
        if self._event:
            kernel32.CloseHandle(self._event)
            self._event = None


# ---------------------------------------------------------------- 读数模型
class Reading:
    __slots__ = ("battery", "charging", "online", "raw", "note", "fresh")

    def __init__(self, battery=None, charging=None, online=None, raw="", note="",
                 fresh=True):
        self.battery = battery
        self.charging = charging
        self.online = online
        self.raw = raw
        self.note = note
        # False 表示这是上一次读到的缓存值，不是设备刚发来的新数据。
        # 上层据此决定要不要刷新“更新时间”，否则鼠标每 3 秒返回一次缓存，
        # 时间戳会被一直顶到当前时刻，永远显示“刚刚”。
        self.fresh = fresh

    def __repr__(self):
        return (f"<Reading {self.battery}% charging={self.charging} "
                f"online={self.online} raw={self.raw!r}>")


def _hex(data):
    return data.hex(" ").upper()


# ---------------------------------------------------------------- 驱动实现
class DriverBase:
    """驱动基类：每个驱动负责一类接收器"""
    key = "base"
    family = ""
    label = ""

    #: [(vid, pid)] 白名单；空表示按 usage page 特征匹配
    ids = []
    #: 需要打开的 usage page
    usage_page = None

    def __init__(self, info):
        self.info = info
        self.name = friendly_name(info.vid, info.pid, info.product or "2.4G 设备")
        self.handle = None
        self._last = None
        self._online = None

    # -- 生命周期
    def open(self):
        self.handle = HidHandle(self.info.path, want_write=self.needs_write)
        return True

    needs_write = False

    def close(self):
        if self.handle:
            self.handle.close()
            self.handle = None

    def poll(self, timeout_ms=1500):
        raise NotImplementedError

    # -- 工具
    def _emit(self, reading):
        if reading and reading.battery is not None:
            self._last = reading
        return reading


class CompxKeyboardDriver(DriverBase):
    """
    Compx / 中颖方案（0xFF02 通道，Report ID 0x13，20 字节）
    发送 13 05 01 00*16 19 → 回包 13 05 01..（握手）+ 13 0A 01..（状态）
    状态包 payload[6] = 电量百分比, payload[7] = 1 表示 2.4G 在线
    """
    key = "compx-kbd"
    family = "Compx/中颖"
    label = "Compx 键盘"
    ids = [(0x3554, 0xFA09)]
    usage_page = 0xFF02
    needs_write = True

    QUERY = bytes([0x13, 0x05, 0x01] + [0] * 16 + [0x19])

    def poll(self, timeout_ms=1500):
        h = self.handle
        if not h:
            return None
        deadline = time.time() + timeout_ms / 1000.0
        next_write = 0.0
        best = None
        while time.time() < deadline:
            if time.time() >= next_write:
                h.write(self.QUERY)
                next_write = time.time() + 0.35
            data = h.read(20, 120)
            if not data:
                continue
            if len(data) >= 8 and data[0] == 0x13 and data[1] == 0x0A:
                online = data[7] == 1
                self._online = online
                if not online:
                    best = Reading(None, False, False, _hex(data), "设备休眠/离线")
                    continue
                return self._emit(Reading(
                    battery=data[6], charging=self._guess_charging(data),
                    online=True, raw=_hex(data)))
            elif best is None:
                best = Reading(None, None, self._online, _hex(data), "等待电量包")
        if best and best.battery is None:
            best.online = self._online
        return best

    @staticmethod
    def _guess_charging(data):
        # 该协议未在状态包中暴露充电标志，保留 None
        return None


class MchoseDongleDriver(DriverBase):
    """
    迈从 MCHOSE（VID 0x258A）2.4G 接收器
    0xFF02 通道会主动推送状态帧（Report ID 0x09）：
        09 0A 05 <电量> 00 00 00 00     ← 电量帧
        09 0A 02 00 00 00 00 00     ← 其它状态帧
    """
    key = "mchose"
    family = "MCHOSE"
    label = "迈从鼠标"
    ids = [(0x258A, 0x0138)]
    usage_page = 0xFF02
    needs_write = False

    def poll(self, timeout_ms=8000):
        """阻塞等一帧。

        这个接收器没有可用的查询指令，只能被动等它自己播报。所以这里
        直接在一次 ReadFile 上睡到有帧为止（内核等待，不占 CPU），
        帧一到立刻返回 → 上层看到的就是"实时"。
        """
        h = self.handle
        if not h:
            return None
        deadline = time.time() + timeout_ms / 1000.0
        other_raw = ""
        while True:
            remain = int((deadline - time.time()) * 1000)
            if remain <= 0:
                break
            data = h.read(8, remain)
            if not data or len(data) < 4:
                break               # 等超时或句柄失效：这一轮没有新帧
            if data[0] == 0x09 and data[1] == 0x0A:
                if data[2] == 0x05:
                    value = data[3]
                    if 0 <= value <= 100:
                        self._online = True
                        return self._emit(Reading(value, None, True, _hex(data)))
                else:
                    other_raw = _hex(data)
        if self._last:
            return Reading(self._last.battery, self._last.charging, self._online,
                           other_raw or self._last.raw, "缓存", fresh=False)
        return Reading(None, None, None, other_raw,
                       "等待状态帧 · 动一下鼠标唤醒")


class GenericCompxDriver(CompxKeyboardDriver):
    """兜底：任何具备 0xFF02 + 20 字节输出报告的设备都按 Compx 协议试一次"""
    key = "compx-generic"
    ids = []
    label = "Compx 兼容设备(试探)"

    @classmethod
    def matches(cls, info):
        return (info.usage_page == 0xFF02 and info.out_len == 20
                and (info.vid, info.pid) not in CompxKeyboardDriver.ids)


DRIVERS = [CompxKeyboardDriver, MchoseDongleDriver]


def find_drivers():
    """
    返回 [(driver_instance_or_None, info)]，已按 usage page 去重
    每个物理设备只保留一条最合适的通道
    """
    devices = enumerate_devices()
    result = []
    used = set()
    for info in devices:
        for cls in DRIVERS:
            if (info.vid, info.pid) in cls.ids and info.usage_page == cls.usage_page:
                if (cls.key, info.vid, info.pid) in used:
                    continue
                used.add((cls.key, info.vid, info.pid))
                d = cls(info)
                try:
                    d.open()
                    result.append(d)
                except OSError:
                    pass
    # 兜底试探
    if not result:
        for info in devices:
            if GenericCompxDriver.matches(info):
                d = GenericCompxDriver(info)
                try:
                    d.open()
                    result.append(d)
                    break
                except OSError:
                    pass
    return result


if __name__ == "__main__":
    print("枚举 HID 接口...")
    for info in enumerate_devices():
        if info.usage_page >= 0xFF00 or info.vid in (0x258A, 0x3554):
            print(" ", info)
    print("\n启动驱动...")
    for drv in find_drivers():
        print(f"  {drv.label}  {drv.name}  ({drv.info.id})")
        for _ in range(2):
            print("    ->", drv.poll(2000))
        drv.close()
