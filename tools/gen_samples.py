#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""输入夹具生成器：产出 README 可直接复制的示例标签。

**为什么夹具必须由生成器产出**（见 plan/07 "README 可跑性第三类缺口"）：
README 引用的输入文件若不存在，本地因工作目录残留看不出来，干净环境一跑就崩。
夹具由生成器产出并纳入"再生成位级一致"守门，这条缺口才被结构性堵住。

用法：
    py -X utf8 tools/gen_samples.py --force
    py -X utf8 tools/gen_samples.py --check
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List

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
SAMPLES_DIR = ROOT / "data" / "samples"

OK_MARKER = "FROZEN_SAMPLES_OK"

#: 合成夹具（假品牌名，零真实品牌；见 plan/05 §四.4）。
#:
#: **保证值口径 = 标签标示口径（as-fed）**：国标理化指标是"以干物质计"，
#: 引擎会先按标示水分换算到干基再比。故夹具里的数值是**按水分折回的标示值**，
#: 不是标准表里的限值本身——直接抄标准限值会让"合规样例"在干基判定下
#: 真的越限（M1 实测踩过）。数值一律避开规则包限值字面量（见零字面量门禁）。
SAMPLES: Dict[str, str] = {
    "label-demo-ok.txt": """测试粮A 猫粮 成年
产品特点：天然
原料组成：鸡肉、糙米、鱼油、维生素预混料
添加剂：维生素A、维生素D3、硫酸锌、氯化胆碱
成分分析保证值：
水分 <= 12%
粗蛋白 >= 23%
粗脂肪 >= 8%
粗灰分 <= 8%
粗纤维 <= 7%
钙 >= 0.7%
总磷 >= 0.55%
水溶性氯化物 >= 0.4%
净含量：2kg
生产企业：某合成宠物食品有限公司
地址：某省某市某区某路 1 号
生产日期：2026-01-01
保质期：18个月
""",
    "label-demo-missing.txt": """测试粮B 犬粮 成年
原料组成：鸡肉、小麦、鱼油
成分分析保证值：
水分 <= 12%
粗蛋白 >= 26%
粗脂肪 >= 10%
生产企业：某合成宠物食品有限公司
生产日期：2026-01-01
""",
    "label-demo-overlimit.txt": """测试粮C 猫粮 成年
原料组成：鸡肉、糙米、鱼油
添加剂：维生素A、维生素D3
成分分析保证值：
水分 <= 12%
粗蛋白 >= 12%
粗脂肪 >= 5%
净含量：2kg
生产企业：某合成宠物食品有限公司
生产日期：2026-01-01
保质期：18个月
""",
    "label-demo-claim.txt": """测试粮D 犬粮 全阶段
产品特点：天然、无谷
成分分析保证值：
粗蛋白 >= 26%
净含量：2kg
生产企业：某合成宠物食品有限公司
生产日期：2026-01-01
保质期：18个月
""",
    #: **M2 边界夹具**：把 M1 实测发现的三处解析缺口摆成可跑的输入——
    #: ① "全价"是产品类型词，与真生命阶段"幼年"同现**不该判阶段歧义**；
    #: ② 净含量单位"oz"不认识 → mapping_uncertain（不是 not_found）；
    #: ③ 生产日期 2026-13-45 非法 → out_of_range。
    #: 这份夹具让"缺口有没有被修好"在 README 的一条命令里就能看见。
    "label-demo-edge.txt": """测试粮E 猫粮 幼年
产品名称：测试粮E全价幼猫粮
产品特点：天然
原料组成：鸡肉、糙米、鱼油
添加剂：维生素A、维生素D3
成分分析保证值：
水分 <= 12%
粗蛋白 >= 30%
粗脂肪 >= 12%
净含量：2oz
生产企业：某合成宠物食品有限公司
生产日期：2026-13-45
保质期：18个月
""",
}


def generate() -> Dict[str, str]:
    return {name: text for name, text in sorted(SAMPLES.items())}


def write_all(samples: Dict[str, str]) -> None:
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    for name, text in samples.items():
        path = SAMPLES_DIR / name
        # newline="\n" 显式指定（Path.write_text(newline=) 是 3.10+ 参数）
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)


def check() -> bool:
    samples = generate()
    ok = True
    for name, text in samples.items():
        path = SAMPLES_DIR / name
        if not path.is_file():
            print("缺失：%s" % name)
            ok = False
            continue
        if path.read_text(encoding="utf-8") != text:
            print("不一致：%s" % name)
            ok = False
    return ok


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="输入夹具生成器")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--force", action="store_true", help="重生成全部夹具")
    group.add_argument("--check", action="store_true", help="位级一致校验")
    args = parser.parse_args(argv)

    if args.check:
        if check():
            print(OK_MARKER)
            return 0
        print("FROZEN_SAMPLES_MISMATCH", file=sys.stderr)
        return 1

    samples = generate()
    write_all(samples)
    print("已生成 %d 份夹具：%s" % (len(samples), SAMPLES_DIR))
    return 0


if __name__ == "__main__":
    sys.exit(main())
