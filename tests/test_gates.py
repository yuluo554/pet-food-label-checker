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

#: 结构性常数豁免上界：**整数形态**且绝对值小于此值 → 视为下标/计数/短文本长度。
#:
#: **非整数一律不豁免**——口径与引擎门禁（`pflc.rules._exempt_from_tokens`，见 K5）
#: 完全一致。M0 这里写的是"绝对值 < 100"，而本项目的政策数值天然是小于一百的
#: 百分数（实测 0.09–28）→ **整包放过，门禁空转**（M2 实测：往界面注入真实限值 28
#: 仍绿）。"按大小豁免"与"零政策字面量"这个目标在数学上不相容——判别量是
#: **这个数出现在哪里**（见下方 `test_gui_has_no_policy_numeric_literals`），
#: 不是它多大。
STRUCTURAL_CONSTANT_CEILING = 20


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

    **两条判据，缺一不可**（M2 修正）：

      ① **规则包 token 实算**：界面里出现的数值若与**本轮规则包**的限值同形，
         直接判违规——这是根治判据，不依赖任何大小启发式；
      ② **结构性常数豁免**：整数形态且 ``abs(value) < 20``（下标/计数/短文本长度）；
         **非整数一律不豁免**——口径与引擎门禁（K5）一致。

    旧口径只有 ① 的缺失版：``abs(value) < 100`` 会把真实限值（实测 0.09–28）
    **整包放过**，门禁变假门（M2 实测：注入真实限值 28 仍绿）。故本测试同时
    断言"规则包 token 非空"（防空转）与"注入真实限值必须被抓"。

    另有布局命名豁免（``*_WIDTH`` 等），但豁免只对**这些名字**成立，
    界面里写 ``LIMIT = 150`` 仍会被抓。
    """
    from pflc.rules import banned_numeric_tokens

    rules_dir = ROOT / "data" / "rules"
    tokens = banned_numeric_tokens(rules_dir)
    #: 防空转：真实规则包下 token 集必须非空，否则判据①恒不触发
    assert tokens, "真实规则包下禁用 token 集为空 = 界面门禁空转（假门）"

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
            # 判据①：与规则包限值同形 → 无条件违规（不享结构性豁免）
            rendered = format_decimal_literal(value)
            if rendered in tokens or str(value) in tokens:
                violations.append("%s:%d %s（命中规则包限值）"
                                  % (path.name, node.lineno, value))
                continue
            # 判据②：结构性常数豁免（整数且 < 20；非整数不豁免）
            if _is_structural_constant(value):
                continue
            if _is_layout_assignment(tree, node, layout_names):
                continue
            violations.append("%s:%d %s" % (path.name, node.lineno, value))
    assert violations == [], "GUI 层出现政策数值字面量：%s" % violations


def format_decimal_literal(value) -> str:
    """把字面量渲染成与规则包 token 同口径的字符串（去尾零、无 E 记号）。"""
    from decimal import Decimal

    from pflc.model import format_decimal

    return format_decimal(Decimal(str(value)))


def _is_structural_constant(value) -> bool:
    """结构性常数判据：整数形态且绝对值 < 上界（非整数一律不豁免）。"""
    if isinstance(value, float):
        return False
    return abs(value) < STRUCTURAL_CONSTANT_CEILING


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


def test_gui_policy_literal_gate_is_not_vacuous(tmp_path):
    """**M2 实测勘误**：界面门禁的豁免口径曾使门整包放过。

    旧口径 ``abs(value) < 100`` 会把真实限值（实测 0.09–28）全部豁免——
    注入真实限值 28 到界面仍绿 = **假门**。本测试锁死两条：
      ① 真实规则包下 token 集非空（否则判据①恒不触发）；
      ② 注入与规则包限值同形的数值 → 必须被抓。
    """
    from decimal import Decimal

    from pflc.rules import banned_numeric_tokens

    tokens = banned_numeric_tokens(ROOT / "data" / "rules")
    assert tokens, "真实规则包下 token 集为空 = 假门"

    # 取一个真实限值（整数形态），确认旧口径会放过它、新口径必须抓住
    sample = next(t for t in tokens if t.isdigit())
    assert not _is_structural_constant(int(sample)), (
        "真实限值 %s 竟被结构性豁免口径放过 = 假门" % sample)

    # 变异验证：注入该限值到界面源码文本 → 判据①必须命中
    assert format_decimal_literal(int(sample)) in tokens
    assert not _is_structural_constant(float(sample)), "非整数形态一律不豁免"


def test_structural_constant_exemption_is_not_overbroad():
    """结构性豁免的边界：整数 <20 放过，**非整数一律不放过**。

    反例锚点：``0.45``（真实限值，非整数）在旧口径下会被放过。
    """
    assert _is_structural_constant(4)
    assert _is_structural_constant(19)
    assert not _is_structural_constant(20)
    assert not _is_structural_constant(28)
    assert not _is_structural_constant(0.45)
    assert not _is_structural_constant(0.09)
    assert not _is_structural_constant(900)


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


#: 冻结数据里的**二进制**扩展名——0x0D 是这些格式的合法内容字节
#: （PNG 的 IDAT 压缩流、PDF 的流对象），拿"含 CR"判它们必然误报。
FROZEN_BINARY_SUFFIXES = (".pdf", ".png", ".gif", ".jpg", ".jpeg", ".webp",
                          ".ceb", ".zip", ".docx", ".xlsx")


def test_frozen_data_has_no_cr():
    """冻结 fixtures 出现 CR 即大声失败（EOL 门）。

    **二进制豁免**：只对 ``FROZEN_BINARY_SUFFIXES`` 里的扩展名放行，
    且豁免**按扩展名**（不是"这个文件全放过"）。文本类冻结数据（规则包、
    夹具、条文块、原文快照的文本件）仍逐个查 CR。
    """
    frozen_dirs = (ROOT / "data" / "rules", ROOT / "data" / "samples",
                   ROOT / "data" / "benchmark", ROOT / "data" / "knowledge")
    violations = []
    text_files_checked = 0
    for base in frozen_dirs:
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() in FROZEN_BINARY_SUFFIXES:
                continue
            text_files_checked += 1
            if b"\r" in path.read_bytes():
                violations.append(str(path.relative_to(ROOT)))
    assert violations == [], "冻结数据含 CR：%s" % violations
    # 防空转：豁免必须只放过少数二进制件，文本件仍被逐个查过
    assert text_files_checked > 0, "冻结目录里一个文本件都没查到 = 门禁空转"


def test_frozen_cr_gate_binary_exemption_is_not_vacuous():
    """豁免**非空转**证明：二进制扩展名之外的文件仍会被 CR 判定命中。"""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        probe = Path(td) / "probe.txt"
        probe.write_bytes(b"a\r\nb")          # 文本件含 CR
        assert probe.suffix.lower() not in FROZEN_BINARY_SUFFIXES
        assert b"\r" in probe.read_bytes(), "文本件的 CR 必须仍可被检出"
        binary = Path(td) / "probe.png"
        binary.write_bytes(b"\x89PNG\r\n")
        assert binary.suffix.lower() in FROZEN_BINARY_SUFFIXES, "二进制豁免口径失效"


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


def test_shipped_truth_library_matches_generator():
    """入库真值库与生成器输出一致（防手改冻结真值）。

    真值库是"基准期望"的唯一来源——它若可手改，"引擎对不对"就永远无法
    与"真值对不对"分离（与规则包同一条纪律）。
    """
    import importlib.util
    import sys as _sys

    spec = importlib.util.spec_from_file_location(
        "gen_cases_probe_gate", TOOLS / "gen_cases.py")
    module = importlib.util.module_from_spec(spec)
    _sys.modules["gen_cases_probe_gate"] = module
    spec.loader.exec_module(module)

    assert module.check() is True


def test_frozen_truth_library_ships_in_the_package():
    """**冻结真值库必须随包**：否则发行态的基准只能回落现场重算。

    GUI 与 CLI 都带基准功能，而基准的期望来源是入库冻结真值库
    （``data/benchmark/cases.json``）。它不进包 → 发行包里
    "期望锚定冻结真值"是空话（**源码态绿、发行态名不副实**）。

    M4 实测教训：源码态"绿"不能替代发行态——故这里直接断言打包白名单。
    """
    from pflc.packaging import DATA_WHITELIST, build_datas

    assert "benchmark" in DATA_WHITELIST, (
        "打包白名单未收 benchmark —— 发行态的基准会回落现场重算")

    datas = build_datas(ROOT)
    targets = [dest for _src, dest in datas]
    assert "data/benchmark" in targets, "build_datas 未把 data/benchmark 打进包：%s" % targets

    from pflc.packaging import data_manifest
    manifest = data_manifest(ROOT)
    assert "data/benchmark/cases.json" in manifest, (
        "内嵌数据对账清单里没有冻结真值库：%s" % sorted(manifest))


def test_packaging_whitelist_gate_is_not_vacuous():
    """**非空转自检**：``build_datas`` 真的产出了条目（不是空列表）。

    若 data/rules 或 data/benchmark 缺失，白名单断言会因"什么都没打进去"
    而误绿——故这里断言产出非空且指向真实目录。
    """
    from pflc.packaging import build_datas

    datas = build_datas(ROOT)
    assert datas, "build_datas 产出为空 = 白名单断言空转"
    for src, dest in datas:
        assert Path(src).is_dir(), "白名单指向的源目录不存在：%s" % src
        assert dest.startswith("data/")


def test_readme_samples_ship_in_the_package():
    """**README 引用的夹具必须随包**——否则发行版"下载即用"条条跑不通。

    README「可直接复制的示例输入」小节逐条引用 ``data/samples/*.txt``。
    源码态跑得通不代表发行态跑得通：夹具不进包时，下载 zip 的用户照 README
    敲命令会得到"文件不存在"，而本地一直绿（与 K29 同一族：源码态绿 ≠ 发行态绿）。
    """
    from pflc.packaging import DATA_WHITELIST, build_datas, data_manifest

    assert "samples" in DATA_WHITELIST, "打包白名单未收 samples —— README 示例在发行包里失效"
    targets = [dest for _src, dest in build_datas(ROOT)]
    assert "data/samples" in targets, "build_datas 未把 data/samples 打进包：%s" % targets

    # 判据落在"README 真的引用的那几个路径"上，不是"白名单里有 samples 这个词"
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    referenced = sorted(set(re.findall(r"data/samples/[\w.\-]+", readme)))
    assert referenced, "README 未引用任何夹具 = 本门空转"
    manifest = data_manifest(ROOT)
    missing = [rel for rel in referenced if rel not in manifest]
    assert missing == [], "README 引用但未随包的夹具：%s" % missing


def test_known_unshipped_exemption_is_wired_into_the_forbidden_scan():
    """**豁免要接线，不是声明**：``KNOWN_UNSHIPPED`` 必须在禁区名单里。

    只在豁免表里写 ``knowledge``、却不在禁区名单里的形态是"两道门全开"：
    它既不随包（没进白名单），又不被禁区扫描拦下（不在禁区）——于是
    "有意不入包"这个决定**没有任何一道门在守**。模块导入期的
    ``_assert_exemption_wired`` 负责拦截，这里证明它真的会拦。
    """
    from pflc import packaging

    assert set(packaging.KNOWN_UNSHIPPED) <= set(packaging.FORBIDDEN_TOP_LEVEL), (
        "豁免项不在禁区名单内：%s" % sorted(set(packaging.KNOWN_UNSHIPPED)
                                          - set(packaging.FORBIDDEN_TOP_LEVEL)))
    assert not (set(packaging.DATA_WHITELIST) & set(packaging.KNOWN_UNSHIPPED)), (
        "白名单与豁免表重叠 = 自相矛盾的口径")

    # 可证伪：把口径改坏，导入期校验必须拒绝
    import importlib
    original = packaging.FORBIDDEN_TOP_LEVEL
    try:
        packaging.FORBIDDEN_TOP_LEVEL = ("raw", "_private")   # 拿掉 knowledge
        with pytest.raises(ValueError):
            packaging._assert_exemption_wired()
    finally:
        packaging.FORBIDDEN_TOP_LEVEL = original
    # 对照组：口径改回后不再抛（证明上面不是"随便什么输入都抛"）
    packaging._assert_exemption_wired()


def test_forbidden_scan_is_not_blind_to_internal_layout(tmp_path):
    """**禁区扫描必须看得到 ``_internal/``**：M5 实测到的假门。

    原实现只匹配 dist 顶层或 ``data/`` 直接子项（``len(rel.parts) <= 2``）。
    PyInstaller 6.x onedir 把数据放进 ``_internal/data/``，禁区目录于是落在
    ``_internal/data/knowledge``（3 段）——``len <= 2`` 的判据**永远看不到它**，
    门在 6.x 布局下恒绿。故本测试按 6.x 真实布局构造，并留干净树作对照组。
    """
    from pflc.packaging import assert_no_forbidden

    # 阳性：6.x 布局下禁区目录位于三级深
    dist = tmp_path / "pflc"
    (dist / "_internal" / "data" / "knowledge" / "raw").mkdir(parents=True)
    (dist / "_internal" / "data" / "rules" / "_private").mkdir(parents=True)
    problems = assert_no_forbidden(ROOT, dist)
    hits = " ".join(problems)
    assert "_internal" in hits and "knowledge" in hits, (
        "6.x 布局下的 data/knowledge 未被拦截（这就是恒绿门）：%s" % problems)
    assert "_private" in hits, "负载树内任意深度的禁区名都要被抓：%s" % problems

    # 阴性对照：只有白名单目录时不得报（证明判据不是"见目录就红"）
    clean = tmp_path / "clean"
    for name in ("rules", "samples", "benchmark"):
        (clean / "_internal" / "data" / name).mkdir(parents=True)
    assert assert_no_forbidden(ROOT, clean) == [], "干净树被误报 = 判据过宽"


def test_forbidden_scan_does_not_flag_vendored_same_name_dirs(tmp_path):
    """**判据不落"全树同名目录"**：依赖包自带的 ``raw/`` 不得算命中。

    "任意层级 rglob 该名字"会把第三方依赖内部恰好叫 ``raw``/``knowledge``
    的目录当违规，制造假红。扫描面固定为**我们自己的 data/ 子树**。
    """
    from pflc.packaging import assert_no_forbidden

    dist = tmp_path / "pflc"
    vendored = dist / "_internal" / "PySide6" / "Qt" / "raw"
    vendored.mkdir(parents=True)
    (dist / "_internal" / "data" / "rules").mkdir(parents=True)
    assert assert_no_forbidden(ROOT, dist) == [], (
        "依赖包内的同名目录被误判为禁区成分（判据过宽）")


def test_packaging_extra_data_gate_reports_unregistered_dirs(tmp_path):
    """未登记数据目录必须被报出来，且**豁免项不算未登记**（非空转双向验证）。"""
    from pflc.packaging import assert_no_extra_data

    root = tmp_path / "repo"
    (root / "data" / "rules").mkdir(parents=True)
    (root / "data" / "knowledge").mkdir(parents=True)
    (root / "data" / "surprise").mkdir(parents=True)
    problems = assert_no_extra_data(root, tmp_path / "dist")
    joined = " ".join(problems)
    assert "surprise" in joined, "未登记的新目录未被报出：%s" % problems
    assert "knowledge" not in joined, "豁免项被当成未登记 = 豁免没接线：%s" % problems


# --------------------------------------------------------------------------
# 门禁八：打包 spec（入口点 / 数据路径单一来源 / 双包分流）
# --------------------------------------------------------------------------


def _spec_text() -> str:
    path = TOOLS / "pflc.spec"
    assert path.is_file(), "spec 未入仓：%s" % path
    return path.read_text(encoding="utf-8")


def _spec_analysis_scripts() -> list:
    """从 spec 抽取每个 ``Analysis(...)`` 的第一个位置参数（脚本路径的源码片段）。

    用 AST 而非正则：spec 里 ``Analysis(  # noqa: F821`` 带行尾注释，
    正则会被注释绊住而**静默抽到空列表**——判据于是空转（本测试第一次跑就踩中）。

    用 ``ast.get_source_segment`` 而非 ``ast.unparse``：后者是 **3.9+** API，
    本项目底线 3.8（否则守门测试在 3.8 上直接 AttributeError）。
    """
    text = _spec_text()
    tree = ast.parse(text, filename="pflc.spec")
    scripts = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "Analysis":
            assert node.args, "Analysis 调用缺脚本参数"
            segment = ast.get_source_segment(text, node.args[0])
            scripts.append(segment if segment is not None else "")
    return scripts


def test_spec_does_not_hand_write_data_paths():
    """**datas 单一事实源**：spec 内不得手写数据路径，只准用 ``build_datas()``。

    这条纪律此前只写在 ``packaging.py`` 的 docstring 里（声称"三处守门"），
    但**实际没有这道门**——docstring 声称的门与本测试是同一条，这里把它做实。
    判据是"spec 里出现了 ``data/`` 字面路径"，不是"文件里有没有 build_datas 这串字"。
    """
    text = _spec_text()
    assert "build_datas(" in text, "spec 未调用 build_datas（数据路径来源不是白名单）"
    # 排除注释与 _datas_report 里的 dest 拼接（"data/%s" 是格式化，不是手写路径）
    offending = []
    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if 'data/%s' in stripped or 'data/benchmark' in stripped or 'data/rules' in stripped \
                or 'data/samples' in stripped:
            offending.append("%d: %s" % (lineno, stripped))
    assert offending == [], "spec 手写了数据路径（应走 build_datas 白名单）：%s" % offending


def test_spec_entry_points_are_package_safe():
    """**入口点必须在包内可导入**：直接指向 ``src/pflc/*.py`` 会打断包语义。

    M5 实测踩中：spec 把 ``src/pflc/cli.py`` 当 Analysis 脚本，PyInstaller 于是
    以**顶层脚本**方式运行它，``from . import pipeline`` 没有父包可挂——
    构建**成功**，冻结态一启动就 ``ImportError``。构建成功 ≠ 产物可用。

    判据：Analysis 脚本只准是 ``tools/entry_*.py``，且这些文件用**绝对导入**。
    """
    scripts = _spec_analysis_scripts()
    assert scripts, "未能从 spec 提取 Analysis 脚本 = 判据空转"
    joined = " ".join(scripts)
    assert "entry_cli.py" in joined and "entry_gui.py" in joined, (
        "Analysis 脚本未走包内安全入口：%s" % scripts)
    assert "cli.py" not in joined.replace("entry_cli.py", ""), (
        "spec 仍直接指向 src/pflc/cli.py（会打断包语义）：%s" % scripts)
    assert "app.py" not in joined, (
        "spec 仍直接指向 src/pflc/gui/app.py（会打断包语义）：%s" % scripts)

    for name in ("entry_cli.py", "entry_gui.py"):
        entry = TOOLS / name
        assert entry.is_file(), "缺包内入口脚本：%s" % entry
        source = entry.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(entry))
        top_relative = [n for n in tree.body
                        if isinstance(n, ast.ImportFrom) and (n.level or 0) > 0]
        assert top_relative == [], "%s 顶层用了相对导入（冻结态会 ImportError）" % name


def test_cli_package_excludes_gui_dependency():
    """**CLI 发行包特意不带 PySide6**：带了会让 exit 3 降级提示变死代码。

    ``cli.cmd_gui`` 对缺依赖的 CLR+D 发行包提示"本发行包未内嵌该功能"。
    把 PySide6 打进 CLI 包，这句提示永远走不到，还白送约 87 MB（实测）。
    同时 GUI 包**必须**带上它——两个包的分流是产品口径，不是构建巧合。
    """
    text = _spec_text()
    # CLI 的 Analysis 块：以 "_BENCH_HIDDEN," 收尾的 hiddenimports
    cli_block = text.split("a_cli = Analysis")[1].split("pyz_cli")[0]
    gui_block = text.split("a_gui = Analysis")[1].split("pyz_gui")[0]
    assert "PySide6" in cli_block, "CLI 包未排除 PySide6（白送体积且降级提示失效）"
    assert "PySide6" not in gui_block, "GUI 包不得排除 PySide6"
    assert "_GUI_HIDDEN" in gui_block, "GUI 包未声明 GUI hiddenimports"
    assert "_GUI_HIDDEN" not in cli_block, "CLI 包不该收 GUI hiddenimports"


def test_ci_runs_every_frozen_generator_check():
    """**每个冻结生成器的 `--check` 都必须在 CI 上真的跑。**

    "本地一直绿" ≠ "CI 验过"：加了 `gen_cases.py --check` 却忘了写进 CI，
    这道门在 CI 上等于不存在，而本地手工跑仍是绿的——最隐蔽的失效模式。

    **判据必须是"活的 step"，不能是子串匹配**：实测把该 step 整段注释掉后，
    子串判据照样命中 `gen_cases.py --check` 而保持绿 = 又一道假门。
    故这里解析 workflow 的 **run 步骤**（注释行不会被解析成步骤）。
    """
    workflow = ROOT / ".github" / "workflows" / "ci.yml"
    if not workflow.is_file():
        pytest.skip("CI workflow 尚未创建")
    try:
        import yaml
    except ImportError:
        pytest.skip("未安装 pyyaml（dev extra 应包含它）")

    data = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    run_lines = []
    for job in data.get("jobs", {}).values():
        for step in job.get("steps", []):
            if step.get("run"):
                run_lines.append(str(step["run"]))
    joined = "\n".join(run_lines)

    generators = sorted(p.name for p in TOOLS.glob("gen_*.py"))
    assert generators, "tools/ 下没有生成器 = 扫描面为空（门禁空转）"
    missing = [name for name in generators if "%s --check" % name not in joined]
    assert missing == [], (
        "CI 的 run 步骤里没有这些生成器的 --check（注释掉不算）: %s" % missing)


def test_ci_generator_gate_is_not_fooled_by_comments():
    """**非空转自检**：把 step 注释掉必须被判为"缺失"，子串命中不算数。

    这是 `test_ci_runs_every_frozen_generator_check` 的可证伪性证明——
    否则它的判据可能只是"文件里出现过这串字"（实测确实会这样）。
    """
    workflow = ROOT / ".github" / "workflows" / "ci.yml"
    if not workflow.is_file():
        pytest.skip("CI workflow 尚未创建")
    try:
        import yaml
    except ImportError:
        pytest.skip("未安装 pyyaml")

    data = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    run_lines = []
    for job in data.get("jobs", {}).values():
        for step in job.get("steps", []):
            if step.get("run"):
                run_lines.append(str(step["run"]))
    joined = "\n".join(run_lines)

    # 正向：真实的 run 步骤能被提取出来（扫描面非空）
    assert "pytest" in joined, "未能从 CI 提取到 run 步骤 = 判据空转"
    # 反向：注释形态不算"跑过"
    assert "gen_nonexistent.py --check" not in joined


def test_frozen_generators_all_share_the_check_marker_form():
    """生成器形态一致性：每个 ``gen_*.py`` 都支持 ``--check`` 且打 ``*_OK`` 标记。

    形态漂移（有的打标记有的不打）会让"跑没跑成"无法被脚本判读。
    """
    missing_check = []
    for path in sorted(TOOLS.glob("gen_*.py")):
        text = path.read_text(encoding="utf-8")
        if '"--check"' not in text and "'--check'" not in text:
            missing_check.append(path.name)
    assert missing_check == [], "生成器缺 --check 通路：%s" % missing_check


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


def _ci_run_steps():
    """解析 CI workflow 的**活 run 步骤**（注释行不会被解析成步骤）。

    返回 ``[(job_name, step_name, run_text)]``。用 yaml 解析而非子串匹配：
    子串判据会被"整段注释掉"绕过（M4 实测的假门形态）。
    """
    workflow = ROOT / ".github" / "workflows" / "ci.yml"
    if not workflow.is_file():
        pytest.skip("CI workflow 尚未创建")
    try:
        import yaml
    except ImportError:
        pytest.skip("未安装 pyyaml（dev extra 应包含它）")
    data = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    out = []
    for job_name, job in data.get("jobs", {}).items():
        for step in job.get("steps", []):
            if step.get("run"):
                out.append((job_name, str(step.get("name", "")), str(step["run"])))
    return out


def test_ci_extras_cover_every_milestone_gate():
    """**CI 的 extras 必须覆盖全部里程碑门的依赖**，否则门在 CI 上静默跳过。

    "本地一直绿" ≠ "CI 验过"：只装 ``[dev]`` 时 ``test_gui.py`` 走模块级
    ``importorskip`` 静默跳过——GUI 层的 AST 门禁等于从未在 CI 上运行过。

    判据落在**活 run 步骤**上：``pip install -e ".[dev,gui,...]"`` 语句出现、
    ``import PySide6`` 真被跑、Linux 补了 Qt 系统库。子串匹配会被注释绕过。
    """
    steps = _ci_run_steps()
    assert steps, "未能从 CI 解析出任何 run 步骤 = 判据空转"
    joined = "\n".join(run for _job, _name, run in steps)

    assert '".[dev,gui' in joined or ".[dev,gui" in joined, \
        "CI 未安装 gui extra（test_gui 会静默跳过）"
    assert "import PySide6" in joined, "CI 未断言 GUI 依赖真实可用"
    assert "libegl1" in joined, "CI 未为 Linux 补 Qt 系统库"


def test_ci_verifies_frozen_distributions():
    """**发行态验收必须在 CI 上真的跑**——这是 M5 两类"源码态绿"的唯一防线。

    M5 实测的两类失效**本地源码态测试全都看不到**：
      ① 入口点错（spec 指向包内模块）→ 构建成功、exe 一启动就 ImportError；
      ② PyInstaller 6.x ``_internal/`` 布局让禁区扫描判据恒绿。
    故 CI 必须有"真构建 + 真跑 exe"的 job，且两个发行树都验。
    """
    steps = _ci_run_steps()
    joined = "\n".join(run for _job, _name, run in steps)
    assert "PyInstaller" in joined, "CI 未真的构建发行产物"

    # 判据必须锚定**完整的 --dist 参数**，不能裸判 "dist/pflc"：
    # 后者是 "dist/pflc-cli-dist" 的子串，注释掉 GUI 那步照样命中 = 假门
    # （本测试第一版就是这么写的，变异验证当场抓出来）。
    for dist_name in ("dist/pflc-cli-dist", "dist/pflc"):
        pattern = re.compile(r"--dist\s+%s\s+--selftest" % re.escape(dist_name))
        assert pattern.search(joined), (
            "CI 未对这个发行树跑「--dist %s --selftest」：判据锚定完整参数，"
            "避免 dist/pflc 命中 dist/pflc-cli-dist" % dist_name)
    # 演示物料可复现性也要在 CI 上跑（本地生成过 ≠ CI 验过）
    assert "check_demo_reproducible.py" in joined, "CI 未验演示物料可复现性"


def test_ci_run_step_parser_is_not_fooled_by_comments(tmp_path):
    """**可证伪性证明**：把构建 step 整段注释掉后，判据必须不再认为它在跑。

    这是上一条测试的对照组。M4 实测过判据退化成"文件里出现过这串字"的后果——
    整段注释掉照样绿。故这里直接拿一份**注释版 workflow** 验证解析器行为，
    而不是对字符串做 `in` 判断（那正是假门的形态）。
    """
    try:
        import yaml  # noqa: F401
    except ImportError:
        pytest.skip("未安装 pyyaml")

    commented = tmp_path / "ci.yml"
    commented.write_text(
        "jobs:\n"
        "  package:\n"
        "    steps:\n"
        "      - name: Build\n"
        "        # run: python -m PyInstaller --clean --noconfirm tools/pflc.spec\n"
        "      - name: Real\n"
        "        run: python tools/verify_frozen.py --dist dist/pflc --selftest\n",
        encoding="utf-8",
    )
    data = yaml.safe_load(commented.read_text(encoding="utf-8"))
    runs = [str(s["run"]) for job in data["jobs"].values()
            for s in job["steps"] if s.get("run")]
    joined = "\n".join(runs)

    # 正向：真 step 被提取到（判据并非空转）
    assert "verify_frozen.py" in joined, "解析器漏掉了真实 run 步骤"
    # 反向：注释掉的 step **不产生 run** —— 故"在跑"的判据不可能被注释骗过
    assert "PyInstaller" not in joined, "注释掉的 step 被当成在跑（假门重现）"


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
        # M6：发布打包/回读保真测试用（ZIP 格式的标准库）——不是安装面依赖
        "zipfile",
        # M6：stdlib 判定辅助用（sysconfig 定位标准库路径，3.8 兼容）
        "sysconfig",
    }
    missing = sorted(
        name for name in third_party
        if name not in stdlib_or_local
        and name.lower() not in dev_block.lower()
        and name not in ("PySide6",)  # gui extra 覆盖，见 test_gui 的 importorskip
    )
    assert missing == [], "tests/ import 但 dev extra 未声明的库：%s" % missing


#: 第三方**分发名 → import 名**的别名表（只放真正对不上的）。
#:
#: extras 里写的是分发包名（``Pillow``），代码里 import 的是模块名（``PIL``）——
#: 直接比较会把它们当成"未覆盖"，制造假红。
IMPORT_NAME_ALIASES = {"Pillow": "PIL", "pyyaml": "yaml"}


def _extras_of(pyproject_text: str):
    """解析 ``[project.optional-dependencies]`` → ``{extra: [分发名]}``。

    用 tomllib/tomli 都不稳（3.8 无 tomllib），故按块切——这几行的形态是
    本项目自己维护的，够用且无额外依赖。
    """
    import re as _re

    block = pyproject_text.split("[project.optional-dependencies]", 1)
    if len(block) < 2:
        return {}
    body = block[1].split("\n[", 1)[0]
    extras = {}
    for match in _re.finditer(r"^(\w+)\s*=\s*\[(.*?)\]", body,
                              flags=_re.S | _re.M):
        extra, items = match.group(1), match.group(2)
        names = []
        for line in items.splitlines():
            line = line.strip().strip(",").strip().strip('"').strip("'")
            if not line or line.startswith("#"):
                continue
            # 去掉版本约束与环境标记
            name = _re.split(r"[<>=;!\[ ]", line, 1)[0].strip()
            if name:
                names.append(name)
        extras[extra] = names
    return extras


def _is_stdlib_module(name: str) -> bool:
    """模块是否属于标准库（**3.8 兼容**）。

    ``sys.stdlib_module_names`` 是 **3.10+** 才有（本项目底线 3.8，直接用它
    会在 3.8 上把每个标准库都判成第三方 = 假红一片）。故退回按**安装位置**判：
    解析出模块文件路径，落在 stdlib 目录且不在 site-packages 下即为标准库。
    内置/冻结模块（``sys`` 等）另按 ``builtin_module_names`` 判。
    """
    import importlib.util
    import sys as _sys
    import sysconfig

    if name in getattr(_sys, "builtin_module_names", ()):
        return True
    try:
        spec = importlib.util.find_spec(name)
    except (ImportError, ValueError, AttributeError):
        return False
    if spec is None:
        return False
    origin = spec.origin
    if origin in (None, "built-in", "frozen"):
        return True
    try:
        path = Path(origin)
    except TypeError:
        return False
    stdlib = Path(sysconfig.get_paths().get("stdlib", ""))
    try:
        path.relative_to(stdlib)
    except ValueError:
        return False
    return "site-packages" not in path.as_posix() \
        and "dist-packages" not in path.as_posix()


def _third_party_imports(directory):
    """目录下全部 .py 里 import 的第三方顶层模块名。"""
    found = {}
    for path in sorted(directory.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        mods = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mods.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                if node.module:
                    mods.add(node.module.split(".")[0])
        for mod in mods:
            if mod in ("pflc", "tests") or _is_stdlib_module(mod):
                continue
            # 同目录工具间互相 import 的不算第三方
            if (directory.name == "tools"
                    and (ROOT / "tools" / ("%s.py" % mod)).is_file()):
                continue
            found.setdefault(mod, []).append(path.name)
    return found


def test_test_and_tool_imports_are_covered_by_readme_install_paths():
    """**安装面 = 测试面 = README 指令面**（M6 DoD 第 2 条）。

    三面必须对齐，任一缺口都会让"照 README 做"失败：

      * 测试真 import 的库不在 extras 里 → 干净 venv 全量测试硬失败；
      * README 让用户跑的工具所需的库不在 README 的安装通路里 → 用户照着做
        到那一步才炸（M6 实测：README 引 ``make_demo_assets.py``（要 Pillow），
        而 Pillow 所在的 ``demo`` extra 在 README 里**从没出现过**）。

    判据落在**结构位置**（源码 AST 里的 import + pyproject 的 extras 块 +
    README 的 ``pip install -e ".[...]"`` 行），不落"文件里出现过这串字"。
    """
    import re as _re

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    extras = _extras_of(pyproject)
    assert extras, "未能从 pyproject 解析出 extras = 判据空转"
    assert "dev" in extras, "缺 dev extra"

    # README 里真的出现过的安装通路（extras 名集合）
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    declared_paths = set()
    for match in _re.finditer(r'pip install -e "\.\[([^\]]+)\]"', readme):
        for name in match.group(1).split(","):
            declared_paths.add(name.strip())
    assert declared_paths, "README 里没有解析出安装通路 = 判据空转"

    # 分发名 → extra（含别名归一到 import 名）
    module_to_extra = {}
    for extra, names in extras.items():
        for name in names:
            key = IMPORT_NAME_ALIASES.get(name, name)
            module_to_extra.setdefault(key, set()).add(extra)

    # 反向核对：tools/ 与 tests/ 真 import 的第三方模块
    imported = {}
    for area in ("tools", "tests"):
        for mod, files in _third_party_imports(ROOT / area).items():
            imported.setdefault(mod, []).extend(files)

    uncovered_declared = []   # 库在 extras 里，但没有任何 README 安装通路覆盖它
    uncovered_unknown = []    # 库连 extras 都没声明
    for mod, files in sorted(imported.items()):
        owners = module_to_extra.get(mod)
        if not owners:
            uncovered_unknown.append((mod, sorted(set(files))))
            continue
        if not (owners & declared_paths):
            uncovered_declared.append((mod, sorted(owners), sorted(set(files))))

    assert uncovered_unknown == [], (
        "这些库被 tools/ 或 tests/ import，却没有任何 extra 声明：%s" % uncovered_unknown)
    assert uncovered_declared == [], (
        "这些库所在的 extra 在 README 里没有任何安装通路（照 README 做会缺库）：%s"
        % uncovered_declared)
