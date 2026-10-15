# HANDOFF-M5：桌面交付（GUI + 打包 + 报告导出）

> 交接快照。上一棒 = M4（合成标签基准，已完成并验证）。
> **新对话怎么开**：`/goal 读取 "<项目绝对路径>\plan\HANDOFF-M5.md" 继续完成任务`
> （启动命令里的绝对路径由用户侧拼出；**库内一律只写相对路径** `plan/HANDOFF-M5.md`。）

---

## 一、当前进度（M0–M4 已完成并验证）

| 项 | 状态 |
|---|---|
| 规则包 | ✅ **45 条**（`label` 8 / `nutrition` 32 / `claim` 5），**43 `verified` + 2 `pending`** |
| 解析层 | ✅ FR-01 全覆盖（M2 收口） |
| 判定引擎 | ✅ 三类判定齐备（`presence` / `threshold` / `claim_support`）+ 双重门控 + 维度聚合 + 分派表结构性守门 |
| 基准 | ✅ **四套件全部达标**：detection 检出 12/12、误报 0.0 · overall 16/16 · boundary 60/60 · traceability 43/43 |
| **冻结真值库** | ✅ **入仓** `data/benchmark/cases.json`（16 用例）；基准**真的读它**（`truth_source=frozen`）；`gen_cases.py --check` 位级守门 |
| 覆盖登记 | ✅ 从真值库实算回填（label 3/8 · nutrition 4/32 · claim 3/5） |
| 测试 | ✅ **255 项**，Python 3.8.8 与 3.12.10 双解释器全绿 |
| 守门 | ✅ **六道 OK 标记门**：`TRANSCRIBE_OK` / `FROZEN_RULESET_OK` / **`FROZEN_CASES_OK`** / `FROZEN_SAMPLES_OK` / `DESSENSITIZE_AUDIT_OK`（HARD 0 / REVIEW 0）/ `SMOKE_CLI_OK` |
| 文档 | ✅ `plan/00`–`07` 已回填 M4 实录；`README.md` / `docs/技术报告.md` / `data/README.md` 同步 |

**M4 末态**：
`py -X utf8 -m pflc.cli diagnostics` → **exit 0**（label 8/8 · nutrition 30/32 · claim 5/5）；
`py -X utf8 -m pflc.cli bench` → **exit 0**（四套件达标，`truth_source=frozen`）；
`py -X utf8 tools/gen_cases.py --check` → **`FROZEN_CASES_OK`**；
`py -X utf8 -m pflc.cli check data/samples/label-demo-ok.txt` → **exit 0**。

### M4 本棒做了什么

**M4 的题眼是"做了 ≠ 记了 ≠ 可复核"**——上一棒转交的 5 条缺口**全部是"产物没入仓 / 台账没回填 / 指标没上文档 / 门没有探活"**，没有一条是"判定逻辑错"。故本棒不重写引擎，而是把每条落成**可核证的产物 + 常驻门**：

| M4 新增/改动 | 内容 |
|---|---|
| `tools/gen_cases.py`（新） | 真值库生成器：`--force` / `--check` + `FROZEN_CASES_OK` |
| `data/benchmark/cases.json`（新） | 冻结真值库 16 用例；sha256 `f2019de7…6811` |
| `runner._sample_cases()` | 改为**入库件优先**，返回 `(cases, truth_source)`；入库件与生成器不符 → `BenchConfigError`（exit 2） |
| `cases.load_cases()` | **载入即校验品牌白名单**（K18 的第二个实例） |
| `cases.coverage_from_cases()` | 覆盖登记**唯一来源**（从真值库实算） |
| `gen_rulesets.py` | 在 `generate()` 内**先由规则包生成真值库、再实算覆盖回填** |
| `packaging.py` | `DATA_WHITELIST` 收 `benchmark`（发行态才读得到冻结真值） |
| `tests/` | +24 条（231 → **255**），含 3 探活 / 2 组非空转 / 行级 README 守门 / CI-门机械对齐 |

**变异验证 7 处（含 1 个已知有效的对照组）**，其中 **2 处暴露出"假门"并当场改判据**（详见 §五）。

---

## 二、下一里程碑（M5）：桌面交付

**M5 目标**：GUI + exe 打包 + 报告导出。

`plan/06` 的 M5 DoD 有 9 条（末条 `plan/HANDOFF-M6.md` 是 M5 自身的出口门）。
**本棒对 M5 现状做了初测**（只登记事实，不替代 M5 收棒的逐条核对）：

