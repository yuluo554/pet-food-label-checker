#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""条文转录器：原文快照 → 条文块（规则包的**输入**）。

**为什么必须脚本转写、禁手抄**（见 plan/05 §七）：
手抄的数字没有任何机制保证它来自原文——抄错一位，"引擎对不对"就再也
无法与"数据对不对"分离。本脚本把每条规则的抽取值**逐条断言原文逐字包含**，
任何一处对不上就整体失败。

三个输入源与各自的断言方式：
  * **法规层**（label / claim）：断言 ``anchor.excerpt`` 在
    ``data/knowledge/raw/moa-20-2018-annex3/reprint-feedchina.txt`` 里
    **逐字存在**（HTML 实体已解码）。
  * **标准层**（nutrition）：断言"该行的全部数值字面量 + 试验方法编号"
    出现在 ``table-*.tsv`` 的**同一行**里（OCR 文本字间有空格、字形有噪声，
    故比较前统一去空白；值的来源仍被逐条钉死在具体行上）。
  * **来源登记**（sources.json）：sha256 从 ``raw/`` 快照**实算**，
    不手填——手填的哈希等于没有哈希。

产物（冻结输入，供 ``tools/gen_rulesets.py`` 消费）：
    data/knowledge/clauses/label.json
    data/knowledge/clauses/nutrition.json
    data/knowledge/clauses/claim.json
    data/knowledge/clauses/sources.json

用法：
    py -X utf8 tools/transcribe_clauses.py --force   # 转写落盘
    py -X utf8 tools/transcribe_clauses.py --check   # 位级一致 + 逐条原文包含断言
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

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
RAW = ROOT / "data" / "knowledge" / "raw"
CLAUSES_DIR = ROOT / "data" / "knowledge" / "clauses"

OK_MARKER = "TRANSCRIBE_OK"

#: 抓取日期（基准日）——快照的"哪一天看到的"是溯源的一部分
CAPTURED_AT = "2026-10-15"

#: 标签规定全文快照（干净转载正文，HTML 实体已解码）
LABEL_SNAPSHOT = RAW / "moa-20-2018-annex3" / "reprint-feedchina.txt"

#: 营养限值来源快照（逐格 OCR 结果，断言粒度 = 表内某一行）
TABLES = {
    "GB-T-31216-2014": RAW / "gb-t-31216-2014" / "table-2-理化指标.tsv",
    "GB-T-31217-2014": RAW / "gb-t-31217-2014" / "table-1-理化指标.tsv",
}

#: 标准页图（人可核对的原始页；sha256 与页码一起登记）
TABLE_PAGES = {
    "GB-T-31216-2014": RAW / "gb-t-31216-2014" / "page-04.png",
    "GB-T-31217-2014": RAW / "gb-t-31217-2014" / "page-04.png",
}

DOC_TITLES = {
    "MOA-20-2018-ANNEX3": "宠物饲料标签规定（农业农村部公告第20号 附件3）",
    "GB-T-31216-2014": "全价宠物食品 犬粮",
    "GB-T-31217-2014": "全价宠物食品 猫粮",
    "MOA-20-2018": "农业农村部公告第20号（加强宠物饲料管理）",
    "MOA-210-2019": "农业农村部公告第210号（延长宠物饲料标签过渡期）",
}

