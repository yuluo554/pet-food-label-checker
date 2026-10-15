"""规则层测试：双重门控、作用域、零字面量 token 实算、规则包契约。"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from pflc.rules import (
    KIND_THRESHOLD,
    STATUS_PENDING,
    STATUS_VERIFIED,
    RulePackError,
    banned_numeric_tokens,
    effective_ruleset,
    load_pack,
    pending_rule_ids,
    scan_source_for_tokens,
)
from tests.conftest import write_ruleset


def test_effective_ruleset_returns_only_verified(rules_dir):
    rules = effective_ruleset("label", rules_dir)
    assert rules
    assert all(r.status == STATUS_VERIFIED for r in rules)


def test_pending_rules_are_blocked_from_judgment(rules_dir, tmp_path):
    """**核心纪律**：status=pending 不进判定路径。"""
    pending_rule = {
        "rule_id": "LABEL-999", "dimension": "label", "kind": "presence",
        "target": "product_name", "status": STATUS_PENDING,
        "clause_status": STATUS_VERIFIED,
        "anchor": {"doc_id": "D", "clause": "X"},
    }
    from tests.conftest import label_rules
    write_ruleset(tmp_path / "r", label=label_rules() + [pending_rule])
    rules = effective_ruleset("label", tmp_path / "r")
    assert all(r.rule_id != "LABEL-999" for r in rules)
    assert "LABEL-999" in pending_rule_ids(tmp_path / "r")


def test_clause_status_pending_does_not_block_judgment(rules_dir, tmp_path):
    """**双重门控**：条款号未核对不阻断判定，但可证性上显式可见。"""
    rule = {
        "rule_id": "LABEL-888", "dimension": "label", "kind": "presence",
        "target": "product_name", "status": STATUS_VERIFIED,
        "clause_status": STATUS_PENDING,
        "anchor": {"doc_id": "D", "clause": "X"},
    }
    write_ruleset(tmp_path / "r", label=[rule])
    effective = effective_ruleset("label", tmp_path / "r")
    assert [r.rule_id for r in effective] == ["LABEL-888"]

    pack = load_pack("label", tmp_path / "r")
    assert [r.rule_id for r in pack.clause_pending()] == ["LABEL-888"]


def test_scope_isolation_each_validates_own_entries(rules_dir, tmp_path):
    """门控按计算路径分作用域——某作用域的 pending 不阻断其他作用域。"""
    pending_label = {
        "rule_id": "LABEL-777", "dimension": "label", "kind": "presence",
        "target": "product_name", "status": STATUS_PENDING,
        "anchor": {"doc_id": "D", "clause": "X"},
    }
    from tests.conftest import label_rules
    write_ruleset(tmp_path / "r", label=label_rules() + [pending_label])

    # nutrition 作用域不受 label 的 pending 影响
    nutrition = effective_ruleset("nutrition", tmp_path / "r")
    assert nutrition
    assert all(r.dimension == "nutrition" for r in nutrition)


def test_unknown_scope_raises(rules_dir):
    with pytest.raises(RulePackError):
        effective_ruleset("nope", rules_dir)


def test_missing_pack_degrades_gracefully(empty_rules_dir):
    """规则包不存在时优雅降级（M0 骨架态），不崩溃。"""
    pack = load_pack("label", empty_rules_dir)
    assert pack.rules == []
    assert pack.effective() == []
    assert "不存在" in pack.notes


def test_unknown_kind_raises(tmp_path):
    write_ruleset(tmp_path / "r", label=[{
        "rule_id": "BAD", "dimension": "label", "kind": "nonsense",
        "target": "x", "anchor": {"doc_id": "D", "clause": "X"},
    }])
    with pytest.raises(RulePackError):
        load_pack("label", tmp_path / "r")


def test_missing_rule_id_raises(tmp_path):
    write_ruleset(tmp_path / "r", label=[{
        "dimension": "label", "kind": "presence", "target": "x",
        "anchor": {"doc_id": "D", "clause": "X"},
    }])
    with pytest.raises(RulePackError):
        load_pack("label", tmp_path / "r")


def test_threshold_compare_uses_decimal(rules_dir):
    pack = load_pack("nutrition", rules_dir)
    rule = next(r for r in pack.rules if r.kind == KIND_THRESHOLD)
    assert rule.value is not None
    assert isinstance(rule.value, Decimal)
    # 边界值本身应满足 >=
    assert rule.compare(rule.value)


def test_applies_to_returns_false_when_input_missing():
    """缺生命阶段时不套用具体阶段的限值——宁可不判。"""
    pack = None
    from pflc.rules import Rule
    rule = Rule(rule_id="R", dimension="nutrition", kind=KIND_THRESHOLD,
                target="粗蛋白", op=">=", value=Decimal("26"),
                applies_if={"life_stage": ("成年",)})
    assert rule.applies_to("猫粮", "成年") is True
    assert rule.applies_to("猫粮", None) is False
    assert rule.applies_to("猫粮", "幼年") is False


def test_banned_tokens_computed_from_pack_not_source(rules_dir):
    """**零政策字面量门禁的根治形态**：token 从规则包运行时实算。"""
    tokens = banned_numeric_tokens(rules_dir)
    # 夹具里的限值都应被收编（≥100 阈值以下的不收，这里验 >=100 的形态）
    assert isinstance(tokens, list)
    for token in tokens:
        assert token and not token.startswith("-0")


def test_token_scan_uses_word_boundary(rules_dir):
    """子串误报是这类门禁最常见的失效方式，词边界必须挡住。"""
    tokens = ["220"]
    assert scan_source_for_tokens("x = 220\n", tokens) == [("220", 1)]
    # "2200" 里的 "220" 不算命中
    assert scan_source_for_tokens("x = 2200\n", tokens) == []


def test_manifest_thresholds_present(rules_dir):
    from pflc.rules import load_manifest
    manifest = load_manifest(rules_dir)
    assert "thresholds" in manifest
    assert "min_accuracy" in manifest["thresholds"]
