"""基准评测（发布前证据）：四套件 runner + 空分母防空 + manifest 门槛下发。

设计纪律（见 plan/03 D11–D16）：

  * **样本驱动 + 规则驱动两层**：样本驱动证明"引擎在这些样本上对"；
    规则驱动不读真值库、只从规则表推导端点，证明"引擎在*所有*有限端点上对"；
  * **空分母不冒充通过**：误报对照零样本时 ``hits(0) <= max(0)`` 恒真 = 假门。
    正解 = ``not_enabled=true`` + notes 声明 + **exit 1**；
  * **验收门槛随 manifest 下发**（数据非代码）：缺失即报配置错误（exit 2），
    **不得回落代码里的默认值**；
  * **退出码三语义**：0 达标 / 1 未达标或门控拦截 / 2 用法或用例名错误。

``--only`` 传未知名必须走 exit 2——否则"跑了个不存在的基准"会被读成成功。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from ..engine import check_card
from ..model import (
    DIM_CLAIM,
    DIM_LABEL,
    DIM_NUTRITION,
    VERDICT_COMPLIANT,
    VERDICT_NONCOMPLIANT,
)
from ..parse import parse_label
from ..rules import KIND_THRESHOLD, load_manifest, load_pack
from .cases import (
    CASE_COMPLIANT,
    CASE_MISSING,
    CASE_OVERLIMIT,
    CASE_UNSUPPORTED_CLAIM,
    compare_nonpass,
    generate_cases,
    observed_nonpass,
)

#: 退出码语义（锁进测试，见 plan/03 D14）
EXIT_OK = 0            #: 达标
EXIT_NOT_MET = 1       #: 未达标或门控拦截
EXIT_USAGE = 2         #: 输入、坐标或用例名错误

#: 套件名
SUITE_DETECTION = "detection"      #: 样本驱动：违规检出率 / 误报率
SUITE_OVERALL = "overall"          #: 样本驱动：整体结论一致率
SUITE_BOUNDARY = "boundary"        #: 规则驱动：限值端点 ± 邻域断言
SUITE_TRACEABILITY = "traceability"  #: 锚点可解析率 + 溯源完整性

SUITES = (SUITE_DETECTION, SUITE_OVERALL, SUITE_BOUNDARY, SUITE_TRACEABILITY)

#: 边界邻域步长（精度约定，非政策数值——可豁免零字面量门禁）
BOUNDARY_STEP = Decimal("0.01")


class BenchConfigError(Exception):
    """门槛未随 manifest 下发——**不得回落代码默认值**（见 plan/03 D13）。"""


@dataclass
class SuiteResult:
    """单套件结果。"""

    name: str
    passed: bool = False
    not_enabled: bool = False
    metrics: Dict[str, Any] = field(default_factory=dict)
    notes: str = ""
    details: List[str] = field(default_factory=list)


@dataclass
class BenchReport:
    """基准总报告。"""

    suites: List[SuiteResult] = field(default_factory=list)
    thresholds: Dict[str, Any] = field(default_factory=dict)

    def exit_code(self) -> int:
        """0 全部达标 / 1 有未达标或未启用套件。"""
        if not self.suites:
            return EXIT_NOT_MET
        for suite in self.suites:
            if suite.not_enabled:
                return EXIT_NOT_MET
            if not suite.passed:
                return EXIT_NOT_MET
        return EXIT_OK

    def overall_passed(self) -> bool:
        return self.exit_code() == EXIT_OK


# --------------------------------------------------------------------------
# 门槛下发
# --------------------------------------------------------------------------


def load_thresholds(rules_dir: Path) -> Dict[str, Any]:
    """从 manifest 读验收门槛。

    **门槛是数据不是代码**：内联在引擎里就是"抄进代码的第二份真相"，
    调门槛要改代码、也易被误读为政策数值。缺失即抛配置错误。
    """
    manifest = load_manifest(Path(rules_dir))
    thresholds = manifest.get("thresholds")
    if not thresholds:
        raise BenchConfigError(
            "规则包 manifest 未下发验收门槛（thresholds 节缺失）——"
            "基准层不得回落代码默认值，请补 manifest 后重跑"
        )
    for key in ("min_accuracy", "max_false_positive"):
        if key not in thresholds:
            raise BenchConfigError("manifest thresholds 缺 %r" % key)
    return thresholds


# --------------------------------------------------------------------------
# 套件实现
# --------------------------------------------------------------------------


def _sample_cases(rules_dir: Path) -> List[Dict[str, Any]]:
    return generate_cases(Path(rules_dir))["cases"]


def run_detection(rules_dir: Path, thresholds: Dict[str, Any]) -> SuiteResult:
    """样本驱动：违规检出率 + 误报率。

    **空分母防空**：违规类样例数为 0 时不能算"全检出"——标 ``not_enabled``。
    """
    cases = _sample_cases(rules_dir)
    violation_cases = [c for c in cases if c["case_type"] != CASE_COMPLIANT]
    clean_cases = [c for c in cases if c["case_type"] == CASE_COMPLIANT]

    result = SuiteResult(name=SUITE_DETECTION)

    if not violation_cases:
        # 违规类零样本 → 检出率恒真 = 假门
        result.not_enabled = True
        result.notes = "违规类用例未生成（分母为 0），检出率不可判定"
        result.metrics = {"violation_cases": 0, "detected": 0, "detection_rate": 0.0}
        return result

    detected = 0
    for case in violation_cases:
        card = parse_label(case["text"], source=case["case_id"])
        check = check_card(card, Path(rules_dir))
        observed = observed_nonpass(check)
        expected = dict(case["expected_findings"])
        diff = compare_nonpass(expected, observed)
        # 命中判据：期望的非 pass 全部被检出（missing 为空即未漏检）
        if not diff["missing"]:
            detected += 1
        else:
            result.details.append("%s 漏检：%s" % (case["case_id"], diff["missing"]))

    detection_rate = Decimal(detected) / Decimal(len(violation_cases))

    # 误报对照：合规样例不应产生任何非 pass
    false_positives = 0
    if not clean_cases:
        result.not_enabled = True
        result.notes = "合规类用例未生成（误报分母为 0），误报率不可判定"
        result.metrics = {
            "violation_cases": len(violation_cases), "detected": detected,
            "detection_rate": float(detection_rate),
            "clean_cases": 0, "false_positives": 0, "false_positive_rate": 0.0,
        }
        return result

    for case in clean_cases:
        card = parse_label(case["text"], source=case["case_id"])
        check = check_card(card, Path(rules_dir))
        nonpass = observed_nonpass(check)
        if nonpass:
            false_positives += 1
            result.details.append("%s 误报：%s" % (case["case_id"], sorted(nonpass)))

    fp_rate = Decimal(false_positives) / Decimal(len(clean_cases))
    min_accuracy = Decimal(str(thresholds["min_accuracy"]))
    max_fp = Decimal(str(thresholds["max_false_positive"]))

    result.metrics = {
        "violation_cases": len(violation_cases),
        "detected": detected,
        "detection_rate": float(detection_rate),
        "clean_cases": len(clean_cases),
        "false_positives": false_positives,
        "false_positive_rate": float(fp_rate),
        "min_accuracy": float(min_accuracy),
        "max_false_positive": float(max_fp),
    }
    result.passed = detection_rate >= min_accuracy and fp_rate <= max_fp
    return result


def run_overall(rules_dir: Path, thresholds: Dict[str, Any]) -> SuiteResult:
    """样本驱动：整体结论一致率（``expected_overall`` vs 引擎聚合结论）。"""
    cases = _sample_cases(rules_dir)
    result = SuiteResult(name=SUITE_OVERALL)
    if not cases:
        result.not_enabled = True
        result.notes = "用例未生成（分母为 0），整体一致率不可判定"
        return result

    matched = 0
    for case in cases:
        card = parse_label(case["text"], source=case["case_id"])
        check = check_card(card, Path(rules_dir))
        observed = check.overall()
        if observed == case["expected_overall"]:
            matched += 1
        else:
            result.details.append(
                "%s 期望 %s，实际 %s" % (case["case_id"], case["expected_overall"], observed)
            )
    rate = Decimal(matched) / Decimal(len(cases))
    min_accuracy = Decimal(str(thresholds["min_accuracy"]))
    result.metrics = {
        "cases": len(cases), "matched": matched, "accuracy": float(rate),
        "min_accuracy": float(min_accuracy),
    }
    result.passed = rate >= min_accuracy
    return result


def run_boundary(rules_dir: Path, thresholds: Dict[str, Any]) -> SuiteResult:
    """**规则驱动**：不读真值库，只从规则表推导端点，做 ±邻域断言。

    对每条阈值规则，在限值 ``±BOUNDARY_STEP`` 处构造观测值，
    断言引擎结论在**跨过端点时翻转**——这证明"引擎在所有有限端点上对"，
    而样本驱动只能证明"在真值库恰好覆盖的样本上对"。
    """
    nutrition = load_pack(DIM_NUTRITION, Path(rules_dir))
    rules = [r for r in nutrition.effective() if r.kind == KIND_THRESHOLD]
    result = SuiteResult(name=SUITE_BOUNDARY)

    if not rules:
        result.not_enabled = True
        result.notes = "营养限值生效规则为 0（分母为 0），边界自洽不可判定"
        result.metrics = {"rules": 0, "checked": 0, "passed": 0}
        return result

    checked = 0
    passed = 0
    for rule in rules:
        category = _first_of(rule, "category")
        life_stage = _first_of(rule, "life_stage")
        if category is None or life_stage is None:
            continue
        for delta, expect_pass in ((BOUNDARY_STEP, True), (-BOUNDARY_STEP, False)):
            observed = _nudge(rule.value, rule.op, delta)
            if observed is None:
                continue
            checked += 1
            text = _boundary_label(category, life_stage, rule.target, rule.op, observed)
            card = parse_label(text, source="boundary:%s" % rule.rule_id)
            check = check_card(card, Path(rules_dir))
            verdict = _verdict_of(check, rule.rule_id)
            if verdict is None:
                result.details.append("%s 邻域 %s 未产生结论" % (rule.rule_id, observed))
                continue
            ok = (verdict == VERDICT_COMPLIANT) if expect_pass else (
                verdict == VERDICT_NONCOMPLIANT)
            if ok:
                passed += 1
            else:
                result.details.append(
                    "%s 邻域 %s 期望 %s，实际 %s" % (
                        rule.rule_id, observed,
                        "compliant" if expect_pass else "noncompliant", verdict)
                )

    if checked == 0:
        result.not_enabled = True
        result.notes = "无可构造端点的规则（分母为 0），边界自洽不可判定"
        return result

    rate = Decimal(passed) / Decimal(checked)
    min_accuracy = Decimal(str(thresholds["min_accuracy"]))
    result.metrics = {
        "rules": len(rules), "checked": checked, "passed": passed,
        "rate": float(rate), "min_accuracy": float(min_accuracy),
    }
    result.passed = rate >= min_accuracy
    return result


def _nudge(value: Decimal, op: str, delta: Decimal) -> Optional[Decimal]:
    """在限值邻域取一个**明确落在某一侧**的观测值。

    对 ``>=``/``>``：``+delta`` 达标、``-delta`` 不达标；
    对 ``<=``/``<``：``-delta`` 达标、``+delta`` 不达标。
    比较运算符为 ``==`` 时不构造邻域（端点语义不同向）。
    """
    if op in (">=", ">"):
        return value + delta
    if op in ("<=", "<"):
        return value - delta
    return None


def _boundary_label(category: str, life_stage: str, target: str, op: str,
                    observed: Decimal) -> str:
    """构造只含单条指标的最小标签文本（数值由调用方从规则表算出）。"""
    return (
        "%s %s\n"
        "原料组成：鸡肉、糙米\n"
        "成分分析保证值：\n"
        "%s %s %s%%\n"
        "净含量：2kg\n"
        "生产企业：某合成宠物食品有限公司\n"
        "生产日期：2026-01-01\n"
        "保质期：18个月\n"
    ) % ("测试粮A", "%s %s" % (category, life_stage), target, op, observed.normalize())


def _verdict_of(check, rule_id: str) -> Optional[str]:
    for finding in check.all_findings():
        if finding.rule_id == rule_id:
            return finding.verdict
    return None


def run_traceability(rules_dir: Path, thresholds: Dict[str, Any]) -> SuiteResult:
    """锚点可解析率 + 溯源完整性（每条生效规则都必须挂可解析锚点）。"""
    result = SuiteResult(name=SUITE_TRACEABILITY)
    total = 0
    resolvable = 0
    for dim in (DIM_LABEL, DIM_NUTRITION, DIM_CLAIM):
        for rule in load_pack(dim, Path(rules_dir)).effective():
            total += 1
            if rule.anchor is not None and rule.anchor.is_resolvable():
                resolvable += 1
            else:
                result.details.append("%s 锚点缺失或不可解析" % rule.rule_id)

    if total == 0:
        result.not_enabled = True
        result.notes = "生效规则为 0（分母为 0），锚点可解析率不可判定"
        result.metrics = {"effective_rules": 0, "resolvable": 0, "rate": 0.0}
        return result

    rate = Decimal(resolvable) / Decimal(total)
    min_accuracy = Decimal(str(thresholds["min_accuracy"]))
    result.metrics = {
        "effective_rules": total, "resolvable": resolvable, "rate": float(rate),
        "min_accuracy": float(min_accuracy),
    }
    result.passed = rate >= min_accuracy
    return result


_RUNNERS: Dict[str, Callable[[Path, Dict[str, Any]], SuiteResult]] = {
    SUITE_DETECTION: run_detection,
    SUITE_OVERALL: run_overall,
    SUITE_BOUNDARY: run_boundary,
    SUITE_TRACEABILITY: run_traceability,
}


def _first_of(rule, key: str) -> Optional[str]:
    allowed = rule.applies_if.get(key)
    if not allowed:
        return None
    return sorted(allowed)[0]


# --------------------------------------------------------------------------
# 入口
# --------------------------------------------------------------------------


def run(rules_dir: Path, only: Optional[Sequence[str]] = None) -> BenchReport:
    """跑基准套件。

    ``only`` 传未知名 → 抛 ``ValueError``（调用方转 exit 2）。
    ``--only`` 部分运行时**不判定未测指标**（否则会把"没测"误报成"未达标"）。
    """
    if only:
        unknown = [name for name in only if name not in _RUNNERS]
        if unknown:
            raise ValueError(
                "未知套件名 %s；可选：%s" % ("、".join(unknown), "、".join(SUITES))
            )
        names: Sequence[str] = list(only)
    else:
        names = SUITES

    thresholds = load_thresholds(Path(rules_dir))
    report = BenchReport(thresholds=thresholds)
    for name in names:
        report.suites.append(_RUNNERS[name](Path(rules_dir), thresholds))
    return report


def render_report(report: BenchReport) -> str:
    """人可读的基准报告文本。"""
    lines: List[str] = ["=== 基准评测 ==="]
    for suite in report.suites:
        if suite.not_enabled:
            status = "NOT_ENABLED"
        else:
            status = "PASS" if suite.passed else "FAIL"
        lines.append("[%s] %s" % (status, suite.name))
        for key in sorted(suite.metrics):
            lines.append("    %s = %s" % (key, suite.metrics[key]))
        if suite.notes:
            lines.append("    notes: %s" % suite.notes)
        for detail in suite.details[:5]:
            lines.append("    - %s" % detail)
        if len(suite.details) > 5:
            lines.append("    ... 另有 %d 条" % (len(suite.details) - 5))
    lines.append("总体：%s" % ("达标" if report.overall_passed() else "未达标"))
    return "\n".join(lines)
