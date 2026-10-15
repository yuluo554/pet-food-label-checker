#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发布物打包器：把两棵发行树打成**确定性 zip**（M6 DoD 第 7 条）。

为什么必须确定性（四条一起才叫"确定性"）：

  1. **条目顺序固定**：按包内路径 ``/`` 分隔后**字典序**排序。zip 里条目顺序
     取决于遍历顺序，不排序则两次打包的字节流不同；
  2. **时间戳固定**：zip 每条目存 DOS 时间。不固定则"同一个 exe、同一天"
     也会因秒级差异产出不同 sha256。这里统一写 ``SOURCE_DATE_EPOCH`` 口径的
     常量时间（``1980-01-01 00:00:00``，DOS 时间的下界）；
  3. **压缩方式固定**：``ZIP_STORED``。发行包内已是 PyInstaller 压缩过的
     PySide6 二进制，再压收益极低，却引入 zlib 版本差异这一非确定性源；
  4. **元数据固定**：外部属性（``external_attr``）与创建系统写常量，
     不沿用宿主 umask / 平台。

**发布物形态（M6 决策，见 plan/RELEASE-M6.md §二）**：两棵树**各打一个 zip**，
而不是"只发 GUI 树"或"合成一棵"——

  * 两棵树是**独立的发行形态**（GUI 含 PySide6；CLI 特意不含，见 K33）。
    合成一棵就得带上 Qt，CLI 的 exit 3 降级提示立成死代码且白送 87 MB；
  * 分开发布让"下哪个"这件事显式化：只要命令行核验的用户不必下 110 MB。

用法：
    py -X utf8 tools/make_release.py --dist dist --out release
    py -X utf8 tools/make_release.py --dist dist --out release --check
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path
from typing import Dict, List, Tuple

for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    if _stream is not None:
        _enc = (getattr(_stream, "encoding", "") or "").lower()
        if _enc not in ("utf-8", "utf8"):
            _reconf = getattr(_stream, "reconfigure", None)
            if _reconf is not None:
                try:
                    _reconf(encoding="utf-8")
                except (ValueError, OSError):
                    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from audit_desensitize import compute_tokens, sensitive_literals  # noqa: E402

OK_MARKER = "RELEASE_PACK_OK"

#: 打包的发行树：``(dist 内目录名, zip 基名)``。
#:
#: zip 基名**必须 ASCII**（M6 DoD 第 8 条）：GitHub Release 附件的文件名会进
#: URL 与 ``Content-Disposition``，非 ASCII 名在不同客户端上下载后名字不一致。
#: 版本号进文件名，附件与源码 tag 因此能对上号。
PACKAGES: Tuple[Tuple[str, str], ...] = (
    ("pflc", "pflc-gui-windows-x64"),
    ("pflc-cli-dist", "pflc-cli-windows-x64"),
)

#: 固定时间戳（DOS epoch 下界）：``(1980, 1, 1, 0, 0, 0)``。
#: ``SOURCE_DATE_EPOCH`` 的通行做法是取该值的 UTC——1980-01-01 是 zip 格式
#: 能表达的最小时间，任何更早的值会被截断成它，等同。
FIXED_DATE_TIME = (1980, 1, 1, 0, 0, 0)

#: 固定外部属性位：``0o100644 << 16``（普通文件、无执行位）。
#: 沿用宿主 umask 会让同一份产物在 Linux/Windows 上产出不同字节。
FIXED_EXTERNAL_ATTR = 0o100644 << 16

#: 版本从包内实算（不写死，避免与 pyproject 漂移）。
def package_version() -> str:
    sys.path.insert(0, str(ROOT / "src"))
    import pflc
    return pflc.__version__


def _entries(dist: Path) -> List[Path]:
    """树内全部文件，按**包内路径**字典序（``/`` 分隔）排序。

    排序键必须是 zip 里那条路径而不是宿主绝对路径——否则同一棵树在不同盘符/
    不同根目录下会排出不同顺序，"确定性"就成了"同一台机器上确定"。
    """
    files = [p for p in dist.rglob("*") if p.is_file()]
    return sorted(files, key=lambda p: p.relative_to(dist).as_posix())


def _zip_entry_name(base: str, rel: str) -> str:
    """zip 内条目名：顶层带一个包目录（解压即得干净目录，不漏一地文件）。"""
    return "%s/%s" % (base, rel)