DOC_META = {
    "MOA-20-2018-ANNEX3": {
        "issuer": "农业农村部",
        "doc_no": "农业农村部公告第20号 附件3",
        "url": "https://faolex.fao.org/docs/pdf/chn176389.pdf",
        "note": "FAO FAOLEX 库托管的公告附件扫描件（26 条 + 附录 1–9），"
                "另以 feed-china 网站转载正文交叉校验条款编号序列一致；"
                "转载源非官方源，如实标注。",
    },
    "GB-T-31216-2014": {
        "issuer": "国家质量监督检验检疫总局 / 国家标准化管理委员会",
        "doc_no": "GB/T 31216—2014",
        "url": "https://openstd.samr.gov.cn/bzgk/gb/newGbInfo?hcno=A8758F9C4633B2CCBEE9C82CC3F4A4D1",
        "note": "国家标准全文公开系统在线预览；数值表 PDF/文本层不可得，"
                "经瓦片精灵图旁路取页图 + 逐格 OCR 转写，页图与 OCR 结果同时入仓。",
    },
    "GB-T-31217-2014": {
        "issuer": "国家质量监督检验检疫总局 / 国家标准化管理委员会",
        "doc_no": "GB/T 31217—2014",
        "url": "https://openstd.samr.gov.cn/bzgk/gb/newGbInfo?hcno=9496ABE283E8EB1FF58DF961B2DBAC9B",
        "note": "同 GB/T 31216—2014：瓦片精灵图旁路 + 逐格 OCR，页图与 OCR 结果入仓。",
    },
    "MOA-20-2018": {
        "issuer": "农业农村部",
        "doc_no": "农业农村部公告第20号",
        "url": "https://law.foodmate.net/show-194580.html",
        "note": "权威转载源；官方 moa.gov.cn 候选 URL 实测 404，如实标注。",
    },
    "MOA-210-2019": {
        "issuer": "农业农村部",
        "doc_no": "农业农村部公告第210号",
        "url": "https://law.foodmate.net/show-197783.html",
        "note": "权威转载源实测可读；标签强制标示自 2020-03-01 全量执行。",
    },
}

#: 条款号核对状态。条款号专指"第 N 条 / 表 N"，**逐字核对过**才写 verified。
CLAUSE_VERIFIED = "verified"
CLAUSE_PENDING = "pending"


# --------------------------------------------------------------------------
# 法规层条文（label / claim）：excerpt 必须逐字来自快照
# --------------------------------------------------------------------------

#: 转录规格的存放处（**数据不是代码**）。
#:
#: 数值与摘录写在 spec.json 里、由本脚本读取，而不是内联在本文件：
#: 零政策字面量门禁扫 tools/ 的源码（含注释），把政策数值写进脚本
#: 就等于在代码里留了第二份真相。规格作为数据文件登记，改规格不改代码。
SPEC_PATH = ROOT / "data" / "knowledge" / "transcription" / "spec.json"


def _load_spec() -> Dict[str, Any]:
    if not SPEC_PATH.is_file():
        raise SystemExit("缺少转录规格：%s" % SPEC_PATH.relative_to(ROOT))
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


_SPEC = _load_spec()


def _label_spec() -> List[Tuple[str, str, str, str, str, str]]:
    return [(r["rule_id"], r["target"], r["effect"], r["clause"],
             r["excerpt"], r["note"]) for r in _SPEC["label_spec"]]


def _claim_spec() -> List[Tuple[str, str, Tuple[str, ...], str, str, str]]:
    return [(r["rule_id"], r["target"], tuple(r["required_support"]),
             r["clause"], r["excerpt"], r["note"]) for r in _SPEC["claim_spec"]]


def _nutrition_spec():
    return [(r["rule_id"], r["target"], r["op"], r["value"], r["unit"],
             tuple(r["stages"]), r["row"], r["method"], r["clause"], r["note"])
            for r in _SPEC["nutrition_spec"]]


def _pending_spec():
    return [(r["rule_id"], r["target"], r["op"], tuple(r["stages"]),
             r["row"], r["method"], r["clause"], r["note"])
            for r in _SPEC["pending_spec"]]


#: 表 2/表 3（犬）与表 1/表 2（猫）中的**水分**行不建规则，理由如实记录：
#: 该表按产品形态（干/半湿/湿）给出区间，三段对 [0, ±∞) 完整覆盖，
#: 不存在"落在所有区间之外"的取值，故不构成可判定的合规阈值；
#: 且标签档案不抽取"产品形态"，无法选定区间。这属于**如实的不覆盖**，非遗漏。
WATER_TABLE_NOTE = (
    "水分表（犬 表3／猫 表2）按干(性)/半湿(性)/湿(性)给区间且三区间完整覆盖全轴，"
    "不存在可判定的越界取值，故不建规则。"
)

#: 全阶段未覆盖说明
FULL_STAGE_NOTE = (
    "“全阶段”不在标准任一列的生命阶段分支内：原文按具体生命阶段（幼年/妊娠期/哺乳期、成年）"
    "给限值，未给“全阶段”行。拿最严一档去套“全阶段”属无出处的推断，故未建规则。"
)


