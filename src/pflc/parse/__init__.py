"""解析层：标签文本 → 结构化 LabelCard（确定性，规则优先，无 LLM）。

三条纪律（见 plan/04 §二）：
  * **规则优先**：正则 + 槽位 + 合法性校验；数值超范围即丢弃；
  * **确定性**：同一文本 → 同一档案，逐字节一致（配守门测试）；
  * **解析不到 = 显式降级**：落 ``not_provided`` + 原因码，绝不猜测补全。

工程陷阱处理：全角/半角混用、CRLF 残留、单位不一致（走同一张别名表）。
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Sequence, Tuple

from ..model import (
    REASON_MAPPING_UNCERTAIN,
    REASON_NOT_FOUND,
    REASON_OUT_OF_RANGE,
    Field,
    LabelCard,
)

# --------------------------------------------------------------------------
# 归一化
# --------------------------------------------------------------------------

#: 全角 → 半角（数字、字母、常见符号）。`≥` 等数学符号单独映射。
_FULLWIDTH_MAP = {chr(0xFF01 + i): chr(0x21 + i) for i in range(94)}


def normalize_text(raw: str) -> str:
    """文本归一化：CRLF → LF、全角符号 → 半角、去行首尾空白。

    归一化必须是**确定性**的（无 locale 依赖、无时间戳），否则
    "同一文本 → 同一档案"的守门测试会随机失败。
    """
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(_FULLWIDTH_MAP.get(ch, ch) for ch in text)
    text = (text.replace("\u2265", ">=").replace("\u2266", "<=")
                .replace("\u2267", ">=").replace("\u2264", "<=")
                .replace("\uFF1A", ":").replace("\uFF0C", ","))
    return text


# --------------------------------------------------------------------------
# 单位别名表（映射与换算**共用同一张表**，见 plan/03 D15）
# --------------------------------------------------------------------------

#: 百分比单位：值本身就是百分数
PERCENT_UNITS = ("%", "％", "g/100g", "g/100ml")

#: 质量单位 → 克
_MASS_TO_GRAM = {
    "g": Decimal(1),
    "kg": Decimal(1000),
    "mg": Decimal("0.001"),
    "斤": Decimal(500),
}

#: 生命阶段白名单（词面 → 规范名）
LIFE_STAGE_ALIASES: Dict[str, str] = {
    "幼年": "幼年", "幼猫": "幼年", "幼犬": "幼年", "离乳期": "幼年",
    "妊娠期": "妊娠哺乳期", "哺乳期": "妊娠哺乳期", "妊娠哺乳期": "妊娠哺乳期",
    "成年": "成年", "成猫": "成年", "成犬": "成年", "全阶段": "全阶段",
    "全价": "全阶段", "全年龄": "全阶段", "各阶段": "全阶段",
    "老年": "老年", "老年期": "老年",
}

#: 产品类别白名单
CATEGORY_ALIASES: Dict[str, str] = {
    "犬": "犬粮", "狗": "犬粮", "犬粮": "犬粮", "狗粮": "犬粮",
    "猫": "猫粮", "猫粮": "猫粮",
}

#: 保证值指标别名（词面 → 规范指标名）。同一词面指多个参数时**不收**（歧义绝不猜）。
GUARANTEED_ALIASES: Dict[str, str] = {
    "粗蛋白": "粗蛋白", "蛋白质": "粗蛋白", "蛋白": "粗蛋白",
    "粗脂肪": "粗脂肪", "脂肪": "粗脂肪",
    "粗纤维": "粗纤维", "纤维": "粗纤维",
    "粗灰分": "粗灰分", "灰分": "粗灰分",
    "水分": "水分", "含水率": "水分",
    "钙": "钙", "总钙": "钙",
    "总磷": "总磷", "磷": "总磷",
    "钙磷比": "钙磷比",
    "水溶性氯化物": "水溶性氯化物", "食盐": "水溶性氯化物", "盐分": "水溶性氯化物",
    "牛磺酸": "牛磺酸",
    "赖氨酸": "赖氨酸",
}

#: 合法数值范围（百分比类指标）——超出即 ``out_of_range`` 丢弃
_PERCENT_RANGE = (Decimal(0), Decimal(100))

#: 保证值行正则：指标名 + 可选冒号 + 比较符 + 数值 + 单位
#:
#: 指标名长度下界是 **1 个汉字**（``{1,12}``）：别名表里有单字指标
#: （``钙``/``磷``），M0 写的 ``{2,12}`` 会让这些行**整行解析不到**——
#: 而别名表里明明列着它们，"表里有、正则不收"是自相矛盾的静默漏项。
#: 数值部分接受小数与科学计数法两种写法（``30`` 与 ``3E+1`` 是同一个值）。
_GUARANTEED_RE = re.compile(
    r"(?P<name>[\u4e00-\u9fa5A-Za-z]{1,12})"
    r"\s*[:：]?\s*"
    r"(?P<op>>=|<=|>|<|=|>=|≥|≤)?\s*"
    r"(?P<value>\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*"
    r"(?P<unit>%|g/100g|g/100ml|mg/kg|g/kg|IU/kg)?"
)

#: 净含量正则
_NET_CONTENT_RE = re.compile(
    r"(?:净含量|净重|规格)\s*[:：]?\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>kg|g|斤|ml|L)"
)

#: 日期正则
_DATE_RE = re.compile(r"(?P<date>\d{4}\s*[-/年]\s*\d{1,2}\s*[-/月]\s*\d{1,2}\s*日?)")

#: 保质期正则
_SHELF_LIFE_RE = re.compile(r"(?:保质期|有效期)\s*[:：]?\s*(?P<value>\d+)\s*(?P<unit>个月|月|天|年)")

#: 宣称用语词表（首期词面；M1 起改为从规则包读取，见 plan/05）
_CLAIM_WORDS = ("天然", "无谷", "无添加", "纯天然", "有机", "鲜肉", "全价", "处方")

#: 字段标签正则（"原料组成：xxx" 形式）
_LABEL_PATTERNS: Dict[str, str] = {
    "ingredients": r"(?:原料组成|配料|原料|成分)\s*[:：]\s*(?P<val>[^\n]{2,})",
    "additives": r"(?:添加剂|饲料添加剂|添加剂组成)\s*[:：]\s*(?P<val>[^\n]{2,})",
    "producer": r"(?:生产企业|生产商|生产者|委托方|生产厂家|地址)\s*[:：]\s*(?P<val>[^\n]{2,})",
    "product_name": r"(?:产品名称|品名|商品名)\s*[:：]\s*(?P<val>[^\n]{2,})",
}


# --------------------------------------------------------------------------
# 数值与单位
# --------------------------------------------------------------------------


def _parse_decimal(text: str) -> Optional[Decimal]:
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def convert_mass_to_gram(value: Decimal, unit: str) -> Optional[Decimal]:
    """质量单位换算（与映射**共用同一张别名表**）。"""
    factor = _MASS_TO_GRAM.get(unit)
    if factor is None:
        return None
    return value * factor


# --------------------------------------------------------------------------
# 单字段抽取
# --------------------------------------------------------------------------


def _extract_labeled(text: str, key: str) -> Field:
    """抽取"标签：内容"形式的字段。"""
    pattern = _LABEL_PATTERNS.get(key)
    if pattern is None:
        return Field.missing(key)
    match = re.search(pattern, text)
    if not match:
        return Field.missing(key, REASON_NOT_FOUND)
    value = match.group("val").strip()
    if not value:
        return Field.missing(key, REASON_NOT_FOUND)
    return Field.provided(key, value, evidence=match.group(0)[:80])


def _extract_category(text: str) -> Field:
    """产品类别：命中唯一类别才提供；同时命中犬与猫 → 歧义，绝不猜。"""
    hits = {canon for word, canon in CATEGORY_ALIASES.items() if word in text}
    if not hits:
        return Field.missing("category", REASON_NOT_FOUND)
    if len(hits) > 1:
        return Field.missing("category", REASON_MAPPING_UNCERTAIN,
                             evidence="同时命中：" + "、".join(sorted(hits)))
    return Field.provided("category", hits.pop())


def _extract_life_stage(text: str) -> Field:
    """生命阶段：命中唯一阶段才提供；多阶段命中 → 歧义。"""
    hits = {canon for word, canon in LIFE_STAGE_ALIASES.items() if word in text}
    if not hits:
        return Field.missing("life_stage", REASON_NOT_FOUND)
    if len(hits) > 1:
        return Field.missing("life_stage", REASON_MAPPING_UNCERTAIN,
                             evidence="同时命中：" + "、".join(sorted(hits)))
    return Field.provided("life_stage", hits.pop())


def _extract_guaranteed(text: str) -> Dict[str, Field]:
    """抽取成分分析保证值键值对。

    合法性校验：百分比类指标超出 [0,100] 即 ``out_of_range`` 丢弃——
    "粗蛋白 300%" 是解析噪声，不能进判定路径。
    """
    out: Dict[str, Field] = {}
    for match in _GUARANTEED_RE.finditer(text):
        raw_name = match.group("name")
        canon = GUARANTEED_ALIASES.get(raw_name)
        if canon is None:
            continue
        if canon in out:
            # 同一指标出现多次：保留首个（行序确定，故结果确定）
            continue
        value = _parse_decimal(match.group("value"))
        if value is None:
            continue
        unit = match.group("unit") or "%"
        if unit in PERCENT_UNITS and not (_PERCENT_RANGE[0] <= value <= _PERCENT_RANGE[1]):
            out[canon] = Field.missing(canon, REASON_OUT_OF_RANGE,
                                       evidence=match.group(0)[:40])
            continue
        out[canon] = Field.provided(canon, value, unit=unit,
                                    evidence=match.group(0)[:40])
    return out


def _extract_net_content(text: str) -> Field:
    match = _NET_CONTENT_RE.search(text)
    if not match:
        return Field.missing("net_content", REASON_NOT_FOUND)
    value = _parse_decimal(match.group("value"))
    unit = match.group("unit")
    if value is None:
        return Field.missing("net_content", REASON_NOT_FOUND)
    return Field.provided("net_content", value, unit=unit, evidence=match.group(0)[:40])


def _extract_product_dates(text: str) -> Field:
    """生产日期 / 保质期。两者都缺才算未提供。"""
    parts: List[str] = []
    date_match = _DATE_RE.search(text)
    if date_match:
        parts.append("生产日期 " + date_match.group("date").replace(" ", ""))
    shelf_match = _SHELF_LIFE_RE.search(text)
    if shelf_match:
        parts.append("保质期 %s%s" % (shelf_match.group("value"), shelf_match.group("unit")))
    if not parts:
        return Field.missing("product_dates", REASON_NOT_FOUND)
    return Field.provided("product_dates", "；".join(parts),
                          evidence="；".join(p[:40] for p in parts))


def _extract_claims(text: str, claim_words: Sequence[str] = _CLAIM_WORDS) -> List[Field]:
    """抽取宣称用语。只判"宣称存在"，不判语义真伪（见 plan/04 §四.1）。"""
    out: List[Field] = []
    for word in claim_words:
        if word in text:
            out.append(Field.provided("claim", word, evidence=word))
    return out


# --------------------------------------------------------------------------
# 主入口
# --------------------------------------------------------------------------


def parse_label(raw_text: str, source: str = "") -> LabelCard:
    """把标签全文解析为 ``LabelCard``。

    确定性保证：无随机、无时间戳、无 locale 依赖；字典键一律排序遍历。
    同一 ``raw_text`` 两次调用产出**逐字节一致**的 ``to_dict()``。
    """
    text = normalize_text(raw_text)
    card = LabelCard(raw_text=text, source=source)

    card.product_name = _extract_labeled(text, "product_name")
    if not card.product_name.is_provided:
        # 回退：取首个非空且不像标签键值对的行作为通用名
        for line in text.split("\n"):
            stripped = line.strip()
            if not stripped:
                continue
            if any(kw in stripped for kw in ("原料组成", "配料", "添加剂", "净含量",
                                             "粗蛋白", "粗脂肪", "水分", "灰分")):
                continue
            if 2 <= len(stripped) <= 40:
                card.product_name = Field.provided("product_name", stripped,
                                                   evidence=stripped[:40])
                break

    card.category = _extract_category(text)
    card.life_stage = _extract_life_stage(text)
    card.guaranteed = _extract_guaranteed(text)
    card.ingredients = _extract_labeled(text, "ingredients")
    card.additives = _extract_labeled(text, "additives")
    card.net_content = _extract_net_content(text)
    card.producer = _extract_labeled(text, "producer")
    card.product_dates = _extract_product_dates(text)
    card.claims = _extract_claims(text)

    card.unparsed = card.missing_fields()
    return card


#: 保证值抽取的正则与别名表对外暴露，供 M1 的转录器/测试共用同一口径。
def guaranteed_field_names() -> Tuple[str, ...]:
    return tuple(sorted(set(GUARANTEED_ALIASES.values())))


def claim_words() -> Tuple[str, ...]:
    return _CLAIM_WORDS