def build_zip(dist: Path, base: str, target: Path) -> Dict[str, object]:
    """把 ``dist`` 打成确定性 zip 写到 ``target``，返回清单信息。"""
    dist = Path(dist)
    if not dist.is_dir():
        raise FileNotFoundError("发行树不存在：%s" % dist)

    entries = _entries(dist)
    if not entries:
        raise ValueError("发行树为空（打包会产出空 zip，判据恒绿）：%s" % dist)

    target.parent.mkdir(parents=True, exist_ok=True)
    # ZIP_STORED + 固定时间戳 + 固定属性 = 逐字节可复现
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_STORED) as zf:
        for path in entries:
            rel = path.relative_to(dist).as_posix()
            info = zipfile.ZipInfo(_zip_entry_name(base, rel), FIXED_DATE_TIME)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 0          # 0 = MS-DOS，跨平台固定
            info.external_attr = FIXED_EXTERNAL_ATTR
            zf.writestr(info, path.read_bytes())

    return {
        "zip": target.name,
        "base": base,
        "file_count": len(entries),
        "bytes": target.stat().st_size,
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
    }


def verify_zip_readback(path: Path, dist: Path, base: str) -> List[str]:
    """**回读保真**：解出来的每个条目与源文件逐字节相同，且集合完全一致。

    只比 sha256 不够——``writestr`` 写错条目名（如少了顶层目录）会让解压结构
    变形而哈希自洽。故这里同时验：条目名集合 == 源文件集合、逐条字节相同。
    """
    problems: List[str] = []
    expected: Dict[str, bytes] = {}
    for p in _entries(dist):
        expected[_zip_entry_name(base, p.relative_to(dist).as_posix())] = p.read_bytes()

    with zipfile.ZipFile(path, "r") as zf:
        got_names = zf.namelist()
        if got_names != sorted(expected):
            missing = sorted(set(expected) - set(got_names))
            extra = sorted(set(got_names) - set(expected))
            problems.append(
                "zip 条目集合与源树不符（缺 %s / 多 %s）"
                % (missing[:5], extra[:5]))
        if got_names != sorted(got_names):
            problems.append("zip 条目未按字典序排列 —— 打包顺序不确定")
        for name in got_names:
            if name not in expected:
                continue
            bad = zf.getinfo(name)
            if bad.date_time != FIXED_DATE_TIME:
                problems.append("条目时间戳未固定：%s（%s）" % (name, bad.date_time))
            if bad.compress_type != zipfile.ZIP_STORED:
                problems.append("条目压缩方式不是 ZIP_STORED：%s" % name)
            if zf.read(name) != expected[name]:
                problems.append("条目解出后与源文件字节不同：%s" % name)
    return problems


def _literal_hits(name: str, data: bytes, literals) -> List[str]:
    """在一段字节里找禁用字面量。**匹配逻辑的唯一实现**。

    ``scan_zip_body`` 与 ``scan_tree_body`` 都调它——两条通路的判据不能各写一份
    （本项目已实测过"同一口径修一边漏另一边"，见 plan/07 K5/M2）。

    ``boundary=True`` 的字面量要求后随字符非字母数字，复现
    ``user_name_signature`` 的排除逻辑。**这条不是洁癖**：实测 Qt 二进制里的
    ``ASUSTek COMPUTER INC``（显卡厂商串）会被裸子串判据误报成用户名命中。
    """
    hits: List[str] = []
    for category, severity, literal, boundary in literals:
        for encoding in ("ascii", "utf-16-le"):
            try:
                needle = literal.encode(encoding)
            except UnicodeEncodeError:
                continue
            at = data.find(needle)
            while at >= 0:
                if boundary:
                    after = at + len(needle)
                    if data[after:after + 1].isalnum():
                        at = data.find(needle, at + 1)
                        continue
                hits.append("%s [%s/%s] 命中于 %s（%s 编码）"
                            % (name, category, severity, name, encoding))
                break       # 每个字面量在单文件里报一次即可，不必刷屏
    return hits


def _iter_tree_files(dist: Path):
    """遍历发行树内的文件：``(包内相对路径, 字节)``，按路径字典序。"""
    for path in _entries(Path(dist)):
        yield path.relative_to(dist).as_posix(), path.read_bytes()


def scan_tree_body(dist: Path) -> List[str]:
    """**产物本体扫描（目录通路）**：在**未压缩的发行树**里找禁用字面量。

    为什么不能只扫已跟踪文件：``dist/`` 在 ``.gitignore`` 内，
    ``audit_desensitize.py --tracked`` **看不到它**（M5 已在 `plan/06` 记过这个
    盲区）。而发行包是**要发给陌生人的东西**，它带本机路径的后果最重。

    为什么按字面量而不是文本正则：exe/dll/pyd 里既有 ASCII 也有 **UTF-16**
    字面量。把字节当文本解码匹配会漏 UTF-16（每字符夹 NUL）；而"去掉 NUL 再
    匹配"会把本就相邻的字符拼成假阳性。字面量可以**精确编码两种形态**。
    """
    literals = sensitive_literals(compute_tokens())
    if not literals:
        return ["禁用字面量集为空 —— 产物扫描会空转（判据源没接上）"]
    problems: List[str] = []
    for name, data in _iter_tree_files(Path(dist)):
        problems.extend(_literal_hits(name, data, literals))
    return problems