| M5 DoD | 初测状态 |
|---|---|
| GUI 多页签、零判定逻辑（AST 三条齐上） | 🔶 **骨架已有**：`gui/app.py` 6 页签（导入/明细/… /基准/关于），AST 三条门禁**已有测试**（`test_gates.py` 三条 + 非空转 + 变异） |
| 编排上收成公开函数组 + 三方对账测试 | ✅ **已有**：`pipeline.py` 公开函数组；`tests/test_pipeline.py::test_three_way_reconciliation`（CLI stdout == pipeline 字段 == 报告章节）实测通过 |
| 报告双轨（md + csv）：单一渲染源 / 无外链 / 逐字节可复现 / 溯源硬约束 | 🔶 `report/__init__.py` 已实现（`report_sections` 单一渲染源 + `render_csv` 无外链断言 + `TraceabilityError` 拒导）；`test_repeated_calls_are_field_identical` 覆盖确定性；**M5 需在打包产物上复验** |
| PyInstaller onedir 双 exe + 构建后三断言 | ⬜ **未构建**。`tools/pflc.spec` 与 `packaging.py` 三断言已就绪；`py -3.12 -m PyInstaller --version` → **6.22.3**（可用） |
| 冻结态 `--selftest <out>` | 🔶 `cmd_selftest` 已实现（`frozen` + `数据目录在 exe 内` + `规则数 > 0`）；**未在真冻结态验过** |
| 中立目录 + `env -i` 跑 CLI 五连 + GUI 存活探针 | ⬜ `tools/verify_frozen.py` 有 `--selftest` 通路（含中立目录 + 剥离环境变量）；**GUI 存活探针待补** |
| 演示素材程序化产出（PNG + GIF 两次 sha256 一致） | 🔶 `tools/make_demo_assets.py` 已实现、M0 已留档两次 sha256 一致。**但物料是 M0 空规则包态渲染的**（页签数 6 与当前一致，实测 `TAB_TITLES` 6 项；内容过时——三页判定维度显示"零生效规则"）。`docs/demo/README.md` 已如实登记"物料落后于数据"，**M5 必须重生成**（填表→点击→出结果的真实判定态），并更新 sha256 留档 |
| 技术报告 `docs/技术报告.md` | ✅ 已存在，M4 已回填 §6.6/§6.9/§6.10/§十 |
| `plan/HANDOFF-M6.md` 已落盘并 commit | ⬜ M5 出口门 |

**M5 的关键风险不是"写界面"，而是"发行态名不副实"**——本项目已有的准备（三断言、冻结态自检、中立目录验收）都在防这件事。
**M4 刚踩到同一个形态**：源码态 `truth_source=frozen` 而发行态若无 `data/benchmark` 就会悄悄变成 `regenerated`——本棒已把 `benchmark` 收进 `DATA_WHITELIST` 修掉。**M5 打包时必须复核这一点真的生效**（构建后三断言里的"数据 sha256 对账"会覆盖它）。

---

## 三、M5 起始待办（按依赖顺序）

1. **打包前先跑一遍 `packaging.assert_no_extra_data` 的既有提示**：它当前会报 `data/samples` 与 `data/knowledge` 未登记。
   - `knowledge` 是**有意不入包**（版权敏感的原文快照，`.gitattributes` 已定），需要把它加进 `assert_no_extra_data` 的**已知豁免**（否则 M5 构建后断言必红）；
   - `samples` 是 README 演示输入，是否入包**要决定**（我倾向**入包**：README 的示例路径在发行版里应可用）。
   - **这不是 M4 的欠账**（M4 未改打包口径），但 **M5 一构建就会撞上**，故提前登记。
2. 构建 onedir 双 exe → 跑 `tools/verify_frozen.py --dist dist/pflc --selftest`（三断言 + 冻结态自检）。
3. 中立目录 + 剥离环境变量跑 CLI 五连；补 GUI 存活探针。
4. 重生成演示素材（**注意页签数与 M0 留档可能不同**），两次 sha256 一致。
5. 三方对账测试（CLI stdout == pipeline 直调 == 报告章节）——若已有，回填证据；若无，补上。
6. 回填 `plan/06` M5 DoD、`plan/00` M5 实录、`data/README.md` M5 末态快照；写 `plan/HANDOFF-M6.md`。

---

## 四、既定口径清单（K 清单，动了会打挂基准）

> 后续任何改数据/加类目/改接口的动作，**先对照本表，改完重跑基准确认不回退**。
> 完整版见 `plan/07-交付对标与决策记录.md` §四。**M4 新增 K29 / K30**。

