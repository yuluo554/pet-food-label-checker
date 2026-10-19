"""命令行入口。

退出码三语义（锁进测试，见 plan/03 D14 / plan/07 K7）：
    0 = 达标 / 无不符合
    1 = 未达标 / 检出不符合 / 有 pending 门控拦截 / **未评估**（DEC3 = B）
    2 = 输入、坐标或用例名错误
    3 = 缺可选依赖（GUI）

**为什么"未评估"必须非 0**（DEC3 = B，2026-10-20）：零生效规则时
``check`` 输出"整体结论：未评估"，若退出码仍是 0，"没检查过"与
"检查过没问题"在脚本眼里**无法区分**——而 README 自己写着
"绝不输出成符合"。``diagnostics``（零生效规则 → exit 1）与
``bench``（门槛缺失 → exit 2）本来就是非 0，三处口径至此统一。

**惰性导入纪律**：``try`` 必须包住**从 import 到调用完成**的整条路径，
不是只包 import 那一行——分层越严（重件只许在函数体内 import），
边界越靠后越易漏（见 plan/07 K23）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from . import pipeline
from .model import OVERALL_NONCOMPLIANT, OVERALL_NOT_ASSESSED
from .benchmark import EXIT_NOT_MET, EXIT_OK, EXIT_USAGE

EXIT_DEP_MISSING = 3


def _ensure_utf8_stdio() -> None:
    """入口编码守卫：按 ``stream.encoding`` 探针决定是否 reconfigure。

    中文控制台（cp936）保持不动，CI 管道（cp1252）则切到 UTF-8。
    这是"编码三层加固"的**入口那一层**——救真实用户（见 plan/07 K22）。
    """
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        encoding = (getattr(stream, "encoding", None) or "").lower()
        if encoding in ("utf-8", "utf8"):
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8")
        except (ValueError, OSError):
            pass


# --------------------------------------------------------------------------
# 输出辅助
# --------------------------------------------------------------------------


def _verdict_label(verdict: str) -> str:
    return {
        "compliant": "符合",
        "noncompliant": "不符合",
        "not_provided": "未提供",
        "skipped": "不适用",
        "unknown": "待人工确认",
        "not_assessed": "未评估",
    }.get(verdict, verdict)


def _print_result(result, verbose: bool = False) -> None:
    print("档案 %s（%s）" % (result.card_id, result.source or "<内存>"))
    print("整体结论：%s" % _verdict_label(result.overall()))
    for dim in result.dimensions:
        if dim.excluded:
            print("  [%s] 未参与聚合（原因码 %s）" % (dim.dimension, dim.exclude_reason))
            continue
        if dim.not_assessed:
            print("  [%s] 未评估（本次无适用规则）" % dim.dimension)
            continue
        counts = dim.counts()
        summary = "、".join(
            "%s %d" % (_verdict_label(v), counts[v]) for v in sorted(counts) if counts[v]
        )
        print("  [%s] %s" % (dim.dimension, summary or "无结论"))
        if verbose:
            for finding in dim.findings:
                anchor = finding.anchor.render() if finding.anchor else "<无锚点>"
                print("      - %s %s：%s（%s）" % (
                    finding.rule_id, finding.target,
                    _verdict_label(finding.verdict), anchor))
    if result.pending_rules:
        print("未生效规则（未挂原文核对，不进入判定路径）：%s"
              % "、".join(result.pending_rules))


# --------------------------------------------------------------------------
# 子命令
# --------------------------------------------------------------------------


def cmd_check(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if not path.is_file():
        print("输入不可用：文件不存在 %s" % path, file=sys.stderr)
        return EXIT_USAGE
    try:
        result = pipeline.check_path(path)
    except (OSError, UnicodeDecodeError) as exc:
        print("输入不可用：%s" % exc, file=sys.stderr)
        return EXIT_USAGE

    _print_result(result, verbose=args.verbose)
    # 未评估（零生效规则 / 全维度未参与聚合）**不是通过**：它意味着
    # "什么都没查"。退出码 0 会让脚本把它读成"检查过、没问题"（DEC3 = B）。
    if result.overall() in (OVERALL_NONCOMPLIANT, OVERALL_NOT_ASSESSED):
        return EXIT_NOT_MET
    return EXIT_OK


def cmd_scan(args: argparse.Namespace) -> int:
    directory = Path(args.directory)
    if not directory.is_dir():
        print("输入不可用：目录不存在 %s" % directory, file=sys.stderr)
        return EXIT_USAGE

    baseline = None
    if args.baseline:
        baseline_path = Path(args.baseline)
        if not baseline_path.is_file():
            print("基线文件不存在：%s" % baseline_path, file=sys.stderr)
            return EXIT_USAGE
        raw = json.loads(baseline_path.read_text(encoding="utf-8"))
        baseline = {k: set(tuple(x) for x in v) for k, v in raw.items()}

    report = pipeline.scan_directory(directory, baseline=baseline)
    print("扫描 %d 件；失败件 %d" % (report["total"], report["failed"]))
    for item in report["items"]:
        if item["kind"] == "failed":
            # 失败件单列，绝不静默吞掉；但它**不改变退出码**
            print("  [失败] %s：%s" % (item["file"], item.get("error", "")))
        else:
            print("  [%s] %s %s" % (
                _verdict_label(item.get("overall", "")),
                item["file"],
                ("违规 " + "、".join(item["violations"])) if item.get("violations") else ""))
    if "delta" in report:
        delta = report["delta"]
        print("对账：新增违规 %d / 已修复 %d / 持续违规 %d / 稳定 %d" % (
            len(delta["new_violation"]), len(delta["fixed"]),
            len(delta["persistent"]), len(delta["stable"])))
    return EXIT_NOT_MET if report["has_violation"] else EXIT_OK


def cmd_bench(args: argparse.Namespace) -> int:
    from .benchmark import BenchConfigError, render_report

    only = args.only.split(",") if args.only else None
    try:
        report = pipeline.run_bench(only=only)
    except ValueError as exc:
        # 未知套件名 → exit 2（否则"跑了个不存在的基准"会被读成成功）
        print("用法错误：%s" % exc, file=sys.stderr)
        return EXIT_USAGE
    except BenchConfigError as exc:
        print("配置错误：%s" % exc, file=sys.stderr)
        return EXIT_USAGE

    print(render_report(report))
    return report.exit_code()


def cmd_report(args: argparse.Namespace) -> int:
    from .report import ReportError, TraceabilityError

    path = Path(args.path)
    if not path.is_file():
        print("输入不可用：文件不存在 %s" % path, file=sys.stderr)
        return EXIT_USAGE
    try:
        result = pipeline.check_path(path)
        paths = pipeline.export_report(result, Path(args.out))
    except TraceabilityError as exc:
        print("溯源不完整，拒绝导出：%s" % exc, file=sys.stderr)
        return EXIT_NOT_MET
    except (ReportError, OSError, UnicodeDecodeError) as exc:
        print("导出失败：%s" % exc, file=sys.stderr)
        return EXIT_USAGE

    for fmt in sorted(paths):
        print("已导出 %s：%s" % (fmt, paths[fmt]))
    return EXIT_OK


def cmd_diagnostics(args: argparse.Namespace) -> int:
    info = pipeline.diagnostics()
    print("运行形态：%s" % ("冻结态（打包产物）" if info["frozen"] else "源码态"))
    print("数据目录：%s" % info["data_dir"])
    print("规则目录：%s" % info["rules_dir"])
    if info["frozen"]:
        in_dist = info["data_dir_in_dist"]
        print("数据目录在 exe 目录内：%s" % ("是" if in_dist else "否（打包缺陷）"))
    print("manifest：%s" % ("已登记" if info["manifest_present"] else "缺失"))
    for dim in info["dimensions"]:
        print("  [%s] 共 %d 条，生效 %d，未生效 %d，条款号待核对 %d（%s）" % (
            dim["dimension"], dim["total"], dim["effective"],
            dim["pending"], dim["clause_pending"], dim["source_file"]))
    for note in info["notes"]:
        print("提示：%s" % note)
    return EXIT_NOT_MET if info["total_effective"] == 0 else EXIT_OK


def cmd_selftest(args: argparse.Namespace) -> int:
    """冻结态自检：结论**写文件回传**（窗口程序无 stdout）。

    断言要点：``frozen`` 标记 + **数据目录落在 exe 目录内** + 生效规则数。
    这是唯一能脚本化验收窗口 exe 的通路。
    """
    from .data_paths import data_path_in_dist, is_frozen

    info = pipeline.diagnostics()
    out: dict = {
        "frozen": is_frozen(),
        "data_dir": info["data_dir"],
        "rules_dir": info["rules_dir"],
        "data_dir_in_dist": data_path_in_dist(),
        "total_effective": info["total_effective"],
        "dimensions": info["dimensions"],
        "checks": {},
    }

    ok = True
    # 冻结态专属断言：数据必须随包走（否则换台机器就废）
    if is_frozen():
        in_dist = data_path_in_dist()
        out["checks"]["data_dir_in_dist"] = bool(in_dist)
        if not in_dist:
            ok = False
    else:
        out["checks"]["data_dir_in_dist"] = None  # 源码态不判 FAIL

    out["checks"]["rules_present"] = info["total_effective"] > 0
    # 规则未录入不算自检失败（M0 骨架态合法），但如实记录
    out["ok"] = ok

    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True)
    with open(target, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(payload + "\n")
    print("自检结论已写入 %s（ok=%s）" % (target, ok))
    return EXIT_OK if ok else EXIT_NOT_MET


def cmd_gui(args: argparse.Namespace) -> int:
    """启动桌面应用。

    **惰性导入边界**：``try`` 包住"从 import 到调用完成"的整段——
    因为 GUI 包内部用的是函数体内 ``_qt()`` 取符号（分层守门要求），
    ``import`` 本身永不抛 ImportError，真正的缺依赖异常在 ``build_app()``
    才抛。只包 import 行的话，缺 extra 时会抛裸异常而非 exit 3。

    **降级提示按运行形态分流**（plan/04 §九）：冻结态提示"下载桌面版"，
    源码态才提示 pip 安装——**冻结态用户没有 pip，也装不上 extra**。
    """
    try:
        from .gui.app import main as gui_main

        return gui_main()
    except ImportError as exc:
        from .data_paths import is_frozen

        if is_frozen():
            print(
                "缺少 GUI 依赖：%s\n"
                "本发行包未内嵌该功能（这是 CLI 发行版）。\n"
                "请改用桌面版发行包（内含 pflc.exe），或执行不带 gui 子命令的 CLI 功能。"
                % exc,
                file=sys.stderr,
            )
        else:
            print(
                "缺少 GUI 依赖：%s\n"
                "源码态请安装：pip install -e \".[gui]\"" % exc,
                file=sys.stderr,
            )
        return EXIT_DEP_MISSING


# --------------------------------------------------------------------------
# 参数解析
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pflc",
        description="宠物食品标签合规比对器（猫犬粮）——法规条款与国标营养限值的确定性规则引擎",
    )
    sub = parser.add_subparsers(dest="command")

    p_check = sub.add_parser("check", help="单件核验标签文本")
    p_check.add_argument("path", help="标签文本文件路径（UTF-8）")
    p_check.add_argument("-v", "--verbose", action="store_true", help="逐条打印结论")
    p_check.set_defaults(func=cmd_check)

    p_scan = sub.add_parser("scan", help="批量扫描目录（可选两轮对账）")
    p_scan.add_argument("directory", help="含 *.txt 标签文件的目录")
    p_scan.add_argument("--baseline", help="上一轮对账基线 JSON")
    p_scan.set_defaults(func=cmd_scan)

    p_bench = sub.add_parser("bench", help="跑内置基准套件")
    p_bench.add_argument("--only", help="只跑指定套件（逗号分隔）")
    p_bench.set_defaults(func=cmd_bench)

    p_report = sub.add_parser("report", help="导出双轨报告（Markdown + CSV）")
    p_report.add_argument("path", help="标签文本文件路径")
    p_report.add_argument("--out", default="output", help="输出目录（默认 output/）")
    p_report.set_defaults(func=cmd_report)

    p_diag = sub.add_parser("diagnostics", help="打印规则与数据状态")
    p_diag.set_defaults(func=cmd_diagnostics)

    p_self = sub.add_parser("selftest", help="冻结态自检（结论写文件回传）")
    p_self.add_argument("--out", default="selftest.json", help="结论输出文件")
    p_self.set_defaults(func=cmd_selftest)

    p_gui = sub.add_parser("gui", help="启动桌面应用")
    p_gui.set_defaults(func=cmd_gui)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _ensure_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return EXIT_USAGE
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
