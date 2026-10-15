#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""冻结产物验收：构建后三断言 + 冻结态自检驱动。

三条断言（互相独立，改一处口径必同步另两处，见 plan/04 §九）：
  1. dist 全树禁区成分扫描；
  2. 内嵌数据与仓库逐份 sha256 对账；
  3. 白名单外多余数据目录检测。

用法：
    py -X utf8 tools/verify_frozen.py --dist dist/pflc
    py -X utf8 tools/verify_frozen.py --dist dist/pflc --selftest
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List

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

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from pflc.packaging import (  # noqa: E402
    assert_data_matches,
    assert_no_extra_data,
    assert_no_forbidden,
)

OK_MARKER = "VERIFY_FROZEN_OK"


def check_dist(root: Path, dist: Path) -> List[str]:
    problems: List[str] = []
    problems.extend(assert_no_forbidden(root, dist))
    problems.extend(assert_data_matches(root, dist))
    problems.extend(assert_no_extra_data(root, dist))
    return problems


def run_selftest(root: Path, dist: Path) -> List[str]:
    """在**中立目录**驱动冻结态 ``--selftest``。

    别在仓库树内跑——CWD 上溯会命中仓库 data，"内嵌数据"验了个寂寞。
    环境用 ``env -i`` 剥离 PATH 类干扰。
    """
    problems: List[str] = []
    # 找 CLI exe（onedir 布局：dist/<name>/<name>.exe）
    candidates = list(dist.rglob("pflc-cli.exe")) + list(dist.rglob("pflc-cli"))
    if not candidates:
        problems.append("dist 内未找到 pflc-cli 可执行文件")
        return problems
    exe = candidates[0]

    with tempfile.TemporaryDirectory(prefix="pflc-verify-") as tmp:
        out_path = Path(tmp) / "selftest.json"
        env = {k: v for k, v in os.environ.items()
               if k.upper() in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH",
                                "SYSTEMDRIVE", "COMSPEC", "PATHEXT")}
        try:
            proc = subprocess.run(
                [str(exe), "selftest", "--out", str(out_path)],
                cwd=tmp,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding="utf-8",
                errors="replace",
                env=env,
                timeout=180,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            problems.append("冻结态自检无法执行：%s" % exc)
            return problems

        if not out_path.is_file():
            problems.append("冻结态自检未回传结论文件（exit=%d）" % proc.returncode)
            return problems

        try:
            payload = json.loads(out_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            problems.append("自检结论无法解析：%s" % exc)
            return problems

        if not payload.get("frozen"):
            problems.append("自检报告 frozen 标记为假 —— 未在冻结态运行")
        if payload.get("checks", {}).get("data_dir_in_dist") is not True:
            problems.append(
                "自检报告数据目录未落在 exe 目录内 —— 打包缺陷（数据没随包走）"
            )
        print("自检结论：%s" % json.dumps(payload.get("checks", {}), ensure_ascii=False))
    return problems


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="冻结产物验收")
    parser.add_argument("--dist", required=True, help="dist 目录路径")
    parser.add_argument("--selftest", action="store_true", help="额外驱动冻结态自检")
    args = parser.parse_args(argv)

    dist = Path(args.dist)
    if not dist.is_absolute():
        dist = (ROOT / dist).resolve()

    problems = check_dist(ROOT, dist)
    if args.selftest:
        problems.extend(run_selftest(ROOT, dist))

    if problems:
        for item in problems:
            print("问题：%s" % item, file=sys.stderr)
        return 1
    print(OK_MARKER)
    return 0


if __name__ == "__main__":
    sys.exit(main())