| K | 口径 |
|---|---|
| K1 | 三态 `compliant`/`noncompliant`/`not_provided` + `skipped`/`unknown`；**无条件义务缺失 = noncompliant**；无适用项 → `not_assessed` |
| K2 | **双重门控**：`status`（数值）门控判定路径，`clause_status`（条款号）只管可证性 |
| K3 | 门控作用域三值 `label`/`nutrition`/`claim`，各只校验自己引用的条目 |
| K4 | 零生效维度不参与聚合 + `dimension_excluded` 原因码 |
| K5 | 数值口径一处定义；**零政策字面量门禁**扫 `src/pflc/`（含 GUI）与 `tools/`，含 docstring/注释；token **运行时实算**。豁免：整数且 < 20，**非整数一律不豁免**，且配非空转守门测试 |
| K5b | **数值基准**：GB/T 理化指标**以干物质计**，标签保证值是 as-fed → `basis=dry_matter` **先换算再比**；缺水分 → `unknown` + `basis_undetermined` |
| K5c | **数值渲染**：一律 `format_decimal()`；**禁 `str(Decimal.normalize())`** |
| K6 | 规则包冻结：禁手改，改走生成器；`--check` 位级一致 |
| K7 | 退出码三语义：`0` 达标 · `1` 未达标/检出不符合 · `2` 用法或未知名错误 · `3` 缺 GUI 依赖 |
| K8 | 溯源完整性硬约束：导出前断言"溯源行数 == 明细行数"且引用 id 可解析，不满足**拒导** |
| K9 | 报告双轨**单一渲染源** `report_sections()`；机读产物逐字节可复现、**禁活动外链** |
| K10 | GUI 零判定逻辑 AST 三条齐上（不 import 规则层 + 无 `BinOp` 算术 + **无政策数值字面量**）。**同一处豁免口径在引擎与界面两侧都要对齐** |
| K11 | 单件与批量共用 `check_card` 分派点 |
| K12 | 失败件 ≠ 违规：解析失败记 `scan_error`/`failed`，**不改退出码** |
| K13 | 两轮对账配对主键 = 稳定身份键（`file:<相对路径>`） |
| **K14** | 基准分样本驱动 + 规则驱动两层；**四套件探活齐备**；**期望锚定冻结真值库**（✅ M4 落实：入库件优先 + `truth_source` 标记） |
| K15 | 验收门槛随 manifest 下发（缺失 → exit 2，不回落代码默认值） |
| K16 | 空分母 `not_enabled=true` + notes 声明 + exit 1 |
| **K17** | 覆盖登记"总数/已核对数/采样数/清单"**双数** + "抽样覆盖非穷举"声明（✅ M4 从真值库实算回填；口径 = "写下显式逐条期望的规则数"） |
| **K18** | 假品牌名白名单硬断言；真实品牌数据与合成基准严格隔离（✅ M4 **两侧齐备**：生成侧 + **载入侧**） |
| K19 | 免责声明强制出现在每份报告与 GUI"关于"页 |
| K20 | 全本地零上传：核心层零第三方依赖、无网络库 |
| K21 | 冻结态自检断言数据目录落在 exe 目录内；非冻结态返回 `None` |
| K22 | 编码三层加固：CI `PYTHONUTF8=1` + 入口 `reconfigure` + 子进程显式 `encoding=`；**覆盖所有会打印的入口含 `tools/`** |
| K23 | 惰性导入 `try` 包住**从 import 到调用完成**整条路径，缺依赖走 exit 3 |
| K24 | 字节冻结分层：文本行尾（`eol=lf` + CR 守门）+ 冻结数据无 CR 守门。**CR 门禁按扩展名豁免二进制件**，豁免须配非空转测试 |
| K25 | **宣称词表单一来源**：只从规则包实算；解析层不留硬编码词表；判定层在唯一分派点按本轮规则包对齐，防"假 skipped" |
| K26 | **字段降级口径**：有值但无法映射一律**丢弃该字段 + 明确原因码** |
| K27 | **解析层字段表纪律**：别名表只放该字段**真正**的词面；单位匹配**最长优先** |
| K28 | **判定 kind 分派表结构性断言**："键存在"不是证据，断言要落在运行路径上 |
| **K29** | **冻结真值库是基准的期望来源**：入仓 + `--check` 位级守门 + **真有调用方** + **必须随包**（`DATA_WHITELIST`）。三者缺一即"没人读的冻结文件" |
| **K30** | **文档里的实测指标必须可核证**：README 指标与**行级**守门测试逐项等值，数值取自实跑；判据落**结构位置**不落"文件里出现过这串字" |

