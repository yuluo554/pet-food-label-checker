"""冻结验收脚本的常驻守门测试。

``tools/verify_frozen.py`` 是**发行态**的验收通路（本地源码态测试覆盖不到
冻结产物）。但"脚本只在收棒时手工跑一次"等于它没有回归保护——改坏一个判据
要等到下次打包才发现。故这里在**合成 dist 树**上驱动它的每个检查。

与 ``tests/test_gates.py`` 的分工：那里守"仓库侧口径"（白名单/豁免/spec），
这里守"验收脚本本身的判据"（能不能真的判出坏产物）。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"


def _load_verify():
    spec = importlib.util.spec_from_file_location("verify_frozen_probe",
                                                  TOOLS / "verify_frozen.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["verify_frozen_probe"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def verify():
    return _load_verify()


def _make_dist(base: Path, kind="cli", exe_names=("pflc-cli",),
               with_data=("rules", "samples", "benchmark")):
    """构造一棵**最小合法** dist 树（PyInstaller 6.x onedir 布局）。"""
    dist = base / ("pflc-cli-dist" if kind == "cli" else "pflc")
    internal = dist / "_internal"
    for name in with_data:
        (internal / "data" / name).mkdir(parents=True, exist_ok=True)
    for name in exe_names:
        (dist / ("%s.exe" % name)).write_bytes(b"MZ")
    return dist


def _write_report(dist: Path, kind, exe_names):
    """写一份与仓库现状一致的构建报告（对照组的基准）。"""
    from pflc.packaging import DATA_WHITELIST, data_manifest

    payload = {
        "data_whitelist": list(DATA_WHITELIST),
        "datas": [{"src_rel": "x", "dest": "data/%s" % n} for n in DATA_WHITELIST],
        "sha256": data_manifest(ROOT),
        "kind": kind,
        "exe_names": list(exe_names),
    }
    with open(dist / "_datas_report.json", "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def test_report_gate_passes_on_faithful_report(verify, tmp_path):
    """对照组：报告与仓库现状一致时**不得报错**（证明判据不是"见报告就红"）。"""
    dist = _make_dist(tmp_path)
    _write_report(dist, "cli", ["pflc-cli"])
    assert verify.check_dist_datasets(ROOT, dist) == []


def test_report_gate_rejects_missing_report(verify, tmp_path):
    """**报告缺失必须报错**——空报告与合规报告不能长得一样（恒绿门）。"""
    dist = _make_dist(tmp_path)
    problems = verify.check_dist_datasets(ROOT, dist)
    assert any("_datas_report.json" in p for p in problems), problems


def test_report_gate_rejects_extra_shipped_dir(verify, tmp_path):
    """**多打目录必须被抓**：报告里多一个白名单外 dest = spec 手写了路径。

    这是 sha256 对账抓不到的一类（对账基准取自仓库清单，手加路径照样一致）。
    """
    dist = _make_dist(tmp_path)
    _write_report(dist, "cli", ["pflc-cli"])
    path = dist / "_datas_report.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["datas"].append({"src_rel": "data/knowledge", "dest": "data/knowledge"})
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    problems = verify.check_dist_datasets(ROOT, dist)
    assert any("多打/少打" in p for p in problems), problems


def test_report_gate_rejects_stale_whitelist(verify, tmp_path):
    """**构建用的白名单与当前不一致必须被抓**（构建后仓库口径变了）。"""
    dist = _make_dist(tmp_path)
    _write_report(dist, "cli", ["pflc-cli"])
    path = dist / "_datas_report.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["data_whitelist"] = ["rules"]          # 少一项
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    problems = verify.check_dist_datasets(ROOT, dist)
    assert any("白名单与当前白名单不一致" in p for p in problems), problems


def test_report_gate_rejects_tampered_data(verify, tmp_path):
    """**报告里的 sha256 与仓库现算不符必须被抓**（构建后数据被改过）。"""
    dist = _make_dist(tmp_path)
    _write_report(dist, "cli", ["pflc-cli"])
    path = dist / "_datas_report.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    key = sorted(payload["sha256"])[0]
    payload["sha256"][key] = "0" * 64
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    problems = verify.check_dist_datasets(ROOT, dist)
    assert any("sha256" in p for p in problems), problems


def test_gui_dep_gate_is_two_way(verify, tmp_path):
    """GUI 依赖分流**双向**验证：桌面包必须有 Qt，CLI 包必须没有。"""
    # 桌面包缺 Qt → 报"废包"
    gui_dist = _make_dist(tmp_path / "a", kind="gui", exe_names=("pflc",))
    _write_report(gui_dist, "gui", ["pflc"])
    problems = verify.check_gui_carries_gui_deps(ROOT, gui_dist)
    assert any("PySide6" in p for p in problems), problems

    # 桌面包带上 Qt → 通过
    (gui_dist / "_internal" / "PySide6").mkdir()
    assert verify.check_gui_carries_gui_deps(ROOT, gui_dist) == []

    # CLI 包带 Qt → 报"降级提示成死代码"
    cli_dist = _make_dist(tmp_path / "b", kind="cli", exe_names=("pflc-cli",))
    _write_report(cli_dist, "cli", ["pflc-cli"])
    (cli_dist / "_internal" / "PySide6").mkdir()
    problems = verify.check_gui_carries_gui_deps(ROOT, cli_dist)
    assert any("降级提示" in p for p in problems), problems


def test_frozen_data_gate_reports_missing_embedded_file(verify, tmp_path):
    """内嵌数据缺失必须被抓（数据没随包走 —— 换台机器就废）。"""
    dist = _make_dist(tmp_path)
    problems = verify.check_dist(ROOT, dist)
    assert any("内嵌数据缺失" in p for p in problems), problems
