"""桌面应用主体：多页签界面 + 中文字体显式加载 + 零判定逻辑。

**PySide6 只在函数体内导入**（``_qt()``），模块顶层不出现 Qt 符号——
这让本模块在无 Qt 环境也能被 import，并让缺依赖成为可捕获的 ``ImportError``。

界面层的三条硬纪律（AST 门禁守住）：
  1. 不 import 规则层/引擎内部模块（唯一入口是 ``pflc.pipeline``）；
  2. 无算术运算 ``BinOp``（``*`` ``/`` ``-`` ``//`` ``%`` ``**``）——界面只做展示与转发；
  3. 无政策数值字面量——数值一律来自规则包。

offscreen 下 Qt 不扫描系统字体目录，中文会渲染成豆腐块 → 必须**显式加载**
CJK 字体；字体路径由 ``WINDIR``/``SystemRoot`` 推导，**不写死绝对盘符**
（换机失效，且脱敏审计会把它当"其他盘路径"复核项）。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

# 唯一允许的取数入口：编排层。界面层不得直接 import 判定内核的任何模块
# （由 tests/test_gates.py 的 AST 门禁守住）。
from .. import pipeline

#: 页签名（纯展示文本，无政策数值）
TAB_TITLES = ("标签导入", "标示项检查", "限值判定", "宣称核查", "基准评测", "关于")

#: 窗口尺寸（布局常量，不是政策数值——命名以 _WIDTH/_HEIGHT 结尾，
#: 供 AST 零字面量门禁按命名豁免；界面里出现真政策数值仍会被抓）
WINDOW_WIDTH = 900
WINDOW_HEIGHT = 700


def _qt():
    """惰性取 Qt 符号——**唯一的 PySide6 导入点**。"""
    from PySide6 import QtCore, QtGui, QtWidgets

    return QtCore, QtGui, QtWidgets


def _cjk_font_candidates() -> List[str]:
    """候选 CJK 字体路径（由环境变量推导，不写死盘符）。"""
    candidates: List[str] = []
    windir = os.environ.get("WINDIR") or os.environ.get("SystemRoot")
    if windir:
        fonts = Path(windir) / "Fonts"
        for name in ("msyh.ttc", "msyh.ttf", "simhei.ttf", "simsun.ttc"):
            candidates.append(str(fonts / name))
    # POSIX 常见发行版路径（CI ubuntu 用）
    for path in (
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        candidates.append(path)
    return candidates


def load_cjk_font(app) -> Optional[str]:
    """显式注册 CJK 字体并设为应用默认字体。返回实际使用的路径。"""
    _, QtGui, _ = _qt()
    for path in _cjk_font_candidates():
        if not Path(path).is_file():
            continue
        font_id = QtGui.QFontDatabase.addApplicationFont(path)
        if font_id < 0:
            continue
        families = QtGui.QFontDatabase.applicationFontFamilies(font_id)
        if families:
            app.setFont(QtGui.QFont(families[0]))
            return path
    return None


class MainWindow:
    """主窗口。**构造时不取 Qt 符号之外的东西**——判定一律走 pipeline。"""

    def __init__(self) -> None:
        QtCore, QtGui, QtWidgets = _qt()
        self._QtWidgets = QtWidgets
        self.window = QtWidgets.QMainWindow()
        self.window.setWindowTitle("宠物食品标签合规比对器")
        self.window.resize(WINDOW_WIDTH, WINDOW_HEIGHT)

        tabs = QtWidgets.QTabWidget()
        self.editor = QtWidgets.QPlainTextEdit()
        self.editor.setPlaceholderText("在此粘贴标签全文……")

        tabs.addTab(self._build_import_tab(), TAB_TITLES[0])
        # 每个结果页签一个**独立** QPlainTextEdit —— Qt 控件只能有一个父级，
        # 把同一个控件 addTab 多次会让 Qt 重新父化它，页签数随之塌掉。
        self.result_views: Dict[str, object] = {}
        for title in TAB_TITLES[1:4]:
            view = QtWidgets.QPlainTextEdit()
            view.setReadOnly(True)
            self.result_views[title] = view
            tabs.addTab(view, title)
        tabs.addTab(self._build_bench_tab(), TAB_TITLES[4])
        tabs.addTab(self._build_about_tab(), TAB_TITLES[5])

        self.window.setCentralWidget(tabs)
        self._tabs = tabs

    # -- 页签 -------------------------------------------------------------

    def _build_import_tab(self):
        QtWidgets = self._QtWidgets
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.addWidget(self.editor)
        button = QtWidgets.QPushButton("核验")
        # 通知走可注入信号，不用模态框（模态 QMessageBox 会挂死 offscreen 测试批）
        button.clicked.connect(self._on_check)
        layout.addWidget(button)
        return page

    def _build_bench_tab(self):
        QtWidgets = self._QtWidgets
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        self.bench_view = QtWidgets.QPlainTextEdit()
        self.bench_view.setReadOnly(True)
        button = QtWidgets.QPushButton("运行基准")
        button.clicked.connect(self._on_bench)
        layout.addWidget(self.bench_view)
        layout.addWidget(button)
        return page

    def _build_about_tab(self):
        QtWidgets = self._QtWidgets
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        view = QtWidgets.QPlainTextEdit()
        view.setReadOnly(True)
        info = pipeline.diagnostics()
        lines = [
            "宠物食品标签合规比对器",
            "",
            "运行形态：%s" % ("冻结态（打包产物）" if info["frozen"] else "源码态"),
            "数据目录：%s" % info["data_dir"],
            "生效规则：%d 条" % info["total_effective"],
            "",
            pipeline.DISCLAIMER,
        ]
        view.setPlainText("\n".join(lines))
        layout.addWidget(view)
        return page

    # -- 事件槽（只调 pipeline，零判定逻辑）---------------------------------

    def _on_check(self) -> None:
        text = self.editor.toPlainText()
        card = pipeline.build_card(text, source="<gui>")
        result = pipeline.check_card_result(card)
        sections = pipeline.build_report_sections(result)

        # 每个维度页签只渲染该维度的明细（结果取自已算好的 sections，界面不重算）
        dimension_titles = {
            pipeline.DIM_LABEL: TAB_TITLES[1],
            pipeline.DIM_NUTRITION: TAB_TITLES[2],
            pipeline.DIM_CLAIM: TAB_TITLES[3],
        }
        detail_section = next(s for s in sections if s.section_id == pipeline.SEC_FINDINGS)
        overview = self._render_sections(
            [s for s in sections if s.section_id != pipeline.SEC_FINDINGS])
        for dimension, title in dimension_titles.items():
            rows = [r for r in detail_section.rows if r.get("维度") == dimension]
            body = [overview, "", "## %s 明细" % dimension]
            for row in rows:
                body.append(" | ".join("%s" % row.get(k, "") for k in row))
            if not rows:
                body.append("（本次该维度无判定条目：零生效规则或本次无适用规则）")
            self.result_views[title].setPlainText("\n".join(body))
        self._tabs.setCurrentIndex(1)

    def _render_sections(self, sections) -> str:
        """把结构化章节渲染为可读文本（界面只做展示，不含判定）。"""
        lines = []
        for section in sections:
            lines.append("## %s" % section.title)
            if section.text:
                lines.append(section.text)
            for row in section.rows:
                lines.append(" | ".join("%s" % row.get(k, "") for k in row))
            if section.note:
                lines.append("（%s）" % section.note)
            lines.append("")
        return "\n".join(lines)

    def _on_bench(self) -> None:
        from ..benchmark import BenchConfigError, render_report

        try:
            report = pipeline.run_bench()
            text = render_report(report)
        except BenchConfigError as exc:
            text = "基准未启用：%s" % exc
        self.bench_view.setPlainText(text)

    # -- 测试/截图辅助 -----------------------------------------------------

    def show(self) -> None:
        self.window.show()


def build_app(argv: Optional[List[str]] = None):
    """构建 QApplication + 主窗口（**不含事件循环**，便于测试与截图）。"""
    QtCore, QtGui, QtWidgets = _qt()
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(argv or [])
    load_cjk_font(app)
    window = MainWindow()
    return app, window


def main(argv: Optional[List[str]] = None) -> int:
    """GUI 主入口（含事件循环）。"""
    app, window = build_app(argv)
    window.show()
    return int(app.exec())
