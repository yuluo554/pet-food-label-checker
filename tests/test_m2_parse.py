"""M2 解析层守门：FR-01 字段全覆盖 + 四类合法性校验 + 边界输入确定性。

**为什么单开一份**（而不是往 test_parse.py 里塞）：M2 的四条缺口全是 M1 实测
发现的**回归**——每一条都对应一个"曾经会静默产出假结论"的失效模式。
它们需要"变异验证"式的断言（把被测行为故意弄坏 → 测试必须变红），
与 test_parse.py 的基础正向断言是两类东西。

四条缺口的失效模式（见 plan/HANDOFF-M2 §三）：

  * 宣称词表硬编码在解析层 → 规则包加一条宣称而解析层不认 → 永远"未宣称"
    → 规则判 ``skipped`` = **假 skipped**（把"没抽过"读成"没宣称"）；
  * 生命阶段别名表混入产品类型词（``全价``）→ 正常标签被判"阶段歧义"
    → 营养维度**整维度 not_assessed**（一条规则都不适用）；
  * 净含量未知单位落 ``not_found`` → 把"写了但单位不认识"和"根本没写"混同；
  * 日期不校验合法性 → ``2026-13-45`` 被当有效日期喂进判定路径。
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from pflc.model import (
    REASON_MAPPING_UNCERTAIN,
    REASON_NOT_FOUND,
    REASON_OUT_OF_RANGE,
)
from pflc.parse import parse_label

#: 与真实规则包 claim 维度 target 集一致的词表（规则包 target 就是宣称词面）
CLAIM_VOCAB = ("天然", "无谷", "无添加", "纯天然", "鲜肉")


# --------------------------------------------------------------------------
# 缺口一：宣称词表来自规则包（单一口径）
# --------------------------------------------------------------------------


def test_claim_vocabulary_comes_from_rule_pack(tmp_path):
    """**头号任务**：词表从规则包实算，规则包加一条 → 解析层能抽出来。

    变异方向：若解析层还留着自己的硬编码词表，新词 ``植物基`` 永远不会被抽出，
    本测试会看到 ``claim_names() == []``。
    """
    from pflc.rules import claim_vocabulary
    from tests.conftest import claim_rules, write_ruleset

    new_rule = {
        "rule_id": "CLAIM-099", "dimension": "claim", "kind": "claim_support",
        "target": "植物基", "effect": "obligation",
        "required_support": ["ingredients"],
        "status": "verified", "clause_status": "verified",
        "anchor": {"doc_id": "D", "clause": "第二十条"},
    }
    rules = tmp_path / "r"
    write_ruleset(rules, claim=claim_rules() + [new_rule])

    vocab = claim_vocabulary(rules)
    assert "植物基" in vocab, "规则包新增的宣称词面未进词表：%s" % (vocab,)

    card = parse_label("测试粮A 猫粮 成年\n产品特点：植物基\n",
                       claim_words=vocab)
    assert "植物基" in card.claim_names(), (
        "规则包加了宣称而解析层抽不出来 = 两份口径漂移（该宣称永远判假 skipped）"
    )


def test_claim_vocabulary_is_sorted_and_deduplicated(tmp_path):
    """词表排序去重——顺序不确定会让档案逐字节不可复现。"""
    from pflc.rules import claim_vocabulary
    from tests.conftest import write_ruleset

    dup = [
        {"rule_id": "C-1", "dimension": "claim", "kind": "claim_support",
         "target": "天然", "status": "verified", "clause_status": "verified"},
        {"rule_id": "C-2", "dimension": "claim", "kind": "claim_support",
         "target": "天然", "status": "verified", "clause_status": "verified"},
        {"rule_id": "C-3", "dimension": "claim", "kind": "claim_support",
         "target": "无谷", "status": "verified", "clause_status": "verified"},
    ]
    rules = write_ruleset(tmp_path / "r", claim=dup)
    vocab = claim_vocabulary(rules)
    assert list(vocab) == sorted(set(vocab))
    assert vocab == ("天然", "无谷")


def test_claim_vocabulary_includes_pending_rules(tmp_path):
    """pending 宣称规则不进判定路径，但**词面仍要抽出来记进档案**。

    否则"规则待核对"期间该宣称在报告里凭空消失，等它转 verified 时
    已无从判断"当时到底有没有宣称"。
    """
    from pflc.rules import claim_vocabulary
    from tests.conftest import write_ruleset

    pending_rule = {
        "rule_id": "CLAIM-P", "dimension": "claim", "kind": "claim_support",
        "target": "处方", "status": "pending", "clause_status": "pending",
    }
    rules = write_ruleset(tmp_path / "r", claim=[pending_rule])
    assert "处方" in claim_vocabulary(rules)


def test_dispatch_point_reconciles_vocabulary(rules_dir):
    """**假 skipped 的根治**：直接 ``parse_label`` 造的空词表档案，
    经唯一分派点判定后仍须抽出宣称——否则规则判 skipped。

    变异方向：去掉 ``_reconcile_claim_vocabulary``，本测试会看到
    CLAIM-001 的结论从 noncompliant/compliant 退化成 skipped。
    """
    from pflc.engine import check_card
    from pflc.model import VERDICT_SKIPPED

    # 不传词表 → claim_vocab=()，档案里一条宣称都没有
    card = parse_label("测试粮A 猫粮 成年\n产品特点：天然\n原料组成：鸡肉\n")
    assert card.claim_names() == []

    result = check_card(card, rules_dir)
    finding = next(f for f in result.all_findings() if f.rule_id == "CLAIM-001")
    assert finding.verdict != VERDICT_SKIPPED, (
        "直接 parse_label 造的档案经分派点后仍判 skipped = 假 skipped"
    )
    # 宣称存在且原料组成齐备 → 支撑齐备 → compliant
    assert finding.verdict == "compliant"


def test_dispatch_point_reconciliation_does_not_invent_claims(rules_dir):
    """重抽**只按 raw_text 实抽**，绝不凭空造宣称（不是"有规则就算宣称"）。"""
    from pflc.engine import check_card
    from pflc.model import VERDICT_SKIPPED

    card = parse_label("测试粮A 猫粮 成年\n原料组成：鸡肉\n")   # 无宣称
    result = check_card(card, rules_dir)
    assert next(f for f in result.all_findings()
                if f.rule_id == "CLAIM-001").verdict == VERDICT_SKIPPED


# --------------------------------------------------------------------------
# 缺口二：生命阶段不再因产品类型词误判歧义
# --------------------------------------------------------------------------


def test_product_type_word_does_not_cause_stage_ambiguity():
    """``全价`` 是**产品类型词**不是生命阶段词——不得进阶段别名表。

    变异方向：把 ``"全价": "全阶段"`` 加回 ``LIFE_STAGE_ALIASES``，
    本测试会看到 mapping_uncertain（"全价"与"幼年"同时命中）。
    """
    card = parse_label(
        "测试粮A 猫粮 幼年\n产品名称：测试粮A全价幼猫粮\n原料组成：鸡肉\n",
        claim_words=CLAIM_VOCAB)
    assert card.life_stage.is_provided, (
        "『全价』被当成生命阶段 → 阶段歧义：%s" % card.life_stage.render())
    assert card.life_stage.value == "幼年"


def test_product_type_word_is_not_a_claim():
    """``全价`` 也不得被当成宣称词（那是产品类型，不是特性声称）。"""
    card = parse_label("测试粮A 猫粮 幼年\n产品名称：测试粮A全价幼猫粮\n",
                       claim_words=CLAIM_VOCAB)
    assert "全价" not in card.claim_names()


def test_real_stage_ambiguity_still_detected():
    """真·多阶段命中仍必须判歧义——修正不能顺手把这条也放过。"""
    card = parse_label("测试粮A 猫粮 幼年 成年\n", claim_words=CLAIM_VOCAB)
    assert not card.life_stage.is_provided
    assert card.life_stage.reason == REASON_MAPPING_UNCERTAIN


def test_full_stage_word_still_recognized():
    """真·全阶段词面（全阶段/全年龄/各阶段）仍须认出来。"""
    for word in ("全阶段", "全年龄", "各阶段"):
        card = parse_label("测试粮A 猫粮 %s\n" % word, claim_words=CLAIM_VOCAB)
        assert card.life_stage.value == "全阶段", word


def test_no_product_type_word_left_in_stage_aliases():
    """结构性断言：阶段别名表里不得再出现产品类型词。

    这条防的是"修完又被加回去"——比逐个文本断言更能覆盖后续新增词面。
    """
    from pflc.parse import LIFE_STAGE_ALIASES

    forbidden = ("全价", "全价粮", "处方", "处方粮")
    leaked = [w for w in forbidden if w in LIFE_STAGE_ALIASES]
    assert leaked == [], "产品类型词混进了生命阶段别名表：%s" % leaked


# --------------------------------------------------------------------------
# 缺口三：净含量未知单位 → mapping_uncertain（不是 not_found）
# --------------------------------------------------------------------------


def test_unknown_net_content_unit_is_mapping_uncertain():
    """``2oz``：有值、有单位、但单位不认识 → mapping_uncertain。

    变异方向：把单位写进正则白名单（旧实现），本测试会看到 not_found——
    把"写了但单位不认识"与"根本没写"混同。
    """
    card = parse_label("测试粮A 猫粮 成年\n净含量：2oz\n", claim_words=CLAIM_VOCAB)
    assert not card.net_content.is_provided
    assert card.net_content.reason == REASON_MAPPING_UNCERTAIN


def test_missing_net_content_is_not_found():
    """真的没写 → not_found（与"单位不认识"必须可区分）。"""
    card = parse_label("测试粮A 猫粮 成年\n原料组成：鸡肉\n",
                       claim_words=CLAIM_VOCAB)
    assert card.net_content.reason == REASON_NOT_FOUND


@pytest.mark.parametrize("text,value,unit", [
    ("净含量：2kg", "2", "kg"),
    ("净含量：500g", "500", "g"),
    ("净含量：1.5L", "1.5", "L"),
    ("净含量：500毫升", "500", "毫升"),
    ("净含量：1斤", "1", "斤"),
])
def test_known_net_content_units_still_parse(text, value, unit):
    """正向对照：已知单位仍须正常解析（修正不能把好路径也堵了）。"""
    card = parse_label("测试粮A 猫粮 成年\n%s\n" % text, claim_words=CLAIM_VOCAB)
    assert card.net_content.is_provided
    assert card.net_content.value == Decimal(value)
    assert card.net_content.unit == unit


def test_net_unit_match_is_longest_first():
    """``2kg`` 不得被读成 ``2 g``（最长优先）——否则值凭空缩小一千倍。"""
    card = parse_label("测试粮A 猫粮 成年\n净含量：2kg\n", claim_words=CLAIM_VOCAB)
    assert card.net_content.unit == "kg"
    assert card.net_content.value == Decimal("2")


# --------------------------------------------------------------------------
# 缺口四：日期合法性校验
# --------------------------------------------------------------------------


@pytest.mark.parametrize("bad_date", ["2026-13-45", "2026-13-01", "2026-00-10",
                                      "2026-01-32", "2026-02-30"])
def test_illegal_date_is_rejected(bad_date):
    """非法日期（月>12 / 日>31 / 组合不存在）→ ``out_of_range``。

    变异方向：去掉 ``_valid_date`` 调用，``2026-13-45`` 会被当有效日期呈现。
    """
    card = parse_label("测试粮A 猫粮 成年\n生产日期：%s\n" % bad_date,
                       claim_words=CLAIM_VOCAB)
    assert not card.product_dates.is_provided
    assert card.product_dates.reason == REASON_OUT_OF_RANGE


@pytest.mark.parametrize("good_date", ["2026-01-01", "2026/12/31", "2026年2月28日",
                                       "2024-02-29"])
def test_legal_date_accepted(good_date):
    """合法日期仍须正常解析（含闰年 2 月 29）。"""
    card = parse_label("测试粮A 猫粮 成年\n生产日期：%s\n" % good_date,
                       claim_words=CLAIM_VOCAB)
    assert card.product_dates.is_provided
    assert "非法" not in str(card.product_dates.value)


def test_illegal_date_keeps_evidence_of_both_parts():
    """日期非法 → 字段降级，但**抽到的原文片段全部留在 evidence 里**可核。

    降级不等于把发现到的东西抹掉：保质期那半截也得能看见。
    """
    card = parse_label("测试粮A 猫粮 成年\n生产日期：2026-13-45\n保质期：18个月\n",
                       claim_words=CLAIM_VOCAB)
    assert not card.product_dates.is_provided
    assert card.product_dates.reason == REASON_OUT_OF_RANGE
    assert "非法" in (card.product_dates.evidence or "")
    assert "18" in (card.product_dates.evidence or "")


def test_illegal_date_never_reads_as_compliant(rules_dir):
    """**假合规防线**：日期非法时，存在性规则不得判 compliant。

    变异方向：若非法日期仍记"已提供"，LABEL-005（product_dates 无条件义务）
    会判 compliant——把一处真实标示缺陷读成合规。
    """
    from pflc.engine import check_card
    from pflc.model import VERDICT_NONCOMPLIANT

    card = parse_label("测试粮A 猫粮 成年\n原料组成：鸡肉\n"
                       "净含量：2kg\n生产企业：某公司\n生产日期：2026-13-45\n",
                       claim_words=CLAIM_VOCAB)
    result = check_card(card, rules_dir)
    finding = next(f for f in result.all_findings() if f.rule_id == "LABEL-005")
    assert finding.verdict == VERDICT_NONCOMPLIANT, (
        "非法日期被读成合规：结论 %s" % finding.verdict)


def test_date_rendering_is_zero_padded_and_stable():
    """日期渲染补齐两位——``2026-1-1`` 与 ``2026-01-01`` 必须同一形态。"""
    a = parse_label("测试粮A 猫粮 成年\n生产日期：2026-1-1\n", claim_words=CLAIM_VOCAB)
    b = parse_label("测试粮A 猫粮 成年\n生产日期：2026-01-01\n", claim_words=CLAIM_VOCAB)
    assert a.product_dates.value == b.product_dates.value


# --------------------------------------------------------------------------
# FR-01 字段矩阵：逐字段正负例（含原因码断言）
# --------------------------------------------------------------------------

#: FR-01 的字段清单（见 plan/02 FR-01 交付物列）
FR01_FIELDS = ("product_name", "category", "life_stage", "ingredients",
               "additives", "net_content", "producer", "product_dates")

#: 一个"每字段都写全"的标签（正例基线）
FULL_LABEL = (
    "测试粮A 猫粮 幼年\n"
    "产品名称：测试粮A幼猫粮\n"
    "原料组成：鸡肉、糙米、鱼油\n"
    "添加剂：维生素A、维生素D3\n"
    "成分分析保证值：\n"
    "水分 <= 12%\n"
    "粗蛋白 >= 30%\n"
    "净含量：2kg\n"
    "生产企业：某合成宠物食品有限公司\n"
    "生产日期：2026-01-01\n"
    "保质期：18个月\n"
)


def test_fr01_every_field_extracted_on_full_label():
    """正例：字段清单里每个字段都能从"写全"的标签上抽出来。"""
    card = parse_label(FULL_LABEL, claim_words=CLAIM_VOCAB)
    missing = []
    for name in FR01_FIELDS:
        field = card.field(name)
        if field is None or not field.is_provided:
            missing.append(name)
    assert missing == [], "FR-01 字段未抽出：%s" % missing
    # 保证值键值对与宣称也须抽到
    assert "粗蛋白" in card.guaranteed
    assert card.guaranteed["粗蛋白"].value == Decimal("30")


def test_fr01_every_field_absent_reports_reason_code():
    """负例：**每个** FR-01 字段缺失时都要有原因码，且不得是"猜出来的值"。

    这是"解析不到 = 显式降级"的逐字段落地——任何一个字段缺失却没有原因码，
    报告里就会出现"未提供()"，与"没做"无从区分。
    """
    card = parse_label("", claim_words=CLAIM_VOCAB)
    for name in FR01_FIELDS:
        field = card.field(name)
        assert field is not None, "字段 %s 不在档案里" % name
        assert not field.is_provided, "空文本不该抽出 %s" % name
        assert field.reason, "字段 %s 缺失但无原因码" % name
    # 保证值：空文本下一条指标都没有（不是"抽出但未提供"）
    assert card.guaranteed == {}


def test_fr01_missing_fields_listed_for_report():
    """缺失清单与原因码一致——报告"未提供清单"取自同一处。

    该文本里有通用名（首行回退）、类别（猫粮）、阶段（成年），故这三个字段是
    **已提供**的；清单里只该出现真正缺的那些，且每个都要带原因码。
    """
    card = parse_label("测试粮A 猫粮 成年\n", claim_words=CLAIM_VOCAB)
    # 已提供的三个字段不得出现在缺失清单里
    for name in ("product_name", "category", "life_stage"):
        assert card.field(name).is_provided, name
        assert name not in card.unparsed, "%s 已提供却进了缺失清单" % name
    # 缺失清单非空，且每个条目都带原因码
    assert card.unparsed
    for name in card.unparsed:
        field = card.field(name)
        assert field is not None, "缺失清单里的 %s 在档案里查不到" % name
        assert field.reason, "未提供字段 %s 无原因码" % name


# --------------------------------------------------------------------------
# 确定性守门：新增字段 + 边界输入
# --------------------------------------------------------------------------


def test_same_text_same_card_bytes_including_new_fields():
    """同一文本 → 同一档案逐字节一致（含 M2 新增的 claim_vocab / 日期形态）。"""
    a = parse_label(FULL_LABEL, source="x.txt", claim_words=CLAIM_VOCAB).to_dict()
    b = parse_label(FULL_LABEL, source="x.txt", claim_words=CLAIM_VOCAB).to_dict()
    assert a == b


def test_determinism_on_boundary_inputs():
    """边界输入（空文本 / 纯噪声 / 超长行 / 全角半角混排）也要逐字节一致。

    这些输入是解析层最容易出非确定行为的地方（正则回溯、字典序、编码归一）。
    """
    boundary_inputs = [
        "",
        "\n\n\n",
        "。，、；！？",
        "   \t  \n \n",
        "测试粮A 猫粮 成年\n" + ("粗蛋白 >= 30%\n" * 200),
        "测试粮Ａ 猫粮 幼年\n粗蛋白：\uFF13\uFF10％\n净含量：２ｋｇ\n",
        "粗蛋白" + ("A" * 5000) + " 30%\n",
        "\u0000\u0001\u0002" * 100,
        "测试粮A\r\n粗蛋白 >= 30%\r\n净含量：2kg\r\n",
    ]
    for text in boundary_inputs:
        a = parse_label(text, source="b", claim_words=CLAIM_VOCAB).to_dict()
        b = parse_label(text, source="b", claim_words=CLAIM_VOCAB).to_dict()
        assert a == b, "边界输入非确定：%r" % text[:40]


def test_card_id_is_content_keyed_not_source_keyed():
    """稳定身份键按**内容**算，不按文件名——改名不该表现为"新增 + 消失"。"""
    a = parse_label(FULL_LABEL, source="a.txt", claim_words=CLAIM_VOCAB)
    b = parse_label(FULL_LABEL, source="b.txt", claim_words=CLAIM_VOCAB)
    assert a.card_id == b.card_id


def test_different_vocabularies_are_different_cards():
    """词表不同 → 档案不同（口径随词表走，"逐字节一致"才有意义）。

    反例：若 ``to_dict`` 不导出词表，两份**抽出内容不同**的档案会在
    ``claim_vocab`` 之外看起来一样，对账时无从分辨"当时按哪套口径抽的"。
    """
    text = "测试粮A 猫粮 成年\n产品特点：天然、植物基\n"
    narrow = parse_label(text, claim_words=("天然",))
    wide = parse_label(text, claim_words=("天然", "植物基"))
    assert narrow.claim_names() == ["天然"]
    assert wide.claim_names() == ["天然", "植物基"]
    assert narrow.to_dict() != wide.to_dict()


def test_vocabulary_order_does_not_change_claims():
    """词表顺序不影响抽取结果（排序去重后的元组，故档案逐字节一致）。"""
    forward = parse_label("测试粮A 猫粮 成年\n产品特点：天然、无谷\n",
                          claim_words=("天然", "无谷"))
    backward = parse_label("测试粮A 猫粮 成年\n产品特点：天然、无谷\n",
                           claim_words=("无谷", "天然"))
    assert forward.claim_names() == backward.claim_names()


# --------------------------------------------------------------------------
# 夹具覆盖 FR-01 每字段（常驻回归门）
# --------------------------------------------------------------------------

#: 仓库夹具目录（由 tools/gen_samples.py 产出并纳入位级一致守门）
SAMPLES_DIR = Path(__file__).resolve().parent.parent / "data" / "samples"


def test_fixtures_cover_every_fr01_field():
    """**夹具必须覆盖 FR-01 的每个字段**（不要求每份夹具都写全，合起来要齐）。

    M1 的 4 份夹具偏重缺失/越限场景，字段覆盖是"碰巧齐了"而不是"被守着齐"。
    这条门禁把它变成结构性保证：新加字段而夹具没跟上 → 门变红。
    """
    from pflc.rules import claim_vocabulary

    rules_dir = SAMPLES_DIR.parent / "rules"
    vocab = claim_vocabulary(rules_dir)

    files = sorted(SAMPLES_DIR.glob("*.txt"))
    assert files, "夹具目录为空 = 门禁空转"

    union = set()
    for path in files:
        card = parse_label(path.read_text(encoding="utf-8"),
                           source=path.name, claim_words=vocab)
        for name in FR01_FIELDS:
            if card.field(name) is not None and card.field(name).is_provided:
                union.add(name)

    missing = [name for name in FR01_FIELDS if name not in union]
    assert missing == [], "没有任何夹具覆盖这些 FR-01 字段：%s" % missing


def test_edge_fixture_exercises_the_four_m2_gaps():
    """边界夹具必须真的把四处缺口摆出来——否则它只是"多一份文件"。

    变异方向：把任一修复回退（如把 ``全价`` 加回阶段别名表），
    本测试会在对应断言上变红。
    """
    from pflc.rules import claim_vocabulary

    path = SAMPLES_DIR / "label-demo-edge.txt"
    assert path.is_file(), "缺边界夹具 label-demo-edge.txt"
    card = parse_label(path.read_text(encoding="utf-8"), source=path.name,
                       claim_words=claim_vocabulary(SAMPLES_DIR.parent / "rules"))

    # ① "全价"与"幼年"同现 → 仍须判出真阶段（不是歧义）
    assert card.life_stage.value == "幼年", (
        "边界夹具未复现缺口一：%s" % card.life_stage.render())
    # ② 未知单位 oz → mapping_uncertain（不是 not_found）
    assert card.net_content.reason == REASON_MAPPING_UNCERTAIN, (
        "边界夹具未复现缺口三：%s" % card.net_content.render())
    # ③ 非法日期 → out_of_range
    assert card.product_dates.reason == REASON_OUT_OF_RANGE, (
        "边界夹具未复现缺口四：%s" % card.product_dates.render())
    # ④ "全价"未被当成宣称
    assert "全价" not in card.claim_names()
