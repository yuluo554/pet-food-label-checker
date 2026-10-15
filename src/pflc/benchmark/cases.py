"""合成标签样例与植入真值（基准的核心资产）。

三条纪律（见 plan/05 §四）：

  * **零真实品牌**：品牌名必须命中假品牌名白名单，白名单外生成器直接报错退出；
  * **真值语义一次定清**：``expected_overall`` 主期望 + ``expected_findings``
    逐规则期望 + ``also_expect`` 同一注入隐含的其余结论 + ``injected`` 人类可读；
  * **确定性**：自研 splitmix64 + 固定 seed，两次运行**逐字节一致**。

对账语义收成**单一实现源**（本模块的 ``observed_nonpass`` / ``compare_nonpass``），
真值库测试与基准**共用**同一函数——否则"基准说达标、测试说不过"的双口径漂移。
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..model import (
    DIM_CLAIM,
    DIM_LABEL,
    DIM_NUTRITION,
    VERDICT_COMPLIANT,
    VERDICT_NONCOMPLIANT,
    VERDICT_NOT_PROVIDED,
    VERDICT_SKIPPED,
    VERDICT_UNKNOWN,
    CheckResult,
)
from .rng import SplitMix64

#: 假品牌名白名单——**禁止真实品牌名入库为基准样例**（见 plan/05 §四.4）
BRAND_WHITELIST: Tuple[str, ...] = (
    "测试粮A", "测试粮B", "测试粮C", "测试粮D", "测试粮E", "测试粮F",
)

#: 样例类型
CASE_COMPLIANT = "compliant"        #: 全部强制项齐备 + 保证值达标 + 宣称有支撑
CASE_MISSING = "missing"            #: 逐项植入缺失
CASE_OVERLIMIT = "overlimit"        #: 保证值越限
CASE_UNSUPPORTED_CLAIM = "unsupported_claim"  #: 宣称无支撑

CASE_TYPES = (CASE_COMPLIANT, CASE_MISSING, CASE_OVERLIMIT, CASE_UNSUPPORTED_CLAIM)

#: 可植入的缺失字段（键为档案字段名）
MISSING_TARGETS = ("net_content", "producer", "additives", "ingredients")

#: 非 pass 结论集合——对账按"文档全部非 pass 集合"比对
NON_PASS = (VERDICT_NONCOMPLIANT, VERDICT_NOT_PROVIDED, VERDICT_UNKNOWN)

#: 默认样例数量（每个类型）
DEFAULT_PER_TYPE = 4

#: 生成器版本（进真值文件，便于溯源"这份真值由哪版生成器产出"）
GENERATOR_VERSION = "1"


class BrandWhitelistError(Exception):
    """品牌名不在白名单内——**直接报错退出**，绝不静默放过。"""


def assert_brand_allowed(brand: str) -> None:
    if brand not in BRAND_WHITELIST:
        raise BrandWhitelistError(
            "品牌名 %r 不在假品牌名白名单内；禁止真实品牌名入库为基准样例" % brand
        )


# --------------------------------------------------------------------------
# 标签文本构造
# --------------------------------------------------------------------------

#: 合成标签的各段落模板。数值**不在这里硬编码**——由调用方按规则包限值算好后传入。
def build_label_text(brand: str, category: str, life_stage: str,
                     guaranteed: Sequence[Tuple[str, str, str]],
                     include_net_content: bool = True,
                     include_producer: bool = True,
                     include_additives: bool = True,
                     include_ingredients: bool = True,
                     claims: Sequence[str] = ()) -> str:
    """拼装一段合成标签全文。

    ``guaranteed`` 为 ``[(指标名, 比较符, 数值字符串)]``。
    """
    assert_brand_allowed(brand)
    lines: List[str] = []
    lines.append("%s %s %s" % (brand, category, life_stage))
    if claims:
        lines.append("产品特点：" + "、".join(claims))
    if include_ingredients:
        lines.append("原料组成：鸡肉、糙米、玉米、鱼油、维生素预混料")
    if include_additives:
        lines.append("添加剂：维生素A、维生素D3、硫酸锌、氯化胆碱")
    lines.append("成分分析保证值：")
    for name, op, value in guaranteed:
        lines.append("%s %s %s%%" % (name, op, value))
    if include_net_content:
        lines.append("净含量：2kg")
    if include_producer:
        lines.append("生产企业：某合成宠物食品有限公司")
    lines.append("生产日期：2026-01-01")
    lines.append("保质期：18个月")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# 样例生成
# --------------------------------------------------------------------------


def _passing_value(limit: Decimal, op: str, margin: Decimal) -> Decimal:
    """按限值算子构造一个**达标**的保证值（留出安全余量）。"""
    if op in (">=", ">"):
        return limit + margin
    if op in ("<=", "<"):
        return max(limit - margin, Decimal("0.1"))
    return limit


def _violating_value(limit: Decimal, op: str, margin: Decimal) -> Decimal:
    """按限值算子构造一个**越限**的保证值。"""
    if op in (">=", ">"):
        return max(limit - margin, Decimal("0.1"))
    if op in ("<=", "<"):
        return limit + margin
    return limit + margin


def generate_cases(rules_dir: Path, per_type: int = DEFAULT_PER_TYPE,
                   seed: int = 20261015) -> Dict[str, Any]:
    """程序化生成四类合成标签样例 + 植入真值。

    **数值全部来自规则包**（经 ``load_pack``），生成器里不出现政策数值字面量——
    与"零政策字面量门禁"同一条纪律。
    """
    from ..rules import KIND_THRESHOLD, load_pack

    rng = SplitMix64(seed)
    nutrition = load_pack("nutrition", rules_dir)
    thresholds = [r for r in nutrition.effective() if r.kind == KIND_THRESHOLD]

    label_pack = load_pack("label", rules_dir)
    presence_rules = {r.target: r for r in label_pack.effective()}
    claim_pack = load_pack("claim", rules_dir)
    claim_rules = list(claim_pack.effective())

    cases: List[Dict[str, Any]] = []
    index = 0

    # --- 类 1：合规样例 -------------------------------------------------
    for i in range(per_type):
        index += 1
        brand = rng.choice(list(BRAND_WHITELIST))
        category, life_stage, guaranteed = _pick_axes(thresholds, rng)
        if not guaranteed:
            break
        text = build_label_text(brand, category, life_stage, guaranteed)
        cases.append(_case(
            case_id="C-%03d" % index, case_type=CASE_COMPLIANT, text=text,
            injected="全部强制标示项齐备；保证值按规则包限值达标",
            expected_overall="compliant",
        ))

    # --- 类 2：缺项样例 -------------------------------------------------
    if presence_rules:
        for i in range(per_type):
            index += 1
            brand = rng.choice(list(BRAND_WHITELIST))
            category, life_stage, guaranteed = _pick_axes(thresholds, rng)
            target = rng.choice(list(MISSING_TARGETS))
            kwargs = {("include_%s" % target): False}
            text = build_label_text(brand, category, life_stage, guaranteed, **kwargs)
            expected: Dict[str, str] = {}
            if target in presence_rules:
                expected[presence_rules[target].rule_id] = VERDICT_NONCOMPLIANT
            cases.append(_case(
                case_id="M-%03d" % index, case_type=CASE_MISSING, text=text,
                injected="植入缺失字段：%s" % target,
                expected_overall="noncompliant" if expected else "not_assessed",
                expected_findings=expected,
                also_expect=[{"target": target, "verdict": VERDICT_NONCOMPLIANT}],
            ))

    # --- 类 3：越限样例 -------------------------------------------------
    if thresholds:
        for i in range(per_type):
            index += 1
            brand = rng.choice(list(BRAND_WHITELIST))
            rule = thresholds[rng.randbelow(len(thresholds))]
            category = _first_of(rule, "category")
            life_stage = _first_of(rule, "life_stage")
            if category is None or life_stage is None:
                continue
            margin = Decimal("2")
            bad = _violating_value(rule.value, rule.op, margin)
            guaranteed = [(rule.target, rule.op, str(bad.normalize()))]
            text = build_label_text(brand, category, life_stage, guaranteed)
            cases.append(_case(
                case_id="O-%03d" % index, case_type=CASE_OVERLIMIT, text=text,
                injected="植入越限：%s %s %s（限值 %s %s）" % (
                    rule.target, rule.op, bad.normalize(), rule.value.normalize(),
                    rule.unit or ""),
                expected_overall="noncompliant",
                expected_findings={rule.rule_id: VERDICT_NONCOMPLIANT},
            ))

    # --- 类 4：宣称无支撑 -----------------------------------------------
    if claim_rules:
        for i in range(per_type):
            index += 1
            rule = claim_rules[rng.randbelow(len(claim_rules))]
            brand = rng.choice(list(BRAND_WHITELIST))
            category, life_stage, guaranteed = _pick_axes(thresholds, rng)
            # 宣称存在但**刻意不提供**其适用条件要求的支撑信息
            text = build_label_text(brand, category, life_stage, guaranteed,
                                    claims=[rule.target],
                                    include_ingredients=False,
                                    include_additives=False)
            cases.append(_case(
                case_id="S-%03d" % index, case_type=CASE_UNSUPPORTED_CLAIM, text=text,
                injected="植入无支撑宣称：%s（缺支撑信息 %s）" % (
                    rule.target, "、".join(rule.required_support)),
                expected_overall="noncompliant",
                expected_findings={rule.rule_id: VERDICT_NONCOMPLIANT},
            ))

    return {
        "generator_version": GENERATOR_VERSION,
        "seed": seed,
        "per_type": per_type,
        "brand_whitelist": list(BRAND_WHITELIST),
        "cases": cases,
    }


def _first_of(rule, key: str) -> Optional[str]:
    allowed = rule.applies_if.get(key)
    if not allowed:
        return None
    return sorted(allowed)[0]


def _pick_axes(thresholds, rng) -> Tuple[str, str, List[Tuple[str, str, str]]]:
    """选一组 (类别, 生命阶段, 达标保证值)。数值按规则包限值算出。"""
    if not thresholds:
        return "", "", []
    # 按 (类别, 生命阶段) 分组，保证同一组内的规则适用同一份档案
    groups: Dict[Tuple[str, str], List[Any]] = {}
    for rule in thresholds:
        category = _first_of(rule, "category")
        life_stage = _first_of(rule, "life_stage")
        if category is None or life_stage is None:
            continue
        groups.setdefault((category, life_stage), []).append(rule)
    if not groups:
        return "", "", []
    keys = sorted(groups)  # 排序后取，保证确定性
    key = keys[rng.randbelow(len(keys))]
    guaranteed: List[Tuple[str, str, str]] = []
    for rule in sorted(groups[key], key=lambda r: r.rule_id):
        good = _passing_value(rule.value, rule.op, Decimal("2"))
        guaranteed.append((rule.target, rule.op, str(good.normalize())))
    return key[0], key[1], guaranteed


def _case(case_id: str, case_type: str, text: str, injected: str,
          expected_overall: str,
          expected_findings: Optional[Dict[str, str]] = None,
          also_expect: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    return {
        "case_id": case_id,
        "case_type": case_type,
        "text": text,
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "injected": injected,
        "expected_overall": expected_overall,
        "expected_findings": expected_findings or {},
        "also_expect": also_expect or [],
    }


# --------------------------------------------------------------------------
# 对账语义（单一实现源，测试与基准共用）
# --------------------------------------------------------------------------


def observed_nonpass(result: CheckResult) -> Dict[str, str]:
    """从判定结果提取"全部非 pass 结论"集合（``rule_id → verdict``）。

    **非 pass = fail ∪ unknown**（``skipped`` 排除在外——那是"不适用"不是
    "缺失"，纳入会制造假结论）。本函数是**单一实现源**，真值库测试与基准
    必须共用，否则双口径漂移。
    """
    out: Dict[str, str] = {}
    for finding in result.all_findings():
        if finding.verdict in NON_PASS:
            out[finding.rule_id] = finding.verdict
    return out


def compare_nonpass(expected: Dict[str, str],
                    observed: Dict[str, str]) -> Dict[str, List[str]]:
    """对账：返回 ``{missing, unexpected, mismatched}``（三集皆空即全对）。"""
    expected_keys = set(expected)
    observed_keys = set(observed)
    missing = sorted(expected_keys - observed_keys)      #: 该报未报（漏检）
    unexpected = sorted(observed_keys - expected_keys)   #: 不该报却报了（误报）
    mismatched = sorted(
        k for k in expected_keys & observed_keys if expected[k] != observed[k]
    )
    return {"missing": missing, "unexpected": unexpected, "mismatched": mismatched}


def write_cases(cases: Dict[str, Any], path: Path) -> None:
    """落盘真值库。**无时间戳**、固定缩进、固定键序——保证逐字节可复现。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(cases, ensure_ascii=False, indent=2, sort_keys=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(payload + "\n")


def load_cases(path: Path) -> Dict[str, Any]:
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8"))


def check_cases_frozen(path: Path, rules_dir: Path,
                       per_type: int = DEFAULT_PER_TYPE,
                       seed: int = 20261015) -> bool:
    """位级一致守门：重新生成并比对入库件。

    返回 True 表示一致（``FROZEN_CASES_OK``）。
    """
    path = Path(path)
    if not path.is_file():
        return False
    on_disk = path.read_text(encoding="utf-8")
    fresh = generate_cases(rules_dir, per_type=per_type, seed=seed)
    expected = json.dumps(fresh, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    return on_disk == expected
