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
#: M0 骨架态：规则包为空 → diagnostics 返回 1（"有 pending/零生效"的既定语义）
#: check 对空规则包返回 0（无不符合检出）；bench 因空分母返回 1。
CASES: List[Tuple[str, List[str], int, str]] = [
    ("diagnostics（骨架态零生效规则 → exit 1）",
     ["diagnostics"], 1, "plan/06 M0：diagnostics 零生效规则时 exit 1"),
    ("check 合规样例（无不符合 → exit 0）",
     ["check", "data/samples/label-demo-ok.txt"], 0, "README：0 = 无不符合"),
    ("check 缺项样例（骨架态无规则 → 无检出）",
     ["check", "data/samples/label-demo-missing.txt"], 0, "README：0 = 无不符合"),
    ("bench（空分母 → exit 1）",
     ["bench"], 1, "plan/03 D12：未启用套件不冒充通过"),
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
