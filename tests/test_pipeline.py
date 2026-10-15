"""编排层测试：**三方对账**（CLI 输出 == pipeline 直调 == 报告章节）。

断言的是**行为一致**，不是 ``assert "pipeline" in source`` 这种字面声明——
后者证明不了函数被调用（见 plan/03 D9）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pflc import pipeline
from pflc.model import DISCLAIMER, DIM_LABEL
from tests.conftest import write_text_lf


def test_build_card_is_pure_and_deterministic(ok_label_text):
    a = pipeline.build_card(ok_label_text, source="x")
    b = pipeline.build_card(ok_label_text, source="x")
    assert a.to_dict() == b.to_dict()


def test_check_card_result_matches_direct_engine(rules_dir, ok_label_text):
    from pflc.engine import check_card

    card = pipeline.build_card(ok_label_text)
    via_pipeline = pipeline.check_card_result(card, rules_dir)
    via_engine = check_card(card, rules_dir)
    assert via_pipeline.overall() == via_engine.overall()
    assert (sorted(f.rule_id for f in via_pipeline.all_findings())
            == sorted(f.rule_id for f in via_engine.all_findings()))


def test_check_path_matches_check_card_result(rules_dir, tmp_path, ok_label_text):
    path = write_text_lf(tmp_path / "a.txt", ok_label_text)
    from_path = pipeline.check_path(path, rules_dir)
    from_card = pipeline.check_card_result(
        pipeline.build_card(ok_label_text, source="a.txt"), rules_dir)
    assert from_path.overall() == from_card.overall()
    assert from_path.card_id == from_card.card_id


def test_three_way_reconciliation(rules_dir, tmp_path, ok_label_text, capsys):
    """**三方对账**：CLI stdout 的结论 == pipeline 字段 == 报告章节结论。"""
    from pflc.cli import main

    path = write_text_lf(tmp_path / "a.txt", ok_label_text)

    # ① pipeline 直调
    direct = pipeline.check_path(path, rules_dir)
    direct_overall = direct.overall()

    # ② 报告章节
    sections = pipeline.build_report_sections(direct, rules_dir)
    input_section = next(s for s in sections if s.section_id == "input")
    report_overall = next(r["值"] for r in input_section.rows if r["字段"] == "整体结论")

    # ③ CLI stdout
    monkeypatch_env = str(rules_dir.parent)
    import os
    old = os.environ.get("PFLC_DATA_DIR")
    os.environ["PFLC_DATA_DIR"] = monkeypatch_env
    try:
        code = main(["check", str(path)])
        captured = capsys.readouterr()
    finally:
        if old is None:
            os.environ.pop("PFLC_DATA_DIR", None)
        else:
            os.environ["PFLC_DATA_DIR"] = old

    cli_labels = {
        "compliant": "符合", "noncompliant": "不符合", "not_provided": "未提供",
        "not_assessed": "未评估",
    }
    assert direct_overall == report_overall, "pipeline 与报告章节结论不一致"
    assert ("整体结论：%s" % cli_labels.get(direct_overall, direct_overall)) in captured.out, \
        "CLI stdout 与 pipeline 结论不一致"
    assert code == 0


def test_repeated_calls_are_field_identical(rules_dir, ok_label_text):
    """同一输入两次调用**逐字段一致**（无隐藏状态/时间戳）。"""
    card = pipeline.build_card(ok_label_text)
    first = pipeline.check_card_result(card, rules_dir).to_dict()
    second = pipeline.check_card_result(card, rules_dir).to_dict()
    assert first == second


def test_diagnostics_degrades_gracefully_without_rules(empty_rules_dir):
    info = pipeline.diagnostics(empty_rules_dir)
    assert info["total_effective"] == 0
    assert info["notes"]  # 显式提示"待数据录入"
    assert len(info["dimensions"]) == 3


def test_diagnostics_reports_pending_rules(rules_dir, tmp_path):
    from tests.conftest import label_rules, write_ruleset
    pending = {
        "rule_id": "LABEL-999", "dimension": "label", "kind": "presence",
        "target": "product_name", "status": "pending",
        "anchor": {"doc_id": "D", "clause": "X"},
    }
    write_ruleset(tmp_path / "r", label=label_rules() + [pending])
    info = pipeline.diagnostics(tmp_path / "r")
    assert "LABEL-999" in info["pending_rules"]


def test_parameter_sources_from_manifest(rules_dir):
    sources = pipeline.parameter_sources(rules_dir)
    assert sources["sources"]
    assert sources["sources"][0]["doc_id"]


def test_export_report_creates_both_formats(rules_dir, tmp_path, ok_label_text):
    result = pipeline.check_path(write_text_lf(tmp_path / "a.txt", ok_label_text), rules_dir)
    paths = pipeline.export_report(result, tmp_path / "out", rules_dir)
    assert paths["markdown"].is_file()
    assert paths["csv"].is_file()


def test_disclaimer_exposed_from_pipeline():
    assert pipeline.DISCLAIMER == DISCLAIMER
    assert "不构成" in pipeline.DISCLAIMER


def test_scan_directory_returns_delta_with_baseline(rules_dir, tmp_path):
    work = tmp_path / "batch"
    work.mkdir()
    write_text_lf(work / "a.txt", "测试粮A 猫粮 成年\n原料组成：鸡肉\n")
    first = pipeline.scan_directory(work, rules_dir)
    second = pipeline.scan_directory(work, rules_dir, baseline=first["current"])
    assert "delta" in second
    assert second["delta"]["new_violation"] == []
