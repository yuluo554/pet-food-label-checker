"""判定引擎：三态判定 + 双重门控 + 维度聚合（纯确定性，零第三方依赖）。

判定语义硬纪律（见 plan/03 D1，这是本项目最容易被攻击的"假合规"点）：

    原文"应当 X"（无条件义务）→ 缺 X 记 noncompliant      # 绝不记 not_applicable
    原文自带"不适用情形"    → 才允许 skipped
    "没看到材料"            → unknown（不是 fail，但计入待人工确认）
    一条规则都不适用        → 维度 not_assessed（绝不输出 compliant）

单件与批量**共用同一分派点** ``check_card``——两条通路各写一套分派，
会对同一文件给出不同结论（最隐蔽的口径漂移，见 plan/03 D17）。
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from ..model import (
    BASIS_AS_FED,
    BASIS_DRY_MATTER,
    DIM_CLAIM,
    DIM_LABEL,
    DIM_NUTRITION,
    DIMENSIONS,
    EFFECT_CONDITIONAL,
    EXCLUDE_NO_EFFECTIVE_RULES,
    FIELD_MOISTURE,
    FIELD_PROVIDED,
    OVERALL_NOT_ASSESSED,
    REASON_BASIS_UNDETERMINED,
    VERDICT_COMPLIANT,
    VERDICT_NONCOMPLIANT,
    VERDICT_NOT_PROVIDED,
    VERDICT_SKIPPED,
    VERDICT_UNKNOWN,
    CheckResult,
    DimensionResult,
    Finding,
    LabelCard,
    format_decimal,
)
from ..rules import (
    KIND_CLAIM_SUPPORT,
    KIND_PRESENCE,
    KIND_THRESHOLD,
    Rule,
    RulePack,
    RulePackError,
    claim_vocabulary,
    load_pack,
)

#: 规则 ``applies_if`` 支持的门控键
_GATE_KEYS = ("category", "life_stage")


class EngineError(Exception):
    """引擎层面的契约错误（如规则 kind 未知）。"""


# --------------------------------------------------------------------------
# 单规则判定
# --------------------------------------------------------------------------


def _judge_presence(rule: Rule, card: LabelCard) -> Finding:
    """存在性判定：标示项是否提供。

    无条件义务（``effect=obligation``）缺失 = **noncompliant**——
    这是"没做绝不记成不用做"的落地（见 plan/03 D1）。
    条件触发项（``effect=conditional``）缺失记 ``unknown``（待人工确认）。
    """
    field = card.field(rule.target)
    if field is None:
        # 规则指向的字段在档案里不存在：这是规则与模型的契约错位，显式报出
        return Finding(
            rule_id=rule.rule_id, dimension=rule.dimension, target=rule.target,
            verdict=VERDICT_UNKNOWN, effect=rule.effect,
            note="规则目标 %r 不在标签档案字段集内" % rule.target,
            anchor=rule.anchor,
        )

    if field.status == FIELD_PROVIDED:
        return Finding(
            rule_id=rule.rule_id, dimension=rule.dimension, target=rule.target,
            verdict=VERDICT_COMPLIANT, effect=rule.effect,
            observed=field.render(), expected="已标示", anchor=rule.anchor,
        )

    # 未提供：区分"无条件义务缺失"与"条件触发项缺失"
    if rule.effect == EFFECT_CONDITIONAL:
        return Finding(
            rule_id=rule.rule_id, dimension=rule.dimension, target=rule.target,
            verdict=VERDICT_UNKNOWN, effect=rule.effect,
            observed=field.render(), expected="条件触发，需人工确认",
            note=field.reason, anchor=rule.anchor,
        )

    return Finding(
        rule_id=rule.rule_id, dimension=rule.dimension, target=rule.target,
        verdict=VERDICT_NONCOMPLIANT, effect=rule.effect,
        observed=field.render(), expected="应当标示", note=field.reason,
        anchor=rule.anchor,
    )


def _to_dry_matter(observed: Decimal, card: LabelCard) -> Optional[Decimal]:
    """把"按标示状态（as-fed）"的观测值换算到**干物质基准**。

    GB/T 31216/31217 的理化指标表头写明"指标（以干物质计）/%"，而标签上标示的
    保证值是按产品标示状态给的。两者**基准不同，直接比会造假结论**：
    高水分的湿粮标示的百分数换算到干基后会显著变大，直接比会误判为不符合。
    实测本项目基准套件正是这样产生过误报。

    换算：``干基值 = 标示值 / (1 - 水分% / 100)``。
    水分未标示 → 无法换算，返回 ``None``（调用方记"基准无法确定"，
    **绝不拿未换算的值去比**，也绝不猜一个水分）。
    """
    moisture = card.guaranteed.get(FIELD_MOISTURE)
    if moisture is None or not moisture.is_provided:
        return None
    try:
        moisture_value = Decimal(str(moisture.value))
    except Exception:
        return None
    # 水分必须是 (0,100) 开区间内的百分数；越界即无法作为换算依据
    if not (Decimal(0) < moisture_value < Decimal(100)):
        return None
    dry_fraction = (Decimal(100) - moisture_value) / Decimal(100)
    return observed / dry_fraction


def _judge_threshold(rule: Rule, card: LabelCard) -> Finding:
    """阈值判定：保证值 vs 限值（全程 Decimal）。

    保证值缺失 → ``not_provided``（不是不符合——没给值 ≠ 值不达标）。

    基准处理：限值若为**干物质基准**（GB/T 理化指标表），先把观测值换算到
    干基再比；换算所需的"水分"缺失时记 ``unknown`` + 原因码
    ``basis_undetermined``——**不拿未换算的值直接比**（那会造假结论）。
    """
    field = card.field(rule.target)
    if field is None or not field.is_provided:
        reason = field.reason if field is not None else "field_absent"
        return Finding(
            rule_id=rule.rule_id, dimension=rule.dimension, target=rule.target,
            verdict=VERDICT_NOT_PROVIDED, effect=rule.effect,
            observed="未提供", expected=_render_expected(rule),
            note=reason, anchor=rule.anchor,
        )

    observed = field.value
    if not isinstance(observed, Decimal):
        try:
            observed = Decimal(str(observed))
        except Exception:
            return Finding(
                rule_id=rule.rule_id, dimension=rule.dimension, target=rule.target,
                verdict=VERDICT_UNKNOWN, effect=rule.effect,
                observed=str(field.value), expected=_render_expected(rule),
                note="观测值无法作为数值比较", anchor=rule.anchor,
            )

    compare_value = observed
    basis_note: Optional[str] = None
    if getattr(rule, "basis", BASIS_AS_FED) == BASIS_DRY_MATTER:
        converted = _to_dry_matter(observed, card)
        if converted is None:
            return Finding(
                rule_id=rule.rule_id, dimension=rule.dimension, target=rule.target,
                verdict=VERDICT_UNKNOWN, effect=rule.effect,
                observed=_render_value(observed, field.unit),
                expected=_render_expected(rule),
                note=REASON_BASIS_UNDETERMINED,
                anchor=rule.anchor,
            )
        compare_value = converted
        basis_note = "标示值 %s 换算为干基 %s（水分 %s%%）" % (
            format_decimal(observed), format_decimal(converted),
            format_decimal(Decimal(str(card.guaranteed[FIELD_MOISTURE].value))))

    try:
        ok = rule.compare(compare_value)
    except RulePackError as exc:
        return Finding(
            rule_id=rule.rule_id, dimension=rule.dimension, target=rule.target,
            verdict=VERDICT_UNKNOWN, effect=rule.effect,
            observed=str(compare_value), expected=_render_expected(rule),
            note=str(exc), anchor=rule.anchor,
        )

    return Finding(
        rule_id=rule.rule_id, dimension=rule.dimension, target=rule.target,
        verdict=VERDICT_COMPLIANT if ok else VERDICT_NONCOMPLIANT,
        effect=rule.effect,
        observed=_render_value(observed, field.unit),
        expected=_render_expected(rule), note=basis_note, anchor=rule.anchor,
    )


def _judge_claim_support(rule: Rule, card: LabelCard) -> Finding:
    """宣称条件齐备性核查。

    **不做语义硬判**——只查"宣称存在 → 其适用条件所要求的信息支撑是否齐备"。
    "配料是否确为天然"这类语义问题不判（见 plan/04 §四.1）。
    """
    claim_present = rule.target in card.claim_names()
    if not claim_present:
        # 宣称不存在 → 该规则不适用（这是"原文写了适用前提"的情形：
        # 规则的前提是"该宣称存在"，未宣称即前提不成立 → skipped 而非 noncompliant）
        return Finding(
            rule_id=rule.rule_id, dimension=rule.dimension, target=rule.target,
            verdict=VERDICT_SKIPPED, effect=rule.effect,
            observed="未宣称", expected="未宣称时不适用", anchor=rule.anchor,
        )

    missing = [name for name in rule.required_support
               if not _support_present(card, name)]
    if missing:
        return Finding(
            rule_id=rule.rule_id, dimension=rule.dimension, target=rule.target,
            verdict=VERDICT_NONCOMPLIANT, effect=rule.effect,
            observed="已宣称但支撑信息不齐备",
            expected="需齐备：" + "、".join(rule.required_support),
            note="缺少：" + "、".join(missing), anchor=rule.anchor,
        )
    return Finding(
        rule_id=rule.rule_id, dimension=rule.dimension, target=rule.target,
        verdict=VERDICT_COMPLIANT, effect=rule.effect,
        observed="已宣称且支撑信息齐备",
        expected="需齐备：" + "、".join(rule.required_support),
        anchor=rule.anchor,
    )


def _support_present(card: LabelCard, name: str) -> bool:
    """支撑信息是否齐备。字段名经档案统一查询入口解析。"""
    field = card.field(name)
    return bool(field is not None and field.is_provided)


def _render_value(value: Decimal, unit: Optional[str]) -> str:
    text = format_decimal(value)
    return "%s %s" % (text, unit) if unit else text


def _render_expected(rule: Rule) -> str:
    if rule.op is None or rule.value is None:
        return ""
    text = "%s %s" % (rule.op, format_decimal(rule.value))
    if rule.unit:
        text = "%s %s" % (text, rule.unit)
    if getattr(rule, "basis", BASIS_AS_FED) == BASIS_DRY_MATTER:
        text = "%s（以干物质计）" % text
    return text


_JUDGES = {
    KIND_PRESENCE: _judge_presence,
    KIND_THRESHOLD: _judge_threshold,
    KIND_CLAIM_SUPPORT: _judge_claim_support,
}


# --------------------------------------------------------------------------
# 维度判定
# --------------------------------------------------------------------------


def judge_dimension(pack: RulePack, card: LabelCard) -> DimensionResult:
    """对单维度跑全部生效规则。

    适用性筛选：``applies_if`` 未命中的规则**不参与**——但维度是否"未评估"
    取决于**有没有生效规则**（而非有没有适用规则），见下方 excluded/not_assessed 区分。
    """
    result = DimensionResult(dimension=pack.dimension)
    effective = pack.effective()

    if not effective:
        # 零生效规则 → 该维度不参与聚合，理由显式记录（见 plan/03 D4）
        result.excluded = True
        result.exclude_reason = EXCLUDE_NO_EFFECTIVE_RULES
        return result

    category = card.category_value()
    life_stage = card.life_stage_value()

    applicable: List[Rule] = []
    for rule in effective:
        if rule.applies_to(category, life_stage):
            applicable.append(rule)

    if not applicable:
        # 有生效规则但本条输入无适用项 → not_assessed（绝不输出 compliant）
        result.not_assessed = True
        return result

    findings: List[Finding] = []
    for rule in applicable:
        judge = _JUDGES.get(rule.kind)
        if judge is None:
            raise EngineError("规则 %s 的 kind=%r 无判定实现" % (rule.rule_id, rule.kind))
        findings.append(judge(rule, card))

    result.findings = findings
    return result


# --------------------------------------------------------------------------
# 全维度判定（单一分派点）
# --------------------------------------------------------------------------


def _reconcile_claim_vocabulary(card: LabelCard, rules_dir: Path) -> LabelCard:
    """把档案的宣称口径对齐到**本轮规则包**（见 plan/04 §2.2）。

    失效模式：调用方直接 ``parse_label(text)``（不传词表）造出档案，
    再交给引擎判定。此时 ``card.claim_names()`` 恒为空，``claim_support``
    规则会把每条宣称规则判成 ``skipped``——**假 skipped**：
    把"这个词我没抽过"读成"标签上没宣称"。

    修法不是让每个调用点自己记得传词表（那正是两份口径的来源），
    而是在**唯一分派点**上核对并按需重抽：词表是 ``raw_text`` 与规则包的
    确定函数，重抽不引入不确定性，且判定结论从此与"调用方是否传词表"无关。
    """
    vocab = claim_vocabulary(rules_dir)
    if set(vocab).issubset(set(card.claim_vocab)):
        # 档案已覆盖本轮词表（含"两者皆空"）→ 无需重抽
        return card
    if not vocab:
        return card
    from ..parse import extract_claims

    card.claims = extract_claims(card.raw_text, vocab)
    card.claim_vocab = tuple(vocab)
    return card


def check_card(card: LabelCard, rules_dir: Path,
               scope: str = "all") -> CheckResult:
    """**唯一分派点**：对一张标签档案跑全维度判定。

    单件（``check_file``）与批量（``scan_dir``）都必须经此函数——
    两条通路各写一套分派 = 对同一文件给出不同结论。
    """
    if scope == "all" or scope == DIM_CLAIM:
        card = _reconcile_claim_vocabulary(card, rules_dir)

    if scope == "all":
        dims: Sequence[str] = DIMENSIONS
    else:
        dims = (scope,)

    results: List[DimensionResult] = []
    pending: List[str] = []
    for dim in dims:
        pack = load_pack(dim, rules_dir)
        pending.extend(r.rule_id for r in pack.pending())
        results.append(judge_dimension(pack, card))

    return CheckResult(
        card_id=card.card_id,
        source=card.source,
        dimensions=results,
        pending_rules=sorted(set(pending)),
    )


def check_file(path: Path, rules_dir: Path, scope: str = "all") -> CheckResult:
    """单件核验。读取失败抛 ``OSError``，由调用方按"未判定"处置。

    宣称词表从 ``rules_dir`` 取出后传给解析层——两条通路（单件/批量）都经
    本函数，故口径只有一处。
    """
    from ..parse import parse_label

    text = Path(path).read_text(encoding="utf-8")
    card = parse_label(text, source=Path(path).name,
                       claim_words=claim_vocabulary(rules_dir))
    return check_card(card, rules_dir, scope=scope)


# --------------------------------------------------------------------------
# 批量 + 两轮对账
# --------------------------------------------------------------------------

#: 对账四类集
DELTA_NEW = "new_violation"          #: 新增违规
DELTA_FIXED = "fixed"                #: 已修复
DELTA_PERSISTENT = "persistent"      #: 持续违规
DELTA_STABLE = "stable"              #: 稳定（两轮同结论）
DELTA_CONTENT_CHANGED = "content_changed"  #: 内容变化但结论未变（另立标记，不退化）

#: 失败件类型（**未判定**，不是违规，见 plan/03 D17）
KIND_OK = "ok"
KIND_FAILED = "failed"

#: 单件输入大小上限（安全阀，防超大输入整体读入内存）
MAX_INPUT_BYTES = 4 * 1024 * 1024


def _violation_keys(result: CheckResult) -> set:
    """违规键集：``(维度, 规则 id)``——**非 pass 但排除 skipped/unknown**。

    ``skipped``（不适用）与 ``unknown``（未观测）**不算违规**：
    前者是原文写了例外，后者是"没看到"而非"缺失"。
    """
    keys = set()
    for finding in result.all_findings():
        if finding.verdict == VERDICT_NONCOMPLIANT:
            keys.add((finding.dimension, finding.rule_id))
    return keys


def compare_rounds(previous: Dict[str, set],
                   current: Dict[str, set]) -> Dict[str, List[str]]:
    """两轮对账（配对主键 = **稳定身份键**，不用内容指纹，见 plan/03 D18）。

    配对逻辑分两步，缺一不可：
      ① **配对**：按稳定身份键（``file:<相对路径>``）把两轮的同一件对上——
         用内容指纹配对时，"已修复"必然内容变了 → 永远配不上 → **永远检不出已修复**；
      ② **判定**：配对成功的件再按**违规条目**比对（不是"键在不在"）——
         上一轮有、本轮无 → ``fixed``；两轮都有 → ``persistent``；本轮新出现 → ``new``。

    返回的是**违规条目级**的键（``file:xxx::维度/规则id``），这样"已修复"
    能指明是哪条规则不再触发了，而不只是"这个文件变好了"。
    键存在 ≠ 有违规——把"键在不在"当判据会让 fixed 恒为空集。
    """
    def _expand(pairs: Dict[str, set]) -> Dict[str, set]:
        out: Dict[str, set] = {}
        for file_key, violations in pairs.items():
            for dim, rule_id in violations:
                out["%s::%s/%s" % (file_key, dim, rule_id)] = {file_key}
        return out

    prev_items = _expand(previous)
    cur_items = _expand(current)

    new_items = sorted(set(cur_items) - set(prev_items))
    fixed_items = sorted(set(prev_items) - set(cur_items))
    persistent_items = sorted(set(prev_items) & set(cur_items))
    # stable = 两轮都无违规的件（按件计，不按违规条目计）
    stable_files = sorted(
        k for k in set(previous) & set(current)
        if not previous[k] and not current[k]
    )
    return {
        DELTA_NEW: new_items,
        DELTA_FIXED: fixed_items,
        DELTA_PERSISTENT: persistent_items,
        DELTA_STABLE: stable_files,
    }


def scan_dir(directory: Path, rules_dir: Path,
             baseline: Optional[Dict[str, set]] = None) -> Dict[str, object]:
    """批量扫描 + 可选两轮对账。

    两条退出码纪律（见 plan/03 D17）：
      * **失败件 ≠ 违规**——坏文件记 ``failed``，**不改变退出码**；
      * **失败隔离**——单件异常不中断整批。
    """
    directory = Path(directory)
    if not directory.is_dir():
        raise EngineError("目录不存在：%s" % directory)

    items: List[Dict[str, object]] = []
    current: Dict[str, set] = {}
    for path in sorted(directory.glob("*.txt")):
        entry: Dict[str, object] = {"file": path.name, "kind": KIND_OK}
        try:
            if path.stat().st_size > MAX_INPUT_BYTES:
                entry["kind"] = KIND_FAILED
                entry["error"] = "input_too_large"
                items.append(entry)
                continue
            result = check_file(path, rules_dir)
            entry["card_id"] = result.card_id
            entry["overall"] = result.overall()
            violations = _violation_keys(result)
            entry["violations"] = sorted("%s/%s" % k for k in violations)
            current["file:%s" % path.name] = violations
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            # 失败隔离：记录后继续，不中断整批
            entry["kind"] = KIND_FAILED
            entry["error"] = "%s: %s" % (type(exc).__name__, exc)
        items.append(entry)

    out: Dict[str, object] = {"items": items, "total": len(items)}
    out["failed"] = sum(1 for i in items if i["kind"] == KIND_FAILED)
    out["has_violation"] = any(bool(i.get("violations")) for i in items)
    if baseline is not None:
        out["delta"] = compare_rounds(baseline, current)
    out["current"] = current
    return out
