"""判定引擎测试：三态语义、门控、聚合、单件/批量共用分派点、失败隔离。"""

from __future__ import annotations

from pathlib import Path

import pytest

from pflc.engine import (
    DELTA_FIXED,
    DELTA_NEW,
    DELTA_PERSISTENT,
    DELTA_STABLE,
    KIND_FAILED,
    KIND_OK,
    check_card,
    check_file,
    compare_rounds,
    scan_dir,
)
from pflc.model import (
    DIM_CLAIM,
    DIM_LABEL,
    DIM_NUTRITION,
    EFFECT_CONDITIONAL,
    EXCLUDE_NO_EFFECTIVE_RULES,
    OVERALL_COMPLIANT,
    OVERALL_NONCOMPLIANT,
    OVERALL_NOT_ASSESSED,
    VERDICT_COMPLIANT,
    VERDICT_NONCOMPLIANT,
    VERDICT_NOT_PROVIDED,
    VERDICT_SKIPPED,
    VERDICT_UNKNOWN,
)
from pflc.parse import parse_label
from tests.conftest import label_rules, write_ruleset, write_text_lf


def _find(result, rule_id):
    for finding in result.all_findings():
        if finding.rule_id == rule_id:
            return finding
    return None


# --------------------------------------------------------------------------
# 标示项检查（presence）
# --------------------------------------------------------------------------


def test_presence_provided_is_compliant(rules_dir, ok_label_text):
    result = check_card(parse_label(ok_label_text), rules_dir)
    assert _find(result, "LABEL-001").verdict == VERDICT_COMPLIANT
    assert _find(result, "LABEL-006").verdict == VERDICT_COMPLIANT


def test_missing_unconditional_obligation_is_noncompliant(rules_dir):
    """**核心纪律**：无条件义务缺失 = noncompliant，绝不记成"不用做"。"""
    text = (
        "测试粮A 猫粮 成年\n"
        "原料组成：鸡肉\n"
        "添加剂：维生素A\n"
        "成分分析保证值：\n粗蛋白 >= 30%\n"
        # 刻意缺 净含量 / 生产企业
        "生产日期：2026-01-01\n保质期：18个月\n"
    )
    result = check_card(parse_label(text), rules_dir)
    assert _find(result, "LABEL-006").verdict == VERDICT_NONCOMPLIANT  # 净含量
    assert _find(result, "LABEL-007").verdict == VERDICT_NONCOMPLIANT  # 生产者
    assert result.overall() == OVERALL_NONCOMPLIANT


def test_conditional_effect_missing_is_unknown_not_noncompliant(rules_dir, tmp_path):
    """条件触发项缺失记 unknown（待人工确认），不计违规。"""
    rules = label_rules() + [{
        "rule_id": "LABEL-C01", "dimension": "label", "kind": "presence",
        "target": "net_content", "effect": EFFECT_CONDITIONAL,
        "status": "verified", "clause_status": "verified",
        "anchor": {"doc_id": "D", "clause": "第九条"},
    }]
    write_ruleset(tmp_path / "r", label=rules)
    text = "测试粮A 猫粮 成年\n原料组成：鸡肉\n添加剂：维生素A\n生产日期：2026-01-01\n"
    result = check_card(parse_label(text), tmp_path / "r")
    assert _find(result, "LABEL-C01").verdict == VERDICT_UNKNOWN


# --------------------------------------------------------------------------
# 营养限值（threshold）
# --------------------------------------------------------------------------


def test_threshold_passing_value_is_compliant(rules_dir, ok_label_text):
    result = check_card(parse_label(ok_label_text), rules_dir)
    assert _find(result, "NUT-001").verdict == VERDICT_COMPLIANT


def test_threshold_violating_value_is_noncompliant(rules_dir):
    text = (
        "测试粮A 猫粮 成年\n"
        "成分分析保证值：\n粗蛋白 >= 10%\n粗脂肪 >= 12%\n水分 <= 12%\n"
    )
    result = check_card(parse_label(text), rules_dir)
    assert _find(result, "NUT-001").verdict == VERDICT_NONCOMPLIANT


def test_threshold_missing_value_is_not_provided_not_noncompliant(rules_dir):
    """没给值 ≠ 值不达标——必须记 not_provided。"""
    text = "测试粮A 猫粮 成年\n成分分析保证值：\n粗脂肪 >= 12%\n"
    result = check_card(parse_label(text), rules_dir)
    finding = _find(result, "NUT-001")
    assert finding.verdict == VERDICT_NOT_PROVIDED


def test_threshold_boundary_exact_value_passes(rules_dir):
    """边界值本身满足 >= ——Decimal 精确比较，无浮点尾差。"""
    text = "测试粮A 猫粮 成年\n成分分析保证值：\n粗蛋白 >= 26%\n"
    result = check_card(parse_label(text), rules_dir)
    assert _find(result, "NUT-001").verdict == VERDICT_COMPLIANT