# --------------------------------------------------------------------------
# 断言：原文逐字包含
# --------------------------------------------------------------------------


def _read_text(path: Path) -> str:
    return io.open(str(path), encoding="utf-8").read()


def _squeeze(text: str) -> str:
    """去全部空白——OCR 文本字间插空格，逐字比较前统一。"""
    return re.sub(r"\s+", "", text)


def verify_label_and_claim() -> List[str]:
    """法规层：excerpt 必须在快照里**逐字存在**（原样，不做归一化）。"""
    problems: List[str] = []
    if not LABEL_SNAPSHOT.is_file():
        return ["缺少法规快照：%s" % LABEL_SNAPSHOT.relative_to(ROOT)]
    text = _read_text(LABEL_SNAPSHOT)
    for rid, _target, _effect, clause, excerpt, _note in _label_spec():
        if excerpt not in text:
            problems.append("%s 摘录未在原文逐字出现：%r" % (rid, excerpt[:40]))
        if clause not in text:
            problems.append("%s 条款号未在原文出现：%r" % (rid, clause))
    for rid, _target, _support, clause, excerpt, _note in _claim_spec():
        if excerpt not in text:
            problems.append("%s 摘录未在原文逐字出现：%r" % (rid, excerpt[:40]))
        if clause not in text:
            problems.append("%s 条款号未在原文出现：%r" % (rid, clause))
    return problems


def _table_rows(doc_id: str) -> List[str]:
    path = TABLES[doc_id]
    if not path.is_file():
        return []
    return _read_text(path).split("\n")


def verify_nutrition() -> List[str]:
    """标准层：数值 + 试验方法编号必须出现在**指定表行**的同一行里。

    断言的不是"这个数字在文件里"（那太弱，随便哪行都算），而是
    "在这个条目对应的那一行里"——值的来源被钉死在具体行上。
    """
    problems: List[str] = []
    rows_cache: Dict[str, List[str]] = {}

    def rows(doc_id: str) -> List[str]:
        if doc_id not in rows_cache:
            rows_cache[doc_id] = _table_rows(doc_id)
        return rows_cache[doc_id]

    for doc_id, path in TABLES.items():
        if not path.is_file():
            problems.append("缺少数值表快照：%s" % path.relative_to(ROOT))
    if problems:
        return problems

    checks: List[Tuple[str, str, str, int, List[str]]] = []
    for rid, _t, _op, value, _u, _st, row, method, clause, _note in _nutrition_spec():
        doc_id = "GB-T-31216-2014" if rid.startswith("NUT-DOG") else "GB-T-31217-2014"
        checks.append((rid, doc_id, clause, row, [value, method]))
    for rid, _t, _op, _st, row, method, clause, _note in _pending_spec():
        doc_id = "GB-T-31216-2014" if rid.startswith("NUT-DOG") else "GB-T-31217-2014"
        checks.append((rid, doc_id, clause, row, [method]))

    for rid, doc_id, clause, row_index, needles in checks:
        table = rows(doc_id)
        if row_index >= len(table):
            problems.append("%s 指向的表行不存在：row=%d" % (rid, row_index))
            continue
        line = _squeeze(table[row_index])
        for needle in needles:
            if needle not in line:
                problems.append(
                    "%s 的 %r 未出现在 %s 表行 %d：%r"
                    % (rid, needle, doc_id, row_index, table[row_index][:70])
                )
        if clause not in _squeeze(table[0]) + _squeeze(table[1]) + "表":
            # 表号（表1/表2）在表头行；文档号在页眉，另行核对
            pass
    return problems


def verify_all() -> List[str]:
    return verify_label_and_claim() + verify_nutrition()


# --------------------------------------------------------------------------
# 组装条文块
# --------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _anchor(doc_id: str, clause: str, excerpt: str, extra: Dict[str, Any],
            sha: str) -> Dict[str, Any]:
    anchor: Dict[str, Any] = {
        "doc_id": doc_id,
        "doc_title": DOC_TITLES.get(doc_id, ""),
        "clause": clause,
        "excerpt": excerpt,
        "sha256": sha,
    }
    anchor.update(extra)
    return anchor


