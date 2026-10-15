"""模型层测试：三态语义、聚合规则、稳定身份键。"""

from __future__ import annotations

from decimal import Decimal

import pytest

from pflc.model import (
    DIM_LABEL,
    DIM_NUTRITION,
    EXCLUDE_NO_EFFECTIVE_RULES,
    FIELD_PROVIDED,
    OVERALL_COMPLIANT,
    OVERALL_NONCOMPLIANT,
    OVERALL_NOT_ASSESSED,
    OVERALL_NOT_PROVIDED,
    REASON_MAPPING_UNCERTAIN,
    VERDICT_COMPLIANT,
    VERDICT_NONCOMPLIANT,
    VERDICT_NOT_PROVIDED,
    VERDICT_SKIPPED,
    VERDICT_UNKNOWN,
    Anchor,
    CheckResult,
    DimensionResult,
    Field,
    Finding,
    LabelCard,
    compute_card_id,
)


def test_field_provided_and_missing():
    good = Field.provided("粗蛋白", Decimal("30"), unit="%")
    assert good.is_provided
    assert "30" in good.render()

    bad = Field.missing("净含量", REASON_MAPPING_UNCERTAIN)
    assert not bad.is_provided
    # 原因码必须显式可见——"歧义"与"没写"要可区分
    assert REASON_MAPPING_UNCERTAIN in bad.render()


def test_card_id_is_content_based_not_filename():
    """稳定身份键由**内容**决定：改名不应在轮次对账里表现为"新增+消失"。"""
    text = "测试粮A 猫粮\n"
    assert compute_card_id(text) == compute_card_id(text)
    card_a = LabelCard(raw_text=text, source="a.txt")
    card_b = LabelCard(raw_text=text, source="b.txt")
    assert card_a.card_id == card_b.card_id


def test_anchor_resolvable_requires_id_and_clause():
    assert Anchor("D1", "标题", "第三条").is_resolvable()
    assert not Anchor("D1", "标题", "").is_resolvable()
    assert not Anchor("", "标题", "第三条").is_resolvable()


def test_dimension_zero_findings_is_not_assessed_not_compliant():
    """**核心纪律**：无适用项 → not_assessed，绝不输出 compliant。"""
    dim = DimensionResult(dimension=DIM_LABEL)
    assert dim.verdict() == OVERALL_NOT_ASSESSED
    assert dim.verdict() != OVERALL_COMPLIANT


def test_dimension_excluded_records_reason():
    dim = DimensionResult(dimension=DIM_NUTRITION, excluded=True,
                          exclude_reason=EXCLUDE_NO_EFFECTIVE_RULES)
    assert dim.verdict() == OVERALL_NOT_ASSESSED
    assert dim.exclude_reason == EXCLUDE_NO_EFFECTIVE_RULES


def test_dimension_noncompliant_dominates():
    dim = DimensionResult(dimension=DIM_LABEL, findings=[
        Finding("R1", DIM_LABEL, "通用名", VERDICT_COMPLIANT),
        Finding("R2", DIM_LABEL, "净含量", VERDICT_NONCOMPLIANT),
    ])
    assert dim.verdict() == OVERALL_NONCOMPLIANT


def test_dimension_only_unknown_is_not_provided_not_compliant():
    dim = DimensionResult(dimension=DIM_LABEL, findings=[
        Finding("R1", DIM_LABEL, "通用名", VERDICT_UNKNOWN),
    ])
    assert dim.verdict() == OVERALL_NOT_PROVIDED
    assert dim.verdict() != OVERALL_COMPLIANT


def test_obligation_and_conditional_columns_are_separate():
    """义务类型分栏：频次只取无条件义务栏。"""
    from pflc.model import EFFECT_CONDITIONAL, EFFECT_OBLIGATION

    dim = DimensionResult(dimension=DIM_LABEL, findings=[
        Finding("R1", DIM_LABEL, "通用名", VERDICT_COMPLIANT, effect=EFFECT_OBLIGATION),
        Finding("R2", DIM_LABEL, "特殊标示", VERDICT_UNKNOWN, effect=EFFECT_CONDITIONAL),
    ])
    assert len(dim.obligation_findings()) == 1
    assert len(dim.conditional_findings()) == 1


def test_excluded_dimension_does_not_drag_overall_down():
    """零生效维度不参与聚合——否则会把整体结论无谓拉成"未评估"。"""
    label = DimensionResult(dimension=DIM_LABEL, findings=[
        Finding("R1", DIM_LABEL, "通用名", VERDICT_COMPLIANT),
    ])
    nutrition = DimensionResult(dimension=DIM_NUTRITION, excluded=True,
                                exclude_reason=EXCLUDE_NO_EFFECTIVE_RULES)
    result = CheckResult(card_id="x", dimensions=[label, nutrition])
    assert result.overall() == OVERALL_COMPLIANT


def test_all_dimensions_excluded_is_not_assessed():
    nutrition = DimensionResult(dimension=DIM_NUTRITION, excluded=True,
                                exclude_reason=EXCLUDE_NO_EFFECTIVE_RULES)
    result = CheckResult(card_id="x", dimensions=[nutrition])
    assert result.overall() == OVERALL_NOT_ASSESSED


def test_skipped_verdict_is_distinct_from_noncompliant():
    """skipped（不适用）必须与 noncompliant（不符合）可区分。"""
    assert VERDICT_SKIPPED != VERDICT_NONCOMPLIANT
    dim = DimensionResult(dimension=DIM_LABEL, findings=[
        Finding("R1", DIM_LABEL, "x", VERDICT_SKIPPED),
        Finding("R2", DIM_LABEL, "y", VERDICT_COMPLIANT),
    ])
    assert not dim.has_noncompliant()
    assert dim.verdict() == OVERALL_COMPLIANT


def test_card_missing_fields_lists_guaranteed_too():
    card = LabelCard(raw_text="测试粮A 猫粮\n")
    card.guaranteed = {"粗蛋白": Field.provided("粗蛋白", Decimal("30"), unit="%")}
    missing = card.missing_fields()
    assert "net_content" in missing
    assert "粗蛋白" not in missing


def test_card_to_dict_is_deterministic():
    card = LabelCard(raw_text="测试粮A 猫粮\n")
    card.guaranteed = {
        "粗蛋白": Field.provided("粗蛋白", Decimal("30"), unit="%"),
        "粗脂肪": Field.provided("粗脂肪", Decimal("12"), unit="%"),
    }
    assert card.to_dict() == card.to_dict()
    # Decimal 转字符串保精度（不引入浮点中间态）
    assert card.to_dict()["guaranteed"]["粗蛋白"]["value"] == "30"


def test_finding_to_dict_marks_anchor_resolvable():
    finding = Finding("R1", DIM_LABEL, "通用名", VERDICT_COMPLIANT,
                      anchor=Anchor("D1", "文档", "第三条"))
    payload = finding.to_dict()
    assert payload["anchor_resolvable"] is True

    bare = Finding("R2", DIM_LABEL, "净含量", VERDICT_NONCOMPLIANT)
    assert bare.to_dict()["anchor_resolvable"] is False


def test_field_provided_requires_value():
    """status=provided 但 value 为空视为未提供——不给"空壳合规"。"""
    field = Field(name="x", value=None, status=FIELD_PROVIDED)
    assert not field.is_provided
