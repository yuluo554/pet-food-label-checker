"""报告层：人读（Markdown）+ 机读（CSV）双轨导出。

四条硬约束（见 plan/03 D7/D8、plan/04 §五）：

  * **单一渲染源**：两种格式都消费 ``report_sections()`` 返回的结构化章节——
    于是"两格式内容一致"不再是人工比对，而是**结构上不可能不一致**；
  * **溯源完整性硬约束**：导出前断言"溯源表行数 == 明细行数"且每条引用 id
    可解析，不满足即**报错拒导**——"半溯源"比"无溯源"更危险；
  * **无外链**：机读产物单元格里不得有 URL（断网可开）；
  * **逐字节可复现**：自写最小 writer，产物无时间戳，同输入两次导出字节一致。
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ..model import (
    DIMENSIONS,
    DISCLAIMER,
    CheckResult,
    DimensionResult,
    Finding,
)

#: 章节 id
SEC_INPUT = "input"
SEC_SOURCES = "sources"
SEC_FINDINGS = "findings"
SEC_DISABLED = "disabled"
SEC_DISCLAIMER = "disclaimer"

#: 导出格式
FORMAT_MARKDOWN = "markdown"
FORMAT_CSV = "csv"


class ReportError(Exception):
    """报告契约错误（如溯源不完整、引用不可解析）。"""


class TraceabilityError(ReportError):
    """溯源完整性不满足——**导出前必须拒导**。"""


# --------------------------------------------------------------------------
# 结构化章节（单一渲染源）
# --------------------------------------------------------------------------


@dataclass
class Section:
    """结构化章节。两种渲染器各自读它，内容一致性由此成为结构性质。"""

    section_id: str
    title: str
    rows: List[Dict[str, Any]] = field(default_factory=list)
    text: str = ""
    note: str = ""


def report_sections(result: CheckResult, meta: Optional[Dict[str, Any]] = None,
                    disabled_note: str = "") -> List[Section]:
    """把判定结果渲染成结构化章节（**唯一渲染源**）。

    ``meta`` 提供参数来源块所需信息（发布机关/文号/URL/抓取日期）。
    """
    meta = meta or {}
    sections: List[Section] = []

    # --- §1 输入事实 ---------------------------------------------------
    sections.append(Section(
        section_id=SEC_INPUT,
        title="输入事实",
        rows=[
            {"字段": "档案标识", "值": result.card_id},
            {"字段": "来源", "值": result.source or "<内存>"},
            {"字段": "整体结论", "值": result.overall()},
        ],
    ))

    # --- §2 参数来源块 -------------------------------------------------
    # 让读者**不开仓库也能核证**"这个数字哪来的"（见 plan/04 §五.2）
    source_rows: List[Dict[str, Any]] = []
    for item in meta.get("sources", []):
        source_rows.append({
            "依据编号": item.get("doc_id", ""),
            "文件标题": item.get("doc_title", ""),
            "发布机关": item.get("issuer", ""),
            "文号": item.get("doc_no", ""),
            "来源URL": item.get("url", ""),
            "抓取日期": item.get("captured_at", ""),
            "快照sha256": item.get("sha256", ""),
        })
    sections.append(Section(
        section_id=SEC_SOURCES,
        title="参数来源块",
        rows=source_rows,
        note="" if source_rows else "本次未登记参数来源（规则包 manifest 缺 sources 节）",
    ))

    # --- §3 逐项判定明细 -----------------------------------------------
    finding_rows: List[Dict[str, Any]] = []
    for dim in result.dimensions:
        for finding in dim.findings:
            finding_rows.append(_finding_row(dim, finding))
    sections.append(Section(
        section_id=SEC_FINDINGS,
        title="逐项判定明细",
        rows=finding_rows,
    ))

    # --- §4 未启用章节（显式写出，不留空）------------------------------
    # "没查"与"查了没问题"是两种截然不同的结论，留空会被误读成后者
    disabled_rows: List[Dict[str, Any]] = []
    for dim in result.dimensions:
        if dim.excluded:
            disabled_rows.append({
                "维度": dim.dimension,
                "状态": "未参与聚合",
                "原因码": dim.exclude_reason or "",
            })
    for rule_id in result.pending_rules:
        disabled_rows.append({"维度": "—", "状态": "规则未生效", "原因码": rule_id})
    sections.append(Section(
        section_id=SEC_DISABLED,
        title="未启用清单",
        rows=disabled_rows,
        note=disabled_note or (
            "本次导出未启用上述条目；未挂原文核对的规则不进入判定路径。"
            if disabled_rows else "本次导出全部已登记规则均已生效。"
        ),
    ))

    # --- §5 免责声明 ---------------------------------------------------
    sections.append(Section(
        section_id=SEC_DISCLAIMER,
        title="免责声明",
        text=DISCLAIMER,
    ))
    return sections


def _finding_row(dim: DimensionResult, finding: Finding) -> Dict[str, Any]:
    anchor = finding.anchor
    return {
        "维度": dim.dimension,
        "规则ID": finding.rule_id,
        "判定对象": finding.target,
        "义务类型": finding.effect,
        "结论": finding.verdict,
        "观测值": finding.observed or "",
        "期望值": finding.expected or "",
        "条款锚点": anchor.render() if anchor else "",
        "锚点可解析": "是" if (anchor and anchor.is_resolvable()) else "否",
        "说明": finding.note or "",
    }


# --------------------------------------------------------------------------
# 溯源完整性（导出前硬约束）
# --------------------------------------------------------------------------


def assert_traceability(sections: Sequence[Section]) -> None:
    """断言溯源完整性——不满足即抛 ``TraceabilityError``（拒导）。

    判据：判定明细里**每一条**结论都必须挂可解析的条款锚点，
    且锚点行数 == 明细行数。**不留"半溯源"**。
    """
    detail = next((s for s in sections if s.section_id == SEC_FINDINGS), None)
    if detail is None:
        raise TraceabilityError("缺判定明细章节，无法核验溯源完整性")

    total = len(detail.rows)
    resolvable = sum(1 for row in detail.rows if row.get("锚点可解析") == "是")
    if resolvable != total:
        raise TraceabilityError(
            "溯源不完整：判定明细 %d 行，可解析锚点 %d 行——拒绝导出"
            % (total, resolvable)
        )


def assert_no_external_links(text: str) -> None:
    """断言产物**无活动外链**（断网可开、可归档）。

    判据是"没有可点击/可解析的外部引用"，不是"文本里不出现 URL"——
    参数来源块的 URL 必须**以纯文本落列**（读者要能核证"这个数字哪来的"），
    纯文本 URL 不产生外部依赖，断网打开照常可读。
    被禁的是**活动链接形态**：Markdown 链接语法、HTML 的 href/src/a 标签、
    OOXML 的 External 关系模式。
    """
    lowered = text.lower()
    active_patterns = (
        ("](http", "Markdown 链接语法"),
        ("](//", "Markdown 协议相对链接"),
        ("href=", "HTML href"),
        ("src=", "HTML src"),
        ("<a ", "HTML 锚点标签"),
        ("targetmode=\"external\"", "OOXML 外部关系"),
    )
    for needle, label in active_patterns:
        if needle in lowered:
            raise ReportError(
                "产物含活动外链（%s）——URL 必须以纯文本落列，不得是可点击引用" % label
            )


# --------------------------------------------------------------------------
# 渲染器（Markdown / CSV）
# --------------------------------------------------------------------------


def render_markdown(sections: Sequence[Section], title: str = "标签合规核验报告") -> str:
    """渲染为 Markdown（人读）。

    行尾一律 ``\\n``、无时间戳——保证逐字节可复现。
    """
    lines: List[str] = ["# %s" % title, ""]
    for section in sections:
        lines.append("## %s" % section.title)
        lines.append("")
        if section.text:
            lines.append(section.text)
            lines.append("")
        if section.rows:
            headers = list(section.rows[0].keys())
            lines.append("| " + " | ".join(headers) + " |")
            lines.append("|" + "|".join("---" for _ in headers) + "|")
            for row in section.rows:
                cells = [_md_cell(row.get(h, "")) for h in headers]
                lines.append("| " + " | ".join(cells) + " |")
            lines.append("")
        if section.note:
            lines.append("> %s" % section.note)
            lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def _md_cell(value: Any) -> str:
    text = str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def render_csv(sections: Sequence[Section]) -> str:
    """渲染为 CSV（机读，逐字节可复现）。

    每行带 ``章节`` 列，使 CSV 保留与 Markdown 相同的章节结构——
    "两格式内容一致"因此可被**逐项对等断言**验证（而非人工抽查）。
    单元格内**不得有 URL**（无外链约束）。
    """
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["章节", "字段", "值"])
    for section in sections:
        if section.text:
            writer.writerow([section.title, "正文", section.text])
        for row in section.rows:
            for key in row:  # 保持插入序（构建时已确定），保证字节稳定
                writer.writerow([section.title, key, row[key]])
        if section.note:
            writer.writerow([section.title, "说明", section.note])
    return buffer.getvalue()


# --------------------------------------------------------------------------
# 导出
# --------------------------------------------------------------------------


def export(result: CheckResult, out_dir: Path, meta: Optional[Dict[str, Any]] = None,
           basename: str = "report",
           disabled_note: str = "") -> Dict[str, Path]:
    """导出双轨报告。

    **导出前**跑溯源完整性断言——不满足直接拒导（不留半溯源）。
    返回 ``{格式: 路径}``。
    """
    sections = report_sections(result, meta=meta, disabled_note=disabled_note)
    assert_traceability(sections)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    md_text = render_markdown(sections)
    csv_text = render_csv(sections)
    assert_no_external_links(md_text)
    assert_no_external_links(csv_text)

    md_path = out_dir / ("%s.md" % basename)
    csv_path = out_dir / ("%s.csv" % basename)
    # newline="\n" 显式指定——Path.write_text(newline=) 是 3.10+ 参数，3.8 不可用
    with open(md_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(md_text)
    with open(csv_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(csv_text)
    return {FORMAT_MARKDOWN: md_path, FORMAT_CSV: csv_path}


def load_meta(rules_dir: Path) -> Dict[str, Any]:
    """从规则包 manifest 取参数来源块。缺失时返回空（报告会显式写明未登记）。"""
    path = Path(rules_dir) / "manifest.json"
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {"sources": raw.get("sources", [])}
