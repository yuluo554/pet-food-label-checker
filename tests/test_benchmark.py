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
from pflc.rules import RulePackError, load_pack
from tests.conftest import write_ruleset

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"

#: 真值库入库位（数据布局：data/rules 与 data/benchmark 同级）
SHIPPED_CASES = ROOT / "data" / "benchmark" / "cases.json"


def load_pack_file(dimension: str):
    """加载**仓库里**的规则包（非夹具），供覆盖登记对账用。"""
    return load_pack(dimension, ROOT / "data" / "rules")


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


def test_probe_overall_suite_fails_when_engine_aggregation_is_blinded(
        rules_dir, monkeypatch):
    """探活：把**引擎的维度聚合**弄成看不见不符合 → overall 套件必须报未达标。

    本条的来历（M4 实测）：`overall` 套件曾**没有任何探活**——把 `run_overall`
    的 `passed` 改成恒真、或把比较改成恒真，**231 项测试全绿**（对照组改
    `run_boundary` 立刻变红）。那就是一道永绿门。

    **注入方向要对**：`overall` 是**样本驱动**套件，期望锚定冻结真值库。
    改规则数值不会让它变红（真值与规则一起变），故能证伪它的是
    "**引擎聚合算错了**"——这里注入"维度永远看不见 noncompliant"的引擎缺陷。
    弄坏后仍绿 = 假门。
    """
    from pflc.model import DimensionResult

    monkeypatch.setattr(DimensionResult, "has_noncompliant", lambda self: False)
    report = run(rules_dir, only=["overall"])
    assert report.suites[0].passed is False
    assert report.exit_code() == EXIT_NOT_MET


def test_probe_overall_suite_is_green_when_engine_is_correct(rules_dir):
    """阳性对照：引擎正常时 overall 必须绿——证明上面那条探活不是"永远红"。

    没有对照组时，"改坏了变红"可能只是因为手法本身无效（变异没生效）。
    """
    report = run(rules_dir, only=["overall"])
    assert report.suites[0].passed is True


