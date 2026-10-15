"""README 基准指标守门：**文档里的数必须等于实跑的数**。

**为什么要有这道门**：指标写进 README 后，下一次改数据/改规则时数值就会漂移。
手抄的数字没有任何机制保证它还是真的——README 写着 1.0、实跑是 0.92，
读文档的人不会知道。本门把"README 里的数"与"`bench` 实跑的数"逐行比对，
使"文档漂移"变成一次红测，而不是一个没人发现的谎言。

**判据落点是"该套件那一行"**（不是"文件里出现过这个数"）：实测把
`overall` 行的 `accuracy=1.0` 改成 `0.9` 后，全文件级子串判据照样绿
（别处还有别的 `1.0`）——那就是假门。故这里先把 README 的表格行切出来，
再在该行内逐项核对。

**期望值一律取自实跑**（本文件不存第二份数字）：文件中只有"哪些指标必须
被文档化"这份清单，数值本身来自 `run()`。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

import pytest

from pflc.benchmark import run

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
RULES_DIR = ROOT / "data" / "rules"

#: 每个套件必须写进 README 的指标（**只列清单，不存数值**——数值取自实跑）。
#: 新增指标要同时改这里与 README 表格，否则门不覆盖它。
METRICS_TO_DOCUMENT: Dict[str, List[str]] = {
    "detection": ["violation_cases", "detected", "detection_rate",
                  "false_positive_rate"],
    "overall": ["cases", "matched", "accuracy"],
    "boundary": ["rules", "checked", "passed", "rate"],
    "traceability": ["effective_rules", "resolvable", "rate"],
}

#: 阈值/来源标记这类"配置回显"不必逐项进 README 表格
IGNORABLE_METRICS = {"min_accuracy", "max_false_positive", "truth_source",
                     "false_positives", "clean_cases"}


def _render(value) -> str:
    """与 ``render_report`` 同口径渲染（CLI 用 ``"%s" % value``，float 1.0 → "1.0"）。

    口径必须与 CLI 一致，否则守门比的是"另一种渲染"，README 与实跑永远对不上。
    """
    return str(value)


#: 实测指标小节的标题（README 里有两个套件表格：上面是"测什么"的说明表，
#: 下面是"实测值"表。行级判据必须落**下面那张**——否则取到的行里根本没有数值）。
METRICS_SECTION_HEADING = "### 实测指标"


def _metrics_section(text: str) -> str:
    """切出"实测指标"小节正文（到下一个 `---` 或二级标题为止）。"""
    start = text.find(METRICS_SECTION_HEADING)
    if start < 0:
        return ""
    rest = text[start + len(METRICS_SECTION_HEADING):]
    end = len(rest)
    for marker in ("\n---", "\n## "):
        idx = rest.find(marker)
        if idx >= 0:
            end = min(end, idx)
    return rest[:end]


def _table_row(section: str, suite_name: str) -> str:
    """取出实测指标表里该套件的那一行。

    找不到即返回空串——调用方据此报"该套件根本没有指标行"，
    这正是需要变红的形态（比"文件里碰巧有这个数"严格）。
    """
    match = re.search(r"^\| `%s` \|(.+)\|$" % re.escape(suite_name), section, re.M)
    return match.group(1) if match else ""


@pytest.fixture(scope="module")
def bench_report():
    return run(RULES_DIR)


def test_readme_bench_metrics_match_actual_bench(bench_report):
    """README 实测指标表的**每一行** == `bench` 实跑结果（逐项等值）。"""
    section = _metrics_section(README.read_text(encoding="utf-8"))
    assert section, "README 里找不到「%s」小节" % METRICS_SECTION_HEADING

    mismatches = []
    for suite in bench_report.suites:
        row = _table_row(section, suite.name)
        if not row:
            mismatches.append("%s：README 实测指标表里没有该套件的行" % suite.name)
            continue
        for key in METRICS_TO_DOCUMENT[suite.name]:
            actual = _render(suite.metrics[key])
            if "%s=%s" % (key, actual) not in row:
                mismatches.append(
                    "%s.%s：该行未写出实跑值 %s（行内容：%s）"
                    % (suite.name, key, actual, row.strip())
                )
    assert mismatches == [], "README 指标行与实际基准不符：%s" % mismatches


def test_readme_metrics_gate_is_not_vacuous(bench_report):
    """**非空转自检**：覆盖表列全四套件，且实跑指标键都被文档化或显式豁免。"""
    assert sorted(METRICS_TO_DOCUMENT) == sorted(s.name for s in bench_report.suites)

    uncovered = []
    for suite in bench_report.suites:
        documented = set(METRICS_TO_DOCUMENT[suite.name])
        missing = set(suite.metrics) - documented - IGNORABLE_METRICS
        if missing:
            uncovered.append("%s: %s" % (suite.name, sorted(missing)))
    assert uncovered == [], "这些实跑指标既没进 README 也没被显式豁免：%s" % uncovered


def test_readme_row_scope_judgement_is_falsifiable():
    """**可证伪性证明**：行级判据必须能抓住"该行的数被手改"。

    实测教训：全文件级子串判据抓不住它（别处还有别的 `1.0`）。
    这里用一段合成文本证明行级判据有效——真值取自实跑，合成行故意写错。
    """
    report = run(RULES_DIR)
    overall = next(s for s in report.suites if s.name == "overall")
    real = _render(overall.metrics["accuracy"])
    assert real == "1.0", "前置：当前实跑 accuracy 应为 1.0，实际 %s" % real

    tampered = "| `overall` | `cases=16`、`matched=16`、`accuracy=0.9` |\n"
    row = _table_row(tampered, "overall")
    assert row, "行提取失效 = 判据空转"
    assert "accuracy=%s" % real not in row, "行级判据抓不住被手改的数 = 假门"


def test_readme_metrics_section_is_located():
    """小节定位必须真的切到"实测指标"那张表（不是上面的说明表）。

    实测教训：不切小节时正则命中的是上方"测什么"表（`detection` 行写的是
    "违规检出率 + 误报率"，没有数值），报出的错全是噪声，判据等于空转。
    """
    section = _metrics_section(README.read_text(encoding="utf-8"))
    assert "detection_rate=" in section, "未切到实测指标表（里面应有检测率数值）"
    assert "违规检出率 + 误报率" not in section, "切到了上方说明表 = 判据落点错"


def test_readme_missing_suite_row_is_detected():
    """行不存在也必须算不合格（比"文件里出现过这个数"严格）。"""
    assert _table_row("| `detection` | `x=1` |\n", "overall") == ""


def test_readme_declares_frozen_truth_source():
    """README 必须写明基准的期望来源是**冻结真值库**（可核证性）。"""
    text = README.read_text(encoding="utf-8")
    assert "data/benchmark/cases.json" in text
    assert "gen_cases.py --check" in text
