# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec：onedir 双 exe（GUI + CLI）。

构建红线（见 plan/04 §九）：
  * datas **白名单**单一事实源 —— 只收运行必需数据，由 ``pflc.packaging.build_datas()``
    产生，spec 内**不手写数据路径**（``tests/test_gates.py`` 的 spec 文本门禁断言这点）；
  * **入口必须是 ``tools/entry_*.py``**，不能直接拿 ``src/pflc/*.py``：PyInstaller
    会把 Analysis 脚本当**顶层脚本**跑，包内相对导入（``from . import pipeline``）
    在冻结态直接崩。这条是 M5 实测踩中的（详见 ``tools/entry_cli.py``）；
  * 构建后三断言（禁区扫描 + 内嵌数据 sha256 对账 + 白名单外多余检测）
    由 ``tools/verify_frozen.py`` 执行；datas 报告（``_datas_report.json``）
    让"构建用了白名单而不是手写路径"可被事后核证；
  * 同一份 spec 兼容 PyInstaller 5.x（平铺布局）与 6.x（``_internal/`` 布局）。

构建命令（发布构建固定用装了 PyInstaller ≥6 的解释器通道）：
    py -3.12 -m PyInstaller --clean --noconfirm tools/pflc.spec
"""

import json
import os
import sys
from pathlib import Path

# spec 内的相对路径解析到 SPECPATH，**不解析到 CWD** —— 必须显式用 ROOT 绝对路径
ROOT = Path(SPECPATH).resolve().parent          # noqa: F821  (SPECPATH 由 PyInstaller 注入)
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from pflc.packaging import DATA_WHITELIST, build_datas, data_manifest  # noqa: E402

datas = build_datas(ROOT)

# 惰性导入的包对静态分析不可见，必须显式声明 hiddenimports。
#: 基准在 GUI 与 CLI 里都是函数体内惰性导入（`pipeline.run_bench` → `benchmark`）
_BENCH_HIDDEN = [
    "pflc.benchmark",
    "pflc.benchmark.cases",
    "pflc.benchmark.runner",
    "pflc.benchmark.rng",
]
#: GUI 包只在桌面包里内嵌。
#:
#: **CLI 发行包特意不带它**——这不是图省事，是产品口径：CLI 包对 `gui` 子命令
#: 走 exit 3 并提示"本发行包未内嵌该功能"（见 `cli.cmd_gui`）。把 PySide6
#: 打进 CLI 包会让这句提示变成死代码，白送 87 MB（实测差距），
#: "降级提示分流"这条设计决策也随之名存实亡。
_GUI_HIDDEN = ["pflc.gui", "pflc.gui.app"]

#: 数据报告：构建事实留档（哪个白名单版本、内嵌了哪些文件、逐份 sha256、
#: **这个树是哪种发行形态、该有哪些可执行文件**）。
#: verify_frozen 拿它与仓库现算清单对账 —— "spec 没手写数据路径"与
#: "验收知道该验哪个 exe"因此都可核证，而不是靠读 spec 源码或猜目录名。
def _datas_report(kind, exe_names):
    return {
        "data_whitelist": list(DATA_WHITELIST),
        "datas": [{"src_rel": os.path.relpath(src, str(ROOT)).replace("\\", "/"),
                   "dest": dest} for src, dest in datas],
        "sha256": {k: v for k, v in sorted(data_manifest(ROOT).items())},
        # 发行形态：两个树是**分开**的（CLI 包特意不含 PySide6），
        # 故"这个树该有哪些 exe"是构建事实，不能被验收脚本猜。
        "kind": kind,
        "exe_names": list(exe_names),
    }


def _write_datas_report(dist_name, kind, exe_names):
    """把数据报告写进 dist（verify_frozen 的核证输入）。

    用 PyInstaller 注入的 ``DISTPATH`` 而非硬编码 ``ROOT/dist`` ——
    传了 ``--distpath`` 时硬编码会把报告写错地方，verify 于是"找不到报告"，
    空报告与合规报告长得一样（又一道恒绿门）。
    """
    base = Path(DISTPATH).resolve()      # noqa: F821  (PyInstaller 注入)
    target = base / dist_name
    target.mkdir(parents=True, exist_ok=True)
    payload = _datas_report(kind, exe_names)
    with open(target / "_datas_report.json", "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return target


a_cli = Analysis(  # noqa: F821
    [str(ROOT / "tools" / "entry_cli.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=_BENCH_HIDDEN,
    hookspath=[],
    runtime_hooks=[],
    # 只排除纯可选重件；**不能排除文档化功能**（如报告导出的依赖）
    excludes=["tkinter", "test", "unittest", "PySide6", "shiboken6"],
    noarchive=False,
)
pyz_cli = PYZ(a_cli.pure)  # noqa: F821
exe_cli = EXE(  # noqa: F821
    pyz_cli, a_cli.scripts, [],
    exclude_binaries=True,
    name="pflc-cli",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,          # CLI 保留控制台：无 Python 机器的脚本化验证通路
)
coll_cli = COLLECT(  # noqa: F821
    exe_cli, a_cli.binaries, a_cli.datas,
    strip=False, upx=False, name="pflc-cli-dist",
)
_write_datas_report("pflc-cli-dist", "cli", ["pflc-cli"])

a_gui = Analysis(  # noqa: F821
    [str(ROOT / "tools" / "entry_gui.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=_BENCH_HIDDEN + _GUI_HIDDEN,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "test", "unittest"],
    noarchive=False,
)
pyz_gui = PYZ(a_gui.pure)  # noqa: F821
exe_gui = EXE(  # noqa: F821
    pyz_gui, a_gui.scripts, [],
    exclude_binaries=True,
    name="pflc",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,         # 窗口程序无 stdout —— 靠 --selftest 写文件回传验收
)
coll_gui = COLLECT(  # noqa: F821
    exe_gui, a_gui.binaries, a_gui.datas,
    strip=False, upx=False, name="pflc",
)
_write_datas_report("pflc", "gui", ["pflc"])