---

## 五、本机环境坑（只写实测过的）

| 坑 | 实测事实与处置 |
|---|---|
| 🔴 **裸 `python` 是 Windows Store 桩，静默不执行** | **本棒实测**：`which python` → `.../AppData/Local/Microsoft/WindowsApps/python`（Windows 应用执行别名桩）；`python -c "print(1)"` → **exit 49，无任何输出**，heredoc 同样（`echo 'print(1)' \| python -` 也 49）。**危害**：用它跑变异脚本会"成功返回"却什么都没改——本棒两次变异验证因此**看起来像是"改坏了测试还绿"**（险些误判成假门）。**处置**：一律用 `py -X utf8`（或用 `python -m pip` 那种 README 明示的形态，但执行脚本一律 `py`）。**变异验证前先用 `py -c "print(1)"` 确认通道可用**。 |
| Python 通道 | `py -0p` → **3.8-64** 与 **3.12-64** 两条。项目底线 3.8；一次性脚本只能用 **3.8 语法**。发布构建固定 `py -3.12`（PyInstaller **6.22.3** 已装） |
| **`Path.write_text(newline=)` 是 3.10+ 参数** | 3.8 上直接 `TypeError`。**已踩中三次** → 一律 `open(..., newline="\n")` 或 `write_bytes` |
| **`py -X utf8 -m pytest -q` 偶发 access violation** | 3.8 全量收集时**偶发**崩在 pytest 断言重写器。处置：**先清 `__pycache__` + `.pytest_cache` 再跑**；单次崩了别急着改代码，复跑确认 |
| 中文控制台编码 | 跑命令一律 `py -X utf8`；入口已加 `_ensure_utf8_stdio()` 探针 |
| **Git Bash `/tmp` 与 Windows Python 路径不通** | 临时文件一律用**工作区相对路径** `.tmp/`（已在 `.gitignore`） |
| pip 被系统代理污染 | `NO_PROXY="*" no_proxy="*" py -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <pkg>` |
| 大文件 curl 同步超时 | `-C -` 断点续传 + `run_in_background` |
| pip 安装后 `pflc.exe` 不在 PATH | 用 `python -m pflc.cli` |
| **`py` 启动器无视已激活 venv** | README 的 venv 段落一律写 `python -m pip ...` |
| PySide6 版本上限 | 3.8 实测可解析最高 **6.6.3.1**（6.7+ 要求 ≥3.9）；`gui` extra 写 `>=6.5,<6.7` |
| PyInstaller 分档 | 打 GUI 必须 **≥6**；只打 CLI 的老解释器用 `>=5.13,<6` |
| offscreen 中文字体 | Qt 6 起不随附字体且 offscreen 不扫系统字体目录 → `load_cjk_font()` 显式 `addApplicationFont`；字体路径由 `WINDIR`/`SystemRoot` 推导，**不写死盘符** |
| Qt 控件父级唯一 | 同一控件 `addTab` 多次会被 Qt 重新父化，页签数塌掉 → 每页签独立控件（已有守门测试） |
| **解析器同一指标只取首个出现** | 夹具里同一指标写两行 → 第二行被忽略。构造测试/夹具时**别重复写同一指标** |
| **`Decimal.normalize()` 产出 E 记号** | `Decimal("30").normalize()` → `Decimal("3E+1")`。一律走 `format_decimal()` |
| **变异验证要留对照组** | 只看到"改坏了测试还绿"不能下结论——要同时改一个**已知有探活的同类**（如 `boundary`）确认手法有效。**但先确认通道可用**（见上条裸 `python` 坑：本次两次"没生效"其实是执行通道坏了） |
| **判据别写成"文件里出现过这串字"** | M4 实测：CI 门子串判据放过"整段注释掉"；README 门全文件子串判据放过"手改数值"。判据要落**结构位置**（解析出的 run 步骤 / 小节内**行级**核对） |
| 🔴 **`--tracked` 审计看不到"尚未 `git add` 的新文件"** | **本棒实测并自己踩中**：`scan_tracked()` 按 `git ls-files` 枚举，故**新建但未暂存**的文件对 `--tracked` **完全不可见**。本棒把 `which python` 的实测路径（含本机用户名）写进**新建的** `plan/HANDOFF-M5.md`，预提交前跑了三次 `--tracked` **全绿**——`git add` 之后才报 `user_name_signature HARD 1`。**处置**：① 涉及"新写文档/新加文件"的收棒，**必须先 `git add` 再跑 `--tracked`**（或跑 `--all` 自查）；② 本次是"提交后跑全量测试"抓到的（`test_desensitize_audit_passes_on_tracked_files` 会 subprocess 跑 `--tracked`）。**这一条与上面"假门"是同一族：绿不等于验过了**。 |

