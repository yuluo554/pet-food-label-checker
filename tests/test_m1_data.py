"""M1 数据层守门测试：原文逐字包含、双 sha256、干基换算、门禁非空转。

**为什么这些门禁必须存在**：M1 把"规则包从 0 条变成 43 条"这件事做实，
而数据类资产（原文快照、条文块、规则包）最容易出的失效模式是
"看起来核对了、其实没核对"。每条门禁都做过**变异验证**（把被测行为
故意弄坏 → 门必须变红），见各测试的 docstring。

本模块只测"可被机器证明"的部分：
  * 条文摘录**逐字**出现在入仓原文里（不是"大意相同"）；
  * 快照 sha256 与台账登记值一致，且克隆后仍一致（``-text`` 生效）；
  * 干基限值与 as-fed 观测值**不直接比**（不同基准）；
  * 零政策字面量门禁**非空转**（真实规则包下 token 集非空）。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
TOOLS = ROOT / "tools"
CLAUSES = ROOT / "data" / "knowledge" / "clauses"
RAW = ROOT / "data" / "knowledge" / "raw"
#: 规则包随包（DEC1 = A），与条文块/原文快照不再同树
RULES = ROOT / "src" / "pflc" / "data" / "rules"


def _load_transcriber():
    """按路径加载转录器模块（tools/ 不是包，不能 import）。"""
    spec = importlib.util.spec_from_file_location(
        "transcribe_clauses_probe", TOOLS / "transcribe_clauses.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["transcribe_clauses_probe"] = module
    spec.loader.exec_module(module)
    return module


def _load_clauses(name: str):
    return json.loads((CLAUSES / name).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# 门禁一：原文逐字包含（转录器的核心断言）
# --------------------------------------------------------------------------


def test_transcriber_source_assertion_passes():
    """转录器的"原文逐字包含"断言必须通过（0 问题）。

    变异验证：把任一条 excerpt 改一个字 → 本测试必须变红。
    """
    module = _load_transcriber()
    problems = module.verify_all()
    assert problems == [], "原文核对失败：%s" % problems


def test_transcriber_is_byte_stable():
    """条文块是**冻结输入**：重新生成与入库件逐字节一致。"""
    module = _load_transcriber()
    assert module.check() is True, "条文块与转录器输出不一致（疑手改）"


def test_verbatim_assertion_is_not_vacuous():
    """**变异验证**：篡改摘录后断言必须报错（防"恒真的假断言"）。"""
    module = _load_transcriber()
    original = module._SPEC["label_spec"]
    try:
        broken = [dict(r) for r in original]
        broken[0] = dict(broken[0])
        broken[0]["excerpt"] = broken[0]["excerpt"] + "本句并不在原文中"
        module._SPEC = dict(module._SPEC)
        module._SPEC["label_spec"] = broken
        problems = module.verify_label_and_claim()
        assert problems, "篡改摘录后断言仍通过 = 假门"
        assert any("LABEL-001" in p for p in problems)
    finally:
        module._SPEC = dict(module._SPEC)
        module._SPEC["label_spec"] = original


def test_nutrition_row_assertion_is_not_vacuous():
    """**变异验证**：把限值挪到一个不含该数值的表行 → 必须报错。"""
    module = _load_transcriber()
    original = module._SPEC["nutrition_spec"]
    try:
        broken = [dict(r) for r in original]
        broken[0] = dict(broken[0])
        broken[0]["row"] = 0          # 表头行，不含任何限值
        module._SPEC = dict(module._SPEC)
        module._SPEC["nutrition_spec"] = broken
        problems = module.verify_nutrition()
        assert problems, "把限值指到错误表行后仍通过 = 假门"
    finally:
        module._SPEC = dict(module._SPEC)
        module._SPEC["nutrition_spec"] = original


# --------------------------------------------------------------------------
# 门禁二：原文快照与 sha256 台账
# --------------------------------------------------------------------------


def test_snapshot_sha256_matches_registry():
    """sources.json 登记的 sha256 必须与快照**实际字节**一致。

    登记值由转录器从文件实算（禁手填）——手填的哈希等于没有哈希。
    """
    sources = _load_clauses("sources.json")
    checked = 0
    for doc_id, entry in sorted(sources.items()):
        if doc_id.startswith("_"):
            continue
        for item in entry.get("snapshot_sha256") or []:
            path = ROOT / item["file"]
            assert path.is_file(), "登记的快照不存在：%s" % item["file"]
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            assert actual == item["sha256"], (
                "%s 的 sha256 与登记值不一致（克隆后字节被改写？）" % item["file"]
            )
            checked += 1
        if entry.get("sha256"):
            path = ROOT / entry["snapshot_file"]
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            assert actual == entry["sha256"], "%s 主快照 sha256 不一致" % doc_id
            checked += 1
    assert checked > 0, "一条 sha256 都没核对 = 门禁空转"


def test_every_verified_rule_has_snapshot_backing():
    """每条 verified 规则必须挂到**入仓快照**上（不能只在内存里核对过）。"""
    violations = []
    for name in ("label.json", "nutrition.json", "claim.json"):
        for rule in _load_clauses(name).get("rules", []):
            if rule.get("status") != "verified":
                continue
            anchor = rule.get("anchor") or {}
            if not anchor.get("sha256"):
                violations.append("%s 缺快照 sha256" % rule["rule_id"])
            if not anchor.get("clause"):
                violations.append("%s 缺条款位置" % rule["rule_id"])
    assert violations == [], "verified 条目缺溯源：%s" % violations


def test_gitattributes_marks_raw_snapshots_text_free():
    """.gitattributes 必须把 raw/ 标 -text，否则克隆后 sha256 失配。"""
    text = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "data/knowledge/raw/** -text" in text


# --------------------------------------------------------------------------
# 门禁三：零政策字面量门禁**非空转**（M1 实测勘误）
# --------------------------------------------------------------------------


def test_real_rule_pack_yields_nonempty_banned_tokens():
    """**M1 核心勘误**：真实规则包下禁用 token 集必须非空。

    M0 的豁免口径是"绝对值 < 100"——那时规则包是空的，看不出问题。
    M1 录入真实国标后，全部百分比限值落在 0.09–28，**被整包放过**，
    ``banned_numeric_tokens`` 返回空集，门禁完全空转。
    本测试锁死"非空"，防这个口径回退。
    """
    from pflc.rules import banned_numeric_tokens

    tokens = banned_numeric_tokens(RULES)
    assert tokens, "真实规则包下禁用 token 集为空 = 门禁空转（假门）"
    # 抽查一个真实限值必须在里面（28.0 是猫粮幼年粗蛋白下限）
    assert "28" in tokens, "整数形态的政策数值未收编：%s" % tokens


def test_real_gate_catches_injected_policy_value():
    """**变异验证**：把真实规则包里的政策数值写进引擎源码 → 必须命中。"""
    from pflc.rules import banned_numeric_tokens, scan_source_for_tokens

    tokens = banned_numeric_tokens(RULES)
    sample = tokens[0]
    broken = "def f(x):\n    return x >= %s\n" % sample
    hits = scan_source_for_tokens(broken, tokens)
    assert hits, "注入真实政策数值 %s 未被命中 = 假门" % sample


def test_engine_sources_have_no_policy_values_from_real_pack():
    """真实规则包的数值不得出现在引擎/工具源码里（含 docstring 与注释）。"""
    from pflc.rules import banned_numeric_tokens, scan_source_for_tokens

    tokens = banned_numeric_tokens(RULES)
    hits = []
    for root in (SRC / "pflc", TOOLS):
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            for token, lineno in scan_source_for_tokens(text, tokens):
                hits.append("%s:%d token=%s" % (path.relative_to(ROOT), lineno, token))
    assert hits == [], "源码出现真实政策数值：%s" % hits


# --------------------------------------------------------------------------
# 门禁四：干基换算（不同基准不得直接比）
# --------------------------------------------------------------------------


def test_dry_matter_conversion_is_applied():
    """**核心正确性**：干基限值必须先换算再比。

    构造一份"水分 80% 的湿粮、标示粗蛋白 10%"的标签：
    按干基算粗蛋白 = 10 / (1 - 0.8) = 50%，远高于猫粮幼年下限 28% → 达标。
    若不换算直接比，10 < 28 → 误判不符合。本测试锁死"换算真的发生了"。
    """
    from pflc.engine import check_card
    from pflc.parse import parse_label

    text = (
        "测试粮A 猫粮 幼年\n"
        "原料组成：鸡肉、糙米\n"
        "成分分析保证值：\n"
        "水分 <= 80%\n"
        "粗蛋白 >= 10%\n"
        "净含量：2kg\n"
        "生产企业：某合成宠物食品有限公司\n"
        "生产日期：2026-01-01\n"
        "保质期：18个月\n"
    )
    card = parse_label(text, source="basis-probe")
    result = check_card(card, RULES)
    finding = next(f for f in result.all_findings()
                   if f.rule_id == "NUT-CAT-001")
    assert finding.verdict == "compliant", (
        "干基换算未生效：标示 10%% 在 80%% 水分下按干基是 50%%，应达标而非 %s"
        % finding.verdict
    )
    assert "干基" in (finding.note or ""), "换算过程未在结论里留痕：%s" % finding.note


def test_missing_moisture_yields_basis_undetermined_not_a_verdict():
    """水分缺失时记 ``unknown`` + 原因码——**绝不拿未换算的值去比**。

    变异方向：若引擎在缺水分时"退化成直接比"，本测试会看到 compliant /
    noncompliant 而不是 unknown。
    """
    from pflc.engine import check_card
    from pflc.model import REASON_BASIS_UNDETERMINED
    from pflc.parse import parse_label

    text = (
        "测试粮A 猫粮 幼年\n"
        "原料组成：鸡肉、糙米\n"
        "成分分析保证值：\n"
        "粗蛋白 >= 30%\n"          # 无水分 → 无法换算
        "净含量：2kg\n"
        "生产企业：某合成宠物食品有限公司\n"
        "生产日期：2026-01-01\n"
        "保质期：18个月\n"
    )
    card = parse_label(text, source="basis-probe")
    result = check_card(card, RULES)
    finding = next(f for f in result.all_findings() if f.rule_id == "NUT-CAT-001")
    assert finding.verdict == "unknown", (
        "缺水分时不得给出 compliant/noncompliant 结论：实际 %s" % finding.verdict)
    assert finding.note == REASON_BASIS_UNDETERMINED


def test_nutrition_rules_declare_dry_matter_basis():
    """营养限值规则必须显式声明基准（干物质），否则换算无从触发。"""
    for rule in _load_clauses("nutrition.json").get("rules", []):
        assert rule.get("basis") == "dry_matter", (
            "%s 未声明 basis=dry_matter" % rule.get("rule_id"))


# --------------------------------------------------------------------------
# 门禁六：脱敏审计（含 M1 新增的原文快照豁免）
# --------------------------------------------------------------------------


def test_desensitize_audit_passes_on_tracked_files():
    """入库文件不得有未处置的 HARD 命中（`--tracked` 必须 OK）。

    变异验证：往任一源码/文档里塞一个本机用户名路径 → 本测试必须变红。
    """
    import subprocess

    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(TOOLS / "audit_desensitize.py"), "--tracked"],
        cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        encoding="utf-8", errors="replace",
    )
    assert "DESSENSITIZE_AUDIT_OK" in (proc.stdout or ""), (
        "脱敏审计未通过：\n%s" % (proc.stdout or "")[-800:])


def test_snapshot_email_exemption_is_bound_to_file_and_rule():
    """豁免**绑定到具体文件 + 具体规则名**，不是"这个文件全放过"。

    原文快照里出现的是**转载站点自己的公开联系邮箱**（第三方文档内容），
    快照纪律要求逐字保真，故按该文件 + `generic_email` 规则豁免。
    本测试断言豁免边界：同样的邮箱换个文件仍会被判 REVIEW。
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "audit_probe", TOOLS / "audit_desensitize.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["audit_probe"] = module
    spec.loader.exec_module(module)

    exempt_path = "data/knowledge/raw/moa-20-2018-annex3/reprint-feedchina.txt"
    assert module._is_exempt(exempt_path, "generic_email"), "快照豁免未生效"
    # 同一文件的其他规则**不受**豁免
    assert not module._is_exempt(exempt_path, "long_hex"), "豁免被过度放宽到其他规则"
    # 同样内容换个文件 → 必须照常命中（证明豁免不是"全放过"）
    assert not module._is_exempt("src/pflc/engine/__init__.py", "generic_email"), \
        "豁免被过度放宽到其他文件 = 假豁免"


