"""开发验证：低电量提醒的判定逻辑 / 文案 / 合并 / 截断

不依赖真实设备、不弹窗、也不需要主程序在跑。
用法：python _dev_notify_test.py
"""
import ctypes
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tray_app as ta          # noqa: E402

OK, NG = "  [OK] ", "  [NG] "
fails = []


def check(name, got, want):
    ok = got == want
    print((OK if ok else NG) + f"{name}: {got!r}" + ("" if ok else f"  期望 {want!r}"))
    if not ok:
        fails.append(name)


class Cfg:
    """冒充 Settings，只提供 gate 需要的三个字段"""

    def __init__(self, threshold=20, rearm=25, enabled=True):
        self.threshold, self.rearm, self.enabled = threshold, rearm, enabled


class R:
    """冒充 battery_hid.Reading"""

    def __init__(self, battery, online=True, fresh=True, charging=None):
        self.battery = battery
        self.online = online
        self.fresh = fresh
        self.charging = charging

    def __repr__(self):
        return (f"R({self.battery},{'on' if self.online else 'off'},"
                f"{'fresh' if self.fresh else 'cache'}"
                f"{',chg' if self.charging else ''})")


def run(seq, cfg=None):
    gate = ta.LowBatteryGate(cfg or Cfg())
    return [gate.feed(r) for r in seq], gate


def F(*xs):
    return list(xs)


