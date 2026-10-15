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

#: 随包的数据目录白名单（**只收运行必需 + README 明示可跑**）。
#:
#: ``benchmark`` 必须入包：GUI 与 CLI 都带基准功能，而基准的期望来源是
#: **入库冻结真值库**（``data/benchmark/cases.json``）。不带它，冻结态只能
#: 回落现场重算——"期望锚定冻结真值"在发行包里就成了空话（源码态绿、
#: 发行态名不副实，正是本项目明令避免的失效模式）。
#:
#: ``samples`` 入包：README 的"可直接复制的示例输入"小节逐条引用了这五个
#: 路径。发行包里若没有它们，README 的示例在**下载即用**场景下条条跑不通
#: （源码态绿、发行态红）——与 benchmark 同一条纪律。
DATA_WHITELIST: Tuple[str, ...] = (
    "rules",
    "benchmark",
    "samples",
)

#: **有意不入包**的 data/ 子目录，每个都要写清理由。
#:
#: 这不是"忽略列表"——豁免必须能被审计，且**必须同时在禁区名单里**：
#: 只在豁免里、不在禁区里的条目 = "放任它进包且无人检查"（`_assert_exemption_wired`
#: 在导入期就把这个口子堵死）。
#:
#: ``knowledge``：版权敏感的原文快照与转录素材，是**核对用素材而非运行时依赖**
#: （``knowledge_raw_dir()`` 只在离线核对通路被调用）。
KNOWN_UNSHIPPED: Tuple[str, ...] = ("knowledge",)

#: 禁区成分（**相对数据根匹配**，不等价于"任意层级"——见 ``_forbidden_hits``）。
#:
#: 匹配点固定为 dist 内的"我们自己的工作根"，而不是全树任意层级：后者会把
#: 第三方依赖自带的同名目录（如某包内的 ``raw/``）当命中，制造假红。
#: 反过来"只在 dist 顶层找"也是错的——PyInstaller 6.x 把数据放在
#: ``_internal/data/`` 下，禁区目录在顶层根本不存在，门会**永远绿**。
FORBIDDEN_TOP_LEVEL = ("knowledge", "raw", "_private")


def _assert_exemption_wired() -> None:
    """白名单与豁免表的口径一致性（导入期即校验）。

    * 两侧**不得重叠**：同一个目录既"随包"又"有意不入包"是自相矛盾的口径；
    * 豁免项**必须**在禁区名单里：否则"豁免"实为"放任"——它既不随包
      （没进白名单）又不被禁区扫描拦下（不在禁区），等于两道门全开。
    """
    overlap = set(DATA_WHITELIST) & set(KNOWN_UNSHIPPED)
    if overlap:
        raise ValueError(
            "DATA_WHITELIST 与 KNOWN_UNSHIPPED 重叠：%s" % sorted(overlap))
    unwired = set(KNOWN_UNSHIPPED) - set(FORBIDDEN_TOP_LEVEL)
    if unwired:
        raise ValueError(
            "豁免项不在禁区名单内（豁免=放任，必须补进 FORBIDDEN_TOP_LEVEL）：%s"
            % sorted(unwired))


_assert_exemption_wired()


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


def _payload_roots(dist_dir: Path) -> List[Path]:
    """onedir 里"我们自己的负载根"。

    PyInstaller 6.x 把 datas 放进 ``<_internal>``，5.x 平铺在 exe 目录下。
    两条布局都要查——**只查顶层正是 M5 实测到的假门**：6.x 下禁区目录
    位于 ``_internal/data/``，顶层压根不存在，门会永远绿。
    """
    roots = []
    for candidate in (dist_dir / "_internal", dist_dir):
        if candidate.is_dir():
            roots.append(candidate)
    return roots


def assert_no_forbidden(root: Path, dist_dir: Path) -> List[str]:
    """构建后断言：dist 内**不再出现禁区成分**。

    判据落在**我们自己的负载树**上，而不是全树 rglob 该名字（后者会把依赖包
    自带的同名目录当命中，制造假红）。两个层面都查：

    * ``<负载根>/data/**`` 子树内任何目录不得叫禁区名——覆盖
      ``data/knowledge``、``data/rules/_private``、``data/rules/raw`` 等
      **任意嵌套深度**；
    * 负载根本身不得直接叫禁区名（散落在 exe 目录旁的残留）。

    深度是必须的：PyInstaller 6.x 把数据放进 ``_internal/``，禁区目录于是
    位于 ``_internal/data/...``——只在顶层找的门在 6.x 下**永远绿**（M5 实测）。
    """
    problems: List[str] = []
    dist_dir = Path(dist_dir)
    if not dist_dir.is_dir():
        return ["dist 目录不存在：%s" % dist_dir]

    forbidden = set(FORBIDDEN_TOP_LEVEL)
    roots = _payload_roots(dist_dir)
    if not roots:
        problems.append("dist 内未找到负载根（既无 _internal/ 也无数据目录）：%s" % dist_dir)
    for base in roots:
        data_root = base / "data"
        if data_root.is_dir():
            for path in sorted(data_root.rglob("*")):
                if path.is_dir() and path.name in forbidden:
                    problems.append("dist 含禁区成分：%s" % path.relative_to(dist_dir))
        for name in FORBIDDEN_TOP_LEVEL:
            candidate = base / name
            if candidate.exists():
                problems.append("dist 含禁区成分：%s" % candidate.relative_to(dist_dir))
        for pattern in ("__pycache__", "*.egg-info", "*.pyc"):
            for candidate in base.glob(pattern):
                problems.append("dist 负载根含缓存混入：%s"
                                % candidate.relative_to(dist_dir))
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
    """构建后断言：白名单外的多余数据目录检测（防"新数据目录悄悄没进包"）。

    **已知豁免**（``KNOWN_UNSHIPPED``）与白名单是两件事：白名单 = "随包"，
    豁免 = "确认过，有意不随包"。两者都要显式登记，未登记的目录一律报出来——
    这条断言的价值就在于"任何新数据目录都必须被有意识地决定一次"。
    """
    problems: List[str] = []
    root = Path(root)
    data_root = root / "data"
    if not data_root.is_dir():
        return problems
    known = set(DATA_WHITELIST) | set(KNOWN_UNSHIPPED) | {"README.md"}
    for child in sorted(data_root.iterdir()):
        if child.name in known:
            continue
        if child.name.startswith("_"):
            continue
        problems.append(
            "data/ 下出现未登记目录 %s —— 请确认是否应进白名单（build_datas）"
            "或登记为有意不随包（KNOWN_UNSHIPPED）" % child.name
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
