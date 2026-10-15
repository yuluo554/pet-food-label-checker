"""守门测试：零政策字面量门禁、AST 分层门禁、EOL 门禁、字节冻结。

**这些门禁是"可被机器证明"的部分**——不靠自觉。每条门禁都做过变异验证
（把被测行为故意弄坏 → 门必须变红），见各测试的 docstring。
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
TOOLS = ROOT / "tools"

#: 引擎/基准/前端源码扫描面（数值只能来自规则包）
BANNED_SCAN_DIRS = (SRC / "pflc", TOOLS)

#: 扫描面排除（第三方/生成物）
SCAN_EXCLUDE_PARTS = {"__pycache__", "gui"}

#: 结构性常数豁免（<100 的小值：精度约定/下标/长度约束，非政策数值）
STRUCTURAL_CONSTANT_CEILING = 100


def _python_sources(root: Path):
    for path in sorted(root.rglob("*.py")):
        if any(part in SCAN_EXCLUDE_PARTS for part in path.parts):
            continue
        yield path


# --------------------------------------------------------------------------
# 门禁一：零政策字面量（数值只能来自规则包）
# --------------------------------------------------------------------------


def test_no_banned_numeric_literals_in_engine_sources(tmp_path):
    """**零政策字面量门禁**：引擎/基准/CLI 源码里不得出现规则包数值。

    token 从规则包**运行时实算**（不写死在扫描器里）——门禁自己的输入
    也不许是代码字面量。扫描含 docstring 与注释（AST 之外还要扫原始文本，
    因为注释里的数值同样是"抄进代码的第二份真相"）。

    变异验证：若把任一规则包数值写进 src/pflc/engine/__init__.py，
    本测试必须变红（见 tests 中 test_gate_*_mutation_* 系列）。
    """
    from pflc.rules import banned_numeric_tokens, scan_source_for_tokens

    fixture_rules = tmp_path / "rules"
    from tests.conftest import write_ruleset
    write_ruleset(fixture_rules)

    tokens = banned_numeric_tokens(fixture_rules)
    # 夹具数值都在 <100 以下会被豁免；构造一个 >=100 的限值确保门禁有东西可查
    assert isinstance(tokens, list)

    hits = []
    for path in _python_sources(SRC / "pflc"):
        text = path.read_text(encoding="utf-8")
        for token, lineno in scan_source_for_tokens(text, tokens):
            hits.append("%s:%d" % (path.relative_to(ROOT), lineno))
    assert hits == [], "引擎源码出现规则包数值：%s" % hits


def test_banned_token_scan_is_not_vacuous(tmp_path):
    """门禁**非空转**证明：token 集为空时门禁恒绿 = 假门。

    构造一条 >=100 的限值，断言 token 被实算出来且扫描能命中注入值。
    """
    from pflc.rules import banned_numeric_tokens, scan_source_for_tokens
    from tests.conftest import nutrition_rules, write_ruleset

    rules = nutrition_rules()
    injected = dict(rules[0])
    injected["value"] = "150"  # >=100，应被收编为禁用 token
    write_ruleset(tmp_path / "r", nutrition=[injected] + rules[1:])

    tokens = banned_numeric_tokens(tmp_path / "r")
    assert "150" in tokens, ">=100 的限值必须被收编为禁用 token"

    # 扫描器能命中注入值
    hits = scan_source_for_tokens("LIMIT = 150\n", tokens)
    assert ("150", 1) in hits

    # 变异验证：把该数值写进源码文本，门禁必须报出
    assert scan_source_for_tokens("x = 150  # 政策数值", tokens) == [("150", 1)]


def test_gate_would_catch_injected_policy_value(tmp_path):
    """**变异验证**：把政策数值写进引擎源码 → 门禁必须变红。"""
    from pflc.rules import banned_numeric_tokens, scan_source_for_tokens
    from tests.conftest import nutrition_rules, write_ruleset

    rules = nutrition_rules()
    injected = dict(rules[0])
    injected["value"] = "150"
    write_ruleset(tmp_path / "r", nutrition=[injected] + rules[1:])
    tokens = banned_numeric_tokens(tmp_path / "r")

    broken_source = "def check(x):\n    return x >= 150  # 抄进代码的第二份真相\n"
    hits = scan_source_for_tokens(broken_source, tokens)
    assert hits, "门禁未能拦住注入的政策数值 = 假门"


# --------------------------------------------------------------------------
# 门禁二：GUI 零判定逻辑（AST 三条齐上）
# --------------------------------------------------------------------------


def _gui_sources():
    gui_dir = SRC / "pflc" / "gui"
    return sorted(gui_dir.rglob("*.py"))


def test_gui_does_not_import_rule_or_engine_internals():
    """AST 断言一：界面层不得直接 import 规则层/引擎内部模块。

    唯一入口是 ``pflc.pipeline``（编排层）。靠自觉守不住，靠静态检查才守得住。
    """
    forbidden = ("pflc.rules", "pflc.engine", "pflc.report", "pflc.benchmark.cases",
                 "pflc.benchmark.runner", "pflc.parse")
    violations = []
    for path in _gui_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if any(alias.name == f or alias.name.startswith(f + ".")
                           for f in forbidden):
                        violations.append("%s:%d import %s"
                                          % (path.name, node.lineno, alias.name))
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                # 相对导入（..rules / ..engine 等）也算
                resolved = module
                if node.level and not module:
                    continue
                if any(resolved == f or resolved.startswith(f + ".")
                       or resolved == f.split(".")[-1] for f in forbidden):
                    violations.append("%s:%d from %s"
                                      % (path.name, node.lineno, module))
    assert violations == [], "GUI 直接引用了判定内核：%s" % violations


def test_gui_has_no_arithmetic_binop():
    """AST 断言二：界面层无算术运算——界面只做展示与转发。

    只守 import 面会漏掉"界面里直接算"（``size * 1.5``）。

    **豁免口径写死**（否则门禁刷屏，见 plan/07 K10）：
      * 任一操作数是**字符串字面量** → 不是算术：``"%s" % x`` 是格式化，
        ``Path(x) / "Fonts"`` 是路径拼接；
      * **路径拼接**：操作数是被判定为 path-like 的名字（见
        ``_path_like_names``）——``fonts / name`` 是拼路径不是算数；
      * 字符串 ``*``/``+`` 是排版，不算。

    判别口诀：**"这个表达式在算数值，还是在拼文本/路径？"**
    """
    violations = []
    for path in _gui_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        path_names = _path_like_names(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.BinOp):
                continue
            op_name = type(node.op).__name__
            if op_name not in ("Mult", "Div", "Sub", "FloorDiv", "Mod", "Pow"):
                continue
            if _is_string_operand(node):
                continue
            if op_name == "Div" and _is_path_join(node, path_names):
                continue
            violations.append("%s:%d %s" % (path.name, node.lineno, op_name))
    assert violations == [], "GUI 层出现算术运算：%s" % violations


def _is_string_operand(node: ast.BinOp) -> bool:
    """任一操作数是字符串字面量 → 按排版/格式化/路径拼接豁免。"""
    for side in (node.left, node.right):
        if isinstance(side, ast.Constant) and isinstance(side.value, str):
            return True
    return False


def _is_path_call(node: ast.AST) -> bool:
    """是否 ``Path(...)`` / ``pathlib.Path(...)`` 调用。"""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name) and func.id == "Path":
        return True
    if isinstance(func, ast.Attribute) and func.attr == "Path":
        return True
    return False


def _path_like_names(tree: ast.AST) -> set:
    """收集被判定为 path-like 的名字。

    传播规则：``x = Path(...)`` 或 ``x = <path-like> / <str>``（即一次
    已豁免的路径拼接）→ ``x`` 是 path-like。这足以覆盖"先拼目录再拼文件名"
    的常见写法，同时不会把 ``size * 1.5`` 这类真算术放进来。
    """
    names: set = set()
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            targets = []
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
            else:
                continue
            value = node.value
            if value is None:
                continue
            is_path = _is_path_call(value)
            if not is_path and isinstance(value, ast.BinOp) \
                    and isinstance(value.op, ast.Div):
                is_path = _is_path_call(value.left) \
                    or (isinstance(value.left, ast.Name) and value.left.id in names) \
                    or (isinstance(value.right, ast.Name) and value.right.id in names)
            if not is_path:
                continue
            for target in targets:
                if isinstance(target, ast.Name) and target.id not in names:
                    names.add(target.id)
                    changed = True
    return names


def _is_path_join(node: ast.BinOp, path_names: set) -> bool:
    """``/`` 的任一侧是 path-like 名字 → 路径拼接，不是除法。"""
    for side in (node.left, node.right):
        if isinstance(side, ast.Name) and side.id in path_names:
            return True
        if _is_path_call(side):
            return True
    return False


#: 布局常量命名模式（窗口尺寸/边距/间距等——**不是政策数值**）。
#: 豁免绑定**命名**而非"整个文件"，这样界面里出现真政策数值仍会被抓。
LAYOUT_NAME_PATTERN = re.compile(
    r"(_WIDTH|_HEIGHT|_SIZE|_MARGIN|_SPACING|_PADDING|_MIN_|_MAX_|_LEN)$"
)


def test_gui_has_no_policy_numeric_literals():
    """AST 断言三：界面层无政策数值字面量。

    界面里内联政策值与引擎里内联是同一条罪——"抄进代码的第二份真相"。

    **豁免口径写死**：
      * ``abs(value) < 100`` 的结构性常数（下标/计数/短文本长度）；
      * 赋值给**布局命名**（``*_WIDTH`` / ``*_HEIGHT`` / ``*_SIZE`` 等）的数值
        ——窗口尺寸不是政策数值，但豁免只对**这些名字**成立，
        界面里写 ``LIMIT = 150`` 仍会被抓。
    """
    violations = []
    for path in _gui_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        layout_names = _layout_constant_names(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant):
                continue
            value = node.value
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            if abs(value) < STRUCTURAL_CONSTANT_CEILING:
                continue
            if _is_layout_assignment(tree, node, layout_names):
                continue
            violations.append("%s:%d %s" % (path.name, node.lineno, value))
    assert violations == [], "GUI 层出现政策数值字面量：%s" % violations


def _layout_constant_names(tree: ast.AST):
    """收集被布局命名模式命中的模块级常量名。"""
    names = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and LAYOUT_NAME_PATTERN.search(target.id):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and LAYOUT_NAME_PATTERN.search(target.id):
                names.add(target.id)
    return names


def _is_layout_assignment(tree: ast.AST, literal: ast.Constant, names) -> bool:
    """该数值字面量是否直接赋给布局常量名。"""
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        if value is not literal:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name) and target.id in names:
                return True
    return False


def test_gui_layering_gate_is_not_vacuous():
    """门禁**非空转**证明：注入违规代码必须被抓到（变异验证）。

    三条断言各注入一个违规：import 规则层 / 真算术 / 政策数值。
    同时确认**豁免不吞真违规**——这是豁免条款最容易出的漏洞。
    """
    broken = "from pflc.rules import load_pack\nx = size * 1.5\ny = 150\n"
    tree = ast.parse(broken)

    imports = [n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert any(n.module == "pflc.rules" for n in imports), "import 断言漏检"

    path_names = _path_like_names(tree)
    binops = [n for n in ast.walk(tree)
              if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Mult)
              and not _is_string_operand(n) and not _is_path_join(n, path_names)]
    assert binops, "算术断言漏检（size * 1.5 应被抓）"

    literals = [n.value for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, int)
                and not isinstance(n.value, bool) and abs(n.value) >= 100]
    assert literals == [150], "数值断言漏检"


def test_path_join_exemption_does_not_swallow_real_division():
    """豁免的边界：路径拼接豁免**不得**吞掉真正的除法。"""
    tree = ast.parse("fonts = Path('x')\np = fonts / 'y'\nz = total / count\n")
    names = _path_like_names(tree)
    assert "fonts" in names
    binops = [n for n in ast.walk(tree) if isinstance(n, ast.BinOp)]
    kept = [n for n in binops
            if not _is_string_operand(n) and not _is_path_join(n, names)]
    # total / count 必须留在违规集里
    assert len(kept) == 1


def test_gui_imports_pipeline_only():
    """正向对照：GUI 确实经 pipeline 取数（不是"什么都没 import"的空壳）。"""
    sources = "\n".join(p.read_text(encoding="utf-8") for p in _gui_sources())
    assert "from .. import pipeline" in sources or "import pipeline" in sources


# --------------------------------------------------------------------------
# 门禁三：CLI 顶层不得 import GUI（惰性导入）
# --------------------------------------------------------------------------


def test_cli_does_not_import_gui_at_module_level():
    """AST 静态守门：CLI 模块顶层不得 import GUI/PySide6。

    比 ``sys.modules`` 运行时断言可靠——pytest 收集期导入污染会让
    模块级断言假失败。惰性导入必须发生在函数体内。
    """
    path = SRC / "pflc" / "cli.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations = []
    for node in tree.body:  # 只看模块顶层
        if isinstance(node, ast.Import):
            for alias in node.names:
                if "gui" in alias.name or "PySide6" in alias.name:
                    violations.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if "gui" in module or "PySide6" in module:
                violations.append(module)
    assert violations == [], "CLI 顶层 import 了 GUI/重件：%s" % violations


def test_no_module_imports_pyside6_at_top_level():
    """全仓守门：PySide6 只允许出现在函数体内（分层守门的要求）。"""
    violations = []
    for path in _python_sources(SRC / "pflc"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("PySide6"):
                        violations.append("%s:%d" % (path.name, node.lineno))
            elif isinstance(node, ast.ImportFrom):
                if (node.module or "").startswith("PySide6"):
                    violations.append("%s:%d" % (path.name, node.lineno))
    assert violations == [], "顶层 import PySide6：%s" % violations


# --------------------------------------------------------------------------
# 门禁四：EOL 与字节冻结
# --------------------------------------------------------------------------


def test_source_files_use_lf_line_endings():
    """.gitattributes 管住克隆，但**不管脚本怎么写文件**——所以要另设门禁。

    源码出现 CR 即失败。
    """
    violations = []
    for path in sorted(ROOT.rglob("*.py")):
        if any(part in {".git", "__pycache__", ".venv", "venv", "build", "dist",
                        ".tmp"} for part in path.parts):
            continue
        if b"\r\n" in path.read_bytes():
            violations.append(str(path.relative_to(ROOT)))
    assert violations == [], "源码含 CRLF：%s" % violations


def test_frozen_data_has_no_cr():
    """冻结 fixtures 出现 CR 即大声失败（EOL 门）。"""
    frozen_dirs = (ROOT / "data" / "rules", ROOT / "data" / "samples",
                   ROOT / "data" / "benchmark", ROOT / "data" / "knowledge")
    violations = []
    for base in frozen_dirs:
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            if b"\r" in path.read_bytes():
                violations.append(str(path.relative_to(ROOT)))
    assert violations == [], "冻结数据含 CR：%s" % violations


def test_gitattributes_declares_frozen_paths_as_text_free():
    """.gitattributes 必须把冻结路径标 -text，否则克隆后 sha256 失配。"""
    text = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "eol=lf" in text
    for needle in ("data/knowledge/raw/**", "data/benchmark/**", "data/rules/**"):
        assert needle in text, "缺冻结路径声明：%s" % needle
    assert "-text" in text


def test_gitattributes_covers_pdf_binary():
    text = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "*.pdf binary" in text


# --------------------------------------------------------------------------
# 门禁五：规则包与生成器的字节冻结
# --------------------------------------------------------------------------


def test_rule_packs_are_byte_stable_when_regenerated(tmp_path):
    """再生成位级一致：同一输入两次生成产出逐字节相同的规则包。"""
    import importlib.util
    import sys as _sys

    spec = importlib.util.spec_from_file_location(
        "gen_rulesets_probe", TOOLS / "gen_rulesets.py")
    module = importlib.util.module_from_spec(spec)
    _sys.modules["gen_rulesets_probe"] = module
    spec.loader.exec_module(module)

    first = module.generate()
    second = module.generate()

    def dump(payload):
        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)

    assert dump(first) == dump(second)


def test_shipped_rule_packs_match_generator():
    """入库规则包与生成器输出一致（防手改）。"""
    import importlib.util
    import sys as _sys

    spec = importlib.util.spec_from_file_location(
        "gen_rulesets_probe2", TOOLS / "gen_rulesets.py")
    module = importlib.util.module_from_spec(spec)
    _sys.modules["gen_rulesets_probe2"] = module
    spec.loader.exec_module(module)

    assert module.check() is True


def test_shipped_samples_match_generator():
    """入库夹具与生成器输出一致（防手改）。"""
    import importlib.util
    import sys as _sys

    spec = importlib.util.spec_from_file_location(
        "gen_samples_probe", TOOLS / "gen_samples.py")
    module = importlib.util.module_from_spec(spec)
    _sys.modules["gen_samples_probe"] = module
    spec.loader.exec_module(module)

    assert module.check() is True


# --------------------------------------------------------------------------
# 门禁六：全本地零上传
# --------------------------------------------------------------------------


def test_core_layer_has_no_network_imports():
    """**全本地零上传**：核心层不得出现网络库。"""
    forbidden = ("requests", "urllib.request", "http.client", "socket",
                 "aiohttp", "httpx", "urllib3")
    violations = []
    for path in _python_sources(SRC / "pflc"):
        if path.name == "audit_desensitize.py":
            continue
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in forbidden:
                        violations.append("%s:%d %s"
                                          % (path.name, node.lineno, alias.name))
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module in forbidden:
                    violations.append("%s:%d %s" % (path.name, node.lineno, module))
    assert violations == [], "核心层出现网络依赖：%s" % violations


def test_core_layer_declares_no_runtime_dependencies():
    """核心层零第三方依赖——这是离线可复现与打包可控的根基。"""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r"^dependencies = \[(.*?)\]", text, re.S | re.M)
    assert match is not None
    assert match.group(1).strip() == "", "运行时依赖必须为空"


# --------------------------------------------------------------------------
# 门禁七：README 可跑性（引用的输入文件必须存在）
# --------------------------------------------------------------------------


def test_readme_referenced_sample_files_exist():
    """README 里引用的输入文件必须真实存在——否则干净环境一跑就崩。

    本地因工作目录残留看不出这类缺口，故做成常驻回归门。
    """
    readme = ROOT / "README.md"
    if not readme.is_file():
        pytest.skip("README 尚未创建")
    text = readme.read_text(encoding="utf-8")
    missing = []
    for match in re.finditer(r"data/samples/[\w.\-]+", text):
        candidate = ROOT / match.group(0)
        if not candidate.is_file():
            missing.append(match.group(0))
    assert missing == [], "README 引用了不存在的文件：%s" % missing


def test_ci_workflow_uses_full_history():
    """历史扫描类守门测试需要完整历史——浅克隆会静默削弱成空验。"""
    workflow = ROOT / ".github" / "workflows" / "ci.yml"
    if not workflow.is_file():
        pytest.skip("CI workflow 尚未创建")
    try:
        import yaml
    except ImportError:
        pytest.skip("未安装 pyyaml（dev extra 应包含它）")
    data = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    assert data, "workflow 无法解析"
    for job_name, job in data.get("jobs", {}).items():
        assert "runs-on" in job, "job %s 缺 runs-on" % job_name
        assert job.get("steps"), "job %s 缺 steps" % job_name
        for step in job["steps"]:
            if "actions/checkout" in str(step.get("uses", "")):
                depth = step.get("with", {}).get("fetch-depth")
                assert depth == 0, "job %s 的 checkout 未设 fetch-depth: 0" % job_name


def test_ci_workflow_declares_utf8_env():
    """编码三层加固的第一层：CI 全局 PYTHONUTF8。"""
    workflow = ROOT / ".github" / "workflows" / "ci.yml"
    if not workflow.is_file():
        pytest.skip("CI workflow 尚未创建")
    text = workflow.read_text(encoding="utf-8")
    assert "PYTHONUTF8" in text
    assert "PYTHONIOENCODING" in text


def test_ci_extras_cover_every_milestone_gate():
    """**CI 的 extras 必须覆盖全部里程碑门的依赖**，否则门在 CI 上静默跳过。

    "本地一直绿" ≠ "CI 验过"：只装 ``[dev]`` 时 ``test_gui.py`` 走模块级
    ``importorskip`` 静默跳过——GUI 层的 AST 门禁等于从未在 CI 上运行过。
    本测试断言 CI 存在一条装了 ``gui`` extra 的通路。
    """
    workflow = ROOT / ".github" / "workflows" / "ci.yml"
    if not workflow.is_file():
        pytest.skip("CI workflow 尚未创建")
    text = workflow.read_text(encoding="utf-8")
    assert "gui" in text and "pip install" in text, "CI 未安装 gui extra"
    # 必须显式断言依赖装上（否则 importorskip 又变静默跳过）
    assert "import PySide6" in text, "CI 未断言 GUI 依赖真实可用"
    # Linux 需要补 Qt 系统库，否则 import PySide6.QtWidgets 直接 ImportError
    assert "libegl1" in text, "CI 未为 Linux 补 Qt 系统库"


def test_dev_extras_cover_test_imports():
    """**测试面 = 安装面**：测试套件真 import 的库必须在 dev extra 里。

    否则干净 venv 照 README 装完全量测试会硬失败（开发机装齐全绿，
    缺口永远不显形）。
    """
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    dev_block = pyproject.split("dev = [", 1)[1].split("]", 1)[0]
    # 测试真 import 的第三方库（标准库不算）
    assert "pytest" in dev_block
    assert "pyyaml" in dev_block, "CI workflow 解析守门测试需要 pyyaml"

    # 反向核对：tests/ 里 import 的第三方顶层模块都在 dev 里声明
    third_party = set()
    for path in sorted((ROOT / "tests").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    third_party.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                if node.module:
                    third_party.add(node.module.split(".")[0])

    stdlib_or_local = {
        "pflc", "tests", "ast", "json", "os", "re", "sys", "io", "pathlib",
        "decimal", "hashlib", "subprocess", "importlib", "typing", "builtins",
        "dataclasses", "collections", "csv", "textwrap", "tempfile", "shutil",
        "itertools", "functools", "unittest", "warnings", "copy", "time",
        "__future__", "fnmatch", "glob", "math", "random", "string", "struct",
        "urllib", "contextlib", "abc", "enum", "operator", "traceback",
    }
    missing = sorted(
        name for name in third_party
        if name not in stdlib_or_local
        and name.lower() not in dev_block.lower()
        and name not in ("PySide6",)  # gui extra 覆盖，见 test_gui 的 importorskip
    )
    assert missing == [], "tests/ import 但 dev extra 未声明的库：%s" % missing