def main():
    print("== 状态机 ==")
    seq, _ = run([R(100), R(46), R(24)])
    check("A 迟滞带内不上膛", seq, F(0, 0, 0))

    seq, _ = run([R(24), R(21), R(20), R(19), R(18)])
    check("B 只在第一次跌破时报", seq, F(0, 0, 1, 0, 0))

    seq, _ = run([R(20), R(19), R(22), R(21), R(19)])
    check("C 19<->20 抖动不重弹（迟滞核心）", seq, F(1, 0, 0, 0, 0))

    seq, gate = run([R(19), R(25), R(24), R(20)])
    check("D 25 重新武装、24 在带内、再跌破才报", seq, F(1, 0, 0, 1))

    seq, gate = run([R(10, fresh=False)])
    check("E1 缓存复述不触发", seq, F(0))
    check("E2 缓存复述也不上膛", gate.notified, False)
    seq, gate = run([R(10, fresh=False), R(9)])
    check("E3 之后真帧仍能报", seq, F(0, 1))

    seq, _ = run([R(None, online=False), R(None, online=None)])
    check("F 离线/未读到帧", seq, F(0, 0))
    seq, _ = run([R(10, online=False)])
    check("G 有电量但 online=False 也要挡住", seq, F(0))

    seq, _ = run([R(15, charging=True), R(15, charging=None)])
    check("H 充电时不打扰，拔电后仍报", seq, F(0, 1))

    seq, _ = run([R(19), R(30, fresh=False), R(18)])
    check("I 重新武装只认 fresh 帧", seq, F(1, 0, 0))

    cfg = Cfg(enabled=False)
    gate = ta.LowBatteryGate(cfg)
    seq = [gate.feed(r) for r in (R(15),)]
    cfg.enabled = True
    seq += [gate.feed(r) for r in (R(20),)]
    check("J1 关闭期间不打扰但记账", seq, F(0, 0))
    seq = [gate.feed(r) for r in (R(30), R(18))]
    check("J2 开启后不补弹，下一次跌破才报", seq, F(0, 1))

    seq, _ = run([R(21), R(20)])
    check("K1 边界 21 不报 / 20 报", seq, F(0, 1))
    seq, _ = run([R(25), R(24)])
    check("K2 25 算武装 / 24 在带内不报", seq, F(0, 0))

    print("== settings.json ==")
    tmpdir = tempfile.mkdtemp(prefix="bt_cfg_")
    p = os.path.join(tmpdir, "settings.json")
    s = ta.Settings(path=p)
    check("L1 文件不存在时用默认值", (s.enabled, s.threshold, s.rearm),
          (True, 20, 25))

    with open(p, "w", encoding="utf-8") as f:
        json.dump({"low_battery": {"threshold": 120, "rearm": 3}}, f)
    s = ta.Settings(path=p)
    check("L2 越界钳制 + 强制 rearm>threshold", (s.threshold, s.rearm), (95, 96))

    with open(p, "w", encoding="utf-8") as f:
        f.write("{")                     # 坏 JSON
    s = ta.Settings(path=p)
    check("L3 坏 JSON 退回默认值", (s.enabled, s.threshold), (True, 20))

    with open(p, "w", encoding="utf-8") as f:
        json.dump({"low_battery": {"enabled": False, "threshold": 15,
                                   "rearm": 18}, "未来字段": [1, 2]}, f,
                  ensure_ascii=False)
    s = ta.Settings(path=p)
    check("L4 正常读取", (s.enabled, s.threshold, s.rearm), (False, 15, 18))
    s.enabled = True
    check("L5 保存成功", s.save(), True)
    with open(p, encoding="utf-8") as f:
        back = json.load(f)
    check("L6 保存时保留未知字段", back.get("未来字段"), [1, 2])
    check("L7 保存后回读一致",
          (back["low_battery"]["enabled"], back["low_battery"]["threshold"]),
          (True, 15))

    print("== 文案与合并 ==")
    long_name = "超级无敌长的设备名称" * 40           # 400 字符
    title, info = ta.BatteryTray._toast_text([(long_name, 8)])
    check("M1 标题长度", len(title) <= 63, True)
    check("M2 正文长度", len(info) <= 255, True)
    nid = ta.NOTIFYICONDATAW()
    try:
        nid.szInfoTitle = title
        nid.szInfo = info
        assigned = True
    except Exception:
        assigned = False
    check("M3 赋值不抛异常（NUL 结尾有余量）", assigned, True)

    title, info = ta.BatteryTray._toast_text(
        [("狼蛛 FN75 键盘", 18), ("迈从 G3 鼠标", 15), ("第三方鼠标", 9)])
    check("M4 多于两台时点名前两台 + 计数", ("9%" in info and "等 3 台" in info), True)
    check("M5 标题", title, "设备电量不足")

    title, info = ta.BatteryTray._toast_text([("甲", 30), ("乙", 12)])
    check("M6 电量低的排在前面", info.find("乙") < info.find("甲"), True)

    print("== _flush_low_alerts 合并 ==")
    app = ta.BatteryTray()          # 不 build()，不开窗口
    app.hwnd_tray, app.tray_added = 1, True
    app._log = lambda *a: None
    app._refresh_tray = lambda **k: None
    sent = []
    ta._shell_notify = lambda cmd, nid: sent.append(
        (cmd, nid.szInfoTitle, nid.szInfo, nid.uFlags, nid.uVersion)) or True

    class FakeSt:
        def __init__(self, key, name, pct):
            self.key, self.display, self.battery = key, name, pct

    app.states = [FakeSt("a", "狼蛛 FN75 键盘", 18),
                  FakeSt("b", "迈从 G3 鼠标", 15)]
    app._pending_low = ["a", "b"]
    app._flush_low_alerts()
    check("N1 两台设备合并成一条", len(sent), 1)
    check("N2 状态用 NIM_MODIFY", sent[0][0], ta.NIM_MODIFY)
    check("N3 只带 NIF_INFO", sent[0][3], ta.NIF_INFO)
    check("N4 uVersion 必须是 0", sent[0][4], 0)
    check("N5 正文含两台电量", ("15%" in sent[0][2] and "18%" in sent[0][2]), True)
    check("N6 drain 后清空", app._pending_low, [])

    sent.clear()
    app._pending_low = ["已经拔掉的设备"]
    app._flush_low_alerts()
    check("N7 队列里的设备已消失：不发也不崩", (len(sent), app._pending_low), (0, []))

    sent.clear()
    app._pending_low = []
    app._flush_low_alerts()
    check("N8 空队列什么都不做", len(sent), 0)

    print("== 真实链路（仅当主程序在跑） ==")
    u = ctypes.WinDLL("user32", use_last_error=True)
    u.FindWindowW.restype = ctypes.c_void_p
    u.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
    u.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                               ctypes.c_size_t, ctypes.c_size_t]
    u.IsWindowVisible.argtypes = [ctypes.c_void_p]
    host = u.FindWindowW("BatteryTrayHost", None)
    panel = u.FindWindowW("BatteryTrayPanel", None)
    if not host or not panel:
        print("  [跳过] 主程序没在运行")
    else:
        for _ in range(3):                     # 先确保面板是收起的
            u.PostMessageW(panel, 0x0100, 0x1B, 0)
            time.sleep(0.2)
        check("O0 起点：面板已收起", bool(u.IsWindowVisible(panel)), False)
        u.PostMessageW(host, 0x8001, 0, 0x0405)   # 模拟用户点了通知本体
        time.sleep(0.6)
        check("O1 点通知 → 弹出卡片", bool(u.IsWindowVisible(panel)), True)
        u.PostMessageW(panel, 0x0100, 0x1B, 0)
        time.sleep(0.4)
        check("O2 Esc 收起（原有行为未回退）", bool(u.IsWindowVisible(panel)), False)

    print()
    if fails:
        print(f"失败 {len(fails)} 项: {fails}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
