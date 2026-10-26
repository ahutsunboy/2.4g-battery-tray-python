"""开发验证：开机自启 .vbs 的生成是否正确

背景：2026-10-26 开机时报
    Windows Script Host  行 5 / 字符 60 / 语句未结束 / 800A0401
两个 bug 叠加：
  * sh.Run 后面的三组引号凑成奇数个 -> 字符串没闭合
  * 文本模式写文件把 CRLF 又翻译了一遍 -> CR CR LF，行号翻倍到 5

本脚本对 tray_app.autostart_script() 的产物做静态校验（不启动 wscript）：
  1. 二进制里不能出现 CR CR LF
  2. 每一行的引号必须成对（按 VBScript 规则把双写引号当一个转义引号）
  3. 带 BOM，能按 UTF-16 解回原文
  4. sh.Run 行的字符串值必须正好是 "pythonw.exe" "tray_app.py" 两个路径

用法：
    python _dev_autostart_test.py           仅校验
    python _dev_autostart_test.py --fix     校验并重写 Startup 里的自启文件
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tray_app as ta          # noqa: E402

OK, NG = "  [OK] ", "  [NG] "
fails = []


def check(name, got, want):
    ok = got == want
    print((OK if ok else NG) + f"{name}: {got!r}" + ("" if ok else f"  期望 {want!r}"))
    if not ok:
        fails.append(name)


def check_true(name, cond, detail=""):
    print((OK if cond else NG) + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def vbscript_literal(line):
    """按 VBScript 规则把一行的字符串字面量解析出来，返回 [(起, 值)]

    未闭合时返回的列表里带 None，表示这行语法错误。
    """
    out = []
    i, n = 0, len(line)
    while i < n:
        if line[i] == '"':
            start = i
            i += 1
            buf = []
            closed = False
            while i < n:
                if line[i] == '"':
                    if i + 1 < n and line[i + 1] == '"':
                        buf.append('"')
                        i += 2
                        continue
                    i += 1
                    closed = True
                    break
                buf.append(line[i])
                i += 1
            out.append((start, "".join(buf) if closed else None))
        else:
            i += 1
    return out


def main():
    run_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    blob = ta.autostart_script(run_dir)

    print("=== 1. 换行 / BOM ===")
    check_true("不含 \\r\\r\\n（旧版行号翻倍的根因）", b"\r\r\n" not in blob)
    check_true("以 UTF-16 BOM 开头", blob[:2] == b"\xff\xfe", blob[:4].hex())

    text = blob.decode("utf-16")
    print("=== 2. 解码后的原文 ===")
    for ln in text.split("\r\n"):
        print("   |" + ln)

    lines = [ln for ln in text.split("\r\n") if ln.strip()]
    check("行数", len(lines), 3)

    print("=== 3. 每行引号闭合 ===")
    for idx, ln in enumerate(lines, 1):
        lits = vbscript_literal(ln)
        bad = [v for _, v in lits if v is None]
        check_true(f"第 {idx} 行引号成对", not bad,
                   f"未闭合 -> {ln}")

    print("=== 4. sh.Run 的实参 ===")
    run_line = [ln for ln in lines if ln.startswith("sh.Run")][0]
    lits = vbscript_literal(run_line)
    check("sh.Run 只有一个字符串实参", len(lits), 1)
    if lits and lits[0][1] is not None:
        cmd = lits[0][1]
        # VBScript 里 \" 就是普通字符；executable 与脚本路径各被一对引号包住
        parts = cmd.split('" "')
        check("命令行切成 2 段", len(parts), 2)
        if len(parts) == 2:
            exe, target = parts[0].strip('"'), parts[1].strip('"')
            check("可执行文件存在", os.path.exists(exe), True)
            check("脚本存在", os.path.exists(target), True)
            check("可执行文件名", os.path.basename(exe).lower(), "pythonw.exe")
            check_true("路径含中文且完整", "电量托盘" in target, target)

    print("=== 5. CurrentDirectory ===")
    cd_line = [ln for ln in lines if ln.startswith("sh.CurrentDirectory")][0]
    lits = vbscript_literal(cd_line)
    check("目录与脚本同目录", os.path.normcase(lits[0][1] or ""),
          os.path.normcase(run_dir))

    if "--fix" in sys.argv:
        print("=== 6. 重写 Startup 自启文件 ===")
        dst = os.path.join(
            os.environ.get("APPDATA", ""),
            r"Microsoft\Windows\Start Menu\Programs\Startup\2.4G电量托盘.vbs")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as f:
            f.write(blob)
        size = os.path.getsize(dst)
        with open(dst, "rb") as f:
            back = f.read()
        check("重写后字节一致", back == blob, True)
        print(f"   -> {dst}  ({size} 字节)")

    print()
    if fails:
        print(f"[FAIL] {len(fails)} 项未通过: {fails}")
        return 1
    print("[PASS] 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
