#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""规则包生成器：条文块 → 版本化规则包（冻结产物，禁手改）。

**为什么规则包必须由生成器产出**：规则包是基准的可信锚。若可手改，
"引擎对不对"就永远无法与"数据对不对"分离。改需求走本脚本整目录重生成，
配 ``--check`` 位级一致守门。

输入（人工/脚本录入的条文块）：
    data/knowledge/clauses/label.json      —— 标签规定条款 → 标示项规则
    data/knowledge/clauses/nutrition.json  —— GB/T 31216/31217 限值 → 阈值规则
    data/knowledge/clauses/claim.json      —— 限定用语条款 → 宣称规则
    data/knowledge/clauses/sources.json    —— 参数来源登记（发布机关/文号/URL/日期/sha256）

输出（冻结产物）：
    data/rules/ruleset-{label,nutrition,claim}.json
    data/rules/manifest.json

确定性纪律（见 plan/05 §三.2）：
    禁 stdlib random、禁 set 迭代序、禁系统时钟；产物无时间戳；
    JSON 序列化固定（sort_keys + ensure_ascii=False + indent=2 + LF）。

用法：
    py -X utf8 tools/gen_rulesets.py --force    # 重生成
    py -X utf8 tools/gen_rulesets.py --check    # 位级一致校验（守门用）
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

# --- 入口编码守卫：覆盖所有会打印的可执行入口（见 plan/07 K22）-------------
for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    if _stream is not None:
        _enc = (getattr(_stream, "encoding", None) or "").lower()
        if _enc not in ("utf-8", "utf8"):
            _reconf = getattr(_stream, "reconfigure", None)
            if _reconf is not None:
                try:
                    _reconf(encoding="utf-8")
                except (ValueError, OSError):
                    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from pflc.rules import RULESET_FILES, load_pack  # noqa: E402
from pflc.benchmark.cases import (  # noqa: E402
    CASES_FILENAME,
    coverage_from_cases,
    generate_cases,
    load_cases,
)

CLAUSES_DIR = ROOT / "data" / "knowledge" / "clauses"
RULES_DIR = ROOT / "data" / "rules"
BENCHMARK_DIR = ROOT / "data" / "benchmark"
CASES_PATH = BENCHMARK_DIR / CASES_FILENAME

#: 规则包版本（人工维护；进 manifest 与每份规则包）
RULESET_VERSION = "2026.1"

#: 验收门槛（**随 manifest 下发，基准层只读**，见 plan/03 D13）
#: 这是数据不是代码：基准不得回落这些值。
THRESHOLDS = {
    "min_accuracy": 0.95,
    "max_false_positive": 0.0,
    "max_runtime_sec": 5,
}


