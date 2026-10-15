"""数据定位（冻结态与源码态统一入口）。

优先级（**改动属"动了会打挂测试"的口径变更**，见 plan/07 K21）:

    1. 显式传入路径（测试与调用方指定）
    2. 环境变量 ``PFLC_DATA_DIR``
    3. 冻结态内嵌数据：
         PyInstaller 6.x  → ``<_MEIPASS>/data``
         PyInstaller 5.x  → ``<exe目录>/data``（平铺布局，无 _internal/）
         PyInstaller 6.x  → ``<exe目录>/_internal/data``
    4. 源码态：从本文件向上回溯到仓库根，取 ``<root>/data``
    5. 兜底：CWD 上溯

冻结态自检必须断言数据目录落在 **exe 目录内**——打包最常见的失效模式是
"数据没随包走、exe 回头读了开发机的仓库"，本地看着能跑，换台机器就废。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

ENV_DATA_DIR = "PFLC_DATA_DIR"


def is_frozen() -> bool:
    """是否运行在 PyInstaller 冻结态。"""
    return bool(getattr(sys, "frozen", False))


def exe_dir() -> Optional[Path]:
    """冻结态的 exe 所在目录；源码态返回 None。"""
    if not is_frozen():
        return None
    return Path(sys.executable).resolve().parent


def _meipass() -> Optional[Path]:
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) if base else None


def repo_root() -> Path:
    """源码态仓库根：从本文件向上回溯到含 pyproject.toml 的目录。"""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    # 冻结态或非常规布局：退回三层上溯
    return here.parents[3]


def data_dir(explicit: Optional[Path] = None) -> Path:
    """解析数据目录（见模块文档的优先级）。"""
    if explicit is not None:
        return Path(explicit).resolve()

    env = os.environ.get(ENV_DATA_DIR)
    if env:
        return Path(env).resolve()

    if is_frozen():
        meipass = _meipass()
        if meipass is not None:
            candidate = meipass / "data"
            if candidate.is_dir():
                return candidate
        ed = exe_dir()
        if ed is not None:
            # PyInstaller 5.x 平铺布局
            candidate = ed / "data"
            if candidate.is_dir():
                return candidate
            # PyInstaller 6.x onedir 布局
            candidate = ed / "_internal" / "data"
            if candidate.is_dir():
                return candidate

    candidate = repo_root() / "data"
    if candidate.is_dir():
        return candidate

    return Path.cwd() / "data"


def data_path_in_dist() -> Optional[bool]:
    """冻结态专属断言：数据目录是否落在 exe 目录之内。

    非冻结态返回 ``None``（不是 FAIL）——不让源码运行被误判为打包缺陷。
    """
    if not is_frozen():
        return None
    ed = exe_dir()
    if ed is None:
        return None
    try:
        d = data_dir()
    except Exception:
        return False
    try:
        return Path(os.path.commonpath([str(ed), str(d)])) == ed
    except ValueError:
        # 跨盘符：commonpath 抛 ValueError，说明数据根本不在 exe 目录下
        return False


def rules_dir(explicit: Optional[Path] = None) -> Path:
    return data_dir(explicit) / "rules"


def samples_dir(explicit: Optional[Path] = None) -> Path:
    return data_dir(explicit) / "samples"


def benchmark_dir(explicit: Optional[Path] = None) -> Path:
    return data_dir(explicit) / "benchmark"


def knowledge_raw_dir(explicit: Optional[Path] = None) -> Path:
    return data_dir(explicit) / "knowledge" / "raw"
