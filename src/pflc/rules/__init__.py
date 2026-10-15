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
    DIMENSIONS,
    EFFECT_CONDITIONAL,
    EFFECT_OBLIGATION,
    STATUS_PENDING,
    STATUS_VERIFIED,
    Anchor,
)

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
            "value": None if self.value is None else str(self.value),
            "unit": self.unit,
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

    return Rule(
        rule_id=rule_id,
        dimension=str(raw.get("dimension", dimension)),
        kind=kind,
        target=str(raw.get("target", "")),
        effect=effect,
        op=None if op is None else str(op),
        value=value,
        unit=None if raw.get("unit") is None else str(raw["unit"]),
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
    rules = [_rule_from_dict(item, dimension) for item in raw.get("rules", [])]
    return RulePack(
        dimension=dimension,
        ruleset_version=str(raw.get("ruleset_version", "")),
        rules=rules,
        source_file=str(path),
        notes=str(raw.get("notes", "")),
    )


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


# --------------------------------------------------------------------------
# 零政策字面量门禁：token 运行时实算
# --------------------------------------------------------------------------

#: 数值豁免下界：小于此值的数视为精度约定/结构性常数，不作为禁用 token。
#: 豁免口径写死在此处（见 plan/03 D5），且**豁免的是"数值大小"不是"文件"**。
NUMERIC_TOKEN_EXEMPT_BELOW = 100


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
            if abs(value) < NUMERIC_TOKEN_EXEMPT_BELOW:
                continue
            text = str(value.normalize())
            tokens.add(text)
            # 整数形态也收编（"22.0" 与 "22" 是同一个政策数值的两种写法）
            if value == value.to_integral_value():
                tokens.add(str(int(value)))
    return sorted(tokens)


def scan_source_for_tokens(source_text: str, tokens: Iterable[str]) -> List[Tuple[str, int]]:
    """在源码文本里扫禁用 token，返回 ``[(token, 行号)]``。

    词边界用 ``(?<![0-9A-Za-z_.])`` / ``(?![0-9A-Za-z_.])``——避免把
    ``220`` 里的 ``22`` 当命中（子串误报是这类门禁最常见的失效方式）。
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
