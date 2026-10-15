"""解析层测试：确定性、三态降级、合法性校验、歧义不猜。"""

from __future__ import annotations

from decimal import Decimal

from pflc.model import (
    REASON_MAPPING_UNCERTAIN,
    REASON_NOT_FOUND,
    REASON_OUT_OF_RANGE,
)
from pflc.parse import (
    convert_mass_to_gram,
    normalize_text,
    parse_label,
)


def test_same_text_same_card_bytes(ok_label_text):
    """同一文本 → 同一档案（逐字节一致）——确定性守门。"""
    a = parse_label(ok_label_text, source="x.txt").to_dict()
    b = parse_label(ok_label_text, source="x.txt").to_dict()
    assert a == b


def test_normalize_handles_crlf_and_fullwidth():
    raw = "测试粮A\r\n粗蛋白：\uFF13\uFF10%\r\n"
    text = normalize_text(raw)
    assert "\r" not in text
    assert "30%" in text  # 全角数字已归一


def test_normalize_maps_fullwidth_operators():
    assert ">=" in normalize_text("粗蛋白\u226530%")
    assert "<=" in normalize_text("水分\u226412%")


def test_category_ambiguous_is_not_guessed():
    """同时命中犬与猫 → mapping_uncertain，**绝不猜一个**。"""
    card = parse_label("测试粮 犬粮 猫粮\n")
    assert not card.category.is_provided
    assert card.category.reason == REASON_MAPPING_UNCERTAIN


def test_life_stage_ambiguous_is_not_guessed():
    card = parse_label("测试粮A 猫粮 幼年 成年\n")
    assert not card.life_stage.is_provided
    assert card.life_stage.reason == REASON_MAPPING_UNCERTAIN


def test_missing_field_reports_not_found():
    card = parse_label("测试粮A 猫粮 成年\n")
    assert not card.ingredients.is_provided
    assert card.ingredients.reason == REASON_NOT_FOUND


def test_out_of_range_value_is_discarded():
    """数值超范围是解析噪声，不能进判定路径。"""
    card = parse_label("测试粮A 猫粮 成年\n成分分析保证值：\n粗蛋白 >= 300%\n")
    field = card.guaranteed.get("粗蛋白")
    assert field is not None
    assert not field.is_provided
    assert field.reason == REASON_OUT_OF_RANGE


def test_guaranteed_extracts_decimal_not_float():
    card = parse_label("测试粮A 猫粮 成年\n成分分析保证值：\n粗蛋白 >= 30.5%\n")
    value = card.guaranteed["粗蛋白"].value
    assert isinstance(value, Decimal)
    assert value == Decimal("30.5")


def test_guaranteed_alias_normalization():
    card = parse_label("测试粮A 猫粮 成年\n成分分析保证值：\n蛋白质 >= 30%\n")
    assert "粗蛋白" in card.guaranteed


def test_net_content_unit_preserved():
    card = parse_label("测试粮A 猫粮 成年\n净含量：2kg\n")
    assert card.net_content.is_provided
    assert card.net_content.unit == "kg"
    assert card.net_content.value == Decimal("2")


def test_claims_extracted():
    """宣称词表由调用方传入（来自规则包）——解析层不留第二份口径。"""
    card = parse_label("测试粮A 猫粮 成年\n产品特点：天然、无谷\n",
                       claim_words=("天然", "无谷", "鲜肉"))
    assert "天然" in card.claim_names()
    assert "无谷" in card.claim_names()
    # 词表外的词面不得被抽出（"全价"是产品类型词，不是宣称）
    assert "全价" not in card.claim_names()


def test_mass_conversion_shares_alias_table():
    """映射与单位换算共用同一张别名表——不留第二份口径。"""
    assert convert_mass_to_gram(Decimal("2"), "kg") == Decimal("2000")
    assert convert_mass_to_gram(Decimal("1"), "斤") == Decimal("500")
    assert convert_mass_to_gram(Decimal("1"), "unknown") is None


def test_dates_combined_field():
    card = parse_label("测试粮A 猫粮 成年\n生产日期：2026-01-01\n保质期：18个月\n")
    assert card.product_dates.is_provided
    assert "2026" in str(card.product_dates.value)
    assert "18" in str(card.product_dates.value)


def test_unparsed_matches_missing_fields():
    card = parse_label("测试粮A 猫粮 成年\n")
    assert card.unparsed == card.missing_fields()


def test_product_name_fallback_skips_key_value_lines():
    card = parse_label("测试粮A 猫粮 成年\n原料组成：鸡肉\n净含量：2kg\n")
    assert card.product_name.is_provided
    assert "原料组成" not in str(card.product_name.value)


def test_parse_empty_text_does_not_crash():
    card = parse_label("")
    assert card.card_id
    assert not card.product_name.is_provided