def test_decimal_rendering_has_no_scientific_notation():
    """``Decimal.normalize()`` 会产出 ``3E+1``——报告与夹具都读不出来。

    变异验证：若退回 ``str(value.normalize())``，本测试必须变红。
    """
    from pflc.model import format_decimal

    cases = {"30": "30", "30.0": "30", "28.0": "28", "0.45": "0.45",
             "150": "150", "0.09": "0.09", "22.0": "22"}
    for raw, expected in sorted(cases.items()):
        assert format_decimal(Decimal(raw)) == expected, (
            "Decimal(%s) 渲染成 %s，期望 %s"
            % (raw, format_decimal(Decimal(raw)), expected))
    # 反例锚点：normalize 确实会产 E 记号，说明这个门禁不是无的放矢
    assert "E" in str(Decimal("30").normalize())


def test_single_char_indicator_names_parse():
    """单字指标名（钙/磷）必须能解析——别名表列了它们，正则就不能漏。"""
    from pflc.parse import parse_label

    card = parse_label(
        "测试粮A 猫粮 幼年\n成分分析保证值：\n钙 >= 1%\n磷 >= 0.8%\n")
    assert "钙" in card.guaranteed, "单字指标『钙』未解析（别名表与正则不一致）"
    assert "总磷" in card.guaranteed, "单字指标『磷』未解析"