def test_wrong_category_rules_do_not_apply(rules_dir):
    """犬粮档案不应被猫粮规则判——applies_if 门控生效。"""
    text = "测试粮A 犬粮 成年\n成分分析保证值：\n粗蛋白 >= 10%\n"
    result = check_card(parse_label(text), rules_dir)
    # NUT-001 是猫粮规则，对犬粮档案不适用
    assert _find(result, "NUT-001") is None
    # NUT-004 是犬粮规则，应判不符合
    assert _find(result, "NUT-004").verdict == VERDICT_NONCOMPLIANT


def test_no_applicable_rules_marks_not_assessed(rules_dir):
    """有生效规则但本条输入无适用项 → not_assessed（不输出 compliant）。"""
    text = "测试粮A 猫粮 幼年\n成分分析保证值：\n粗蛋白 >= 30%\n"
    result = check_card(parse_label(text), rules_dir)
    nutrition = result.dimension(DIM_NUTRITION)
    assert nutrition.not_assessed
    assert nutrition.verdict() == OVERALL_NOT_ASSESSED


# --------------------------------------------------------------------------
# 宣称核查（claim_support）
# --------------------------------------------------------------------------


def test_claim_absent_is_skipped(rules_dir, ok_label_text):
    """未宣称 → 规则前提不成立 → skipped（不适用），不是违规。"""
    result = check_card(parse_label(ok_label_text), rules_dir)
    assert _find(result, "CLAIM-001").verdict == VERDICT_SKIPPED


def test_claim_present_with_support_is_compliant(rules_dir):
    text = "测试粮A 猫粮 成年\n产品特点：天然\n原料组成：鸡肉、糙米\n"
    result = check_card(parse_label(text), rules_dir)
    assert _find(result, "CLAIM-001").verdict == VERDICT_COMPLIANT


def test_claim_present_without_support_is_noncompliant(rules_dir):
    """宣称存在但支撑信息缺失 → noncompliant（结构化核查，不做语义硬判）。"""
    text = "测试粮A 猫粮 成年\n产品特点：天然\n成分分析保证值：\n粗蛋白 >= 30%\n"
    result = check_card(parse_label(text), rules_dir)
    finding = _find(result, "CLAIM-001")
    assert finding.verdict == VERDICT_NONCOMPLIANT
    assert "ingredients" in (finding.note or "")


# --------------------------------------------------------------------------
# 维度排除与聚合
# --------------------------------------------------------------------------


def test_zero_effective_dimension_is_excluded_not_judged(rules_dir, tmp_path):
    """零生效规则的维度不参与聚合，理由显式记录。"""
    write_ruleset(tmp_path / "r", nutrition=[])
    result = check_card(parse_label("测试粮A 猫粮 成年\n"), tmp_path / "r")
    nutrition = result.dimension(DIM_NUTRITION)
    assert nutrition.excluded
    assert nutrition.exclude_reason == EXCLUDE_NO_EFFECTIVE_RULES


def test_all_dimensions_empty_is_not_assessed(empty_rules_dir):
    result = check_card(parse_label("测试粮A 猫粮 成年\n"), empty_rules_dir)
    assert result.overall() == OVERALL_NOT_ASSESSED


def test_pending_rules_listed_in_result(rules_dir, tmp_path):
    pending = {
        "rule_id": "LABEL-999", "dimension": "label", "kind": "presence",
        "target": "product_name", "status": "pending",
        "anchor": {"doc_id": "D", "clause": "X"},
    }
    write_ruleset(tmp_path / "r", label=label_rules() + [pending])
    result = check_card(parse_label("测试粮A 猫粮 成年\n"), tmp_path / "r")
    assert "LABEL-999" in result.pending_rules


def test_every_finding_carries_resolvable_anchor(rules_dir, ok_label_text):
    """溯源完整性：每条结论都必须挂可解析锚点。"""
    result = check_card(parse_label(ok_label_text), rules_dir)
    for finding in result.all_findings():
        assert finding.anchor is not None
        assert finding.anchor.is_resolvable()


# --------------------------------------------------------------------------
# 单件 / 批量
# --------------------------------------------------------------------------


def test_check_file_matches_check_card(rules_dir, tmp_path, ok_label_text):
    """**单一分派点**：check_file 与 check_card 必须给同一结论。"""
    path = write_text_lf(tmp_path / "label.txt", ok_label_text)
    from_file = check_file(path, rules_dir)
    from_card = check_card(parse_label(ok_label_text, source=path.name), rules_dir)
    assert from_file.overall() == from_card.overall()
    assert from_file.card_id == from_card.card_id
    assert (sorted(f.rule_id for f in from_file.all_findings())
            == sorted(f.rule_id for f in from_card.all_findings()))


