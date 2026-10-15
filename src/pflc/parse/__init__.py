"""解析层：标签文本 → 结构化 LabelCard（确定性，规则优先，无 LLM）。

三条纪律（见 plan/04 §二）：
  * **规则优先**：正则 + 槽位 + 合法性校验；数值超范围即丢弃；
  * **确定性**：同一文本 → 同一档案，逐字节一致（配守门测试）；
  * **解析不到 = 显式降级**：落 ``not_provided`` + 原因码，绝不猜测补全。

工程陷阱处理：全角/半角混用、CRLF 残留、单位不一致（走同一张别名表）。

**宣称词表的来源**（M2 修订）：解析层**不读文件、不持有词表**。词表由调用方
从规则包取出后作为 ``parse_label(claim_words=...)`` 传入——若在解析层再留一份
硬编码词表，两份口径必然漂移：规则包加一条宣称，解析层不认它，该宣称永远抽不出来，
规则永远判"未宣称"= **假 skipped**（见 plan/04 §2.2"词表来自规则包"）。
"""

from __future__ import annotations

import re
from datetime import date
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
#:
#: **产品类型词不得进这张表**（M2 修正）：``全价`` 指"全价配合饲料"这一产品类型，
#: 不是生命阶段。M0 把它映射成 ``全阶段`` 后，"测试粮A 猫粮 幼年"这类正常标签
#: 会因 ``全价``（别名 全阶段）与 ``幼年`` 同时命中而被判"阶段歧义"，
#: 进而使营养维度**整维度 not_assessed**（一条规则都不适用）。
#: 真·全阶段词面（``全阶段``/``全年龄``/``各阶段``）保留。
LIFE_STAGE_ALIASES: Dict[str, str] = {
    "幼年": "幼年", "幼猫": "幼年", "幼犬": "幼年", "离乳期": "幼年",
    "妊娠期": "妊娠哺乳期", "哺乳期": "妊娠哺乳期", "妊娠哺乳期": "妊娠哺乳期",
    "成年": "成年", "成猫": "成年", "成犬": "成年", "全阶段": "全阶段",
    "全年龄": "全阶段", "各阶段": "全阶段",
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

#: 净含量正则：**只抓"关键词 + 数值"**，单位另判。
#:
#: 为什么单位不写进正则：写死白名单（``kg|g|斤|ml|L``）时，"净含量：2oz"
#: 这种**有值但不认识单位**的写法整行匹配失败 → 落 ``not_found``——
#: 把"写了但单位不认识"和"根本没写"混为一谈。而放宽成"任意 1–3 字符"又会
#: 贪婪吞掉紧随其后的汉字（``2kg产品`` 被读成单位 ``kg产``，凭空造假歧义）。
#: 故单位在代码里按**最长优先**的已知单位表判定，认不出再退化为
#: ``mapping_uncertain``（见 plan/04 §2.2）。
_NET_CONTENT_RE = re.compile(
    r"(?:净含量|净重|规格)\s*[:：]?\s*(?P<value>\d+(?:\.\d+)?)"
)

#: 净含量已知单位白名单——**按长度降序**用于最长优先匹配
#: （``kg`` 必须先于 ``g`` 试，否则 "2kg" 会被读成 "2 g"）。
NET_CONTENT_UNITS: Tuple[str, ...] = (
    "千克", "公斤", "毫克", "毫升", "kg", "mg", "ml", "斤", "克", "升", "g", "L", "l",
)

#: 认不出单位时，向后最多吃这么多字符作为"疑似单位"（仅用于生成证据片段）
_UNIT_PROBE_LEN = 3

#: 日期正则：抓"年-月-日"三段，月日**分开捕获**以便合法性校验。
_DATE_RE = re.compile(
    r"(?P<year>\d{4})\s*[-/年]\s*(?P<month>\d{1,2})\s*[-/月]\s*(?P<day>\d{1,2})\s*日?"
)

#: 保质期正则
_SHELF_LIFE_RE = re.compile(r"(?:保质期|有效期)\s*[:：]?\s*(?P<value>\d+)\s*(?P<unit>个月|月|天|年)")

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
    """净含量：抓"关键词 + 数值"，单位按**最长优先**的已知表判定。

    **单位不认识 ≠ 没写**：``2oz`` 里的 ``oz`` 不在白名单里，但"净含量"这个词
    与数值都在文本里——这是"有值但单位无法映射"，落 ``mapping_uncertain``；
    只有连"净含量"关键词与数值都找不到时才落 ``not_found``。
    """
    match = _NET_CONTENT_RE.search(text)
    if not match:
        return Field.missing("net_content", REASON_NOT_FOUND)
    value = _parse_decimal(match.group("value"))
    if value is None:
        return Field.missing("net_content", REASON_NOT_FOUND)

    tail = text[match.end():].lstrip()
    unit = _match_net_unit(tail)
    if unit is None:
        # 有值但单位不在白名单：绝不猜单位（不假定为 g，也不假定为 kg）
        probe = match.group(0) + tail[:_UNIT_PROBE_LEN]
        return Field.missing("net_content", REASON_MAPPING_UNCERTAIN,
                             evidence=probe[:40])
    return Field.provided("net_content", value, unit=unit,
                          evidence=(match.group(0) + unit)[:40])


def _match_net_unit(tail: str) -> Optional[str]:
    """在数值之后的文本里按**最长优先**认一个已知单位。

    最长优先是必须的：按别名表声明顺序试会让 ``2kg`` 先命中 ``g``
    （"kg" 以 "g" 结尾）→ 值 2 被读成 2 克，凭空缩小一千倍。
    """
    for unit in sorted(NET_CONTENT_UNITS, key=len, reverse=True):
        if tail.startswith(unit):
            return unit
    return None


def _valid_date(year: str, month: str, day: str) -> bool:
    """日期合法性：月 ≤12、日 ≤31，且该年月日**真实存在**。

    只做正则匹配会把 ``2026-13-45`` 当成有效日期（M1 实测发现）。
    合法性校验用 ``datetime.date``——它连"2 月 30 日"这种"月日各自合法
    但组合不存在"的情形也一并挡下（那同样是非法日期）。
    """
    try:
        date(int(year), int(month), int(day))
    except ValueError:
        return False
    return True


def _extract_product_dates(text: str) -> Field:
    """生产日期 / 保质期。两者都缺才算未提供。

    日期**必须校验合法性**（见 plan/04 §2.2）：``2026-13-45`` 非法 → 原因码
    ``out_of_range``，不把非法日期当有效日期喂进判定路径。

    **非法日期 = 丢弃该字段**（不是"标个非法还当已提供"）：本字段是
    "生产日期 + 保质期"的合并体，而存在性规则（``LABEL-005``）只看"有没有提供"。
    若非法日期仍算"已提供"，这条无条件义务会判成 **compliant**——
    把一处真实标示缺陷读成合规，正是本项目最要避免的假结论。
    这与数值口径一致：``粗蛋白 >= 300%`` 也是 ``out_of_range`` 丢弃、不进判定。

    抽到的**全部原文片段**（含非法日期与保质期）留在 ``evidence`` 里可核——
    降级不等于把发现到的东西抹掉。
    """
    parts: List[str] = []
    evidence_parts: List[str] = []
    date_match = _DATE_RE.search(text)
    date_valid: Optional[bool] = None
    if date_match:
        year = date_match.group("year")
        month = date_match.group("month")
        day = date_match.group("day")
        rendered = "%s-%02d-%02d" % (year, int(month), int(day))
        date_valid = _valid_date(year, month, day)
        parts.append(("生产日期 " + rendered) if date_valid
                     else ("生产日期 %s（非法）" % rendered))
        evidence_parts.append(parts[-1])
    shelf_match = _SHELF_LIFE_RE.search(text)
    if shelf_match:
        parts.append("保质期 %s%s" % (shelf_match.group("value"), shelf_match.group("unit")))
        evidence_parts.append(parts[-1])

    if not parts:
        return Field.missing("product_dates", REASON_NOT_FOUND)

    if date_valid is False:
        # 日期非法：整字段降级（证据保留全部原文片段，含保质期）
        return Field.missing("product_dates", REASON_OUT_OF_RANGE,
                             evidence="；".join(p[:40] for p in evidence_parts))
    return Field.provided("product_dates", "；".join(parts),
                          evidence="；".join(p[:40] for p in parts))


def _extract_claims(text: str, claim_words: Sequence[str]) -> List[Field]:
    """抽取宣称用语。只判"宣称存在"，不判语义真伪（见 plan/04 §四.1）。

    词表**由调用方传入**（源自规则包的 ``target`` 集），解析层不留第二份口径。

    遍历顺序取 ``sorted(set(...))``：档案是 ``(文本, 词表**集**)`` 的纯函数——
    若按传入顺序产出，两个调用方传同一组词面但顺序不同就会得到**不同的档案字节**
    （``claims`` 列表顺序不同），"同一文本 → 同一档案"就守不住了。
    """
    out: List[Field] = []
    for word in sorted(set(claim_words)):
        if word and word in text:
            out.append(Field.provided("claim", word, evidence=word))
    return out


def extract_claims(text: str, claim_words: Sequence[str]) -> List[Field]:
    """按给定词表抽取宣称（**对判定层公开**）。

    判定层在分派点上用它把档案的宣称口径统一到本轮规则包——
    否则"直接调 ``parse_label`` 造档案"的通路会因词表为空而把规则判成
    ``skipped``（假 skipped：把"没抽过这个词"读成"没宣称"）。
    """
    return _extract_claims(normalize_text(text), claim_words)


# --------------------------------------------------------------------------
# 主入口
# --------------------------------------------------------------------------


def parse_label(raw_text: str, source: str = "",
                claim_words: Sequence[str] = ()) -> LabelCard:
    """把标签全文解析为 ``LabelCard``。

    确定性保证：无随机、无时间戳、无 locale 依赖；字典键一律排序遍历。
    同一 ``raw_text`` 两次调用产出**逐字节一致**的 ``to_dict()``。

    ``claim_words`` 是**宣称词表**（来自规则包 ``target`` 集），由调用方传入。
    解析层不读文件、不留第二份词表——``()`` 表示"不抽宣称"，
    这是显式取舍而不是"忘了传"：解析层无从知道有哪些宣称词面。
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
    card.claims = _extract_claims(text, claim_words)
    card.claim_vocab = tuple(claim_words)

    card.unparsed = card.missing_fields()
    return card


#: 保证值抽取的正则与别名表对外暴露，供 M1 的转录器/测试共用同一口径。
def guaranteed_field_names() -> Tuple[str, ...]:
    return tuple(sorted(set(GUARANTEED_ALIASES.values())))


def life_stage_names() -> Tuple[str, ...]:
    """生命阶段规范名（供测试与文档共用同一口径）。"""
    return tuple(sorted(set(LIFE_STAGE_ALIASES.values())))
