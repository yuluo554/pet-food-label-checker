#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PyInstaller 包内入口：CLI。

**为什么需要这个文件**：直接把 ``src/pflc/cli.py`` 交给 PyInstaller 当
Analysis 脚本会**打断包语义**——那时 ``cli.py`` 是被当**顶层脚本**执行的，
它的包内相对导入（``from . import pipeline``）没有父包可挂，冻结后一启动就
``ImportError: attempted relative import with no known parent package``。
本文件只做一件事：以**绝对导入**进入包内 ``main``，让包结构在冻结态依然成立。

源码态等价通路是 ``python -m pflc.cli``（见 ``pyproject.toml`` 的 console script）。
"""

import sys

from pflc.cli import main

if __name__ == "__main__":
    sys.exit(main())
