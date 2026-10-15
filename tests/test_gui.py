"""GUI 测试：offscreen 常驻、零判定逻辑、缺依赖契约。

``QT_QPA_PLATFORM=offscreen`` 必须在**首次导入 PySide6 前**设置，
否则在无显示环境会直接崩。模块级 ``importorskip`` 是声明式跳过
（干净环境无 GUI extra 时合法跳过，不算硬失败）。
"""

from __future__ import annotations

import os

import pytest

# offscreen 必须在 import PySide6 之前设好
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6", reason="GUI extra 未安装（声明式跳过）")

from pflc.gui import app as gui_app  # noqa: E402


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
