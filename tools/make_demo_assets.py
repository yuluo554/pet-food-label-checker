#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""演示物料程序化产出：PNG 截图 + GIF。

纪律（见 plan/03、plan/06 M5）：
  * **offscreen 渲染必须显式加载 CJK 字体**——Qt 6 起不随附字体、
    offscreen 也不扫描系统字体目录，中文会渲染成豆腐块；
  * **演示图必须是真实判定态**（填表 → 点击 → 出结果），空表单图没有信息量；
  * 素材入仓后是**冻结资产**：生成器固定窗口尺寸、不写当前时间，
    验收 = 两次独立生成的全部文件 sha256 逐个一致；
  * GIF 用 Pillow 编码（**不自写 LZW**——码长增长时机与表满处理在
    标准解码器上多轮对拍仍有边界分歧）。Pillow 函数体内惰性 import，
    缺它只跳过 GIF 保留 PNG。

用法：
    py -X utf8 tools/make_demo_assets.py --out docs/demo
"""

from __future__ import annotations

import argparse
import os
import sys
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

# offscreen 平台必须在**首次导入 PySide6 前**设置
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

#: 窗口尺寸固定（素材可复现的前提）
WINDOW_SIZE = (1000, 720)

#: 演示用合成标签（与"演示一律合成数据"红线一致）
DEMO_LABEL = """测试粮A 猫粮 成年
产品特点：天然、无谷
原料组成：鸡肉、糙米、鱼油、维生素预混料
添加剂：维生素A、维生素D3、硫酸锌
成分分析保证值：
粗蛋白 >= 30%
粗脂肪 >= 12%
水分 <= 12%
净含量：2kg
生产企业：某合成宠物食品有限公司
生产日期：2026-01-01
保质期：18个月
"""


def capture(out_dir: Path) -> List[Path]:
    """渲染各页签 PNG。"""
    from PySide6 import QtCore, QtWidgets

    from pflc.gui.app import build_app

    out_dir.mkdir(parents=True, exist_ok=True)
    app, window = build_app([])
    window.window.resize(*WINDOW_SIZE)
    window.show()

    # 灌入演示数据并触发一次真实判定（演示图必须是真实计算态）
    window.editor.setPlainText(DEMO_LABEL)
    window._on_check()

    saved: List[Path] = []
    tabs = window._tabs
    for index in range(tabs.count()):
        tabs.setCurrentIndex(index)
        app.processEvents()
        QtCore.QTimer.singleShot(0, lambda: None)
        app.processEvents()
        pixmap = window.window.grab()
        target = out_dir / ("tab-%d.png" % index)
        # QPixmap.save(BytesIO) 在 6.6 不可用 → 走 QBuffer
        buffer = QtCore.QBuffer()
        buffer.open(QtCore.QIODevice.WriteOnly)
        pixmap.save(buffer, "PNG")
        target.write_bytes(bytes(buffer.data()))
        saved.append(target)
    return saved


def make_gif(pngs: List[Path], target: Path) -> bool:
    """由 PNG 合成 GIF（Pillow 惰性 import，缺它只跳过）。"""
    try:
        from PIL import Image
    except ImportError:
        print("提示：未安装 Pillow，跳过 GIF 合成（PNG 已保留）")
        return False
    if not pngs:
        return False
    frames = [Image.open(str(p)).convert("RGB") for p in pngs]
    # 固定时长与调色板参数，保证可复现
    frames[0].save(
        str(target),
        save_all=True,
        append_images=frames[1:],
        duration=900,
        loop=0,
        optimize=False,
    )
    return True


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="演示物料程序化产出")
    parser.add_argument("--out", default="docs/demo", help="输出目录")
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir

    try:
        pngs = capture(out_dir)
    except ImportError as exc:
        print("缺少 GUI 依赖（PySide6）：%s" % exc, file=sys.stderr)
        return 3

    print("已产出 %d 张 PNG：%s" % (len(pngs), out_dir))
    gif = out_dir / "demo.gif"
    if make_gif(pngs, gif):
        print("已产出 GIF：%s" % gif)
    return 0


if __name__ == "__main__":
    sys.exit(main())
