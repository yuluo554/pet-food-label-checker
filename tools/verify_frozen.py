#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""冻结产物验收：构建后三断言 + 冻结态自检驱动。

三条断言（互相独立，改一处口径必同步另两处，见 plan/04 §九）：
  1. dist 全树禁区成分扫描；
  2. 内嵌数据与仓库逐份 sha256 对账；
  3. 白名单外多余数据目录检测。

用法：
    py -X utf8 tools/verify_frozen.py --dist dist/pflc
    py -X utf8 tools/verify_frozen.py --dist dist/pflc --selftest
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List

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

from pflc.packaging import (  # noqa: E402
    DATA_WHITELIST,
    assert_data_matches,
    assert_no_extra_data,
    assert_no_forbidden,
    data_manifest,
)

OK_MARKER = "VERIFY_FROZEN_OK"


def _payload_roots(dist: Path) -> List[Path]:
    """onedir 的负载根：6.x 在 ``_internal/``，5.x 平铺（兼容两种布局）。"""
    return [base for base in (Path(dist) / "_internal", Path(dist)) if base.is_dir()]


def load_report(dist: Path):
    """读构建期数据报告；缺失或不可解析返回 ``None``。"""
    path = Path(dist) / "_datas_report.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def check_dist_datasets(root: Path, dist: Path) -> List[str]:
    """核证**构建真的按白名单打的数据**（读构建期留档的 datas 报告）。

    构建后三断言证明"包里的数据与仓库一致"，但证明不了"它是按白名单打的"——
    spec 里手写一条额外路径，sha256 对账照样通过（对账基准取自仓库现算清单）。
    故这里读构建期写入的 ``_datas_report.json``，与仓库现算口径三方对齐：
    白名单 / 报告内清单 / 报告内 sha256。

    报告缺失即报错——**空报告与合规报告不能长得一样**（否则又是一道恒绿门）。
    """
    problems: List[str] = []
    payload = load_report(dist)
    if payload is None:
        problems.append(
            "缺构建期数据报告 _datas_report.json（或无法解析）—— 无法核证按白名单打包")
        return problems

    declared = list(payload.get("data_whitelist") or [])
    if declared != list(DATA_WHITELIST):
        problems.append(
            "构建期白名单与当前白名单不一致（报告 %r / 当前 %r）——"
            "构建用的不是同一份口径" % (declared, list(DATA_WHITELIST)))

    reported = {item["dest"] for item in payload.get("datas") or []}
    expected = {"data/%s" % name for name in DATA_WHITELIST}
    if reported != expected:
        problems.append(
            "构建期数据清单与白名单不符（多打/少打）：报告 %s / 期望 %s"
            % (sorted(reported), sorted(expected)))

    actual_manifest = data_manifest(root)
    reported_sha = payload.get("sha256") or {}
    if reported_sha != actual_manifest:
        differing = sorted(set(reported_sha) ^ set(actual_manifest))
        problems.append(
            "数据报告 sha256 与仓库现算不一致（构建后仓库数据被改过？）：%s" % differing)
    if not actual_manifest:
        problems.append("数据清单为空 —— 本断言空转")
    return problems


def check_dist(root: Path, dist: Path) -> List[str]:
    problems: List[str] = []
    problems.extend(assert_no_forbidden(root, dist))
    problems.extend(assert_data_matches(root, dist))
    problems.extend(assert_no_extra_data(root, dist))
    problems.extend(check_dist_datasets(root, dist))
    return problems


def _stripped_env() -> dict:
    """剥离环境变量的执行环境（``env -i`` 等价物）。

    只留 exe 启动必需的 Windows 变量；**特意不传 PATH**——若 exe 依赖
    开发机的 PATH 才能起来，那是发行缺陷，应当在验收阶段暴露而非发货后。
    """
    keep = ("SYSTEMROOT", "WINDIR", "TEMP", "TMP", "SYSTEMDRIVE",
            "COMSPEC", "PATHEXT")
    return {k: v for k, v in os.environ.items() if k.upper() in keep}


def _run(exe: Path, argv: List[str], cwd: Path, env: dict, timeout: int = 180):
    return subprocess.run(
        [str(exe)] + argv,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=timeout,
    )


def _find_exe(dist: Path, name: str) -> List[Path]:
    return sorted(dist.rglob("%s.exe" % name)) + sorted(dist.rglob(name))


