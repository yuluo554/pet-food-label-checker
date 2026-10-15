"""CLI 测试：退出码三语义、编码守卫、惰性导入缺依赖路径、端到端。"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from pflc.cli import EXIT_DEP_MISSING, build_parser, main
from tests.conftest import write_text_lf

#: 退出码（与 README/决策记录声明一致，锁进测试防漂移）
EXIT_OK = 0
EXIT_NOT_MET = 1
EXIT_USAGE = 2


def _run(argv, monkeypatch, rules_dir):
    """跑 CLI，把数据目录指到夹具规则包。"""
    monkeypatch.setenv("PFLC_DATA_DIR", str(rules_dir.parent))
    return main(argv)


def test_no_subcommand_is_usage_error(monkeypatch):
    monkeypatch.setenv("PFLC_DATA_DIR", ".")
    assert main([]) == EXIT_USAGE


def test_check_missing_file_is_usage_error(tmp_path, monkeypatch, rules_dir):
    assert main(["check", str(tmp_path / "nope.txt")]) == EXIT_USAGE


def test_check_clean_label_exits_zero(tmp_path, monkeypatch, rules_dir, ok_label_text):
    path = write_text_lf(tmp_path / "ok.txt", ok_label_text)
    assert main(["check", str(path)]) == EXIT_OK


def test_check_violating_label_exits_one(tmp_path, monkeypatch, rules_dir):
    """检出不符合 → exit 1（README 明示语义）。"""
    text = "测试粮A 猫粮 成年\n原料组成：鸡肉\n添加剂：维生素A\n生产日期：2026-01-01\n"
    path = write_text_lf(tmp_path / "bad.txt", text)
    assert main(["check", str(path)]) == EXIT_NOT_MET


def test_scan_missing_dir_is_usage_error(tmp_path):
    assert main(["scan", str(tmp_path / "nope")]) == EXIT_USAGE


def test_scan_reports_and_exit_code(tmp_path, rules_dir, ok_label_text):
    work = tmp_path / "batch"
    work.mkdir()
    write_text_lf(work / "ok.txt", ok_label_text)
    assert main(["scan", str(work)]) == EXIT_OK


def test_scan_baseline_missing_file_is_usage_error(tmp_path, rules_dir, ok_label_text):
    work = tmp_path / "batch"
    work.mkdir()
    write_text_lf(work / "ok.txt", ok_label_text)
    assert main(["scan", str(work), "--baseline", str(tmp_path / "nope.json")]) == EXIT_USAGE


def test_bench_exit_zero_on_fixture(rules_dir, monkeypatch):
    monkeypatch.setenv("PFLC_DATA_DIR", str(rules_dir.parent))
    assert main(["bench"]) == EXIT_OK


def test_bench_unknown_suite_is_usage_error(rules_dir, monkeypatch):
    """``--only`` 未知名 → exit 2，否则"跑了个不存在的基准"会被读成成功。"""
    monkeypatch.setenv("PFLC_DATA_DIR", str(rules_dir.parent))
    assert main(["bench", "--only", "nope"]) == EXIT_USAGE


def test_report_exports_both_formats(tmp_path, rules_dir, ok_label_text, monkeypatch):
    monkeypatch.setenv("PFLC_DATA_DIR", str(rules_dir.parent))
    path = write_text_lf(tmp_path / "ok.txt", ok_label_text)
    out = tmp_path / "out"
    assert main(["report", str(path), "--out", str(out)]) == EXIT_OK
    assert (out / "report.md").is_file()
    assert (out / "report.csv").is_file()


def test_diagnostics_exit_one_when_no_effective_rules(empty_rules_dir, monkeypatch):
    monkeypatch.setenv("PFLC_DATA_DIR", str(empty_rules_dir.parent))
    assert main(["diagnostics"]) == EXIT_NOT_MET


def test_selftest_writes_file(tmp_path, rules_dir, monkeypatch):
    """冻结态自检结论**写文件回传**（窗口程序无 stdout 的唯一脚本化通路）。"""
    monkeypatch.setenv("PFLC_DATA_DIR", str(rules_dir.parent))
    out = tmp_path / "selftest.json"
    assert main(["selftest", "--out", str(out)]) == EXIT_OK
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert "checks" in payload
    # 源码态不判 FAIL（非冻结态该项返回 None）
    assert payload["checks"]["data_dir_in_dist"] is None


def test_gui_missing_dependency_returns_exit_3(monkeypatch, rules_dir, capsys):
    """**惰性导入边界**：缺 PySide6 必须走 exit 3 而非裸异常。

    用 ``builtins.__import__`` 打桩让 PySide6 抛 ImportError——
    这在本机即可复现，不必等 CI 的无 Qt 环境。

    同时断言**降级提示按运行形态分流**：源码态说 pip，冻结态说"下载桌面版"。
    只断言退出码会漏掉这条口径——冻结态用户被指去 ``pip install`` 是
    误导（他没有 pip，也装不上 extra，见 plan/04 §九）。
    """
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("PySide6"):
            raise ImportError("No module named 'PySide6'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setenv("PFLC_DATA_DIR", str(rules_dir.parent))

    # ① 源码态：提示 pip
    assert main(["gui"]) == EXIT_DEP_MISSING
    source_msg = capsys.readouterr().err
    assert "pip install" in source_msg, "源码态未提示 pip 安装通路"

    # ② 冻结态：不得再提示 pip（那正是"冻结态用户装不上 pip"的失效形态）
    monkeypatch.setattr("pflc.data_paths.is_frozen", lambda: True)
    assert main(["gui"]) == EXIT_DEP_MISSING
    frozen_msg = capsys.readouterr().err
    assert "pip install" not in frozen_msg, (
        "冻结态仍提示 pip 安装（用户装不上）—— 降级提示未分流：%s" % frozen_msg)
    assert "桌面版" in frozen_msg, "冻结态未提示改用桌面版发行包：%s" % frozen_msg


def test_parser_has_all_documented_subcommands():
    parser = build_parser()
    actions = [a for a in parser._actions if getattr(a, "choices", None)]
    names = set()
    for action in actions:
        if isinstance(action.choices, dict):
            names.update(action.choices)
    assert {"check", "scan", "bench", "report", "diagnostics", "selftest",
            "gui"} <= names


def test_ensure_utf8_stdio_reconfigures_cp1252_stream(monkeypatch):
    """编码守卫：cp1252 管道应被切到 UTF-8（CI 环境差异的本机复现）。"""
    from pflc.cli import _ensure_utf8_stdio

    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252", errors="strict")
    monkeypatch.setattr("sys.stdout", stream)
    _ensure_utf8_stdio()
    assert stream.encoding.lower().replace("-", "") == "utf8"
    # 中文写入不再抛 UnicodeEncodeError
    print("测试")
    stream.flush()
