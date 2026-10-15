"""统一中间表示（Unified Intermediate Representation）。

判定链路的全部数据都收敛到这里定义的四个类型：

    Anchor     —— 条款锚点（可溯源性的最小单元）
    Field      —— 单字段（三态载体：provided / not_provided + 原因码）
    LabelCard  —— 标签档案（解析层的输出，判定引擎的输入）
    Finding    —— 单条判定结论（引擎的输出，报告的输入）

设计纪律（见 plan/03 的 D1/D15/D16）：
  * 解析不到的字段落 ``not_provided`` 并带**原因码**，绝不猜测补全；
  * 原因码是**显式第三态**的载体——"歧义"与"没写"必须可区分；
  * 本模块只做数据结构，不含任何判定逻辑，也不含任何政策数值。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

# --------------------------------------------------------------------------
# 状态常量
# --------------------------------------------------------------------------

#: 字段状态
FIELD_PROVIDED = "provided"
FIELD_NOT_PROVIDED = "not_provided"

#: 字段缺失原因码（显式第三态，见 plan/03 D15/D16）
REASON_NOT_FOUND = "not_found"              #: 文本里确实没有该字段
REASON_MAPPING_UNCERTAIN = "mapping_uncertain"  #: 歧义：可能指多个参数，绝不猜
REASON_STRUCTURE_BROKEN = "structure_broken"    #: 文本结构损坏，无法切分
REASON_OUT_OF_RANGE = "out_of_range"            #: 抽到数值但超出合法范围，丢弃
REASON_BASIS_UNDETERMINED = "basis_undetermined"  #: 限值与观测值基准不同且缺换算所需字段

REASONS = (
    REASON_NOT_FOUND,
    REASON_MAPPING_UNCERTAIN,
    REASON_STRUCTURE_BROKEN,
    REASON_OUT_OF_RANGE,
    REASON_BASIS_UNDETERMINED,
)

#: 判定结论（三态 + 两种非结论，见 plan/03 D1）
VERDICT_COMPLIANT = "compliant"
VERDICT_NONCOMPLIANT = "noncompliant"
VERDICT_NOT_PROVIDED = "not_provided"
VERDICT_SKIPPED = "skipped"          #: 不适用——原文明确写了例外情形
VERDICT_UNKNOWN = "unknown"          #: 未观测——"没看到"而非"缺失"

VERDICTS = (
    VERDICT_COMPLIANT,
    VERDICT_NONCOMPLIANT,
    VERDICT_NOT_PROVIDED,
    VERDICT_SKIPPED,
    VERDICT_UNKNOWN,
)

#: 聚合结论（维度级与整体级共用）
OVERALL_COMPLIANT = "compliant"
OVERALL_NONCOMPLIANT = "noncompliant"
OVERALL_NOT_PROVIDED = "not_provided"
OVERALL_NOT_ASSESSED = "not_assessed"  #: 零适用项——绝不输出成 compliant

#: 维度被排除出聚合的原因码（见 plan/03 D4）
EXCLUDE_NO_EFFECTIVE_RULES = "no_effective_rules"
EXCLUDE_STANDARD_NOT_EFFECTIVE = "standard_not_effective"

#: 维度名
DIM_LABEL = "label"
DIM_NUTRITION = "nutrition"
DIM_CLAIM = "claim"
DIMENSIONS = (DIM_LABEL, DIM_NUTRITION, DIM_CLAIM)

#: 规则核对状态（双重门控，见 plan/03 D2）
STATUS_VERIFIED = "verified"
STATUS_PENDING = "pending"

#: 义务类型（见 plan/03 D1 分栏纪律）
EFFECT_OBLIGATION = "obligation"      #: 无条件义务——缺失记不符合
EFFECT_CONDITIONAL = "conditional"    #: 条件触发（如"监管部门可以要求"）——不计入频次

#: 限值的计量基准（见 plan/07 决策记录 M1 条）
#: GB/T 31216/31217 的理化指标表头写明"指标（以干物质计）/%"，而标签上标示的
#: 保证值是按标示状态（as-fed）给的——两者**不同基准，不能直接比**。
BASIS_AS_FED = "as_fed"                #: 按标示状态计（标签保证值的默认基准）
BASIS_DRY_MATTER = "dry_matter"        #: 以干物质计（国标理化指标表的基准）

#: 干基换算所需的字段名（标签应当标示水分，见规定附录 4）
FIELD_MOISTURE = "水分"


# --------------------------------------------------------------------------
# 免责声明（强制出现在每份报告与 GUI"关于"页，见 plan/07 K19）
# --------------------------------------------------------------------------

DISCLAIMER = (
    "免责声明：本输出为基于公开法规条款与国家标准限值的合规检查发现，"
    "不构成产品合格判定、检测结论或行政认定，也不构成兽医意见。"
    "正式结论以具备资质的检验检测机构报告与主管部门口径为准；"
    "宠物健康问题以执业兽医意见为准。"
)


# --------------------------------------------------------------------------
# Anchor —— 条款锚点
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Anchor:
    """条款锚点：结论可溯源性的最小单元。

    ``excerpt`` 必须是入仓原文快照里**逐字存在**的片段——这是"未挂原文核对
    不得生效"纪律的落地判据（见 plan/05 §三）。
    """

    doc_id: str            #: 依据编号，如 "MOA-20-2018-ANNEX3"
    doc_title: str         #: 文件标题
    clause: str            #: 条款位置，如 "第十一条"
    excerpt: str = ""      #: 原文摘录（逐字，核对用）
    source_url: str = ""   #: 来源 URL（转载源如实标注）
    captured_at: str = ""  #: 抓取日期
    sha256: str = ""       #: 快照文件 sha256（可证性）

    def render(self) -> str:
        """人可读的单行锚点（用于报告）。"""
        parts = [self.doc_id]
        if self.doc_title:
            parts.append(self.doc_title)
        if self.clause:
            parts.append(self.clause)
        return " · ".join(parts)

    def is_resolvable(self) -> bool:
        """溯源完整性判据：编号 + 条款位置齐备才可解析。"""
        return bool(self.doc_id and self.clause)


# --------------------------------------------------------------------------
# Field —— 单字段（三态载体）
# --------------------------------------------------------------------------


@dataclass
class Field:
    """单个标签字段。

    ``status`` 只有两个值；"未取得"的**原因**由 ``reason`` 承载——
    这是"解析不到 = 显式降级"的载体，绝不把解析失败伪装成"没写"。
    """

    name: str
    value: Any = None
    status: str = FIELD_NOT_PROVIDED
    reason: Optional[str] = None
    unit: Optional[str] = None
    evidence: Optional[str] = None   #: 原文摘录（抽取依据）

    @classmethod
    def provided(cls, name: str, value: Any, unit: Optional[str] = None,
                 evidence: Optional[str] = None) -> "Field":
        return cls(name=name, value=value, status=FIELD_PROVIDED, unit=unit,
                   evidence=evidence)

    @classmethod
    def missing(cls, name: str, reason: str = REASON_NOT_FOUND,
                evidence: Optional[str] = None) -> "Field":
        return cls(name=name, value=None, status=FIELD_NOT_PROVIDED,
                   reason=reason, evidence=evidence)

    @property
    def is_provided(self) -> bool:
        return self.status == FIELD_PROVIDED and self.value is not None

    def render(self) -> str:
        if not self.is_provided:
            return "未提供(%s)" % (self.reason or REASON_NOT_FOUND)
        text = str(self.value)
        if self.unit:
            text = "%s %s" % (text, self.unit)
        return text


# --------------------------------------------------------------------------
# LabelCard —— 标签档案
# --------------------------------------------------------------------------


@dataclass
class LabelCard:
    """结构化标签档案：解析层的输出，判定引擎的输入。

    ``card_id`` 是**稳定身份键**（内容 sha256 前缀），供两轮对账配对使用——
    绝不用内容指纹当配对主键，否则"已修复"永远配不上（见 plan/03 D18）。
    """

    raw_text: str
    card_id: str = ""
    source: str = ""                        #: 来源标识（文件名或 "<stdin>"）

    product_name: Field = None              # type: ignore[assignment]
    category: Field = None                  # type: ignore[assignment]
    life_stage: Field = None                # type: ignore[assignment]
    guaranteed: Dict[str, Field] = field(default_factory=dict)
    ingredients: Field = None               # type: ignore[assignment]
    additives: Field = None                 # type: ignore[assignment]
    net_content: Field = None               # type: ignore[assignment]
    producer: Field = None                  # type: ignore[assignment]
    product_dates: Field = None             # type: ignore[assignment]
    claims: List[Field] = field(default_factory=list)
    unparsed: List[str] = field(default_factory=list)

    #: 本档案抽取宣称时使用的**词表**（来自规则包）。空元组 = 未按任何词表抽取。
    #: 记下它是为了堵一个假结论：若调用方拿一份"未按规则包词表抽取"的档案去判定，
    #: 规则会因 `target not in claim_names()` 判成 ``skipped``——**假 skipped**
    #: （把"没抽到"当"没宣称"）。判定层据此与本轮规则包词表核对并重抽（见引擎）。
    claim_vocab: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.card_id:
            self.card_id = compute_card_id(self.raw_text)
        for attr in ("product_name", "category", "life_stage", "ingredients",
                     "additives", "net_content", "producer", "product_dates"):
            if getattr(self, attr) is None:
                setattr(self, attr, Field.missing(attr))

    # -- 查询辅助 ---------------------------------------------------------

    def field(self, name: str) -> Optional[Field]:
        """按字段名取 Field（含 guaranteed 内的指标）。"""
        if name in self.guaranteed:
            return self.guaranteed[name]
        alias = {
            "product_name": self.product_name,
            "category": self.category,
            "life_stage": self.life_stage,
            "ingredients": self.ingredients,
            "additives": self.additives,
            "net_content": self.net_content,
            "producer": self.producer,
            "product_dates": self.product_dates,
        }
        return alias.get(name)

    def category_value(self) -> Optional[str]:
        return self.category.value if self.category.is_provided else None

    def life_stage_value(self) -> Optional[str]:
        return self.life_stage.value if self.life_stage.is_provided else None

    def claim_names(self) -> List[str]:
        return [f.value for f in self.claims if f.is_provided]

    def missing_fields(self) -> List[str]:
        """返回全部未提供字段名（含保证值指标），供报告"未提供清单"。"""
        out: List[str] = []
        for attr in ("product_name", "category", "life_stage", "ingredients",
                     "additives", "net_content", "producer", "product_dates"):
            f = getattr(self, attr)
            if not f.is_provided:
                out.append(attr)
        for key, f in self.guaranteed.items():
            if not f.is_provided:
                out.append(key)
        return sorted(out)

    def to_dict(self) -> Dict[str, Any]:
        """确定性字典表示（供报告与测试对账；Decimal 转字符串保精度）。

        ``claim_vocab`` 一并导出：档案的宣称抽取口径随它走，"逐字节一致"
        的判据才完整（同一文本在不同词表下抽出不同宣称，是**两种档案**）。
        """

        def _f(f: Field) -> Dict[str, Any]:
            return {
                "name": f.name,
                "value": _jsonable(f.value),
                "status": f.status,
                "reason": f.reason,
                "unit": f.unit,
            }

        return {
            "card_id": self.card_id,
            "source": self.source,
            "product_name": _f(self.product_name),
            "category": _f(self.category),
            "life_stage": _f(self.life_stage),
            "guaranteed": {k: _f(v) for k, v in sorted(self.guaranteed.items())},
            "ingredients": _f(self.ingredients),
            "additives": _f(self.additives),
            "net_content": _f(self.net_content),
            "producer": _f(self.producer),
            "product_dates": _f(self.product_dates),
            "claims": [_f(c) for c in self.claims],
            "claim_vocab": list(self.claim_vocab),
            "unparsed": sorted(self.unparsed),
        }


def _jsonable(value: Any) -> Any:
    """把值转成可确定性序列化的形式（Decimal → str 保精度）。"""
    if isinstance(value, Decimal):
        return format_decimal(value)
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def format_decimal(value: Decimal) -> str:
    """把 ``Decimal`` 渲染成**非科学计数法**文本，并去掉无意义的尾随零。

    ``Decimal("30.0").normalize()`` 得到 ``Decimal("3E+1")``——``str()`` 出来就是
    ``"3E+1"``。这个形态有三个害处，每个都实测踩过：

      * 报告里出现 ``3E+1 %``，人读不出来；
      * 基准把限值写回标签文本时产出 ``粗蛋白 >= 3E+1%``，再解析回 ``3``，
        即"生成器写的"与"解析器读的"不是同一个数；
      * 禁用 token 实算会把 ``3E+1`` 当成一个 token，而它在任何源码里都不可能
        出现——门禁变成空转。

    故一律走 ``format(value, "f")``（定点表示，无 E 记号）再裁尾零。
    """
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def compute_card_id(raw_text: str) -> str:
    """稳定身份键：原始文本的 sha256 前 16 位十六进制。

    用**文本内容**而非文件名——同一份标签换个文件名仍是同一件，
    改名不应在轮次对账里表现为"新增 + 消失"。
    """
    digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    return digest[:16]


# --------------------------------------------------------------------------
# Finding —— 单条判定结论
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    """单条判定结论。``anchor`` 为空表示该结论不可溯源——导出层会拒导。"""

    rule_id: str
    dimension: str
    target: str
    verdict: str
    effect: str = EFFECT_OBLIGATION
    observed: Optional[str] = None
    expected: Optional[str] = None
    anchor: Optional[Anchor] = None
    note: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "dimension": self.dimension,
            "target": self.target,
            "verdict": self.verdict,
            "effect": self.effect,
            "observed": self.observed,
            "expected": self.expected,
            "anchor": self.anchor.render() if self.anchor else "",
            "anchor_resolvable": bool(self.anchor and self.anchor.is_resolvable()),
            "note": self.note,
        }


# --------------------------------------------------------------------------
# DimensionResult / CheckResult
# --------------------------------------------------------------------------


@dataclass
class DimensionResult:
    """单维度判定结果。

    ``excluded`` 为真时该维度**不参与聚合**（零生效规则 / 标准尚未生效），
    ``exclude_reason`` 记录原因码——报告保留区块并写明排除理由，
    绝不静默把"无可判项"混进整体结论（见 plan/03 D4）。
    """

    dimension: str
    findings: List[Finding] = field(default_factory=list)
    excluded: bool = False
    exclude_reason: Optional[str] = None
    not_assessed: bool = False

    # -- 统计 -------------------------------------------------------------

    def counts(self) -> Dict[str, int]:
        out = {v: 0 for v in VERDICTS}
        for f in self.findings:
            out[f.verdict] = out.get(f.verdict, 0) + 1
        return out

    def obligation_findings(self) -> List[Finding]:
        """无条件义务栏——**频次/计数只取这一栏**（见 plan/03 D1）。"""
        return [f for f in self.findings if f.effect == EFFECT_OBLIGATION]

    def conditional_findings(self) -> List[Finding]:
        """条件触发栏（如"监管部门可以要求"）——分栏呈现，不计频次。"""
        return [f for f in self.findings if f.effect == EFFECT_CONDITIONAL]

    def has_noncompliant(self) -> bool:
        return any(f.verdict == VERDICT_NONCOMPLIANT for f in self.findings)

    def verdict(self) -> str:
        """维度级聚合结论（见 plan/04 §四.3）。"""
        if self.excluded:
            return OVERALL_NOT_ASSESSED
        if self.not_assessed or not self.findings:
            return OVERALL_NOT_ASSESSED
        if self.has_noncompliant():
            return OVERALL_NONCOMPLIANT
        if any(f.verdict == VERDICT_COMPLIANT for f in self.findings):
            return OVERALL_COMPLIANT
        return OVERALL_NOT_PROVIDED


@dataclass
class CheckResult:
    """一次核验的完整结果。"""

    card_id: str
    source: str = ""
    dimensions: List[DimensionResult] = field(default_factory=list)
    pending_rules: List[str] = field(default_factory=list)
    disclaimer: str = DISCLAIMER

    def dimension(self, name: str) -> Optional[DimensionResult]:
        for d in self.dimensions:
            if d.dimension == name:
                return d
        return None

    def all_findings(self) -> List[Finding]:
        out: List[Finding] = []
        for d in self.dimensions:
            out.extend(d.findings)
        return out

    def participated(self) -> List[DimensionResult]:
        """参与聚合的维度——排除"零生效规则/标准未生效"的维度。"""
        return [d for d in self.dimensions if not d.excluded]

    def overall(self) -> str:
        """整体聚合结论。

        规则：任一参与维度有 noncompliant → noncompliant；
              全部参与维度均 not_assessed（或没有参与维度）→ not_assessed；
              有 compliant 且无 noncompliant → compliant；
              否则 not_provided。
        """
        parts = self.participated()
        if not parts:
            return OVERALL_NOT_ASSESSED
        if any(p.has_noncompliant() for p in parts):
            return OVERALL_NONCOMPLIANT
        if all(p.not_assessed or not p.findings for p in parts):
            return OVERALL_NOT_ASSESSED
        if any(p.verdict() == OVERALL_COMPLIANT for p in parts):
            return OVERALL_COMPLIANT
        return OVERALL_NOT_PROVIDED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "card_id": self.card_id,
            "source": self.source,
            "overall": self.overall(),
            "dimensions": [
                {
                    "dimension": d.dimension,
                    "verdict": d.verdict(),
                    "excluded": d.excluded,
                    "exclude_reason": d.exclude_reason,
                    "not_assessed": d.not_assessed,
                    "counts": d.counts(),
                    "findings": [f.to_dict() for f in d.findings],
                }
                for d in self.dimensions
            ],
            "pending_rules": sorted(self.pending_rules),
        }