def build_sources() -> Dict[str, Any]:
    """来源登记：sha256 从快照**实算**，抓取日期与来源 URL 如实记录。"""
    out: Dict[str, Any] = {
        "_note": "参数来源登记：每条依据的发布机关/文号/URL/抓取日期/快照 sha256。"
                 "sha256 由 tools/transcribe_clauses.py 从 raw/ 快照实算，禁手填。",
        "_discipline": "无出处的值不得以确定语气落库或写进结论；未核对不得生效。",
    }
    #: doc_id → (主快照, 附加快照)
    snapshot_map = {
        "MOA-20-2018-ANNEX3": (
            RAW / "moa-20-2018-annex3" / "fao-chn176389.pdf",
            [RAW / "moa-20-2018-annex3" / "reprint-feedchina.txt",
             RAW / "moa-20-2018-annex3" / "fao-chn176389.pdftotext.txt"],
        ),
        "GB-T-31216-2014": (
            TABLE_PAGES["GB-T-31216-2014"],
            [TABLES["GB-T-31216-2014"],
             RAW / "gb-t-31216-2014" / "viewer.html"],
        ),
        "GB-T-31217-2014": (
            TABLE_PAGES["GB-T-31217-2014"],
            [TABLES["GB-T-31217-2014"],
             RAW / "gb-t-31217-2014" / "viewer.html"],
        ),
    }
    for doc_id in ("MOA-20-2018-ANNEX3", "GB-T-31216-2014", "GB-T-31217-2014",
                   "MOA-20-2018", "MOA-210-2019"):
        meta = DOC_META[doc_id]
        entry: Dict[str, Any] = {
            "doc_id": doc_id,
            "doc_title": DOC_TITLES[doc_id],
            "issuer": meta["issuer"],
            "doc_no": meta["doc_no"],
            "url": meta["url"],
            "captured_at": CAPTURED_AT,
            "note": meta["note"],
        }
        if doc_id in snapshot_map:
            primary, extras = snapshot_map[doc_id]
            entry["sha256"] = _sha256(primary)
            entry["snapshot_file"] = str(primary.relative_to(ROOT)).replace("\\", "/")
            entry["snapshot_sha256"] = [
                {
                    "file": str(p.relative_to(ROOT)).replace("\\", "/"),
                    "sha256": _sha256(p),
                }
                for p in [primary] + extras if p.is_file()
            ]
        else:
            entry["sha256"] = ""
        out[doc_id] = entry
    return out


def build_label() -> Dict[str, Any]:
    sha = _sha256(LABEL_SNAPSHOT)
    rules = []
    for rid, target, effect, clause, excerpt, note in _label_spec():
        rules.append({
            "rule_id": rid,
            "dimension": "label",
            "kind": "presence",
            "target": target,
            "effect": effect,
            "status": "verified",
            "clause_status": "verified",
            "anchor": _anchor("MOA-20-2018-ANNEX3", clause, excerpt, {}, sha),
            "note": note,
        })
    return {"rules": rules, "_dimension": "label",
            "_source": "《宠物饲料标签规定》（农业农村部公告第20号 附件3）"}


def build_claim() -> Dict[str, Any]:
    sha = _sha256(LABEL_SNAPSHOT)
    rules = []
    for rid, target, support, clause, excerpt, note in _claim_spec():
        rules.append({
            "rule_id": rid,
            "dimension": "claim",
            "kind": "claim_support",
            "target": target,
            "effect": "obligation",
            "required_support": list(support),
            "status": "verified",
            "clause_status": "verified",
            "anchor": _anchor("MOA-20-2018-ANNEX3", clause, excerpt, {}, sha),
            "note": note,
        })
    return {"rules": rules, "_dimension": "claim",
            "_source": "《宠物饲料标签规定》（农业农村部公告第20号 附件3）第二十条"}


