# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec：onedir 双 exe（GUI + CLI）。

构建红线（见 plan/04 §九）：
  * datas **白名单**单一事实源 —— 只收运行必需数据，由 ``pflc.packaging.build_datas()``
    产生，spec 内**不手写数据路径**（spec 文本守门测试断言这点）；
  * 构建后三断言（禁区扫描 + 内嵌数据 sha256 对账 + 白名单外多余检测）
    由 ``tools/verify_frozen.py`` 执行；
  * 同一份 spec 兼容 PyInstaller 5.x（平铺布局）与 6.x（``_internal/`` 布局）。

构建命令（发布构建固定用装了 PyInstaller ≥6 的解释器通道）：
    py -3.12 -m PyInstaller --clean --noconfirm tools/pflc.spec
"""

import os
import sys
from pathlib import Path

# spec 内的相对路径解析到 SPECPATH，**不解析到 CWD** —— 必须显式用 ROOT 绝对路径
ROOT = Path(SPECPATH).resolve().parent          # noqa: F821  (SPECPATH 由 PyInstaller 注入)
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from pflc.packaging import build_datas  # noqa: E402

datas = build_datas(ROOT)

# 惰性导入的包对静态分析不可见，必须显式声明 hiddenimports
hiddenimports = [
    "pflc.gui",
    "pflc.gui.app",
    "pflc.benchmark",
    "pflc.benchmark.cases",
    "pflc.benchmark.runner",
    "pflc.benchmark.rng",
]

a_cli = Analysis(
    [str(SRC / "pflc" / "cli.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # 只排除纯可选重件；**不能排除文档化功能**（如报告导出的依赖）
    excludes=["tkinter", "test", "unittest"],
    noarchive=False,
)
pyz_cli = PYZ(a_cli.pure)  # noqa: F821
exe_cli = EXE(
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

a_gui = Analysis(
    [str(SRC / "pflc" / "gui" / "app.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "test", "unittest"],
    noarchive=False,
)
pyz_gui = PYZ(a_gui.pure)  # noqa: F821
exe_gui = EXE(
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