---

## 六、关键命令速查

```bash
# --- 执行通道自检（先跑这个）---
py -X utf8 -c "print('channel-ok')"          # 必须打印；裸 python 会 exit 49 静默失败

# --- 测试与守门（每次收尾必跑）---
py -X utf8 -m pytest -q                      # 全量（应 255 passed）
py -3.12 -X utf8 -m pytest -q                # 双解释器验证
py -X utf8 tools/transcribe_clauses.py --check   # TRANSCRIBE_OK
py -X utf8 tools/gen_rulesets.py --check         # FROZEN_RULESET_OK
py -X utf8 tools/gen_cases.py --check            # FROZEN_CASES_OK（M4 新增门）
py -X utf8 tools/gen_samples.py --check          # FROZEN_SAMPLES_OK
py -X utf8 tools/audit_desensitize.py --selftest # 阳性 4 / 阴性 5 / 放行 1 / 豁免边界 6
py -X utf8 tools/audit_desensitize.py --tracked  # HARD 0 / REVIEW 0 → DESSENSITIZE_AUDIT_OK
py -X utf8 tools/smoke_cli.py                    # SMOKE_CLI_OK

# --- 数据层（改数据后必跑）---
py -X utf8 tools/transcribe_clauses.py --force   # 改 spec.json 后重转录
py -X utf8 tools/gen_rulesets.py --force         # 重生成规则包（**内部**先产真值库再实算覆盖登记）
py -X utf8 tools/gen_cases.py --force            # 重生成真值库（入库件）
# 改规则时**顺序就这两条**：`gen_rulesets` 的覆盖登记是从"当前规则包"内存生成真值库后实算的，
# 不读盘上的 cases.json，故**不需要**再跑第二遍 gen_rulesets（实测：跑完再 --check 双双 OK）。

# --- 数据状态与端到端 ---
py -X utf8 -m pflc.cli diagnostics               # 应 exit 0
py -X utf8 -m pflc.cli bench                     # 四套件达标；看 truth_source=frozen
py -X utf8 -m pflc.cli check data/samples/label-demo-ok.txt -v
py -X utf8 -m pflc.cli report data/samples/label-demo-missing.txt --out output/

# --- M5 打包通路（本棒初测可用）---
py -3.12 -m PyInstaller --version                # 6.22.3
py -X utf8 tools/make_demo_assets.py             # 演示素材（页签数可能已变，需复核）
py -X utf8 tools/verify_frozen.py --dist dist/pflc --selftest
```

**环境变量**：`PFLC_DATA_DIR` 可把数据目录指到别处（测试与验收用）。

---

## 七、一条**已知的、非本棒引入**的历史审计发现（如实记录，不掩盖）

`tools/audit_desensitize.py --all`（含历史模式）实测 **HARD 1 / REVIEW 2**，**全部来自历史提交**，
**与 M2/M3/M4 的改动无关**：

| 命中 | 位置 | 性质 |
|---|---|---|
| `user_name_signature` HARD | 提交 `a214320` 的 `plan/HANDOFF-M2.md` | 那版 HANDOFF 的"启动命令"示例里带了本机用户名的绝对路径 |
| `generic_email` REVIEW | 提交 `a214320` / `e4ebc2c` | 同上，原文快照的转载站点邮箱 |

**处置现状**：工作区与 `--tracked` 实测 **HARD 0 / REVIEW 0**；`plan/HANDOFF-M3.md` / `HANDOFF-M4.md` / `HANDOFF-M5.md`（本棒新增）实测**零命中**。
但 **git 历史不可变**，故 `--all` 会一直报它。

**为什么不动它**：修它需要 **git 历史重写**（`filter-branch`/`filter-repo` + 强推），
这是**破坏性且需用户授权**的操作，且本项目**尚未接远端**（未推送 = 无外泄面）。
留待**首推前**由用户决定。

**口径纪律**：本项目声明的 DoD 审计门是 `--tracked`（**当前全绿**）。`--all` 是更强的自查模式，
其 HARD 已在此如实登记，**不得把它当作"已修"或"不存在"**。

