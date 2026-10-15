"""宠物食品标签合规比对器（pflc）。

判定内核（``model``/``parse``/``rules``/``engine``/``report``）与基准
（``benchmark``）**零第三方依赖**，只用标准库——这是"全本地零上传 +
基准可离线复现 + 冻结包体积可控"的根基。

分层（见 plan/03 §一）：
    pipeline   编排层（CLI 与 GUI 共用的公开函数组）
    model      统一中间表示
    parse      解析层（确定性，无 LLM）
    rules      规则层（双重门控 + 零政策字面量 token 实算）
    engine     判定引擎（三态语义）
    report     报告双轨导出（单一渲染源）
    benchmark  合成标签基准（确定性生成 + 植入真值）
    cli        命令行入口
    gui        桌面应用（惰性导入 PySide6，零判定逻辑）
"""

__version__ = "0.1.0"

#: 冻结态标记（供外部快速判断，避免 import sys）
def is_frozen() -> bool:  # pragma: no cover - 薄转发
    from .data_paths import is_frozen as _impl

    return _impl()