def test_scan_dir_reports_failed_items_without_changing_exit_semantics(
        rules_dir, tmp_path):
    """**失败件 ≠ 违规**：坏文件记 failed，不改变"是否检出违规"的判据。"""
    work = tmp_path / "batch"
    work.mkdir()
    write_text_lf(work / "good.txt", "测试粮A 猫粮 成年\n原料组成：鸡肉\n")
    # 写入非法 UTF-8 字节 → 解析失败
    (work / "bad.txt").write_bytes(b"\xff\xfe\x00bad")

    report = scan_dir(work, rules_dir)
    assert report["total"] == 2
    assert report["failed"] == 1
    kinds = {i["file"]: i["kind"] for i in report["items"]}
    assert kinds["bad.txt"] == KIND_FAILED
    assert kinds["good.txt"] == KIND_OK
    # 失败件单列，未被静默吞掉
    assert any(i.get("error") for i in report["items"] if i["kind"] == KIND_FAILED)


def test_scan_dir_isolates_failures_and_continues(rules_dir, tmp_path):
    """失败隔离：单件异常不中断整批。"""
    work = tmp_path / "batch"
    work.mkdir()
    for name in ("a.txt", "b.txt", "c.txt"):
        (work / name).write_bytes(b"\xff\xfe\x00broken")
    report = scan_dir(work, rules_dir)
    assert report["total"] == 3
    assert report["failed"] == 3  # 全部处理了，没有中途抛出


def test_scan_dir_missing_directory_raises(rules_dir, tmp_path):
    from pflc.engine import EngineError
    with pytest.raises(EngineError):
        scan_dir(tmp_path / "nope", rules_dir)


# --------------------------------------------------------------------------
# 两轮对账
# --------------------------------------------------------------------------


def test_compare_rounds_detects_new_and_fixed():
    """配对主键是稳定身份键——用内容指纹会让"已修复"永远检不出。

    返回的是**违规条目级**键（``file::维度/规则``），"已修复"能指明哪条规则
    不再触发，而不只是"这个文件变好了"。
    """
    previous = {"file:a.txt": {("label", "LABEL-006")}}
    current = {"file:b.txt": {("label", "LABEL-007")}}
    delta = compare_rounds(previous, current)
    assert delta[DELTA_NEW] == ["file:b.txt::label/LABEL-007"]
    assert delta[DELTA_FIXED] == ["file:a.txt::label/LABEL-006"]


def test_compare_rounds_key_presence_alone_is_not_a_violation():
    """键存在 ≠ 有违规：空违规集的文件不应被记成新增/持续违规。"""
    previous = {"file:a.txt": set()}
    current = {"file:a.txt": set()}
    delta = compare_rounds(previous, current)
    assert delta[DELTA_NEW] == []
    assert delta[DELTA_FIXED] == []
    assert delta[DELTA_PERSISTENT] == []
    assert delta[DELTA_STABLE] == ["file:a.txt"]


def test_compare_rounds_persistent_and_stable():
    previous = {"file:a.txt": {("label", "LABEL-006")}, "file:b.txt": set()}
    current = {"file:a.txt": {("label", "LABEL-006")}, "file:b.txt": set()}
    delta = compare_rounds(previous, current)
    assert delta[DELTA_PERSISTENT] == ["file:a.txt::label/LABEL-006"]
    assert "file:b.txt" in delta[DELTA_STABLE]


def test_fixed_file_is_detected_across_rounds(rules_dir, tmp_path):
    """端到端验证"已修复"可检出（稳定身份键 + 同文件名）。"""
    work = tmp_path / "batch"
    work.mkdir()
    bad = work / "case.txt"
    write_text_lf(bad, "测试粮A 猫粮 成年\n原料组成：鸡肉\n添加剂：维生素A\n"
                       "生产日期：2026-01-01\n")
    first = scan_dir(work, rules_dir)
    assert first["has_violation"] is True

    # 补齐缺项
    write_text_lf(bad, "测试粮A 猫粮 成年\n原料组成：鸡肉\n添加剂：维生素A\n"
                       "成分分析保证值：\n粗蛋白 >= 30%\n粗脂肪 >= 12%\n水分 <= 12%\n"
                       "净含量：2kg\n生产企业：某公司\n生产日期：2026-01-01\n保质期：18个月\n")
    second = scan_dir(work, rules_dir, baseline=first["current"])
    delta = second["delta"]
    # 缺项违规已修复（净含量/生产者）
    assert any("LABEL-006" in k or "LABEL-007" in k for k in delta[DELTA_FIXED])