---

## 八、绝对禁止（M0–M6 全程）

- **不得虚报 CI**：无远端时 DoD 只能写"**本地等价校验通过**（未接远端，CI 待首推验证）"；**未推送 = 未跑 CI**。
- **不得编造标准内容**：核对没覆盖的条款**不建规则**；数值拿不到就 `pending`，**绝不臆造**。
- **不得手改冻结产物**：规则包/夹具/**真值库**改了走生成器重生成。
- **不得把"没做"记成"不用做"**：无条件义务缺失 = 不符合。
- **不得把"解析不到"当"合规"或"违规"**：显式降级 + 原因码。
- **不得在仓库树内跑冻结态验收**：CWD 上溯会命中仓库 `data/`。
- **不得在公开文档写姊妹项目的领域具体名词**：一律用"方向级描述"。
- **里程碑收尾不写 HANDOFF 就结束对话**：实测必然漏。
- **不得让门禁"看起来绿"而实际空转**：任何豁免/门控口径必须配**非空转守门测试**，
  且**同类口径要一次对齐全部实例**。
- **不得只验豁免函数本身**：要验"调用方有没有真的调它"。
- **不得把"有测试"当"测试有效"**：**每个新门都要做变异验证**（改坏 → 必须变红），
  且**留一个已知有效的对照组**（防"变异根本没生效"）。
- **变异验证前先确认执行通道可用**：本棒实测裸 `python` exit 49 静默不执行，
  会让变异脚本"看起来没生效"而误判成假门。**先 `py -c "print(1)"`**。
- **不得把判据写成"文件里出现过这串字"**：M4 实测两处假门都是这个形态
  （注释掉 CI step / 手改 README 数值 都能绕过）。判据要落**结构位置**。
- **不得照抄上一棒的结论当事实**：交接文档的口径同样要被核对（M3 交接曾漏报 2 条）。
- **不得让"源码态绿"当"发行态绿"**：M4 实测的形态——冻结产物不进包时，
  发行态会悄悄回落现场重算。打包后必须复核三断言真的覆盖了新产物。

---

## 九、参考文档索引

| 文档 | 用途 |
|---|---|
| `plan/00-README总览.md` | 项目总览 + **M0/M1/M2/M3/M4 实录** |
| `plan/02-需求解读.md` | 痛点→能力转译、**FR 清单**、边界与非目标 |
| `plan/03-架构与技术选型.md` | 分层架构、**D1–D18 关键设计决策**（**D11 已补 M4 实测注**） |
| `plan/04-模块详设.md` | 逐模块接口与判定语义 |
| `plan/05-数据计划.md` | 数据先行、规则包冻结形态、**§4.4/4.5 白名单与覆盖登记（M4 已补）**、渠道实录 |
| `plan/06-里程碑.md` | M0–M6 目标/DoD（**M4 已标 ✅ 并回填实测结果 + §M4 实录**；**M5 待做**） |
| `plan/07-交付对标与决策记录.md` | 评分对标、**决策记录（含 M4 各条）**、**K1–K30 既定口径**、反模式清单 |
| `data/README.md` | 数据台账（依据三态 + 渠道实录 + sha256 表 + **§九 M4 末态快照** + 勘误表） |
| `docs/技术报告.md` | 规则化方法、三态框架、基准设计、**§6.6 探活方法论 / §6.10 冻结真值三要素 / §十 M4 实测值** |
| `src/pflc/benchmark/cases.py` | 真值生成 + 白名单（**两侧**）+ `write/load/check_cases_frozen` + **覆盖登记实算** |
| `src/pflc/benchmark/runner.py` | 四套件 + **`_sample_cases()` 入库件优先** + 门槛下发 + 退出码 |
| `tools/gen_cases.py` | **真值库生成器**（`--force` / `--check` 形态参照模板） |
| `tests/test_benchmark.py` | 基准守门（探活 / 位级一致 / 空分母 / **冻结真值库被真读** / 覆盖口径） |
| `tests/test_readme_bench_metrics.py` | **文档指标可核证守门**（行级判据） |
| `src/pflc/packaging.py` | 打包白名单（**M4 收 `benchmark`**）与构建后三断言（**M5 主战场**） |
| `tools/verify_frozen.py` | 冻结产物验收（三断言 + 冻结态自检驱动） |
| `tools/make_demo_assets.py` | 演示素材程序化产出（M5 需重生成并复核） |