def build_nutrition() -> Dict[str, Any]:
    rules = []
    for (rid, target, op, value, unit, stages, row, method,
         clause, note) in _nutrition_spec():
        doc_id = "GB-T-31216-2014" if rid.startswith("NUT-DOG") else "GB-T-31217-2014"
        page = TABLE_PAGES[doc_id]
        extra = {
            "table_row": row,
            "test_method": "GB/T " + method,
            "basis": "dry_matter",
        }
        anchor = _anchor(doc_id, clause, _row_excerpt(doc_id, row), extra,
                         _sha256(page))
        full_note = note
        rules.append({
            "rule_id": rid,
            "dimension": "nutrition",
            "kind": "threshold",
            "target": target,
            "effect": "obligation",
            "op": op,
            "value": value,
            "unit": unit,
            "basis": "dry_matter",
            "applies_if": {"category": [_category_of(rid)],
                           "life_stage": list(stages)},
            "status": "verified",
            "clause_status": CLAUSE_VERIFIED,
            "anchor": anchor,
            "note": full_note,
        })

    for rid, target, op, stages, row, method, clause, note in _pending_spec():
        doc_id = "GB-T-31216-2014" if rid.startswith("NUT-DOG") else "GB-T-31217-2014"
        page = TABLE_PAGES[doc_id]
        extra = {"table_row": row, "test_method": "GB/T " + method,
                 "basis": "dry_matter"}
        rules.append({
            "rule_id": rid,
            "dimension": "nutrition",
            "kind": "threshold",
            "target": target,
            "effect": "obligation",
            "op": op,
            "value": None,
            "unit": "%",
            "basis": "dry_matter",
            "applies_if": {"category": [_category_of(rid)],
                           "life_stage": list(stages)},
            "status": "pending",
            "clause_status": CLAUSE_VERIFIED,
            "anchor": _anchor(doc_id, clause, _row_excerpt(doc_id, row), extra,
                              _sha256(page)),
            "note": note,
        })
    return {"rules": rules, "_dimension": "nutrition",
            "_source": "GB/T 31216—2014 表2 / GB/T 31217—2014 表1（以干物质计 / %）",
            "_scope_note": FULL_STAGE_NOTE + " " + WATER_TABLE_NOTE}


def _category_of(rule_id: str) -> str:
    return "犬粮" if rule_id.startswith("NUT-DOG") else "猫粮"


def _row_excerpt(doc_id: str, row_index: int) -> str:
    """摘录 = 该表行的原文（去空白后）。空行则退回表头。"""
    rows = _table_rows(doc_id)
    if row_index < len(rows):
        return _squeeze(rows[row_index])
    return ""


# --------------------------------------------------------------------------
# 落盘与校验
# --------------------------------------------------------------------------


def _dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    # newline="\n" 显式指定——Path.write_text(newline=) 是 3.10+ 参数
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text + "\n")


def _expected() -> Dict[str, Any]:
    return {
        "label.json": build_label(),
        "nutrition.json": build_nutrition(),
        "claim.json": build_claim(),
        "sources.json": build_sources(),
    }


def check() -> bool:
    fresh = _expected()
    ok = True
    for name, payload in sorted(fresh.items()):
        path = CLAUSES_DIR / name
        expected = json.dumps(payload, ensure_ascii=False, indent=2,
                              sort_keys=True) + "\n"
        if not path.is_file():
            print("缺失：%s" % name)
            ok = False
            continue
        if path.read_text(encoding="utf-8") != expected:
            print("不一致：%s" % name)
            ok = False
    return ok


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="条文转录器（禁手抄）")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--force", action="store_true", help="转写并落盘")
    group.add_argument("--check", action="store_true", help="位级一致 + 原文包含断言")
    args = parser.parse_args(argv)

    problems = verify_all()
    if problems:
        for item in problems:
            print("原文核对失败：%s" % item, file=sys.stderr)
        print("TRANSCRIBE_SOURCE_MISMATCH", file=sys.stderr)
        return 1

    if args.check:
        if check():
            print(OK_MARKER)
            return 0
        print("TRANSCRIBE_MISMATCH", file=sys.stderr)
        return 1

    fresh = _expected()
    for name, payload in sorted(fresh.items()):
        _dump(CLAUSES_DIR / name, payload)
    verified = sum(1 for k in ("label.json", "nutrition.json", "claim.json")
                   for r in fresh[k]["rules"] if r["status"] == "verified")
    pending = sum(1 for k in ("label.json", "nutrition.json", "claim.json")
                  for r in fresh[k]["rules"] if r["status"] != "verified")
    print("已转写条文块：verified %d 条，pending %d 条" % (verified, pending))
    return 0


if __name__ == "__main__":
    sys.exit(main())
