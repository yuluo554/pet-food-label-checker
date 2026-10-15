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
    BASIS_DRY_MATTER,
    EFFECT_OBLIGATION,
    DIM_CLAIM,
    DIM_LABEL,
    DIM_NUTRITION,
    FIELD_MOISTURE,
    STATUS_VERIFIED,
    VERDICT_COMPLIANT,
    VERDICT_NONCOMPLIANT,
    VERDICT_NOT_PROVIDED,
    VERDICT_SKIPPED,
    VERDICT_UNKNOWN,
    CheckResult,
    format_decimal,
)
from ..rules import RulePackError
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

#: 标签模板**能移除**的字段（生成器的构造能力，不是判定口径）。
#: 判定口径（"缺了算不符合还是未观测"）一律由规则包决定——M0 曾在这里
#: 把 additives 当成无条件义务写死，M1 按原文核对后该条是条件触发，
#: 于是基准自己产出了一条假真值。**能移除 ≠ 缺了就违规**。
MISSING_TARGETS = ("net_content", "producer", "additives", "ingredients")

#: 非 pass 结论集合——对账按"文档全部非 pass 集合"比对
NON_PASS = (VERDICT_NONCOMPLIANT, VERDICT_NOT_PROVIDED, VERDICT_UNKNOWN)

#: 默认样例数量（每个类型）
DEFAULT_PER_TYPE = 4

#: 生成器版本（进真值文件，便于溯源"这份真值由哪版生成器产出"）
GENERATOR_VERSION = "1"

#: 冻结真值库文件名（入库件；见 plan/03 D11）
CASES_FILENAME = "cases.json"

#: 覆盖登记声明（**写清口径**，否则"采样数"三个字本身就歧义）。
#:
#: ``sampled_in_truth`` 的定义见 ``sampled_rule_ids``：真值库为该规则写下了
#: **显式逐条期望**（``expected_findings`` 的 key）。**不是**"被用例触达的规则数"
#: ——后者恒等于生效规则总数，是又一个假台账。
COVERAGE_NOTE = (
    "抽样覆盖、非逐因素穷举。sampled_in_truth = 真值库为该规则写下显式逐条期望"
    "（expected_findings）的规则数；合规类用例虽逐条判了全部生效规则但无显式期望，"
    "故不计入采样数"
)


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


#: 合成标签标示的水分含量（**夹具数据，不是政策数值**）。
#:
#: 国标理化指标是干基，标签标示是 as-fed；要构造"按干基恰好达标/越限"的
#: 合成样例，标签上就必须有一个水分，引擎才有换算依据。这个值由夹具自己定，
#: 与规则包无关（它不是任何标准里的限值），故不属于"政策数值"。
#: 取一个干粮口径的值，使"标示值 ≠ 干基值"成立——正是这样才让"基准不同"
#: 这件事在基准套件里真的被测到，而不是被"水分=0"的退化情形掩盖。
SYNTHETIC_MOISTURE = Decimal("12")


def _sample_moisture(thresholds) -> Decimal:
    """合成样例标示的水分（夹具数据，见 ``SYNTHETIC_MOISTURE``）。"""
    return SYNTHETIC_MOISTURE


def _to_declared(limit: Decimal, op: str, basis: str,
                 moisture: Optional[Decimal]) -> Decimal:
    """把**干基**限值换算成该标签应当标示的**as-fed**值。

    只在样例确实要构造"达标/越限"的标示值、且限值是干基时才需要：
    ``as-fed = 干基 × (1 - 水分%/100)``。
    """
    if basis != BASIS_DRY_MATTER or moisture is None:
        return limit
    return limit * (Decimal(100) - moisture) / Decimal(100)