def check_cli_in_neutral_dir(root: Path, dist: Path) -> List[str]:
    """**中立目录 + 剥离环境变量**下跑 CLI 五连。

    别在仓库树内跑——CWD 上溯会命中仓库 ``data/``，"内嵌数据"验了个寂寞。
    夹具从**包内**取（``_internal/data/samples``），验证"数据真的随包走、
    且发行版的 README 示例路径可用"。
    """
    problems: List[str] = []
    candidates = _find_exe(dist, "pflc-cli")
    if not candidates:
        return ["dist 内未找到 pflc-cli 可执行文件"]
    exe = candidates[0]

    # 包内夹具（6.x 在 _internal/ 下，5.x 平铺）
    samples = None
    for base in (dist / "_internal", dist):
        if (base / "data" / "samples").is_dir():
            samples = base / "data" / "samples"
            break
    if samples is None:
        return ["dist 内未找到内嵌夹具 data/samples —— 数据没随包走"]

    env = _stripped_env()
    with tempfile.TemporaryDirectory(prefix="pflc-neutral-") as tmp:
        work = Path(tmp)
        # 把夹具拷进中立工作目录：命令行里出现的路径必须是中立目录下的，
        # 否则断言的是"开发机仓库里那个文件"，不是"包里的数据"。
        local = work / "samples"
        local.mkdir()
        for path in sorted(samples.glob("*.txt")):
            (local / path.name).write_bytes(path.read_bytes())

        cases = [
            ("diagnostics", ["diagnostics"], 0),
            ("check 合规样例", ["check", "samples/label-demo-ok.txt"], 0),
            ("check 缺项样例", ["check", "samples/label-demo-missing.txt"], 1),
            ("bench", ["bench"], 0),
            ("report 导出", ["report", "samples/label-demo-ok.txt", "--out", "out"], 0),
        ]
        for label, argv, expected in cases:
            try:
                proc = _run(exe, argv, work, env)
            except (OSError, subprocess.TimeoutExpired) as exc:
                problems.append("CLI 五连「%s」无法执行：%s" % (label, exc))
                continue
            if proc.returncode != expected:
                problems.append(
                    "CLI 五连「%s」退出码 %d（期望 %d）\n    输出：%s"
                    % (label, proc.returncode, expected,
                       (proc.stdout or proc.stderr or "").strip()[:400]))
        # report 真的产出了双轨文件（否则"exit 0"可能只是空跑）
        for name in ("out/report.md", "out/report.csv"):
            if not (work / name).is_file():
                problems.append("CLI 五连 report 未产出 %s" % name)
        # bench 必读的是**包内冻结真值库**（K29）：发行态不得回落现场重算
        try:
            bench_out = _run(exe, ["bench"], work, env).stdout or ""
        except (OSError, subprocess.TimeoutExpired) as exc:
            problems.append("bench 复核无法执行：%s" % exc)
            bench_out = ""
        if "frozen" not in bench_out:
            problems.append(
                "冻结态 bench 的 truth_source 不是 frozen —— 发行态回落现场重算了\n"
                "    输出：%s" % bench_out.strip()[:400])
    return problems


