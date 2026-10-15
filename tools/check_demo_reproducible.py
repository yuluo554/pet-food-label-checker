#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""演示物料可复现性守门：两次独立生成 + 与入仓留档逐份对账。

三件事一起验（缺一件都不足以说"素材可复现"）：

  1. **两次独立生成全部文件 sha256 逐个一致** —— 生成器无时间戳/无随机；
  2. **与入仓留档（``docs/DIST-sha256-M5.txt``）一致** —— 留档没跟物料脱节；
  3. **素材不含本机路径** —— 脱敏审计看不到 PNG（二进制豁免），
     故这条只能在产素材这一步守（生成器内部也有一道硬断言）。

在**临时目录**里生成，不覆盖入仓物料——守门脚本不该有写坏仓库的副作用。

用法：
    py -X utf8 tools/check_demo_reproducible.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import sys
import tempfile
from pathlib import Path
from typing import Dict, List

for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    if _stream is not None:
        _enc = (getattr(_stream, "encoding", None) or "").lower()
        if _enc not in ("utf-8", "utf8"):
            _reconf = getattr(_stream, "reconfigure", None)
            if _reconf is not None:
                try:
                    _reconf(encoding="utf-8")
                except (ValueError, OSError):
                    pass

# offscreen 必须在**首次导入 PySide6 前**设置
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

OK_MARKER = "DEMO_ASSETS_OK"

#: 入仓留档（当前有效版本）
LEDGER = ROOT / "docs" / "DIST-sha256-M5.txt"


def _digests(directory: Path) -> Dict[str, str]:
    """生成器产出的素材哈希（``tab-*.png`` + ``demo.gif``）。

    只取这两类：目录里还有 ``README.md``（说明文档，非生成物）——
    "把目录里所有文件都比一遍"会让加个说明文件就报"留档不符"。
    """
    out: Dict[str, str] = {}
    for path in sorted(Path(directory).iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in (".png", ".gif"):
            continue
        out[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def _load_generator():
    spec = importlib.util.spec_from_file_location(
        "make_demo_assets_probe_cli", ROOT / "tools" / "make_demo_assets.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["make_demo_assets_probe_cli"] = module
    spec.loader.exec_module(module)
    return module


def _parse_ledger(path: Path) -> Dict[str, str]:
    declared: Dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        declared[parts[-1]] = parts[0]
    return declared


def main() -> int:
    problems: List[str] = []
    try:
        generator = _load_generator()
    except ImportError as exc:
        print("缺少 GUI 依赖（PySide6）：%s" % exc, file=sys.stderr)
        return 3

    with tempfile.TemporaryDirectory(prefix="pflc-demo-") as tmp:
        first = Path(tmp) / "run1"
        second = Path(tmp) / "run2"
        for target in (first, second):
            try:
                generator.capture(target)
            except ImportError as exc:
                print("缺少 GUI 依赖（PySide6）：%s" % exc, file=sys.stderr)
                return 3
            try:
                generator.make_gif(sorted(target.glob("tab-*.png")),
                                   target / "demo.gif")
            except ImportError:
                problems.append("未安装 Pillow，GIF 未产出（GIF 合成是 DoD 的一部分）")

        digests_a = _digests(first)
        digests_b = _digests(second)
        if not digests_a:
            problems.append("生成器没产出任何文件 = 本门空转")
        if digests_a != digests_b:
            differing = sorted(k for k in set(digests_a) | set(digests_b)
                               if digests_a.get(k) != digests_b.get(k))
            problems.append("两次生成不一致（生成器有非确定性输入）：%s" % differing)

        if LEDGER.is_file():
            declared = _parse_ledger(LEDGER)
            if not declared:
                problems.append("留档里没有解析出哈希 = 判据空转")
            if sorted(declared) != sorted(digests_a):
                problems.append(
                    "留档与生成物料不符：留档 %s / 生成 %s"
                    % (sorted(declared), sorted(digests_a)))
            mismatched = [n for n in digests_a
                          if n in declared and declared[n] != digests_a[n]]
            if mismatched:
                problems.append(
                    "留档哈希与生成物料不符（物料变了没更新留档，或生成器变了）：%s"
                    % mismatched)
        else:
            problems.append("缺入仓留档：%s" % LEDGER)

    if problems:
        for item in problems:
            print("问题：%s" % item, file=sys.stderr)
        return 1
    print(OK_MARKER)
    return 0


if __name__ == "__main__":
    sys.exit(main())
