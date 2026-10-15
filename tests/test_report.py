"""报告层测试：单一渲染源、溯源硬约束、无外链、逐字节可复现。"""

from __future__ import annotations

from pathlib import Path

import pytest

from pflc.engine import check_card
from pflc.model import (
    DIM_LABEL,
    VERDICT_NONCOMPLIANT,
    Anchor,
    CheckResult,
    DimensionResult,
    Finding,
)
from pflc.parse import parse_label
from pflc.report import (
    SEC_DISABLED,
    SEC_DISCLAIMER,
    SEC_FINDINGS,
    SEC_INPUT,
    SEC_SOURCES,
    ReportError,
    TraceabilityError,
    assert_no_external_links,
    assert_traceability,
    export,
    render_csv,
    render_markdown,
    report_sections,
)


def test_sections_contain_all_required_blocks(rules_dir, ok_label_text):
    """报告必含四块：输入事实 / 参数来源 / 逐项明细 / 免责声明。"""
    result = check_card(parse_label(ok_label_text), rules_dir)
    sections = report_sections(result)
    ids = [s.section_id for s in sections]
    assert SEC_INPUT in ids
    assert SEC_SOURCES in ids
    assert SEC_FINDINGS in ids
    assert SEC_DISCLAIMER in ids


def test_single_render_source_makes_formats_consistent(rules_dir, ok_label_text):
    """**单一渲染源**：两格式内容一致是结构性质，不靠人工比对。"""
    result = check_card(parse_label(ok_label_text), rules_dir)
    sections = report_sections(result)
    md = render_markdown(sections)
    csv_text = render_csv(sections)
    # 明细章节的每条规则 id 都应同时出现在两种格式里
    for section in sections:
        if section.section_id != SEC_FINDINGS:
            continue
        for row in section.rows:
            assert row["规则ID"] in md
            assert row["规则ID"] in csv_text


def test_traceability_assertion_rejects_half_traceability():
    """**溯源硬约束**：有结论无锚点 → 拒导（半溯源比无溯源更危险）。"""
    bad = DimensionResult(dimension=DIM_LABEL, findings=[
        Finding("R1", DIM_LABEL, "通用名", VERDICT_NONCOMPLIANT, anchor=None),
    ])
    result = CheckResult(card_id="x", dimensions=[bad])
    sections = report_sections(result)
    with pytest.raises(TraceabilityError):
        assert_traceability(sections)


def test_traceability_passes_when_all_anchored(rules_dir, ok_label_text):
    result = check_card(parse_label(ok_label_text), rules_dir)
    sections = report_sections(result)
    assert_traceability(sections)  # 不抛即通过


def test_unresolvable_anchor_also_fails_traceability():
    """锚点存在但不可解析（缺条款位置）同样算半溯源。"""
    bad = DimensionResult(dimension=DIM_LABEL, findings=[
        Finding("R1", DIM_LABEL, "x", VERDICT_NONCOMPLIANT,
                anchor=Anchor("D1", "文档", "")),
    ])
    result = CheckResult(card_id="x", dimensions=[bad])
    with pytest.raises(TraceabilityError):
        assert_traceability(report_sections(result))


def test_export_rejects_untraceable_result(tmp_path):
    bad = DimensionResult(dimension=DIM_LABEL, findings=[
        Finding("R1", DIM_LABEL, "x", VERDICT_NONCOMPLIANT, anchor=None),
    ])
    result = CheckResult(card_id="x", dimensions=[bad])
    with pytest.raises(TraceabilityError):
        export(result, tmp_path / "out")


def test_no_external_links_in_products(rules_dir, ok_label_text, tmp_path):
    """机读产物无外链——"断网可开"做成硬断言。"""
    result = check_card(parse_label(ok_label_text), rules_dir)
    paths = export(result, tmp_path / "out")
    for path in paths.values():
        assert_no_external_links(path.read_text(encoding="utf-8"))


