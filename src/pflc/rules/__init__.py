"""规则层：规则条目模型、规则包加载、双重门控、零政策字面量 token 实算。

本模块是"未挂原文核对不得生效"纪律的**唯一落地点**——引擎不直接读规则
文件，一律经 ``effective_ruleset()`` 取生效条目（见 plan/03 D2/D3）。

三重纪律：
  * **双重门控**：``status``（数值核对）门控判定路径；``clause_status``
    （条款号核对）只管可证性展示，不阻断判定；
  * **按计算路径分作用域**：``label`` / ``nutrition`` / ``claim`` 各只校验
    自己引用的条目——不用"整包全 verified"当唯一门；
  * **数值口径一处定义**：限值只存在于规则包；本模块的 ``banned_numeric_tokens()``
    从规则包**运行时实算**禁用 token，源码里不留任何政策数值字面量。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ..model import (
    BASIS_AS_FED,
    BASIS_DRY_MATTER,
    DIM_CLAIM,
    DIMENSIONS,
    EFFECT_CONDITIONAL,
    EFFECT_OBLIGATION,
    STATUS_PENDING,
    STATUS_VERIFIED,
    Anchor,
    format_decimal,
)

#: 限值计量基准白名单
BASES = (BASIS_AS_FED, BASIS_DRY_MATTER)

# --------------------------------------------------------------------------
# 判定方式
# --------------------------------------------------------------------------

KIND_PRESENCE = "presence"          #: 存在性判定（标示项是否提供）
KIND_THRESHOLD = "threshold"        #: 阈值判定（保证值 vs 限值）
KIND_CLAIM_SUPPORT = "claim_support"  #: 宣称条件齐备性核查

KINDS = (KIND_PRESENCE, KIND_THRESHOLD, KIND_CLAIM_SUPPORT)

#: 支持的比较运算符（"收紧/放宽"方向语义只对同向阈值运算符成立，见 plan/03）
OPERATORS = (">=", "<=", ">", "<", "==")

_OPERATOR_FUNCS = {
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    "==": lambda a, b: a == b,
}


class RulePackError(Exception):
    """规则包缺失、损坏或不符合契约。"""


# --------------------------------------------------------------------------
# Rule
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Rule:
    """单条判定规则。

    ``status`` 与 ``clause_status`` 是**两个独立状态**（见 plan/03 D2）：
    耦合成单一状态会导致"条款号核不到 → 已核对数值也被无谓阻断"，
    或"只看数值 → 条款号没核对却看起来已核对"。
    """

    rule_id: str
    dimension: str
    kind: str
    target: str
    effect: str = EFFECT_OBLIGATION
    op: Optional[str] = None
    value: Optional[Decimal] = None
    unit: Optional[str] = None
    basis: str = BASIS_AS_FED
    applies_if: Dict[str, Sequence[str]] = field(default_factory=dict)
    required_support: Sequence[str] = ()
    status: str = STATUS_PENDING
    clause_status: str = STATUS_PENDING
    anchor: Optional[Anchor] = None
    note: str = ""

    # -- 适用性 -----------------------------------------------------------

    def applies_to(self, category: Optional[str], life_stage: Optional[str]) -> bool:
        """按 ``applies_if`` 判适用性。

        ``applies_if`` 的键目前支持 ``category``（产品类别）与 ``life_stage``
        （生命阶段）。**未提供的输入不满足任何条件分支**——宁可不判，
        也不拿"缺生命阶段"去套一个具体阶段的限值。
        """
        for key, allowed in self.applies_if.items():
            observed = {"category": category, "life_stage": life_stage}.get(key)
            if observed is None:
                return False
            if observed not in allowed:
                return False
        return True

    def compare(self, observed: Decimal) -> bool:
        """阈值比较（全程 Decimal）。"""
        if self.op is None or self.value is None:
            raise RulePackError("规则 %s 缺 op/value，无法比较" % self.rule_id)
        func = _OPERATOR_FUNCS.get(self.op)
        if func is None:
            raise RulePackError("规则 %s 的运算符 %r 不受支持" % (self.rule_id, self.op))
        return bool(func(observed, self.value))

    def is_effective(self) -> bool:
        """是否进入判定路径——**只看数值 status**。"""
        return self.status == STATUS_VERIFIED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "dimension": self.dimension,
            "kind": self.kind,
            "target": self.target,
            "effect": self.effect,
            "op": self.op,
            "value": None if self.value is None else format_decimal(self.value),
            "unit": self.unit,
            "basis": self.basis,
            "applies_if": {k: list(v) for k, v in sorted(self.applies_if.items())},
            "required_support": list(self.required_support),
            "status": self.status,
            "clause_status": self.clause_status,
            "anchor": None if self.anchor is None else {
                "doc_id": self.anchor.doc_id,
                "doc_title": self.anchor.doc_title,
                "clause": self.anchor.clause,
                "source_url": self.anchor.source_url,
                "captured_at": self.anchor.captured_at,
                "sha256": self.anchor.sha256,
            },
            "note": self.note,
        }


# --------------------------------------------------------------------------
# 解析
# --------------------------------------------------------------------------


def _anchor_from_dict(raw: Optional[Dict[str, Any]]) -> Optional[Anchor]:
    if not raw:
        return None
    return Anchor(
        doc_id=str(raw.get("doc_id", "")),
        doc_title=str(raw.get("doc_title", "")),
        clause=str(raw.get("clause", "")),
        excerpt=str(raw.get("excerpt", "")),
        source_url=str(raw.get("source_url", "")),
        captured_at=str(raw.get("captured_at", "")),
        sha256=str(raw.get("sha256", "")),
    )


def _rule_from_dict(raw: Dict[str, Any], dimension: str) -> Rule:
    rule_id = str(raw.get("rule_id", "")).strip()
    if not rule_id:
        raise RulePackError("规则条目缺 rule_id：%r" % (raw,))
    kind = str(raw.get("kind", "")).strip()
    if kind not in KINDS:
        raise RulePackError("规则 %s 的 kind=%r 不受支持" % (rule_id, kind))

    op = raw.get("op")
    value: Optional[Decimal] = None
    raw_value = raw.get("value")
    if raw_value is not None:
        # Decimal 解析用字符串入口，避免二进制浮点中间态引入尾差。
        value = Decimal(str(raw_value))

    applies_if_raw = raw.get("applies_if") or {}
    applies_if: Dict[str, Sequence[str]] = {
        str(k): tuple(str(x) for x in v) for k, v in applies_if_raw.items()
    }

    effect = str(raw.get("effect", EFFECT_OBLIGATION))
    if effect not in (EFFECT_OBLIGATION, EFFECT_CONDITIONAL):
        raise RulePackError("规则 %s 的 effect=%r 不受支持" % (rule_id, effect))

    basis = str(raw.get("basis", BASIS_AS_FED))
    if basis not in BASES:
        raise RulePackError("规则 %s 的 basis=%r 不受支持" % (rule_id, basis))

    return Rule(
        rule_id=rule_id,
        dimension=str(raw.get("dimension", dimension)),
        kind=kind,
        target=str(raw.get("target", "")),
        effect=effect,
        op=None if op is None else str(op),
        value=value,
        unit=None if raw.get("unit") is None else str(raw["unit"]),
        basis=basis,
        applies_if=applies_if,
        required_support=tuple(str(x) for x in (raw.get("required_support") or ())),
        status=str(raw.get("status", STATUS_PENDING)),
        clause_status=str(raw.get("clause_status", STATUS_PENDING)),
        anchor=_anchor_from_dict(raw.get("anchor")),
        note=str(raw.get("note", "")),
    )


# --------------------------------------------------------------------------
# RulePack
# --------------------------------------------------------------------------


@dataclass
class RulePack:
    """一份规则包（单维度）。"""

    dimension: str
    ruleset_version: str = ""
    rules: List[Rule] = field(default_factory=list)
    source_file: str = ""
    notes: str = ""

    def effective(self) -> List[Rule]:
        """生效条目（**唯一门控点**）。"""
        return [r for r in self.rules if r.is_effective()]

    def pending(self) -> List[Rule]:
        """未生效条目——必须显式呈现，绝不静默丢弃。"""
        return [r for r in self.rules if not r.is_effective()]

    def clause_pending(self) -> List[Rule]:
        """条款号未核对的条目——不阻断判定，但可证性上要显式标注。"""
        return [r for r in self.rules if r.clause_status != STATUS_VERIFIED]


#: 维度 → 规则包文件名
RULESET_FILES = {
    "label": "ruleset-label.json",
    "nutrition": "ruleset-nutrition.json",
    "claim": "ruleset-claim.json",
}


def parse_pack(dimension: str, raw: Dict[str, Any]) -> RulePack:
    """把已解析的规则包 JSON 转成 ``RulePack``（**唯一解析路径**）。

    ``load_pack`` 是"读文件 + 本函数"；生成器要用**内存中的**规则包内容
    算覆盖登记时也走本函数——两条路径各写一套解析 = 最隐蔽的口径漂移。
    """
    if dimension not in DIMENSIONS:
        raise RulePackError("未知维度 %r" % (dimension,))
    rules = [_rule_from_dict(item, dimension) for item in raw.get("rules", [])]
    return RulePack(
        dimension=dimension,
        ruleset_version=str(raw.get("ruleset_version", "")),
        rules=rules,
        source_file=str(raw.get("source_file", "")),
        notes=str(raw.get("notes", "")),
    )


def load_pack(dimension: str, rules_dir: Path) -> RulePack:
    """加载单维度规则包。

    文件不存在时**不抛异常**而是返回空包——M0 骨架阶段规则包尚未录入，
    ``diagnostics`` 要能优雅降级并显式提示，而不是崩溃。
    """
    if dimension not in DIMENSIONS:
        raise RulePackError("未知维度 %r" % (dimension,))
    path = Path(rules_dir) / RULESET_FILES[dimension]
    if not path.is_file():
        return RulePack(dimension=dimension, source_file=str(path),
                        notes="规则包文件不存在：%s（待数据录入）" % path.name)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RulePackError("规则包 %s 无法解析：%s" % (path.name, exc))
    pack = parse_pack(dimension, raw)
    pack.source_file = str(path)
    return pack


def load_manifest(rules_dir: Path) -> Dict[str, Any]:
    """加载 manifest（含验收门槛与覆盖登记）。缺失时返回空 dict。"""
    path = Path(rules_dir) / "manifest.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RulePackError("manifest.json 无法解析：%s" % exc)


def effective_ruleset(scope: str, rules_dir: Path) -> List[Rule]:
    """**唯一门控点**：取指定作用域的生效规则。

    ``scope`` 取 ``label`` / ``nutrition`` / ``claim`` / ``all``。
    每个作用域**只校验自己引用的条目**——不用"整包全 verified"当唯一门，
    否则与某路径无关的 pending 会阻断整条路径（见 plan/03 D3）。
    """
    if scope == "all":
        out: List[Rule] = []
        for dim in DIMENSIONS:
            out.extend(load_pack(dim, rules_dir).effective())
        return out
    if scope not in DIMENSIONS:
        raise RulePackError("未知作用域 %r" % (scope,))
    return load_pack(scope, rules_dir).effective()


def pending_rule_ids(rules_dir: Path) -> List[str]:
    """全部未生效规则 id（供报告"未启用清单"显式呈现）。"""
    out: List[str] = []
    for dim in DIMENSIONS:
        out.extend(r.rule_id for r in load_pack(dim, rules_dir).pending())
    return sorted(out)


def claim_vocabulary(rules_dir: Path) -> Tuple[str, ...]:
    """宣称词表：**从规则包实算**，解析层不持有第二份口径（见 plan/04 §2.2）。

    取 ``claim`` 维度的 ``target`` 集——规则包的 ``target`` 就是宣称词面。
    两份口径必然漂移的失效模式：规则包加一条宣称而解析层不认它 →
    该宣称永远抽不出来 → 规则永远判"未宣称" = **假 skipped**。

    **含 pending 条目**：pending 不进判定路径，但词面仍要抽出来记进档案——
    否则"规则待核对"期间该宣称在报告里凭空消失，等它转 verified 时
    也无从判断"当时到底有没有宣称"。抽出来只进档案、不产生结论。

    返回**排序去重**的元组：顺序确定 → 档案逐字节可复现。
    """
    pack = load_pack(DIM_CLAIM, rules_dir)
    return tuple(sorted({r.target for r in pack.rules if r.target}))


# --------------------------------------------------------------------------
# 零政策字面量门禁：token 运行时实算
# --------------------------------------------------------------------------

#: 数值豁免上界：**整数形态**且绝对值小于此值 → 视为结构性常数（下标 / 计数 /
#: 短文本长度），不作为禁用 token。
#:
#: **非整数一律不豁免**——这条是 M1 的实测勘误。M0 把豁免写成"绝对值 < 100"，
#: 那时规则包是空的、看不出问题；M1 录入真实国标后，全部百分比限值都落在
#: 一百以内的区间，**被该口径整包放过**，``banned_numeric_tokens`` 返回空集——
#: 门禁完全空转（"假门"是本项目明令避免的失效模式）。
#: 本项目的政策数值天然是小于一百的百分数，"按大小豁免"与"零政策字面量"
#: 这个目标在数学上不相容；正确的判别量是**这个数出现在哪里**（见下方定义点），
#: 而不是它多大。
NUMERIC_TOKEN_EXEMPT_INTEGER_BELOW = 20

#: 政策数值的**唯一定义处**：转录器把数值带进系统（且逐条断言原文逐字包含）。
#: 它持有字面量是**定义**不是"抄进代码的第二份真相"——规则包由它生成，
#: 下游一律从规则包读。门禁扫其余全部源码，只对这一处按文件名放行。
POLICY_VALUE_DEFINITION_SITE = "transcribe_clauses.py"


def _exempt_from_tokens(value: Decimal) -> bool:
    """该数值是否作为"结构性常数"豁免出禁用 token 集。"""
    if value == value.to_integral_value():
        return abs(value) < NUMERIC_TOKEN_EXEMPT_INTEGER_BELOW
    return False


def banned_numeric_tokens(rules_dir: Path) -> List[str]:
    """从规则包**运行时实算**禁用数值 token。

    这是"零政策字面量门禁"的根治形态：门禁自己的输入**也不是代码字面量**。
    扫描器源码里不出现任何政策数值，token 全部来自规则包。
    """
    tokens: set = set()
    for dim in DIMENSIONS:
        pack = load_pack(dim, rules_dir)
        for rule in pack.rules:
            if rule.value is None:
                continue
            value = rule.value
            if _exempt_from_tokens(value):
                continue
            tokens.add(format_decimal(value))
            # 整数形态也收编（同一个政策数值的两种写法必须都进 token 集）
            if value == value.to_integral_value():
                tokens.add(str(int(value)))
    return sorted(tokens)


def scan_source_for_tokens(source_text: str, tokens: Iterable[str]) -> List[Tuple[str, int]]:
    """在源码文本里扫禁用 token，返回 ``[(token, 行号)]``。

    词边界用 ``(?<![0-9A-Za-z_.])`` / ``(?![0-9A-Za-z_.])``——避免把
    更长数字里的前缀当命中（子串误报是这类门禁最常见的失效方式）。
    """
    hits: List[Tuple[str, int]] = []
    lines = source_text.splitlines()
    for token in tokens:
        if not token:
            continue
        pattern = re.compile(
            r"(?<![0-9A-Za-z_.])" + re.escape(token) + r"(?![0-9A-Za-z_.])"
        )
        for idx, line in enumerate(lines, start=1):
            if pattern.search(line):
                hits.append((token, idx))
    return hits