def _read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _dump(path: Path, payload: Any) -> None:
    """确定性落盘：固定键序、固定缩进、LF 行尾、无时间戳。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    # newline="\n" 显式指定——Path.write_text(newline=) 是 3.10+ 参数，3.8 不可用
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text + "\n")


def build_pack(dimension: str, clauses: List[Dict[str, Any]],
               sources: Dict[str, Any], version: str) -> Dict[str, Any]:
    """把条文块组装成一份规则包。

    每条规则的两个门控状态**原样保留**（不在这里"顺手"改成 verified）：
    `status` 与 `clause_status` 由录入核对流程决定，生成器不做判断。
    """
    rules: List[Dict[str, Any]] = []
    for item in clauses:
        rule = dict(item)
        rule.setdefault("status", "pending")
        rule.setdefault("clause_status", "pending")
        rule.setdefault("effect", "obligation")
        # 锚点补全来源信息（URL/抓取日期/sha256 从 sources.json 取）
        anchor = dict(rule.get("anchor") or {})
        doc_id = anchor.get("doc_id", "")
        src = sources.get(doc_id, {})
        anchor.setdefault("source_url", src.get("url", ""))
        anchor.setdefault("captured_at", src.get("captured_at", ""))
        anchor.setdefault("sha256", src.get("sha256", ""))
        if src.get("doc_title"):
            anchor.setdefault("doc_title", src["doc_title"])
        rule["anchor"] = anchor
        rules.append(rule)
    rules.sort(key=lambda r: str(r.get("rule_id", "")))  # 固定顺序 = 确定性
    return {
        "dimension": dimension,
        "ruleset_version": version,
        "rules": rules,
    }


def build_manifest(packs: Dict[str, Dict[str, Any]],
                   sources: Dict[str, Any], version: str,
                   coverage: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """组装 manifest：版本锚点 + 门槛下发 + 覆盖登记 + 来源块。

    ``coverage`` 由 ``_coverage_from_truth()`` 实算后传入——**覆盖登记必须与
    冻结真值库同源**，手写清单必然漂移（见 plan/05 §4.5）。
    """
    source_list = []
    for doc_id in sorted(sources):
        if doc_id.startswith("_"):
            continue  # 元数据键（_note/_discipline 等）不是来源条目
        item = sources[doc_id]
        if not isinstance(item, dict):
            continue
        source_list.append({
            "doc_id": doc_id,
            "doc_title": item.get("doc_title", ""),
            "issuer": item.get("issuer", ""),
            "doc_no": item.get("doc_no", ""),
            "url": item.get("url", ""),
            "captured_at": item.get("captured_at", ""),
            "sha256": item.get("sha256", ""),
        })
    # 缺维度时补空登记：manifest 的 coverage 必须与规则包维度集合一致，
    # 否则"没登记"会被读成"这一维不用覆盖"。
    for dim in ("label", "nutrition", "claim"):
        coverage.setdefault(dim, {
            "total_rules": 0, "verified_rules": 0,
            "sampled_in_truth": 0, "sample_list": [],
            "note": "该维度无规则包",
        })

    return {
        "ruleset_version": version,
        "files": {dim: RULESET_FILES[dim] for dim in sorted(RULESET_FILES)},
        "thresholds": dict(THRESHOLDS),
        "coverage": coverage,
        "sources": source_list,
    }


def _coverage_from_truth(packs: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """覆盖登记的**唯一来源**：由规则包生成真值库，再从真值库实算。

    顺序约束（见 plan/05 §4.5）：规则包 → 真值库 → 回填 coverage →
    重冻结 manifest。这里直接调生成器（不读盘），保证"登记的数"与
    "真值库里的数"同源；入库件与生成器输出的位级一致由 ``gen_cases.py --check``
    单独守门。
    """
    from pflc.rules import parse_pack

    loaded = {dim: parse_pack(dim, packs[dim])
              for dim in ("label", "nutrition", "claim")}
    cases = generate_cases(RULES_DIR, packs=loaded)
    return coverage_from_cases(cases, loaded)


def generate() -> Dict[str, Dict[str, Any]]:
    """产出全部规则包与 manifest 的内容（不落盘）。"""
    sources = _read_json(CLAUSES_DIR / "sources.json", {})
    packs: Dict[str, Dict[str, Any]] = {}
    for dim in ("label", "nutrition", "claim"):
        clauses = _read_json(CLAUSES_DIR / ("%s.json" % dim), [])
        if isinstance(clauses, dict):
            clauses = clauses.get("rules", [])
        packs[dim] = build_pack(dim, clauses, sources, RULESET_VERSION)
    coverage = _coverage_from_truth(packs)
    packs["__manifest__"] = build_manifest(
        {k: v for k, v in packs.items() if not k.startswith("__")},
        sources, RULESET_VERSION, coverage)
    return packs


def write_all(packs: Dict[str, Dict[str, Any]]) -> None:
    for dim in ("label", "nutrition", "claim"):
        _dump(RULES_DIR / RULESET_FILES[dim], packs[dim])
    _dump(RULES_DIR / "manifest.json", packs["__manifest__"])


def check() -> bool:
    """位级一致校验：重生成内容与入库件逐字节比对。"""
    fresh = generate()
    targets = [(RULES_DIR / RULESET_FILES[d], fresh[d]) for d in
               ("label", "nutrition", "claim")]
    targets.append((RULES_DIR / "manifest.json", fresh["__manifest__"]))
    ok = True
    for path, payload in targets:
        expected = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if not path.is_file():
            print("缺失：%s" % path.name)
            ok = False
            continue
        actual = path.read_text(encoding="utf-8")
        if actual != expected:
            print("不一致：%s" % path.name)
            ok = False
    return ok


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="规则包生成器（冻结产物）")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--force", action="store_true", help="重生成全部规则包")
    group.add_argument("--check", action="store_true", help="位级一致校验")
    args = parser.parse_args(argv)

    if args.check:
        if check():
            print("FROZEN_RULESET_OK")
            return 0
        print("FROZEN_RULESET_MISMATCH", file=sys.stderr)
        return 1

    packs = generate()
    write_all(packs)
    total = sum(len(packs[d]["rules"]) for d in ("label", "nutrition", "claim"))
    print("已生成规则包：共 %d 条规则（%s）" % (total, RULESET_VERSION))
    for dim in ("label", "nutrition", "claim"):
        rules = packs[dim]["rules"]
        verified = sum(1 for r in rules if r.get("status") == "verified")
        print("  %s：%d 条，其中已核对 %d 条" % (dim, len(rules), verified))
    return 0


if __name__ == "__main__":
    sys.exit(main())