def scan_zip_body(path: Path) -> List[str]:
    """**产物本体扫描（zip 通路）**：扫**真正要发出去的那个字节流**。

    目录通路扫的是源树；这条扫的是最终产物。两者都要有——产物是在"打包"这一步
    定型的，而判据的最后一站必须是**发货物本身**（"源树干净"推不出"zip 干净"，
    反过来也一样）。
    """
    literals = sensitive_literals(compute_tokens())
    if not literals:
        return ["禁用字面量集为空 —— 产物扫描会空转（判据源没接上）"]
    problems: List[str] = []
    with zipfile.ZipFile(path, "r") as zf:
        for name in zf.namelist():
            problems.extend(_literal_hits("%s!%s" % (path.name, name),
                                          zf.read(name), literals))
    return problems


def ledger_text(records: List[Dict[str, object]], version: str) -> str:
    """发布物 sha256 留档（入仓，供"真下载复核"对账）。"""
    lines = [
        "# 发布物 zip sha256 留档（M6）",
        "# 生成：py -X utf8 tools/make_release.py --dist dist --out release",
        "# 版本：%s" % version,
        "#",
        "# 确定性口径：ZIP_STORED + 条目字典序 + 固定时间戳 1980-01-01。",
        "# 两次独立打包的 zip sha256 必须一致（守门见 tests/test_release.py）。",
        "#",
        "# 格式：<sha256>  <附件名>  <文件数>",
        "",
    ]
    for rec in sorted(records, key=lambda r: str(r["zip"])):
        lines.append("%s  %s  %d" % (rec["sha256"], rec["zip"], rec["file_count"]))
    lines.append("")
    return "\n".join(lines)


def parse_ledger(path: Path) -> Dict[str, Tuple[str, int]]:
    """解析留档：``{附件名: (sha256, 文件数)}``。

    **唯一解析实现**：测试与任何下游消费者都调它。各写一份解析必然漂移
    （本项目已实测过"同一口径修一边漏另一边"）。
    """
    out: Dict[str, Tuple[str, int]] = {}
    text = Path(path).read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        out[parts[1]] = (parts[0], int(parts[2]))
    return out


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="发布物确定性打包器")
    parser.add_argument("--dist", default="dist", help="dist 根目录")
    parser.add_argument("--out", default="release", help="zip 输出目录")
    parser.add_argument("--check", action="store_true",
                        help="额外做：两次独立打包 sha256 一致 + 回读保真 + 产物本体扫描")
    parser.add_argument("--ledger", default=None,
                        help="写 sha256 留档到该路径（--check 时用）")
    args = parser.parse_args(argv)

    dist_root = Path(args.dist)
    if not dist_root.is_absolute():
        dist_root = ROOT / dist_root
    out_root = Path(args.out)
    if not out_root.is_absolute():
        out_root = ROOT / out_root

    version = package_version()
    problems: List[str] = []
    records: List[Dict[str, object]] = []

    for dist_name, base in PACKAGES:
        dist = dist_root / dist_name
        if not dist.is_dir():
            problems.append("发行树缺失：%s（先跑 PyInstaller 构建）" % dist)
            continue
        target = out_root / ("%s-%s.zip" % (base, version))
        try:
            record = build_zip(dist, base, target)
        except (FileNotFoundError, ValueError) as exc:
            problems.append(str(exc))
            continue
        records.append(record)
        print("打包 %s -> %s（%d 文件，%.1f MB）"
              % (dist_name, target.name, record["file_count"],
                 record["bytes"] / 1024 / 1024))

        if args.check:
            problems.extend(verify_zip_readback(target, dist, base))
            problems.extend(scan_zip_body(target))
            problems.extend(scan_tree_body(dist))

            # 第二次独立打包：产物 sha256 必须一致（才叫确定性）
            with_second = out_root / ("_repeat-" + target.name)
            second = build_zip(dist, base, with_second)
            if second["sha256"] != record["sha256"]:
                problems.append(
                    "两次打包 sha256 不一致 —— 打包不确定：%s" % target.name)
            with_second.unlink()

    if args.ledger and records and not problems:
        ledger = Path(args.ledger)
        if not ledger.is_absolute():
            ledger = ROOT / ledger
        with open(ledger, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(ledger_text(records, version))
        print("留档已写：%s" % ledger)

    if problems:
        for item in problems:
            print("问题：%s" % item, file=sys.stderr)
        return 1
    print("发布物：%s" % json.dumps(
        [{k: r[k] for k in ("zip", "file_count", "sha256")} for r in records],
        ensure_ascii=False, indent=2))
    print(OK_MARKER)
    return 0


if __name__ == "__main__":
    sys.exit(main())
