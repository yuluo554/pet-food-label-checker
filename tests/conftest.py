"""测试共享夹具。

**为什么用临时规则包而不是仓库 data/rules/**：仓库里的规则包在 M1 数据录入前
是**空的**（诚实状态）。测试需要"有生效规则"的环境，故在临时目录里构造
一份夹具规则包——这也顺带验证了规则包格式契约本身。

夹具里的数值是**测试数据**，不是政策数值：它们随夹具一起进临时目录，
不进引擎源码（零政策字面量门禁扫的是 src/ 与 tools/，不扫 tests/）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def write_text_lf(path: Path, text: str) -> Path:
    """以 LF 行尾写文本。

    ``Path.write_text(newline=)`` 是 **3.10+** 参数，3.8 上直接 TypeError——
    本项目底线 3.8，故一律走 ``open(..., newline="\\n")``。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return path

#: 夹具用的限值（测试数据，与真实国标数值无关）
FIXTURE_MIN_PROTEIN = "26"
FIXTURE_MIN_FAT = "9"
FIXTURE_MAX_MOISTURE = "14"


def _anchor(rule_suffix: str, clause: str) -> Dict[str, Any]:
    return {
        "doc_id": "FIXTURE-DOC",
        "doc_title": "夹具依据文档",
        "clause": clause,
        "excerpt": "夹具摘录 %s" % rule_suffix,
        "source_url": "https://example.invalid/fixture",
        "captured_at": "2026-10-15",
        "sha256": "0" * 64,
    }


def label_rules() -> List[Dict[str, Any]]:
    """标示项规则：覆盖"无条件义务"与"条件触发"两类。"""
    specs = [
        ("LABEL-001", "product_name", "obligation", "第三条"),
        ("LABEL-002", "category", "obligation", "第三条"),
        ("LABEL-003", "life_stage", "obligation", "第三条"),
        ("LABEL-004", "ingredients", "obligation", "第四条"),
        ("LABEL-005", "additives", "obligation", "第五条"),
        ("LABEL-006", "net_content", "obligation", "第六条"),
        ("LABEL-007", "producer", "obligation", "第七条"),
        ("LABEL-008", "product_dates", "obligation", "第八条"),
    ]
    return [
        {
            "rule_id": rid,
            "dimension": "label",
            "kind": "presence",
            "target": target,
            "effect": effect,
            "status": "verified",
            "clause_status": "verified",
            "anchor": _anchor(rid, clause),
        }
        for rid, target, effect, clause in specs
    ]


def nutrition_rules() -> List[Dict[str, Any]]:
    """营养限值规则：按类别 × 生命阶段分支。"""
    specs = [
        ("NUT-001", "粗蛋白", ">=", FIXTURE_MIN_PROTEIN, "猫粮", "成年", "表1"),
        ("NUT-002", "粗脂肪", ">=", FIXTURE_MIN_FAT, "猫粮", "成年", "表1"),
        ("NUT-003", "水分", "<=", FIXTURE_MAX_MOISTURE, "猫粮", "成年", "表1"),
        ("NUT-004", "粗蛋白", ">=", FIXTURE_MIN_PROTEIN, "犬粮", "成年", "表1"),
        ("NUT-005", "粗脂肪", ">=", FIXTURE_MIN_FAT, "犬粮", "成年", "表1"),
        ("NUT-006", "水分", "<=", FIXTURE_MAX_MOISTURE, "犬粮", "成年", "表1"),
    ]
    return [
        {
            "rule_id": rid,
            "dimension": "nutrition",
            "kind": "threshold",
            "target": target,
            "effect": "obligation",
            "op": op,
            "value": value,
            "unit": "%",
            "applies_if": {"category": [category], "life_stage": [stage]},
            "status": "verified",
            "clause_status": "verified",
            "anchor": _anchor(rid, clause),
        }
        for rid, target, op, value, category, stage, clause in specs
    ]


def claim_rules() -> List[Dict[str, Any]]:
    """宣称规则：需要的信息支撑。"""
    specs = [
        ("CLAIM-001", "天然", ["ingredients"], "第十二条"),
        ("CLAIM-002", "无谷", ["ingredients"], "第十三条"),
    ]
    return [
        {
            "rule_id": rid,
            "dimension": "claim",
            "kind": "claim_support",
            "target": target,
            "effect": "obligation",
            "required_support": support,
            "status": "verified",
            "clause_status": "verified",
            "anchor": _anchor(rid, clause),
        }
        for rid, target, support, clause in specs
    ]


def write_ruleset(rules_dir: Path, label: Optional[List] = None,
                  nutrition: Optional[List] = None,
                  claim: Optional[List] = None,
                  thresholds: Optional[Dict[str, Any]] = None) -> Path:
    """把夹具规则包写进 ``rules_dir``。"""
    rules_dir = Path(rules_dir)
    rules_dir.mkdir(parents=True, exist_ok=True)
    packs = {
        "ruleset-label.json": {
            "dimension": "label", "ruleset_version": "fixture",
            "rules": label if label is not None else label_rules(),
        },
        "ruleset-nutrition.json": {
            "dimension": "nutrition", "ruleset_version": "fixture",
            "rules": nutrition if nutrition is not None else nutrition_rules(),
        },
        "ruleset-claim.json": {
            "dimension": "claim", "ruleset_version": "fixture",
            "rules": claim if claim is not None else claim_rules(),
        },
    }
    for name, payload in packs.items():
        text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        with open(rules_dir / name, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text + "\n")

    manifest = {
        "ruleset_version": "fixture",
        "files": {k: k for k in ("label", "nutrition", "claim")},
        "thresholds": thresholds or {
            "min_accuracy": 0.95, "max_false_positive": 0.0, "max_runtime_sec": 5,
        },
        "coverage": {},
        "sources": [{
            "doc_id": "FIXTURE-DOC", "doc_title": "夹具依据文档",
            "issuer": "夹具", "doc_no": "FIXTURE-001",
            "url": "https://example.invalid/fixture",
            "captured_at": "2026-10-15", "sha256": "0" * 64,
        }],
    }
    text = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True)
    with open(rules_dir / "manifest.json", "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text + "\n")
    return rules_dir


@pytest.fixture()
def rules_dir(tmp_path: Path, monkeypatch) -> Path:
    """带全部维度生效规则的夹具规则目录。

    同时把 ``PFLC_DATA_DIR`` 指向其父目录，使 ``pipeline``/``cli`` 的默认
    数据定位也落到夹具上——否则 CLI 测试会静默读到仓库里的空规则包，
    出现"测试通过但没验到东西"的假绿。
    """
    target = write_ruleset(tmp_path / "rules")
    monkeypatch.setenv("PFLC_DATA_DIR", str(tmp_path))
    return target


@pytest.fixture()
def empty_rules_dir(tmp_path: Path, monkeypatch) -> Path:
    """无任何规则包的空目录（模拟 M0 骨架态）。"""
    target = tmp_path / "empty-rules"
    target.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PFLC_DATA_DIR", str(tmp_path))
    return target


@pytest.fixture()
def ok_label_text() -> str:
    return (
        "测试粮A 猫粮 成年\n"
        "原料组成：鸡肉、糙米、鱼油\n"
        "添加剂：维生素A、维生素D3\n"
        "成分分析保证值：\n"
        "粗蛋白 >= 30%\n"
        "粗脂肪 >= 12%\n"
        "水分 <= 12%\n"
        "净含量：2kg\n"
        "生产企业：某合成宠物食品有限公司\n"
        "生产日期：2026-01-01\n"
        "保质期：18个月\n"
    )