def generate_cases(rules_dir: Path, per_type: int = DEFAULT_PER_TYPE,
                   seed: int = 20261015,
                   packs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """程序化生成四类合成标签样例 + 植入真值。

    **数值全部来自规则包**（经 ``load_pack``），生成器里不出现政策数值字面量——
    与"零政策数值字面量门禁"同一条纪律。

    ``packs`` 可传**已加载的** ``{维度: RulePack}``（生成器用内存中的规则包
    算覆盖登记时走这条），默认从 ``rules_dir`` 加载——**同一套生成逻辑**，
    不因入口不同而产出不同的真值。
    """
    from ..rules import KIND_THRESHOLD, load_pack

    rng = SplitMix64(seed)
    if packs is None:
        nutrition = load_pack("nutrition", rules_dir)
        label_pack = load_pack("label", rules_dir)
        claim_pack = load_pack("claim", rules_dir)
    else:
        nutrition = packs["nutrition"]
        label_pack = packs["label"]
        claim_pack = packs["claim"]
    thresholds = [r for r in nutrition.effective() if r.kind == KIND_THRESHOLD]
    presence_rules = {r.target: r for r in label_pack.effective()}
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
    # 期望**从规则包的 effect 实算**，不写死："无条件义务缺失 = noncompliant；
    # 条件触发项缺失 = unknown（待人工确认）"。M0 把 additives 写死成义务，
    # M1 按原文核对后该条是条件触发 → 写死就会产出假真值。
    if presence_rules:
        for i in range(per_type):
            index += 1
            brand = rng.choice(list(BRAND_WHITELIST))
            category, life_stage, guaranteed = _pick_axes(thresholds, rng)
            target = rng.choice(list(MISSING_TARGETS))
            kwargs = {("include_%s" % target): False}
            text = build_label_text(brand, category, life_stage, guaranteed, **kwargs)
            expected: Dict[str, str] = {}
            rule = presence_rules.get(target)
            if rule is not None:
                # 义务类型决定缺失结论（见 plan/03 D1 分栏纪律）
                expected[rule.rule_id] = (
                    VERDICT_NONCOMPLIANT
                    if rule.effect == EFFECT_OBLIGATION else VERDICT_UNKNOWN
                )
            overall = (
                "noncompliant"
                if any(v == VERDICT_NONCOMPLIANT for v in expected.values())
                else "compliant"
            )
            cases.append(_case(
                case_id="M-%03d" % index, case_type=CASE_MISSING, text=text,
                injected="植入缺失字段：%s（该字段的规则 effect=%s）" % (
                    target, rule.effect if rule is not None else "无规则"),
                expected_overall=overall,
                expected_findings=expected,
                also_expect=[{"target": target,
                              "verdict": expected.get(rule.rule_id, "")
                              if rule is not None else ""}],
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
            moisture = _sample_moisture(thresholds)
            # 越限样例：把干基限值先换算成 as-fed，再往下压出"越限"的标示值；
            # 直接拿干基限值减余量会得到一个**按 as-fed 看低得离谱**的数，
            # 而它换算回干基后可能反而达标——"期望不符合"就成了假真值。
            declared_limit = _to_declared(rule.value, rule.op, rule.basis, moisture)
            bad = _violating_value(declared_limit, rule.op, margin)
            guaranteed: List[Tuple[str, str, str]] = []
            # 目标指标本身是水分时不另写一行：解析器对同一指标只取首个出现，
            # 多写会把真正要断言的那个值顶掉（夹具自相矛盾）。
            if moisture is not None and rule.target != FIELD_MOISTURE:
                guaranteed.append((FIELD_MOISTURE, "<=", format_decimal(moisture)))
            guaranteed.append((rule.target, rule.op, format_decimal(bad)))
            text = build_label_text(brand, category, life_stage, guaranteed)
            cases.append(_case(
                case_id="O-%03d" % index, case_type=CASE_OVERLIMIT, text=text,
                injected="植入越限：%s %s %s（标示口径；干基限值 %s %s）" % (
                    rule.target, rule.op, format_decimal(bad),
                    format_decimal(rule.value), rule.unit or ""),
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
    """选一组 (类别, 生命阶段, 达标保证值)。数值按规则包限值算出。

    **基准换算**：国标理化指标是干基，标签标示是 as-fed。样例同时标示水分，
    标示值由干基限值换算而来——否则"按干基比"的引擎会把合规样例判成不符合
    （实测本项目基准套件正是这样报过误报）。
    """
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
    moisture = _sample_moisture(thresholds)
    guaranteed: List[Tuple[str, str, str]] = []
    if moisture is not None:
        guaranteed.append((FIELD_MOISTURE, "<=", format_decimal(moisture)))
    for rule in sorted(groups[key], key=lambda r: r.rule_id):
        if rule.target == FIELD_MOISTURE:
            continue  # 水分已单独标示，不重复
        declared_limit = _to_declared(rule.value, rule.op, rule.basis, moisture)
        good = _passing_value(declared_limit, rule.op, Decimal("2"))
        guaranteed.append((rule.target, rule.op, format_decimal(good)))
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


def cases_path_for(rules_dir: Path) -> Path:
    """真值库入库件路径（数据布局：``<data>/rules`` 与 ``<data>/benchmark`` 同级）。

    单一定义源——工具、基准、测试**共用**它，避免各自拼路径而漂移。
    """
    return Path(rules_dir).parent / "benchmark" / CASES_FILENAME


def render_cases(cases: Dict[str, Any]) -> str:
    """真值库的确定性文本形态（**无时间戳**、固定缩进、固定键序）。

    落盘与位级比对共用本函数——否则"写的时候一种序列化、比的时候另一种"，
    守门比的是一个永远不存在的字节串（假门）。
    """
    return json.dumps(cases, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_cases(cases: Dict[str, Any], path: Path) -> None:
    """落盘真值库（逐字节可复现）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(render_cases(cases))


def _case_brand(case: Dict[str, Any]) -> str:
    """取用例文本首行的品牌名（生成侧与载入侧**同一判据**）。"""
    text = str(case.get("text", ""))
    return text.split("\n", 1)[0].split(" ")[0] if text else ""


def assert_cases_brands_allowed(cases: Dict[str, Any]) -> None:
    """载入侧白名单硬断言（K18 的**第二个实例**）。

    生成侧已有 ``assert_brand_allowed``，但载入侧原本零校验——实测：
    手工构造含真实品牌名的 ``cases.json`` 交给 ``load_cases`` 会被**原样接受**。
    一旦入库件被手改、或未来支持外部真值库，真实品牌数据就能绕过白名单
    进入基准真值，与"真实品牌数据与合成基准严格隔离"直接冲突。

    **同一口径要一次对齐全部实例**（M2 的教训：一侧修了、另一侧漏了 = 假门）。
    """
    declared = cases.get("brand_whitelist")
    if list(declared or []) != list(BRAND_WHITELIST):
        raise BrandWhitelistError(
            "真值库声明的 brand_whitelist 与生成器白名单不一致：%r" % (declared,)
        )
    for case in cases.get("cases", []):
        brand = _case_brand(case)
        if brand not in BRAND_WHITELIST:
            raise BrandWhitelistError(
                "真值库用例 %s 的品牌名 %r 不在假品牌名白名单内；"
                "禁止真实品牌数据进入合成基准" % (case.get("case_id", "<无 id>"), brand)
            )


def load_cases(path: Path) -> Dict[str, Any]:
    """加载冻结真值库。**载入即校验品牌白名单**（见 ``assert_cases_brands_allowed``）。"""
    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert_cases_brands_allowed(payload)
    return payload


def cases_match_generator(cases: Dict[str, Any], rules_dir: Path,
                          per_type: int = DEFAULT_PER_TYPE,
                          seed: int = 20261015) -> bool:
    """入库件内容 == 生成器输出（内容级比对，不读盘）。"""
    fresh = generate_cases(rules_dir, per_type=per_type, seed=seed)
    return render_cases(cases) == render_cases(fresh)


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
    return on_disk == render_cases(fresh)


# --------------------------------------------------------------------------
# 覆盖登记（manifest.coverage 的唯一来源）
# --------------------------------------------------------------------------


def sampled_rule_ids(cases: Dict[str, Any], packs) -> Dict[str, List[str]]:
    """真值库**对该规则带显式逐条期望**的规则 id（按维度归集）。

    **口径（单一定义源，写死在这里）**：采样数 = ``expected_findings`` 的 key
    归集出的规则数。即"真值库为这条规则写下了明确的非 pass 期望"。

    **为什么不用"被用例触达的规则数"**：合规类用例的 ``expected_findings`` 是
    ``{}``，但它同样逐条判了全部生效规则——按"触达"算，采样数会**恒等于生效
    规则总数**（本项目实测 8/8、5/5、30/30）。那个数永远 100%，不携带任何信息，
    且与"抽样覆盖非穷举"的声明自相矛盾——**它就是又一个假台账**。
    """
    by_id: Dict[str, str] = {}
    for dim in sorted(packs):
        for rule in packs[dim].rules:
            by_id[rule.rule_id] = dim

    out: Dict[str, List[str]] = {dim: [] for dim in sorted(packs)}
    for case in cases.get("cases", []):
        for rule_id in sorted(case.get("expected_findings", {})):
            dim = by_id.get(rule_id)
            if dim is None:
                raise RulePackError(
                    "真值库期望引用了规则包里不存在的规则 %r（真值与规则包已脱钩）"
                    % rule_id
                )
            if rule_id not in out[dim]:
                out[dim].append(rule_id)
    return {dim: sorted(ids) for dim, ids in out.items()}


def coverage_from_cases(cases: Dict[str, Any], packs) -> Dict[str, Dict[str, Any]]:
    """从**冻结真值库 + 本轮规则包**实算覆盖登记。

    ``packs`` 为 ``{维度: RulePack}``。返回与 ``manifest.coverage`` 同形。
    """
    sampled = sampled_rule_ids(cases, packs)
    out: Dict[str, Dict[str, Any]] = {}
    for dim in sorted(packs):
        rules = packs[dim].rules
        ids = sampled.get(dim, [])
        out[dim] = {
            "total_rules": len(rules),
            "verified_rules": sum(
                1 for r in rules if r.status == STATUS_VERIFIED
            ),
            "sampled_in_truth": len(ids),
            "sample_list": ids,
            "note": COVERAGE_NOTE,
        }
    return out
