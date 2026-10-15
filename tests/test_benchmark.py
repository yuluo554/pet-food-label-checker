"""基准测试：确定性、真值对账、空分母防空、门槛下发、退出码、探活变异验证。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pflc.benchmark import (
    EXIT_NOT_MET,
    EXIT_OK,
    EXIT_USAGE,
    BenchConfigError,
    SplitMix64,
    assert_brand_allowed,
    BrandWhitelistError,
    compare_nonpass,
    generate_cases,
    load_thresholds,
    observed_nonpass,
    render_report,
    run,
)
from pflc.benchmark.cases import (
    CASE_COMPLIANT,
    CASE_MISSING,
    CASE_OVERLIMIT,
    CASE_UNSUPPORTED_CLAIM,
    build_label_text,
)
from pflc.engine import check_card
from pflc.model import VERDICT_COMPLIANT, VERDICT_NONCOMPLIANT
from pflc.parse import parse_label
from tests.conftest import write_ruleset


# --------------------------------------------------------------------------
# RNG 确定性
# --------------------------------------------------------------------------


def test_splitmix64_is_deterministic():
    a, b = SplitMix64(12345), SplitMix64(12345)
    assert [a.next_u64() for _ in range(20)] == [b.next_u64() for _ in range(20)]


def test_splitmix64_different_seeds_diverge():
    a, b = SplitMix64(1), SplitMix64(2)
    assert [a.next_u64() for _ in range(5)] != [b.next_u64() for _ in range(5)]


def test_splitmix64_randbelow_range():
    rng = SplitMix64(7)
    assert all(0 <= rng.randbelow(10) < 10 for _ in range(200))


def test_splitmix64_shuffled_is_deterministic():
    a = SplitMix64(99).shuffled(["a", "b", "c", "d"])
    b = SplitMix64(99).shuffled(["a", "b", "c", "d"])
    assert a == b
    assert sorted(a) == ["a", "b", "c", "d"]


# --------------------------------------------------------------------------
# 品牌白名单
# --------------------------------------------------------------------------


def test_brand_whitelist_rejects_unknown_brand():
    """白名单外品牌名**直接报错**，绝不静默放过。"""
    with pytest.raises(BrandWhitelistError):
        assert_brand_allowed("某真实品牌")
    assert_brand_allowed("测试粮A")


def test_build_label_text_enforces_whitelist():
    with pytest.raises(BrandWhitelistError):
        build_label_text("真实品牌", "猫粮", "成年", [])


# --------------------------------------------------------------------------
# 生成器确定性
# --------------------------------------------------------------------------


def test_generate_cases_is_byte_deterministic(rules_dir):
    first = generate_cases(rules_dir)
    second = generate_cases(rules_dir)
    assert (json.dumps(first, ensure_ascii=False, sort_keys=True)
            == json.dumps(second, ensure_ascii=False, sort_keys=True))


def test_generate_cases_covers_all_four_types(rules_dir):
    cases = generate_cases(rules_dir)
    types = {c["case_type"] for c in cases["cases"]}
    assert CASE_COMPLIANT in types
    assert CASE_MISSING in types
    assert CASE_OVERLIMIT in types
    assert CASE_UNSUPPORTED_CLAIM in types


def test_generated_cases_use_only_whitelisted_brands(rules_dir):
    cases = generate_cases(rules_dir)
    for case in cases["cases"]:
        brand = case["text"].split()[0]
        assert brand in cases["brand_whitelist"]


# --------------------------------------------------------------------------
# 对账语义
# --------------------------------------------------------------------------


def test_compare_nonpass_three_sets():
    diff = compare_nonpass({"R1": VERDICT_NONCOMPLIANT}, {"R2": VERDICT_NONCOMPLIANT})
    assert diff["missing"] == ["R1"]
    assert diff["unexpected"] == ["R2"]
    assert diff["mismatched"] == []


def test_compare_nonpass_mismatch():
    diff = compare_nonpass({"R1": VERDICT_NONCOMPLIANT}, {"R1": "not_provided"})
    assert diff["mismatched"] == ["R1"]


def test_observed_nonpass_excludes_skipped(rules_dir):
    """**skipped 排除在非 pass 之外**——那是"不适用"不是"缺失"。"""
    text = "测试粮A 猫粮 成年\n原料组成：鸡肉\n添加剂：维生素A\n"
    result = check_card(parse_label(text), rules_dir)
    nonpass = observed_nonpass(result)
    # 宣称规则判 skipped，不应进非 pass 集
    assert "CLAIM-001" not in nonpass
    assert "CLAIM-002" not in nonpass


def test_clean_case_produces_no_false_positive(rules_dir, ok_label_text):
    result = check_card(parse_label(ok_label_text), rules_dir)
    assert observed_nonpass(result) == {}


# --------------------------------------------------------------------------
# 套件运行
# --------------------------------------------------------------------------


def test_run_all_suites_passes_on_fixture(rules_dir):
    report = run(rules_dir)
    assert report.exit_code() == EXIT_OK
    names = {s.name for s in report.suites}
    assert names == {"detection", "overall", "boundary", "traceability"}


def test_run_only_subset_does_not_judge_untested(rules_dir):
    """``--only`` 部分运行时不判定未测指标。"""
    report = run(rules_dir, only=["traceability"])
    assert len(report.suites) == 1
    assert report.suites[0].name == "traceability"


def test_run_unknown_suite_raises_usage_error(rules_dir):
    """``--only`` 传未知名 → 抛错（调用方转 exit 2），不静默跳过。"""
    with pytest.raises(ValueError):
        run(rules_dir, only=["nope"])


def test_empty_rules_gives_not_enabled_and_exit_not_met(empty_rules_dir):
    """**空分母防空**：零规则时不能算"全达标"。"""
    from tests.conftest import write_ruleset
    write_ruleset(empty_rules_dir, label=[], nutrition=[], claim=[])
    report = run(empty_rules_dir)
    assert report.exit_code() == EXIT_NOT_MET
    for suite in report.suites:
        assert suite.not_enabled
        assert suite.notes  # notes 声明"未生成"


def test_thresholds_must_come_from_manifest(tmp_path):
    """**门槛是数据不是代码**：manifest 缺 thresholds → 配置错误，不回落默认值。"""
    write_ruleset(tmp_path / "r")
    manifest_path = tmp_path / "r" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    del manifest["thresholds"]
    with open(manifest_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    with pytest.raises(BenchConfigError):
        load_thresholds(tmp_path / "r")


def test_report_render_mentions_status(rules_dir):
    report = run(rules_dir)
    text = render_report(report)
    assert "PASS" in text
    assert "达标" in text


# --------------------------------------------------------------------------
# 探活（可证伪）——注入缺陷必须让基准变红
# --------------------------------------------------------------------------


def test_probe_boundary_suite_fails_when_engine_comparison_is_broken(
        rules_dir, monkeypatch):
    """探活：把**引擎的比较行为**弄坏 → boundary 套件必须报未达标。

    注意：boundary 是**规则驱动**套件——它从规则表推导端点再断言引擎结论，
    因此改规则数值不会让它变红（两边一起变）。能证伪它的是"引擎算错了"，
    所以这里注入的是引擎缺陷（比较恒真），不是数据缺陷。

    弄坏后仍绿 = 假门。
    """
    from pflc.rules import Rule

    monkeypatch.setattr(Rule, "compare", lambda self, observed: True)
    report = run(rules_dir, only=["boundary"])
    suite = report.suites[0]
    assert suite.passed is False
    assert report.exit_code() == EXIT_NOT_MET


def test_probe_boundary_suite_is_green_when_engine_is_correct(rules_dir):
    """阳性对照：引擎正常时 boundary 必须绿——证明上面那条探活不是"永远红"。"""
    report = run(rules_dir, only=["boundary"])
    assert report.suites[0].passed is True


def test_probe_detection_suite_fails_when_engine_detection_is_blinded(
        rules_dir, monkeypatch):
    """探活：让引擎对越限视而不见 → detection 套件必须报未达标。"""
    from pflc.engine import _judge_threshold
    from pflc.model import VERDICT_COMPLIANT, Finding

    def blinded(rule, card):
        return Finding(rule_id=rule.rule_id, dimension=rule.dimension,
                       target=rule.target, verdict=VERDICT_COMPLIANT,
                       effect=rule.effect, anchor=rule.anchor)

    monkeypatch.setitem(__import__("pflc.engine", fromlist=["_JUDGES"])._JUDGES,
                        "threshold", blinded)
    report = run(rules_dir, only=["detection"])
    assert report.suites[0].passed is False


def test_probe_traceability_suite_fails_when_anchor_missing(tmp_path):
    """探活：抽掉锚点条款位置 → traceability 套件必须报未达标。"""
    from tests.conftest import claim_rules, label_rules, nutrition_rules

    broken = []
    for rule in label_rules():
        item = dict(rule)
        item["anchor"] = {"doc_id": "D", "clause": ""}  # 条款位置缺失
        broken.append(item)
    write_ruleset(tmp_path / "r", label=broken, nutrition=nutrition_rules(),
                  claim=claim_rules())
    report = run(tmp_path / "r", only=["traceability"])
    assert report.suites[0].passed is False


def test_probe_detection_suite_fails_when_rule_disabled(tmp_path):
    """探活：把越限规则停用（status=pending）→ detection 必须报未达标。

    停用后越限样例不再被检出，检出率跌破门槛。
    """
    from tests.conftest import claim_rules, label_rules, nutrition_rules

    disabled = []
    for rule in nutrition_rules():
        item = dict(rule)
        item["status"] = "pending"  # 门控拦下 → 该维度零生效规则
        disabled.append(item)
    write_ruleset(tmp_path / "r", label=label_rules(), nutrition=disabled,
                  claim=claim_rules())
    report = run(tmp_path / "r", only=["detection"])
    assert report.suites[0].passed is False


def test_probe_not_enabled_when_no_cases(tmp_path):
    """探活：零规则 → not_enabled 且 exit 1（不是"恒真通过"）。"""
    from tests.conftest import write_ruleset
    write_ruleset(tmp_path / "r", label=[], nutrition=[], claim=[])
    report = run(tmp_path / "r", only=["detection"])
    assert report.suites[0].not_enabled is True
    assert report.exit_code() == EXIT_NOT_MET


# --------------------------------------------------------------------------
# 位级一致守门
# --------------------------------------------------------------------------


def test_check_cases_frozen_detects_drift(rules_dir, tmp_path):
    from pflc.benchmark import check_cases_frozen, write_cases

    target = tmp_path / "cases.json"
    write_cases(generate_cases(rules_dir), target)
    assert check_cases_frozen(target, rules_dir) is True

    # 篡改入库件 → 位级一致守门必须报不一致
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["cases"][0]["expected_overall"] = "tampered"
    with open(target, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    assert check_cases_frozen(target, rules_dir) is False
