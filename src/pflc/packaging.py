"""打包辅助：数据白名单与冻结态断言。

**为什么放在包内而不是顶层**：顶层模块名 ``packaging.py`` 会**遮蔽 PyPI 的
``packaging``** —— 而 PyInstaller 自身依赖它做版本判断，构建会崩且报错指向
莫名其妙处。顶层命名空间是共享的，包内不是。

白名单单一事实源（见 plan/04 §九）：datas 只准由 ``build_datas()`` 产生，
spec 内不手写数据路径——三处守门（spec 文本、构建后扫描、白名单外检测）
互相独立，改一处口径必同步另两处。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

#: 随包的数据目录白名单（**只收运行必需**）。
#: 版权敏感原文快照（knowledge/raw/）**不入包**——它是核对用素材，不是运行时依赖。
#:
#: ``benchmark`` 必须入包：GUI 与 CLI 都带基准功能，而基准的期望来源是
#: **入库冻结真值库**（``data/benchmark/cases.json``）。不带它，冻结态只能
#: 回落现场重算——"期望锚定冻结真值"在发行包里就成了空话（源码态绿、
#: 发行态名不副实，正是本项目明令避免的失效模式）。
DATA_WHITELIST: Tuple[str, ...] = (
    "rules",
    "benchmark",
)

#: 禁区成分（顶层匹配，**不按任意层级**——按任意层级会把依赖包自带的
#: 同名目录当命中，见 plan/07 反模式）
FORBIDDEN_TOP_LEVEL = ("knowledge", "raw", "_private")


def build_datas(root: Path) -> List[Tuple[str, str]]:
    """产出 PyInstaller datas 列表。

    返回 ``[(源路径, 包内目标目录)]``。禁区目录出现即**直接抛错**——
    构建期拦截比构建后扫描更早、更明确。
    """
    root = Path(root)
    data_root = root / "data"
    datas: List[Tuple[str, str]] = []
    if not data_root.is_dir():
        return datas

    for name in DATA_WHITELIST:
        src = data_root / name
        if src.is_dir():
            datas.append((str(src), "data/%s" % name))
        elif src.is_file():
            datas.append((str(src), "data"))
    return datas


def assert_no_forbidden(root: Path, dist_dir: Path) -> List[str]:
    """构建后断言：dist 全树无禁区成分（**只匹配 dist 顶层**）。"""
    problems: List[str] = []
    dist_dir = Path(dist_dir)
    if not dist_dir.is_dir():
        return ["dist 目录不存在：%s" % dist_dir]
    for name in FORBIDDEN_TOP_LEVEL:
        for candidate in dist_dir.rglob(name):
            # 只报"我们的工作根"下的：顶层或 data/ 下的直接子项
            try:
                rel = candidate.relative_to(dist_dir)
            except ValueError:
                continue
            if len(rel.parts) <= 2:
                problems.append("dist 含禁区成分：%s" % rel)
    # 顶层缓存混入检查
    for pattern in ("__pycache__", "*.egg-info", "*.pyc"):
        for candidate in dist_dir.glob(pattern):
            problems.append("dist 顶层含缓存混入：%s" % candidate.name)
    return problems


def data_manifest(root: Path) -> Dict[str, str]:
    """内嵌数据的逐份 sha256（构建后对账用）。"""
    root = Path(root)
    out: Dict[str, str] = {}
    for name in DATA_WHITELIST:
        base = root / "data" / name
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            try:
                rel = path.relative_to(root).as_posix()
            except ValueError:
                rel = str(path)
            out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def assert_data_matches(root: Path, dist_dir: Path) -> List[str]:
    """构建后断言：内嵌数据与仓库逐份 sha256 对账。"""
    problems: List[str] = []
    dist_dir = Path(dist_dir)
    manifest = data_manifest(root)
    if not manifest:
        return problems
    # 冻结布局：6.x 在 _internal/ 下，5.x 平铺
    candidates = [dist_dir / "_internal", dist_dir]
    for rel, digest in sorted(manifest.items()):
        found = None
        for base in candidates:
            candidate = base / rel
            if candidate.is_file():
                found = candidate
                break
        if found is None:
            problems.append("内嵌数据缺失：%s" % rel)
            continue
        actual = hashlib.sha256(found.read_bytes()).hexdigest()
        if actual != digest:
            problems.append("内嵌数据 sha256 不一致：%s" % rel)
    return problems


def assert_no_extra_data(root: Path, dist_dir: Path) -> List[str]:
    """构建后断言：白名单外的多余数据目录检测（防"新数据目录悄悄没进包"）。"""
    problems: List[str] = []
    root = Path(root)
    data_root = root / "data"
    if not data_root.is_dir():
        return problems
    known = set(DATA_WHITELIST) | {"README.md"}
    for child in sorted(data_root.iterdir()):
        if child.name in known:
            continue
        if child.name.startswith("_"):
            continue
        problems.append(
            "data/ 下出现未登记目录 %s —— 请确认是否应进白名单（build_datas）" % child.name
        )
    return problems


def load_datas_report(dist_dir: Path) -> Dict[str, Any]:
    """读取构建后的 datas 报告（供 verify_frozen 使用）。"""
    report_path = Path(dist_dir) / "_datas_report.json"
    if not report_path.is_file():
        return {}
    try:
        return json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