def test_external_link_detection_flags_active_links():
    """禁的是**活动链接形态**；纯文本 URL 允许（参数来源块要能核证）。"""
    with pytest.raises(ReportError):
        assert_no_external_links("[来源](https://example.org/x)")
    with pytest.raises(ReportError):
        assert_no_external_links('<a href="https://example.org/x">来源</a>')
    with pytest.raises(ReportError):
        assert_no_external_links('<img src="https://example.org/x.png">')


def test_plain_text_url_is_allowed_in_products():
    """纯文本 URL 不产生外部依赖——断网打开照常可读。"""
    assert_no_external_links("来源URL：https://example.org/x")


def test_export_is_byte_reproducible(rules_dir, ok_label_text, tmp_path):
    """相同输入两次导出**逐字节一致**（自写 writer，产物无时间戳）。"""
    result = check_card(parse_label(ok_label_text), rules_dir)
    first = export(result, tmp_path / "a")
    second = export(result, tmp_path / "b")
    for fmt in first:
        assert first[fmt].read_bytes() == second[fmt].read_bytes()


def test_disabled_section_written_explicitly(rules_dir, ok_label_text):
    """"未启用"章节显式写出——"没查"与"查了没问题"必须可区分。"""
    result = check_card(parse_label(ok_label_text), rules_dir)
    sections = report_sections(result)
    disabled = next(s for s in sections if s.section_id == SEC_DISABLED)
    assert disabled.note  # 不留空


def test_pending_rules_appear_in_disabled_section(rules_dir, tmp_path, ok_label_text):
    from tests.conftest import label_rules, write_ruleset
    pending = {
        "rule_id": "LABEL-999", "dimension": "label", "kind": "presence",
        "target": "product_name", "status": "pending",
        "anchor": {"doc_id": "D", "clause": "X"},
    }
    write_ruleset(tmp_path / "r", label=label_rules() + [pending])
    result = check_card(parse_label(ok_label_text), tmp_path / "r")
    sections = report_sections(result)
    disabled = next(s for s in sections if s.section_id == SEC_DISABLED)
    assert any(row.get("原因码") == "LABEL-999" for row in disabled.rows)


def test_excluded_dimension_shown_in_disabled_section(rules_dir, tmp_path):
    from tests.conftest import write_ruleset
    write_ruleset(tmp_path / "r", nutrition=[])
    result = check_card(parse_label("测试粮A 猫粮 成年\n"), tmp_path / "r")
    sections = report_sections(result)
    disabled = next(s for s in sections if s.section_id == SEC_DISABLED)
    assert any(row.get("状态") == "未参与聚合" for row in disabled.rows)


def test_disclaimer_present_in_markdown(rules_dir, ok_label_text):
    from pflc.model import DISCLAIMER
    result = check_card(parse_label(ok_label_text), rules_dir)
    md = render_markdown(report_sections(result))
    assert DISCLAIMER in md


def test_sources_block_carries_provenance(rules_dir, ok_label_text):
    """参数来源块：让读者**不开仓库也能核证**数据出处。"""
    from pflc.report import load_meta
    result = check_card(parse_label(ok_label_text), rules_dir)
    sections = report_sections(result, meta=load_meta(rules_dir))
    sources = next(s for s in sections if s.section_id == SEC_SOURCES)
    assert sources.rows
    assert sources.rows[0]["来源URL"]


def test_csv_has_section_column(rules_dir, ok_label_text):
    result = check_card(parse_label(ok_label_text), rules_dir)
    csv_text = render_csv(report_sections(result))
    assert csv_text.splitlines()[0] == "章节,字段,值"


def test_export_uses_lf_line_endings(rules_dir, ok_label_text, tmp_path):
    """产物行尾一律 LF（跨平台字节一致的前提）。"""
    result = check_card(parse_label(ok_label_text), rules_dir)
    paths = export(result, tmp_path / "out")
    for path in paths.values():
        assert b"\r\n" not in path.read_bytes()
