"""安装面守门：**非 editable 安装**必须"装完能用"（DEC2 = A）。

**为什么这道门必须存在**：本仓全部既有验证（CI 三个 job、`plan/RELEASE-M6.md`、
`plan/HANDOFF-FINAL.md`）用的都是 ``pip install -e .``。editable 安装下
``data_paths.repo_root()`` 命中仓库根，``data/`` 正常——于是"数据没随包"
这件事**在任何一道门里都看不见**。

实测过的失效形态（修复前）：

* ``pip wheel .`` 产出 23 条目、**data 条目 0 个**；
* 干净 venv 装完后 ``data_dir()`` = ``<venv>/data``（不存在）；
* ``pflc diagnostics`` → "manifest：缺失 / 共 0 条"，exit 1；
* ``pflc bench`` → "配置错误：…thresholds 节缺失"，exit 2；
* 而 ``pflc check`` → "整体结论：未评估" 却 **exit 0** ——
  脚本会把"什么都没查"当成"通过"（与 DEC3 同一条口径缺口）。

**判据落在规则条数（45）上，不落在"退出码 0"上**：D1 的形态正是
"能跑、但读不到数据"——只断言退出码会漏掉它。同理断言 wheel 里
**有数据条目**、且 ``data_dir()`` 落在 site-packages 内（不是 ``<venv>/data``）。

**负控已验**（2026-10-20，本机）：删掉 ``pyproject.toml`` 的
``[tool.setuptools.package-data]`` 后重跑本文件 →
``test_wheel_carries_data_files`` 与 ``test_installed_package_reads_data``
双双变红（详见 ``update/03-执行记录.md``）。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Dict, List, Tuple

import pytest

ROOT = Path(__file__).resolve().parent.parent

#: 随包数据在 wheel 里的条目数（rules 4 + benchmark 1 + samples 5）。
#: 钉死数量而不是 ``> 0``：少一个文件同样是缺陷，且这条数在数据台账里有据。
EXPECTED_DATA_ENTRIES = 10

#: 规则总数（label 8 + nutrition 32 + claim 5）—— diagnostics 的实跑口径。
EXPECTED_RULE_TOTAL = 45
EXPECTED_DIMENSION_TOTALS = {"label": 8, "nutrition": 32, "claim": 5}


def _venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _clean_env() -> Dict[str, str]:
    """剥离会把"仓库源码"或"仓库数据"带进被测环境的变量。

    ``PYTHONPATH`` 尤其关键：留着它，新 venv 里的 ``import pflc`` 会命中
    **仓库源码**而不是装进去的 wheel，于是这道门验的是 editable 形态——
    正是它要防的那个盲区。``PFLC_DATA_DIR`` 同理（它会把数据目录指回仓库）。
    """
    env = {k: v for k, v in os.environ.items()
           if k.upper() not in ("PYTHONPATH", "PFLC_DATA_DIR")}
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _run(argv: List, cwd: Path) -> Tuple[int, str]:
    """跑子进程并**显式取退出码**（不走 shell 管道，见 plan/07 的坑）。"""
    proc = subprocess.run(
        [str(a) for a in argv],
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
        env=_clean_env(),
        timeout=900,
    )
    return proc.returncode, proc.stdout or ""


@pytest.fixture(scope="module")
def built_wheel(tmp_path_factory) -> Path:
    """按仓库现状打一个 wheel（**非 editable**，且不做构建隔离）。

    两处刻意的选择，都是为了让这道门**真的**在验当前源码：

    * **从干净副本构建**，不在仓库树里就地打：``pip wheel .`` 会复用
      ``build/`` 与 ``src/*.egg-info/SOURCES.txt`` 里的陈旧清单——实测删掉
      ``[tool.setuptools.package-data]`` 后，因陈旧清单仍列着数据文件，
      wheel 照样带 10 个数据条目，**门禁假绿**。故先把构建所需文件复制到
      临时目录（排除 ``__pycache__`` / ``*.egg-info`` / ``build``）再打。
    * **不做构建隔离**（``--no-build-isolation``）：构建隔离会去索引下载
      setuptools——那会让"安装面门禁"依赖网络，红起来分不清是代码坏了
      还是网络抖了。故 ``dev`` extra 里带了 setuptools 与 wheel。
    """
    try:
        import setuptools  # noqa: F401
    except ImportError as exc:      # pragma: no cover - 环境不完整即硬失败
        pytest.fail("打 wheel 需要 setuptools（应在 dev extra 里）：%s" % exc)

    base = tmp_path_factory.mktemp("wheel-build")
    _copy_build_tree(base)
    out = tmp_path_factory.mktemp("wheel-out")
    code, output = _run(
        [sys.executable, "-m", "pip", "wheel", ".", "--no-deps",
         "--no-build-isolation", "-w", out],
        cwd=base,
    )
    wheels = sorted(out.glob("*.whl"))
    assert code == 0 and wheels, "打 wheel 失败（exit %d）：\n%s" % (code, output[-2000:])
    return wheels[0]


def _copy_build_tree(target: Path) -> None:
    """把构建 wheel 所需的文件复制到 ``target``（**不带构建残留**）。

    只取 ``pyproject.toml`` / ``README.md`` / ``LICENSE`` 与 ``src/``：
    wheel 的输入面就这些。``__pycache__``、``*.egg-info``、``build`` 一律不带——
    它们正是"陈旧清单让门禁假绿"的来源。
    """
    import shutil

    for name in ("pyproject.toml", "README.md", "LICENSE"):
        src = ROOT / name
        if src.is_file():
            shutil.copy2(src, target / name)

    def _ignore(directory: str, names: List[str]) -> set:
        return {n for n in names
                if n in ("__pycache__", "build") or n.endswith(".egg-info")
                or n.endswith(".pyc")}

    shutil.copytree(ROOT / "src", target / "src", ignore=_ignore)


@pytest.fixture(scope="module")
def installed(built_wheel: Path, tmp_path_factory):
    """干净 venv + 装 wheel；返回 ``(python, data_dir, work_dir)``。

    全程在 **中立目录**（tmp）里跑：在仓库树内跑会让 ``repo_root()``
    命中仓库根，验的就不是安装态了。
    """
    base = tmp_path_factory.mktemp("install")
    venv_dir = base / "venv"
    code, output = _run([sys.executable, "-m", "venv", venv_dir], cwd=base)
    assert code == 0, "建 venv 失败（exit %d）：\n%s" % (code, output[-2000:])

    py = _venv_python(venv_dir)
    assert py.is_file(), "venv 内未找到解释器：%s" % py

    # 运行时依赖为空（dependencies = []）→ --no-index 可离线装
    code, output = _run([py, "-m", "pip", "install", "--no-index", built_wheel],
                        cwd=base)
    assert code == 0, "装 wheel 失败（exit %d）：\n%s" % (code, output[-2000:])

    probe = (
        "import json\n"
        "from pflc.data_paths import data_dir, package_data_dir\n"
        "print('PROBE=' + json.dumps({'data_dir': str(data_dir()),\n"
        "  'is_dir': data_dir().is_dir(),\n"
        "  'package_data_dir': str(package_data_dir()),\n"
        "  'file': __import__('pflc').__file__}))\n"
    )
    code, output = _run([py, "-c", probe], cwd=base)
    assert code == 0, "探测 data_dir 失败（exit %d）：\n%s" % (code, output[-2000:])
    line = [ln for ln in output.splitlines() if ln.startswith("PROBE=")][-1]
    info = json.loads(line[len("PROBE="):])

    work = base / "neutral"
    work.mkdir()
    return {"python": py, "info": info, "work": work, "base": base}


def test_wheel_carries_data_files(built_wheel: Path):
    """wheel 必须带**随包数据**：这是 D1 的直接判据。

    修复前实测：23 条目、``data entries: 0``、顶层只有 ``pflc`` 与 dist-info。
    """
    names = zipfile.ZipFile(built_wheel).namelist()
    data_entries = [n for n in names if "/data/" in n]
    assert len(data_entries) == EXPECTED_DATA_ENTRIES, (
        "wheel 内随包数据条目 %d 个（期望 %d）：%s"
        % (len(data_entries), EXPECTED_DATA_ENTRIES, sorted(data_entries)))
    # 判据落在**具体文件**上：四个规则包 + 真值库 + 夹具
    for needle in ("pflc/data/rules/manifest.json",
                   "pflc/data/rules/ruleset-nutrition.json",
                   "pflc/data/benchmark/cases.json",
                   "pflc/data/samples/label-demo-ok.txt"):
        assert needle in names, "wheel 缺 %s（数据没随包）" % needle
    # knowledge 有意不入包（KNOWN_UNSHIPPED）——它出现在 wheel 里是口径事故
    assert not [n for n in names if "/data/knowledge/" in n], (
        "wheel 混入了 knowledge（版权敏感、有意不随包）")


def test_installed_package_reads_data(installed):
    """装完的包必须**真的读到随包数据**（而不是回落到 ``<venv>/data``）。

    修复前实测：``data_dir()`` = ``<venv>/data``、``is_dir() = False``。
    """
    info = installed["info"]
    assert info["is_dir"] is True, (
        "安装态 data_dir() 不存在：%s（这正是 D1 的形态）" % info["data_dir"])
    assert "site-packages" in info["data_dir"], (
        "data_dir() 未落在 site-packages 内：%s" % info["data_dir"])
    assert info["data_dir"] == info["package_data_dir"], (
        "安装态 data_dir() 未走包内分支（%s != %s）"
        % (info["data_dir"], info["package_data_dir"]))
    # 装进去的确实是 wheel，不是仓库源码
    assert "site-packages" in info["file"], (
        "被测解释器 import 到的是仓库源码而不是装进去的包：%s" % info["file"])


def test_installed_diagnostics_reports_45_rules(installed):
    """安装态 ``diagnostics``：exit 0 **且**规则总数 45（8/32/5）。

    只断言退出码会漏掉 D1 的形态——它能跑，只是读不到数据。
    """
    py, work = installed["python"], installed["work"]
    code, output = _run([py, "-m", "pflc.cli", "diagnostics"], cwd=work)
    assert code == 0, "安装态 diagnostics exit %d（期望 0）：\n%s" % (code, output[-2000:])
    assert "manifest：已登记" in output, "安装态读不到 manifest：\n%s" % output[-2000:]
    totals = {dim: int(n) for dim, n in re.findall(r"\[(\w+)\] 共 (\d+) 条", output)}
    assert totals == EXPECTED_DIMENSION_TOTALS, (
        "安装态规则条数 %s（期望 %s）—— 退出码 0 不等于读到了数据"
        % (totals, EXPECTED_DIMENSION_TOTALS))
    assert sum(totals.values()) == EXPECTED_RULE_TOTAL


def test_installed_bench_passes_on_frozen_truth(installed):
    """安装态 ``bench``：exit 0 + 四套件 ``[PASS]`` + ``truth_source=frozen``。

    最后一项防的是"发行态回落现场重算"：真值库没随包时它会悄悄变成
    ``regenerated``，源码态绿、发行态名不副实。
    """
    py, work = installed["python"], installed["work"]
    code, output = _run([py, "-m", "pflc.cli", "bench"], cwd=work)
    assert code == 0, "安装态 bench exit %d（期望 0）：\n%s" % (code, output[-2000:])
    assert output.count("[PASS]") == 4, (
        "安装态 bench 通过套件数 %d（期望 4）：\n%s"
        % (output.count("[PASS]"), output[-2000:]))
    assert "truth_source = frozen" in output, (
        "安装态 bench 的期望来源不是冻结真值库（回落现场重算了）：\n%s"
        % output[-2000:])


def test_installed_cli_verdicts_match_source_state(installed):
    """安装态的**结论**必须与源码态一致：合规样例 exit 0 / 缺项样例 exit 1。

    这条防的是"能跑、但判定走空"：零生效规则时 ``check`` 输出
    "整体结论：未评估"——若退出码仍是 0，脚本会把"没查过"读成"通过"
    （DEC3 = B 之后它必须非 0；本测试锁死安装态的这一行为）。
    """
    py, work = installed["python"], installed["work"]
    samples = Path(installed["info"]["data_dir"]) / "samples"
    assert samples.is_dir(), "安装态找不到包内夹具：%s" % samples
    for path in sorted(samples.glob("*.txt")):
        (work / path.name).write_bytes(path.read_bytes())

    code, output = _run([py, "-m", "pflc.cli", "check", work / "label-demo-ok.txt"],
                        cwd=work)
    assert code == 0, "安装态合规样例 exit %d（期望 0）：\n%s" % (code, output[-2000:])
    assert "整体结论：符合" in output, "安装态合规样例结论异常：\n%s" % output[-2000:]

    code, output = _run([py, "-m", "pflc.cli", "check", work / "label-demo-missing.txt"],
                        cwd=work)
    assert code == 1, "安装态缺项样例 exit %d（期望 1）：\n%s" % (code, output[-2000:])
    assert "整体结论：不符合" in output, "安装态缺项样例结论异常：\n%s" % output[-2000:]