def check_selftest(root: Path, dist: Path, exe_name: str) -> List[str]:
    """在**中立目录**驱动 ``--selftest`` 写文件回传结论。

    CLI 与 GUI 各跑一遍：窗口 exe 无 stdout，这是它唯一的脚本化验收通路。
    """
    problems: List[str] = []
    candidates = _find_exe(dist, exe_name)
    if not candidates:
        return ["dist 内未找到 %s 可执行文件" % exe_name]
    exe = candidates[0]

    with tempfile.TemporaryDirectory(prefix="pflc-verify-") as tmp:
        out_path = Path(tmp) / "selftest.json"
        try:
            proc = _run(exe, ["selftest", "--out", str(out_path)],
                        Path(tmp), _stripped_env())
        except (OSError, subprocess.TimeoutExpired) as exc:
            problems.append("%s 自检无法执行：%s" % (exe_name, exc))
            return problems

        if not out_path.is_file():
            problems.append("%s 自检未回传结论文件（exit=%d）\n    输出：%s"
                            % (exe_name, proc.returncode,
                               (proc.stdout or proc.stderr or "").strip()[:400]))
            return problems

        try:
            payload = json.loads(out_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            problems.append("%s 自检结论无法解析：%s" % (exe_name, exc))
            return problems

        if not payload.get("frozen"):
            problems.append("%s 自检报告 frozen 标记为假 —— 未在冻结态运行" % exe_name)
        if payload.get("checks", {}).get("data_dir_in_dist") is not True:
            problems.append(
                "%s 自检报告数据目录未落在 exe 目录内 —— 打包缺陷（数据没随包走）" % exe_name)
        if payload.get("checks", {}).get("rules_present") is not True:
            problems.append("%s 自检报告生效规则数为 0 —— 发行包没带上规则包" % exe_name)
        print("%s 自检结论：%s" % (
            exe_name, json.dumps(payload.get("checks", {}), ensure_ascii=False)))
    return problems


def check_gui_liveness(root: Path, dist: Path) -> List[str]:
    """**GUI 存活探针**：窗口 exe 真的起得来且主窗口建出来了。

    GUI 是 ``console=False``，没有 stdout，源码态测试跑的也只是 ``build_app``
    **不是**打包后的 exe——"双击能开"因此最容易漏验。探针走 ``--gui-selftest``：
    offscreen 下真构窗口，回传页签数与标题。
    """
    problems: List[str] = []
    candidates = _find_exe(dist, "pflc")
    if not candidates:
        return ["dist 内未找到 pflc（GUI）可执行文件"]
    exe = candidates[0]

    with tempfile.TemporaryDirectory(prefix="pflc-gui-") as tmp:
        out_path = Path(tmp) / "gui.json"
        try:
            proc = _run(exe, ["--gui-selftest", str(out_path)], Path(tmp),
                        _stripped_env(), timeout=180)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return ["GUI 存活探针无法执行：%s" % exc]

        if not out_path.is_file():
            return ["GUI 存活探针未回传结论（exit=%d）—— exe 起不来\n    输出：%s"
                    % (proc.returncode, (proc.stdout or proc.stderr or "").strip()[:400])]
        try:
            payload = json.loads(out_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return ["GUI 探针结论无法解析：%s" % exc]

        if payload.get("gui_alive") is not True:
            problems.append("GUI 探针未报告存活")
        expected_tabs = 6
        if payload.get("tab_count") != expected_tabs:
            problems.append("GUI 页签数 %s（期望 %d）—— 界面不完整"
                            % (payload.get("tab_count"), expected_tabs))
        if not payload.get("window_title"):
            problems.append("GUI 主窗口无标题 —— 窗口可能未真正构建")
        print("GUI 探针：页签 %s 个 %s" % (
            payload.get("tab_count"), payload.get("tabs")))
    return problems


def check_gui_carries_gui_deps(root: Path, dist: Path) -> List[str]:
    """桌面发行包**必须**内嵌 PySide6；CLI 发行包**必须没有**。

    两条都是产品口径（见 spec 的 ``_GUI_HIDDEN`` 注释）：桌面包缺 Qt 就是废包，
    CLI 包带 Qt 则让 ``cmd_gui`` 的 exit 3 降级提示变成死代码并白送体积。
    判据落在**包内实际存在的目录**，而不是 spec 文本（构建配置对不等于产物对）。
    """
    problems: List[str] = []
    report = load_report(dist)
    kind = (report or {}).get("kind")
    if kind is None:
        return []          # 报告缺失已在 check_dist_datasets 报过，不重复刷屏
    has_qt = any((base / "PySide6").is_dir() for base in _payload_roots(dist))
    if kind == "gui" and not has_qt:
        problems.append("桌面发行包内没有 PySide6 —— 双击打不开（废包）")
    if kind == "cli" and has_qt:
        problems.append(
            "CLI 发行包内嵌了 PySide6 —— 降级提示（exit 3）成为死代码且白送体积")
    return problems


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="冻结产物验收")
    parser.add_argument("--dist", required=True, help="dist 目录路径")
    parser.add_argument("--selftest", action="store_true",
                        help="额外驱动冻结态自检 + 中立目录 CLI 五连 + GUI 存活探针")
    args = parser.parse_args(argv)

    dist = Path(args.dist)
    if not dist.is_absolute():
        dist = (ROOT / dist).resolve()

    problems = check_dist(ROOT, dist)
    problems.extend(check_gui_carries_gui_deps(ROOT, dist))
    if args.selftest:
        report = load_report(dist) or {}
        kind = report.get("kind")
        exe_names = list(report.get("exe_names") or [])
        if not exe_names:
            problems.append(
                "发行树未声明可执行文件清单 —— 验收无从下手"
                "（报告缺 exe_names，构建事实不完整）")
        # 每个声明的 exe 都必须能跑冻结态自检（数据随包 + 规则在包里）
        for name in exe_names:
            problems.extend(check_selftest(ROOT, dist, name))
        if kind == "cli":
            # CLI 五连只在 CLI 树上跑：桌面包没有 `check`/`bench` 子命令入口
            problems.extend(check_cli_in_neutral_dir(ROOT, dist))
        elif kind == "gui":
            problems.extend(check_gui_liveness(ROOT, dist))

    if problems:
        for item in problems:
            print("问题：%s" % item, file=sys.stderr)
        return 1
    print(OK_MARKER)
    return 0


if __name__ == "__main__":
    sys.exit(main())
