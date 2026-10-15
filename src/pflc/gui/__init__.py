"""桌面应用（PySide6）。

**零判定逻辑**：本包只消费 ``pflc.pipeline`` 的公开函数，绝不复现判定规则、
绝不做算术运算、绝不内联政策数值——这三条由 AST 静态门禁守住（见 plan/07 K10）。
只守"不 import 规则层"会漏掉"界面里直接算"与"界面里内联政策值"两种绕过。

**PySide6 惰性导入**：模块顶层不 import Qt，由 ``_qt()`` 在函数体内取符号——
这让"缺依赖"成为运行期可捕获的 ``ImportError``（CLI 转 exit 3），
也让本包在无 Qt 环境可被 import（分层守门与测试的需要）。
"""

from .app import main  # noqa: F401

__all__ = ["main"]