def test_probe_overall_suite_fails_when_truth_expectation_is_tampered(rules_dir):
    """探活（第二条独立注入方向）：**真值库期望被篡改** → 必须响。

    与"引擎算错"是两个不同的失效来源：真值库本身漂移了同样会让评测失真。
    处置是**冻结守门先拦**（``BenchConfigError``）——真值漂移必须响，
    绝不"拿一份与当前规则包不符的旧真值静默继续跑"。
    """
    from pflc.benchmark import cases_path_for, load_cases

    target = cases_path_for(rules_dir)
    _write_frozen_library(rules_dir)
    payload = load_cases(target)
    payload["cases"][0]["expected_overall"] = "tampered"
    with open(target, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")

    with pytest.raises(BenchConfigError):
        run(rules_dir, only=["overall"])


# --------------------------------------------------------------------------
# 冻结真值库：入库件被真的读、且有"入库件 == 生成器输出"守门
# --------------------------------------------------------------------------


def _write_frozen_library(rules_dir):
    """把生成器输出落到真值库入库位（与``gen_cases.py --force``同一条路）。"""
    from pflc.benchmark import cases_path_for, write_cases

    target = cases_path_for(rules_dir)
    write_cases(generate_cases(rules_dir), target)
    return target


def test_bench_reads_frozen_truth_library_when_present(rules_dir):
    """基准的期望来源是**入库件**（``truth_source=frozen``），不是现场重算。

    M4 实测的旧实现每次跑基准都现场算真值，``load_cases`` / ``check_cases_frozen``
    在全仓**零调用**——"冻结真值库"是个没人读的文件。本测试锁死它被真的读。
    """
    from pflc.benchmark import TRUTH_SOURCE_FROZEN, cases_path_for

    assert not cases_path_for(rules_dir).is_file()  # 前置：夹具目录里没有入库件
    _write_frozen_library(rules_dir)

    report = run(rules_dir, only=["overall"])
    assert report.suites[0].metrics["truth_source"] == TRUTH_SOURCE_FROZEN
    assert report.suites[0].passed is True


def test_bench_marks_regenerated_when_no_frozen_library(rules_dir):
    """无入库件时回落生成器（生成器是唯一真值源），并**如实标记来源**。

    回落不算错，但"来源"必须在输出里可见——否则"到底读了什么"无从核证。
    """
    from pflc.benchmark import TRUTH_SOURCE_REGENERATED, cases_path_for

    assert not cases_path_for(rules_dir).is_file()
    report = run(rules_dir, only=["detection"])
    assert report.suites[0].metrics["truth_source"] == TRUTH_SOURCE_REGENERATED


def test_bench_rejects_frozen_library_that_drifted_from_generator(rules_dir):
    """**可证伪性证明**：入库件与生成器输出不符 → 配置错误（exit 2），不静默重算。

    这条同时证明了"入库件被真的读了"——若基准根本不看这个文件，
    篡改它不会引发任何反应（旧实现正是如此）。
    """
    from pflc.benchmark import cases_path_for, load_cases

    target = cases_path_for(rules_dir)
    _write_frozen_library(rules_dir)
    payload = load_cases(target)
    payload["cases"][0]["text"] = payload["cases"][0]["text"] + "篡改\n"
    with open(target, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")

    with pytest.raises(BenchConfigError):
        run(rules_dir, only=["detection"])


# --------------------------------------------------------------------------
# 载入侧品牌白名单（K18 的第二个实例）
# --------------------------------------------------------------------------


def test_load_cases_rejects_real_brand(rules_dir):
    """**载入侧硬断言**：手改入库件掺入真实品牌名 → 载入即报错。

    M4 实测的旧实现：白名单只在**生成侧**生效，``load_cases`` 原样接受含
    真实品牌的真值库——一旦入库件被手改或未来支持外部真值库，真实品牌数据
    就能绕过白名单进入合成基准，与"真实品牌数据与合成基准严格隔离"冲突。
    """
    from pflc.benchmark import BrandWhitelistError, cases_path_for, load_cases

    target = cases_path_for(rules_dir)
    _write_frozen_library(rules_dir)
    payload = json.loads(target.read_text(encoding="utf-8"))
    first = payload["cases"][0]
    first["text"] = "某真实品牌 猫粮 成年\n" + first["text"].split("\n", 1)[1]
    with open(target, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")

    with pytest.raises(BrandWhitelistError):
        load_cases(target)


def test_load_cases_rejects_whitelist_mismatch(rules_dir):
    """声明的白名单与生成器白名单不一致 → 报错（不许"自带一套白名单"）。"""
    from pflc.benchmark import BrandWhitelistError, cases_path_for, load_cases

    target = cases_path_for(rules_dir)
    _write_frozen_library(rules_dir)
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["brand_whitelist"] = ["某真实品牌"]
    with open(target, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")

    with pytest.raises(BrandWhitelistError):
        load_cases(target)


def test_shipped_truth_library_loads_and_passes_whitelist():
    """阳性对照：**入库的那份**真值库能正常载入且品牌全在白名单内。"""
    from pflc.benchmark import BRAND_WHITELIST, load_cases

    target = SHIPPED_CASES
    assert target.is_file(), "真值库未入仓：%s" % target
    payload = load_cases(target)  # 载入即含白名单断言，不抛即通过
    assert payload["cases"], "真值库用例为空"
    for case in payload["cases"]:
        assert case["text"].split()[0] in BRAND_WHITELIST


# --------------------------------------------------------------------------
# 覆盖登记（manifest.coverage）——与冻结真值库同源
# --------------------------------------------------------------------------


def test_coverage_sampled_count_comes_from_truth_library():
    """覆盖登记的"采样数/清单"由**冻结真值库实算**，且与清单长度自洽。

    手写清单必然漂移——本项目实测的旧台账正是 `sampled_in_truth=null` +
    `sample_list=[]`。
    """
    from pflc.benchmark import coverage_from_cases, load_cases

    cases = load_cases(SHIPPED_CASES)
    packs = {dim: load_pack_file(dim) for dim in ("label", "nutrition", "claim")}
    computed = coverage_from_cases(cases, packs)

    manifest = json.loads(
        (ROOT / "data" / "rules" / "manifest.json").read_text(encoding="utf-8"))
    for dim, block in computed.items():
        shipped = manifest["coverage"][dim]
        assert shipped["sampled_in_truth"] == block["sampled_in_truth"] == len(
            block["sample_list"])
        assert shipped["sample_list"] == block["sample_list"]
        assert shipped["total_rules"] == block["total_rules"]
        assert shipped["note"] == block["note"]


def test_coverage_sampled_count_is_not_vacuous():
    """**采样数不得恒等于生效规则总数**——那是"触达口径"，等于没登记。

    合规类用例虽逐条判了全部生效规则，但 `expected_findings` 是 `{}`
    （无显式期望），故采样数必须**严格小于**生效规则数。若哪天相等，
    说明口径被换成了"触达"——那个数永远 100%，不携带信息 = 又一个假台账。
    """
    from pflc.benchmark import coverage_from_cases, load_cases

    cases = load_cases(SHIPPED_CASES)
    packs = {dim: load_pack_file(dim) for dim in ("label", "nutrition", "claim")}
    computed = coverage_from_cases(cases, packs)

    for dim, block in computed.items():
        assert block["sampled_in_truth"] > 0, "%s 采样数为 0 = 空转" % dim
        effective = len(packs[dim].effective())
        assert block["sampled_in_truth"] < effective, (
            "%s 采样数 %d >= 生效规则数 %d：口径退化成“触达”，登记失去意义"
            % (dim, block["sampled_in_truth"], effective))


def test_coverage_raises_when_truth_references_unknown_rule():
    """真值库引用了规则包里不存在的规则 → 报错（真值与规则包脱钩必须响）。"""
    from pflc.benchmark import coverage_from_cases, load_cases

    cases = load_cases(SHIPPED_CASES)
    cases = json.loads(json.dumps(cases))
    cases["cases"][0]["expected_findings"]["NOPE-999"] = "noncompliant"
    packs = {dim: load_pack_file(dim) for dim in ("label", "nutrition", "claim")}

    with pytest.raises(RulePackError):
        coverage_from_cases(cases, packs)


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
