"""编排层：CLI 与 GUI **共用的公开函数组**。

分层纪律（见 plan/03 D9）：判定逻辑只有一份实现，就在本层之下；
CLI 与 GUI 都是"取数 + 渲染"的薄壳，只准经本模块的公开函数取数。

同一个业务判断在项目里多于一处实现 = 分层没做完。测试用**三方对账**
（CLI stdout 结论 == 直接调 pipeline 字段 == 报告章节结论）验证行为一致，
而不是 `assert "pipeline" in source` 这种字面声明。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from .data_paths import (
    benchmark_dir,
    data_dir,
    data_path_in_dist,
    is_frozen,
    rules_dir as default_rules_dir,
    samples_dir,
)
from .engine import check_card, check_file, scan_dir
from .model import (
    DIM_CLAIM,
    DIM_LABEL,
    DIM_NUTRITION,
    DISCLAIMER,
    CheckResult,
    LabelCard,
)
from .parse import parse_label
from .report import SEC_FINDINGS, export, load_meta, report_sections
from .rules import DIMENSIONS, STATUS_VERIFIED, load_pack

__all__ = [
    "build_card",
    "check_card_result",
    "check_path",
    "scan_directory",
    "run_bench",
    "build_report_sections",
    "export_report",
    "diagnostics",
    "parameter_sources",
    "DISCLAIMER",
    # 展示层需要的枚举/常量也经编排层转发——GUI 只认 pipeline 这一个入口，
    # 不得直接 import 判定内核的模块（由 AST 门禁守住）。
    "DIM_LABEL",
    "DIM_NUTRITION",
    "DIM_CLAIM",
    "SEC_FINDINGS",
]


# --------------------------------------------------------------------------
# 输入
# --------------------------------------------------------------------------


def build_card(raw_text: str, source: str = "") -> LabelCard:
    """文本 → 标签档案（唯一入口，GUI 的输入校验也走这里）。"""
    return parse_label(raw_text, source=source)


def read_card(path: Path) -> LabelCard:
    """从文件读入并解析（UTF-8）。"""
    text = Path(path).read_text(encoding="utf-8")
    return parse_label(text, source=Path(path).name)


# --------------------------------------------------------------------------
# 判定
# --------------------------------------------------------------------------


def check_card_result(card: LabelCard, rules: Optional[Path] = None,
                      scope: str = "all") -> CheckResult:
    """对档案跑全维度判定。"""
    return check_card(card, rules or default_rules_dir(), scope=scope)


def check_path(path: Path, rules: Optional[Path] = None,
               scope: str = "all") -> CheckResult:
    """对文件跑判定（单件通路）。"""
    return check_file(Path(path), rules or default_rules_dir(), scope=scope)


def scan_directory(directory: Path, rules: Optional[Path] = None,
                   baseline: Optional[Dict[str, set]] = None) -> Dict[str, Any]:
    """批量扫描 + 可选两轮对账（批量通路）。"""
    return scan_dir(Path(directory), rules or default_rules_dir(), baseline=baseline)


# --------------------------------------------------------------------------
# 基准
# --------------------------------------------------------------------------


def run_bench(rules: Optional[Path] = None, only: Optional[List[str]] = None):
    """跑基准套件。"""
    from .benchmark import run as bench_run

    return bench_run(rules or default_rules_dir(), only=only)


# --------------------------------------------------------------------------
# 报告
# --------------------------------------------------------------------------


def parameter_sources(rules: Optional[Path] = None) -> Dict[str, Any]:
    """参数来源块（报告用）。"""
    return load_meta(rules or default_rules_dir())


def build_report_sections(result: CheckResult, rules: Optional[Path] = None,
                          disabled_note: str = "") -> List[Any]:
    """结构化章节（**唯一渲染源**，两种格式都消费它）。"""
    return report_sections(result, meta=parameter_sources(rules),
                           disabled_note=disabled_note)


def export_report(result: CheckResult, out_dir: Path, rules: Optional[Path] = None,
                  basename: str = "report") -> Dict[str, Path]:
    """导出双轨报告（导出前跑溯源完整性断言）。"""
    return export(result, Path(out_dir), meta=parameter_sources(rules),
                  basename=basename)


# --------------------------------------------------------------------------
# 诊断
# --------------------------------------------------------------------------


def diagnostics(rules: Optional[Path] = None) -> Dict[str, Any]:
    """规则/数据状态总览（供 CLI ``diagnostics`` 与 GUI"关于"页）。

    规则包不存在时**优雅降级**（不是崩溃）——M0 骨架阶段规则尚未录入，
    这里要能明确告诉用户"待数据录入"。
    """
    rdir = rules or default_rules_dir()
    out: Dict[str, Any] = {
        "frozen": is_frozen(),
        "data_dir": str(data_dir()),
        "rules_dir": str(rdir),
        "data_dir_in_dist": data_path_in_dist(),
        "dimensions": [],
        "pending_rules": [],
        "manifest_present": (Path(rdir) / "manifest.json").is_file(),
        "notes": [],
    }

    for dim in DIMENSIONS:
        pack = load_pack(dim, rdir)
        effective = pack.effective()
        pending = pack.pending()
        clause_pending = pack.clause_pending()
        out["dimensions"].append({
            "dimension": dim,
            "source_file": Path(pack.source_file).name,
            "total": len(pack.rules),
            "effective": len(effective),
            "pending": len(pending),
            "clause_pending": len(clause_pending),
            "ruleset_version": pack.ruleset_version,
        })
        out["pending_rules"].extend(r.rule_id for r in pending)
        if pack.notes:
            out["notes"].append("%s: %s" % (dim, pack.notes))

    out["pending_rules"] = sorted(out["pending_rules"])
    out["total_effective"] = sum(d["effective"] for d in out["dimensions"])
    if out["total_effective"] == 0:
        out["notes"].append(
            "当前无生效规则：规则包待数据录入并逐条挂原文核对（见 plan/05 数据计划 M1）"
        )
    return out


def samples_path() -> Path:
    return samples_dir()


def benchmark_path() -> Path:
    return benchmark_dir()
