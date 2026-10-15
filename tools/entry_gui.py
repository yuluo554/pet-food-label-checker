#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PyInstaller 包内入口：GUI（窗口程序）。

**为什么需要这个文件**：``src/pflc/gui/app.py`` 里有 ``from .. import pipeline``，
把它直接当顶层脚本交给 PyInstaller，冻结后一启动就
``ImportError: attempted relative import with no known parent package``。
本文件只做一件事：以**绝对导入**进入包内 ``main``，让包结构在冻结态依然成立。

两条脚本化验收通路（窗口程序 ``console=False``，没有 stdout，只能靠写文件）：

* ``selftest --out <file>`` —— 冻结态数据自检，**与 CLI 同一实现**（转交
  ``pflc.cli``）。这样"数据有没有随包走"在桌面包上也能被机器核验；
* ``--gui-selftest <file>`` —— **存活探针**：offscreen 下真构主窗口，
  回传页签数与标题。"exe 起得来且窗口真的建出来了"因此可判定，
  而不是靠人眼点一下。

**offscreen 只在探针模式置位**：正常启动必须用平台默认窗口后端，否则双击
打开的是"渲染到离屏缓冲、屏幕上什么都没有"的隐形窗口——探针可用性与真实
可用性是两件事，不能共用一个默认值。
"""

import os
import sys

#: 探针模式的开关。判据只读 argv，**不导入 Qt**——窗口后端必须在首次导入
#: PySide6 前决定，导入之后再设就晚了。
_GUI_SELFTEST_FLAG = "--gui-selftest"


def _cjk_font_env() -> None:
    """窗口后端相关的环境准备（保留默认后端，仅确保字体可寻）。"""
    # 此处刻意不设置 QT_QPA_PLATFORM：真实桌面启动要用平台默认后端。
    # 字体加载由 pflc.gui.app.load_cjk_font() 按 WINDIR/SystemRoot 推导。
    return None


if os.environ.get("QT_QPA_PLATFORM") is None and _GUI_SELFTEST_FLAG in sys.argv[1:]:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

from pflc.gui.app import build_app  # noqa: E402
from pflc.gui.app import main as gui_main  # noqa: E402


def _gui_alive(out_path) -> int:
    """存活探针：构窗 + 回传结论。"""
    import json

    app, window = build_app([])
    tabs = window._tabs
    payload = {
        "gui_alive": True,
        "tab_count": tabs.count(),
        "tabs": [tabs.tabText(i) for i in range(tabs.count())],
        "window_title": window.window.windowTitle(),
    }
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == [_GUI_SELFTEST_FLAG]:
        if len(argv) < 2:
            print("用法：--gui-selftest <结论文件>", file=sys.stderr)
            return 2
        return _gui_alive(argv[1])
    if argv[:1] == ["selftest"]:
        # 冻结态数据自检：与 CLI 共用同一实现，不在界面层重写一份
        from pflc.cli import main as cli_main

        return int(cli_main(argv))
    _cjk_font_env()
    return int(gui_main(argv))


if __name__ == "__main__":
    sys.exit(main())
