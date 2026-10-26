"""开发验证：项目里所有 .vbs / .bat 的编码与语法体检

起因：Windows Script Host **只认 ANSI 和 UTF-16（带 BOM）**，不认 UTF-8。
      只要文件头是 EF BB BF（UTF-8 BOM），双击就报
          无效字符  行 1 字符 1  800A0408
      这个坑在 启动.vbs 和 开机自启 .vbs 上各踩过一次，所以做成脚本常驻。

规则：
  * .vbs 必须是 ①纯 ASCII、②ANSI(cp936)、③UTF-16 LE/BE 带 BOM 三者之一
  * 出现 EF BB BF 直接判失败
  * 不允许 CR CR LF（会让报错行号翻倍）
  * 每行引号必须成对（VBScript 规则，`""` 算转义引号）
  * .bat 只检查有没有 UTF-8 BOM（cmd 会把 BOM 当命令的一部分）

用法：python _dev_vbs_check.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _dev_autostart_test import vbscript_literal     # noqa: E402

OK, NG = "  [OK] ", "  [NG] "
WARN, FAILS = "  [!!] ", []

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STARTUP = os.path.join(os.environ.get("APPDATA", ""),
                       r"Microsoft\Windows\Start Menu\Programs\Startup")

UTF8_BOM = b"\xef\xbb\xbf"
UTF16_LE = b"\xff\xfe"
UTF16_BE = b"\xfe\xff"


def report(level, name, msg=""):
    print(level + name + ("" if not msg else f"  {msg}"))
    if level is NG:
        FAILS.append(name)


def decode_vbs(path, raw):
    """返回 (文本, 编码说明, 是否合规)"""
    if raw.startswith(UTF8_BOM):
        return None, "UTF-8 BOM", False
    if raw.startswith(UTF16_LE):
        return raw.decode("utf-16"), "UTF-16 LE + BOM", True
    if raw.startswith(UTF16_BE):
        return raw.decode("utf-16"), "UTF-16 BE + BOM", True
    if b"\x00" in raw[:64]:
        return None, "疑似 UTF-16 但缺 BOM", False
    try:
        return raw.decode("ascii"), "纯 ASCII", True
    except UnicodeDecodeError:
        pass
    try:
        return raw.decode("gbk"), "ANSI / cp936", True
    except UnicodeDecodeError:
        return None, "未知编码", False


def check_vbs(path):
    name = os.path.basename(path)
    if not os.path.exists(path):
        report(WARN, name, "不存在，跳过")
        return
    raw = open(path, "rb").read()
    text, enc, ok = decode_vbs(path, raw)
    if not ok:
        report(NG, f"{name} 编码", f"{enc} —— WSH 会报 800A0408 无效字符")
        return
    report(OK, f"{name} 编码", f"{enc}  {len(raw)} 字节")

    if b"\r\r\n" in raw:
        report(NG, f"{name} 换行", "含 CR CR LF，报错行号会翻倍")
    else:
        report(OK, f"{name} 换行", "CRLF 正常")

    bad = []
    for idx, line in enumerate(text.split("\n"), 1):
        line = line.rstrip("\r")
        lits = vbscript_literal(line)
        if any(v is None for _, v in lits):
            bad.append(idx)
    if bad:
        report(NG, f"{name} 引号", f"第 {bad} 行字符串未闭合")
    else:
        report(OK, f"{name} 引号", "每行都成对")


def check_bat(path):
    name = os.path.basename(path)
    raw = open(path, "rb").read()
    if raw.startswith(UTF8_BOM):
        report(NG, f"{name} 编码", "带 UTF-8 BOM，cmd 会把首行当命令的一部分")
        return
    try:
        raw.decode("ascii")
        report(OK, f"{name} 编码", f"纯 ASCII  {len(raw)} 字节")
    except UnicodeDecodeError:
        report(WARN, f"{name} 编码", "含非 ASCII（GBK 控制台下中文可能乱码，不影响执行）")


def main():
    print("=== 项目目录 ===")
    for fn in sorted(os.listdir(ROOT)):
        p = os.path.join(ROOT, fn)
        if fn.lower().endswith(".vbs"):
            check_vbs(p)
        elif fn.lower().endswith(".bat"):
            check_bat(p)

    print("=== 开机启动目录 ===")
    if os.path.isdir(STARTUP):
        vbs = [f for f in os.listdir(STARTUP) if f.lower().endswith(".vbs")]
        if not vbs:
            report(WARN, "Startup", "没有 .vbs（开机自启未开启）")
        for fn in sorted(vbs):
            check_vbs(os.path.join(STARTUP, fn))
    else:
        report(WARN, "Startup", "目录不存在")

    print()
    if FAILS:
        print(f"[FAIL] {len(FAILS)} 项不合格: {FAILS}")
        return 1
    print("[PASS] 全部合格")
    return 0


if __name__ == "__main__":
    sys.exit(main())
