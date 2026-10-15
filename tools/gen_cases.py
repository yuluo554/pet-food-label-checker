#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合成基准真值库生成器：规则包 → 冻结真值库（`data/benchmark/cases.json`）。

**为什么真值库必须入库并被"再生成位级一致"守门**（见 plan/03 D11 / K14）：
K14 要求"期望锚定冻结真值"。若基准每次现场重算真值，就没有任何入库件可供
对账——"冻结"只是名义上的（M4 实测：旧实现正是这样，`load_cases` 全仓零调用）。
本脚本把真值库落盘，`--check` 让它可被常驻守门；基准层读的就是这个入库件。

**生成器是唯一真值源**：真值库由规则包确定性产出，改规则后必须重生成。
形态参照 `tools/gen_samples.py`（`--force` / `--check` + `FROZEN_CASES_OK`）。

**载入侧白名单**：`load_cases()` 内置假品牌名硬断言——入库件被手改掺入
真实品牌时，`--check` 与基准都会立刻报错（K18 的第二个实例）。

用法：
    py -X utf8 tools/gen_cases.py --force    # 重生成真值库
    py -X utf8 tools/gen_cases.py --check    # 位级一致校验（守门用）
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

# --- 入口编码守卫：覆盖所有会打印的可执行入口（见 plan/07 K22）-------------
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

from pflc.benchmark.cases import (  # noqa: E402
    cases_path_for,
    check_cases_frozen,
    generate_cases,
    write_cases,
)

RULES_DIR = ROOT / "data" / "rules"

OK_MARKER = "FROZEN_CASES_OK"


def target_path() -> Path:
    return cases_path_for(RULES_DIR)


def write_all() -> Path:
    cases = generate_cases(RULES_DIR)
    path = target_path()
    write_cases(cases, path)
    return path


def check() -> bool:
    return check_cases_frozen(target_path(), RULES_DIR)


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="合成基准真值库生成器（冻结产物）")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--force", action="store_true", help="重生成真值库")
    group.add_argument("--check", action="store_true", help="位级一致校验")
    args = parser.parse_args(argv)

    if args.check:
        if check():
            print(OK_MARKER)
            return 0
        print("FROZEN_CASES_MISMATCH", file=sys.stderr)
        return 1

    path = write_all()
    cases = generate_cases(RULES_DIR)["cases"]
    types: dict = {}
    for case in cases:
        types[case["case_type"]] = types.get(case["case_type"], 0) + 1
    print("已生成真值库：%d 个用例（%s）" % (len(cases), path))
    for case_type in sorted(types):
        print("  %s：%d" % (case_type, types[case_type]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
