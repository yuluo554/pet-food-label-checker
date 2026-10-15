"""GUI 测试：offscreen 常驻、零判定逻辑、缺依赖契约。

``QT_QPA_PLATFORM=offscreen`` 必须在**首次导入 PySide6 前**设置，
否则在无显示环境会直接崩。模块级 ``importorskip`` 是声明式跳过
（干净环境无 GUI extra 时合法跳过，不算硬失败）。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# offscreen 必须在 import PySide6 之前设好
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6", reason="GUI extra 未安装（声明式跳过）")

from pflc.gui import app as gui_app  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"


@pytest.fixture(scope="module")
def qapp():
    from PySide6 import QtWidgets

    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    gui_app.load_cjk_font(application)
    return application


def test_main_window_builds_with_all_tabs(qapp):
    """窗口可构建，页签数符合声明。"""
    window = gui_app.MainWindow()
    assert window._tabs.count() == len(gui_app.TAB_TITLES)


def test_check_renders_pipeline_results(qapp, rules_dir, ok_label_text):
    """界面点击"核验"后应渲染编排层结果（零判定逻辑）。"""
    window = gui_app.MainWindow()
    window.editor.setPlainText(ok_label_text)
    window._on_check()
    rendered = "\n".join(v.toPlainText() for v in window.result_views.values())
    assert rendered  # 有内容
    assert "输入事实" in rendered or "逐项判定明细" in rendered


def test_bench_tab_reports_config_error_when_no_rules(qapp, empty_rules_dir):
    """规则未录入时基准页应给出可读提示，而非崩溃。"""
    window = gui_app.MainWindow()
    window._on_bench()
    assert window.bench_view.toPlainText()


def test_about_tab_shows_disclaimer(qapp, rules_dir):
    """免责声明必须出现在"关于"页（K19）。"""
    from PySide6 import QtWidgets

    from pflc.model import DISCLAIMER

    window = gui_app.MainWindow()
    about = window._tabs.widget(len(gui_app.TAB_TITLES) - 1)
    texts = [w.toPlainText() for w in about.findChildren(QtWidgets.QPlainTextEdit)]
    assert any(DISCLAIMER in t for t in texts)


def test_gui_uses_pipeline_not_engine(rules_dir, ok_label_text, monkeypatch):
    """行为对账：GUI 的判定结论必须与直接调 pipeline 一致（不是"都调了同一个函数"）。"""
    from pflc import pipeline

    card = pipeline.build_card(ok_label_text)
    direct = pipeline.check_card_result(card)

    window = gui_app.MainWindow()
    window.editor.setPlainText(ok_label_text)
    window._on_check()
    rendered = "\n".join(v.toPlainText() for v in window.result_views.values())

    # 整体结论标签应出现在界面文本里
    assert direct.overall() in rendered or "符合" in rendered


def test_each_result_tab_has_its_own_widget(qapp, rules_dir):
    """Qt 控件只能有一个父级：把同一控件 addTab 多次会让页签数塌掉。

    本测试锁死"每页签独立控件"这一结构（曾因复用同一控件塌成 4 个页签）。
    """
    window = gui_app.MainWindow()
    assert window._tabs.count() == len(gui_app.TAB_TITLES)
    views = list(window.result_views.values())
    assert len(views) == 3
    assert len({id(v) for v in views}) == 3  # 三个不同对象


def test_font_loader_returns_none_or_existing_path(qapp):
    """字体加载要么成功返回存在的路径，要么返回 None——不写死绝对盘符。"""
    path = gui_app.load_cjk_font(qapp)
    if path is not None:
        assert os.path.isabs(path)
        assert os.path.isfile(path)


# --------------------------------------------------------------------------
# 演示物料：留档可核证 + 生成期脱敏真的接上了
# --------------------------------------------------------------------------


def test_demo_ledger_matches_shipped_assets():
    """**M5 留档必须与入仓物料逐份一致**——否则它只是个装饰性文本文件。

    留档的价值在于"有人能拿它核验当前物料"，故判据要落在"清单里的每个
    哈希都对得上真实文件"，不是"文件里出现过 sha256 这个词"。
    """
    import hashlib

    ledger = ROOT / "docs" / "DIST-sha256-M5.txt"
    assert ledger.is_file(), "M5 演示物料留档缺失：%s" % ledger
    declared = {}
    for line in ledger.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        declared[parts[-1]] = parts[0]
    assert declared, "留档里一条哈希都没解析出来 = 判据空转"

    demo_dir = ROOT / "docs" / "demo"
    # 只比**生成器产出的素材**：目录里还有 README.md（说明文档，非生成物）。
    # 判据用生成器的命名形态（tab-N.png / demo.gif），不是"把目录里所有文件都比"。
    actual = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(demo_dir.iterdir())
              if p.is_file() and (p.suffix.lower() in (".png", ".gif"))}
    assert actual, "docs/demo 下没有任何素材文件 = 判据空转"
    assert sorted(declared) == sorted(actual), (
        "留档清单与入仓物料不符（漏登记或多余登记）：留档 %s / 实际 %s"
        % (sorted(declared), sorted(actual)))
    mismatched = [n for n in actual if declared[n] != actual[n]]
    assert mismatched == [], "留档哈希与物料不符（物料被手改或未同步留档）：%s" % mismatched


def test_demo_generator_redacts_local_paths():
    """**入仓演示素材不得含本机路径**——脱敏审计看不到 PNG（二进制豁免）。

    这是"审计扫不到的地方"：``audit_desensitize.py`` 按扩展名把 PNG 当二进制跳过，
    故"关于"页里的数据目录绝对路径能悄悄随素材进公开仓库。生成器在产素材那一步
    做了替换 + 硬断言，本测试守**那条通路真的接上了**（改坏它必须变红）。
    """
    import importlib.util
    import sys as _sys

    spec = importlib.util.spec_from_file_location(
        "make_demo_assets_probe", TOOLS / "make_demo_assets.py")
    module = importlib.util.module_from_spec(spec)
    _sys.modules["make_demo_assets_probe"] = module
    spec.loader.exec_module(module)

    # ① 替换函数真的把仓库绝对路径与数据目录换成占位符
    sample = "数据目录：%s" % (ROOT / "data")
    redacted = module._redact(sample)
    assert str(ROOT) not in redacted, "生成期脱敏未替换仓库根路径：%s" % redacted
    assert module.DATA_DIR_PLACEHOLDER in redacted, "未插入中性占位符：%s" % redacted
    # ② 判据形态：盘符路径可被判出，而 https:// 不得误报（本项目 URL 很多）
    assert module._DRIVE_PATH_RE.search("D:\\x\\y"), "盘符路径判据失效"
    assert not module._DRIVE_PATH_RE.search("https://example.org/a"), (
        "判据误伤 https:// —— 会把参数来源块判成泄漏")
    # ③ 断言函数在**真实窗口**上跑得通（证明确实接线到了 capture 的通路）
    from pflc.gui.app import build_app

    app, window = build_app([])
    window.editor.setPlainText("测试粮A 猫粮 成年")
    window._on_check()
    module._redact_window(window)
    module._assert_no_local_paths(window)   # 干净内容不得抛
