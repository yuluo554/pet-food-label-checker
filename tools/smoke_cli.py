#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI 端到端冒烟：按 **README 明示的退出码语义**逐条验收。

**为什么不用 ``cmd || true``**：那样会把真失败也吞掉。退出码非 0 不等于
跑挂——判据是"符合 README/决策记录声明过的契约"。所以本脚本**显式断言
每条的期望退出码**，不匹配即失败。

用法：
    py -X utf8 tools/smoke_cli.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

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

OK_MARKER = "SMOKE_CLI_OK"

#: (说明, argv, 期望退出码, 期望退出码的语义来源)
#:
#: **M1 末态**：规则包已录入并逐条核对（43 条 verified / 2 条 pending）。
#: 故这里断言的是"M1 真实数据下的契约"，M0 骨架态的期望（空规则 → diagnostics 1、
#: bench 1）已随数据录入而失效——**期望随数据一起演进，不写死成恒真的空断言**。
CASES: List[Tuple[str, List[str], int, str]] = [
    ("diagnostics（已录入规则 → exit 0）",
     ["diagnostics"], 0, "plan/06 M1：规则生效后 diagnostics 正常返回"),
    ("check 合规样例（无不符合 → exit 0）",
     ["check", "data/samples/label-demo-ok.txt"], 0, "README：0 = 无不符合"),
    ("check 缺项样例（检出不符合 → exit 1）",
     ["check", "data/samples/label-demo-missing.txt"], 1, "README：1 = 检出不符合"),
    ("check 越限样例（检出不符合 → exit 1）",
     ["check", "data/samples/label-demo-overlimit.txt"], 1, "README：1 = 检出不符合"),
    ("check 宣称无支撑样例（检出不符合 → exit 1）",
     ["check", "data/samples/label-demo-claim.txt"], 1, "README：1 = 检出不符合"),
    ("bench（四套件达标 → exit 0）",
     ["bench"], 0, "plan/03 D12：门槛达标才返回 0"),
    ("selftest（源码态不判 FAIL → exit 0）",
     ["selftest", "--out", ".tmp/smoke-selftest.json"], 0, "plan/03 D21"),
    ("check 不存在的文件（用法错误 → exit 2）",
     ["check", "data/samples/does-not-exist.txt"], 2, "README：2 = 输入错误"),
    ("bench --only 未知名（用法错误 → exit 2）",
     ["bench", "--only", "nope"], 2, "plan/03 D14：未知名必须 exit 2"),
]


def run_case(argv: List[str]) -> Tuple[int, str]:
    # 把 src/ 放进 PYTHONPATH：源码态（未 pip install）与安装态都能跑，
    # 免得冒烟脚本本身依赖"先装过包"这个隐含前提。
    env = dict(os.environ)
    src = str(ROOT / "src")
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = src + (os.pathsep + existing if existing else "")
    env.setdefault("PYTHONUTF8", "1")
    proc = subprocess.run(
        [sys.executable, "-m", "pflc.cli"] + argv,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    return proc.returncode, proc.stdout or ""


def main() -> int:
    (ROOT / ".tmp").mkdir(exist_ok=True)
    failures = []
    for label, argv, expected, source in CASES:
        code, output = run_case(argv)
        status = "OK" if code == expected else "FAIL"
        print("[%s] %s → exit %d（期望 %d）" % (status, label, code, expected))
        if code != expected:
            failures.append((label, code, expected, source))
            for line in output.splitlines()[:8]:
                print("      | %s" % line)

    if failures:
        for label, code, expected, source in failures:
            print("失败：%s（实际 %d / 期望 %d；依据 %s）"
                  % (label, code, expected, source), file=sys.stderr)
        return 1
    print(OK_MARKER)
    return 0


if __name__ == "__main__":
    sys.exit(main())
