# HANDOFF-M3：规则引擎三模块（判定层收口 → M4 基准冻结）

> 交接快照。上一棒 = M2（标签文本导入器），已完成并验证。
> **新对话怎么开**：`/goal 读取 "<项目绝对路径>\plan\HANDOFF-M3.md" 继续完成任务`
> （启动命令里的绝对路径由用户侧拼出；**库内一律只写相对路径** `plan/HANDOFF-M3.md`。）

---

## 一、当前进度（M0–M2 已完成并验证）

| 项 | 状态 |
|---|---|
| 规则包 | ✅ **45 条**（`label` 8 / `nutrition` 32 / `claim` 5），**43 `verified` + 2 `pending`** |
| 解析层 | ✅ **FR-01 全覆盖**（M2 收口；四处缺口 + 两处假门已修，逐处配变异验证） |
| 判定引擎 | ✅ **三类判定齐备**（`presence` / `threshold` / `claim_support`）+ 双重门控 + 维度聚合 |
| 测试 | ✅ **229 项**，Python 3.8.8 与 3.12.10 双解释器全绿 |
| 基准 | ✅ **四套件全部达标**（detection 检出率 1.00 / 误报 0.00；overall 1.00；boundary 60/60；traceability 43/43） |
| 守门 | ✅ `TRANSCRIBE_OK` / `FROZEN_RULESET_OK` / `FROZEN_SAMPLES_OK` / `DESSENSITIZE_AUDIT_OK`（HARD 0 / **REVIEW 0**）/ `SMOKE_CLI_OK` |
| 文档 | ✅ `plan/00`–`07` 已回填 M2 实录与勘误；`README.md` / `docs/技术报告.md` 同步 |

**M2 末态**：`py -X utf8 -m pflc.cli diagnostics` → **exit 0**；
`py -X utf8 -m pflc.cli bench` → **exit 0**（四套件达标）；
`py -X utf8 -m pflc.cli check data/samples/label-demo-ok.txt` → **exit 0**。

### M2 修的四处缺口（解析层，**每处都配变异验证**）

| # | 缺口 | 后果 | 修法 |
|---|---|---|---|
| 1 | 宣称词表硬编码在解析层，与规则包**两份口径** | 规则包加宣称 → 解析层不认 → 永远"未宣称" → **假 `skipped`** | 词表经 `rules.claim_vocabulary()` 从规则包实算，作为 `parse_label(claim_words=...)` **参数**传入；判定层在唯一分派点按本轮规则包对齐（不足则重抽） |
| 2 | 阶段别名表混入产品类型词（`全价` → `全阶段`） | 正常标签判"阶段歧义" → 营养维度**整维度 `not_assessed`** | 移除产品类型词；真·全阶段词面保留 |
| 3 | 净含量未知单位落 `not_found` | "写了但单位不认识"混同"根本没写" | 正则只抓"关键词+数值"；单位按**最长优先**判定（`2kg` ≠ `2 g`）；认不出 → `mapping_uncertain` |
| 4 | 日期不校验合法性 | `2026-13-45` 被当有效日期 | `datetime.date()` 校验 → `out_of_range` 且**丢弃该字段**（不"标个非法还当已提供"） |

### M2 顺带修掉的两处**假门**（都是"看起来有处置、实际空转"）

- **脱敏审计的死豁免**：给原文快照声明的 `generic_email` 豁免是死代码（扫描器内联实现、没调 `_is_exempt`），文件照报 `REVIEW 1`——与文档记的 `REVIEW 0` 不符。已接上豁免表 + **双向**非空转自检（豁免边界自检 3 项 → 6 项）。
- **GUI 政策字面量门禁的 `abs<100` 豁免**：M1 只修了**引擎**侧同一处勘误（K5），**界面侧原样留着**——政策数值天然 <100（实测 0.09–28）→ 整包放过。实测注入真实限值 `28` 到 `gui/app.py`，门禁**照绿**。已改为"与规则包限值同形即违规"（根治判据 + 断言 token 集非空）+ 结构性豁免收紧为"整数且 <20、非整数不豁免"。

> **教训（K10 补记）**：同一处豁免口径在引擎与界面两侧都要对齐——**修了一边，另一边会原样留着**。

---

## 二、下一里程碑（M3）状态：判定层已实质完成，**主要工作是补 DoD 证据与 M4 前置**

**M3 目标**：三个判定维度全部可用，三态结论 + 条款锚点。

### 已实测确认**已实现且有测试锁死**的条目

| M3 DoD 条目 | 证据（实测） |
|---|---|
| 标示项检查（`presence`）：无条件义务缺失 = `noncompliant` | `tests/test_engine.py::test_missing_unconditional_obligation_is_noncompliant` |
| **无适用项 → `not_assessed`**（绝不输出 compliant） | `test_no_applicable_rules_marks_not_assessed`；实跑：无生命阶段 → nutrition `not_assessed`（8 条 label 照判） |
| 营养限值（`threshold`）：按阶段筛适用；全程 `Decimal`；缺值 → `not_provided` | `test_threshold_*`（4 项，含边界精确值） |
| 宣称核查（`claim_support`）：条件齐备性结构化核查，不做语义硬判 | `test_claim_absent_is_skipped` / `_present_with_support_is_compliant` / `_present_without_support_is_noncompliant` |
| 双重门控：`status=pending` 不进判定路径；`clause_status=pending` 不阻断但显式呈现 | `tests/test_rules.py::test_clause_status_pending_does_not_block_judgment`；`Rule.is_effective()` 只看 `status` |
| 零生效维度不参与聚合 + 原因码 | `test_zero_effective_dimension_is_excluded_not_judged`；报告"未启用清单"列 `exclude_reason` |
| 义务类型分栏（`obligation` vs `conditional`） | `tests/test_model.py::`（`obligation_findings()` / `conditional_findings()`）；`test_conditional_effect_missing_is_unknown_not_noncompliant` |
| 零政策字面量门禁（引擎/基准/CLI/**GUI**，含 docstring/注释） | `test_no_banned_numeric_literals_in_engine_sources` + `test_gui_has_no_policy_numeric_literals`（**M2 已修**）+ 两条非空转/变异测试 |
| 单件与批量共用 `check_card` 分派点 | `test_check_file_matches_check_card`；`scan_dir` 亦经 `check_file` → `check_card` |

**结论**：M3 的 DoD 条目**代码与测试都已就位**，上一棒（M2）在收口解析层时顺带把判定层的
M2 前置（宣称词表口径、维度对齐）一并打通了。**本棒不重复造判定层**。

### M3 真正剩下的收尾（本棒应做的）

1. **把 M3 DoD 逐条勾掉并回填实测证据**（`plan/06` M3 段落 + `plan/00` M3 实录）——
   现在 `plan/06` 的 M3 DoD 还是全 `[ ]`，而实测已全绿：**不补证据就等于"做了没记"**。
2. **补一条 M3 缺失的守门**：`test_engine.py` 里**没有**"三类 kind 各自的分派实现都存在"的
   结构性断言（`_JUDGES` 三键齐备）。加一条防"加了 kind 却忘了实现"。
3. **M4 的三处真实缺口**（见 §三）——M3 收尾后 M4 才是下一棒的主体。

### DoD（逐项 checklist，M3）

- [ ] 三类判定 kind 齐备且有分派实现的结构性断言（新增 1 条测试）
- [ ] `plan/06` M3 段落 DoD 全部勾掉 + 回填实测结果表
- [ ] `plan/00` 补 **M3 实录**（口径同 M1/M2：产出 / 实测证据表 / 勘误 / 诚实口径）
- [ ] `py -X utf8 -m pytest -q` 全绿（3.8 与 3.12 双解释器）
- [ ] 六道守门全绿（`transcribe_clauses` / `gen_rulesets` / `gen_samples` / `audit_desensitize --selftest` / `--tracked` / `smoke_cli`）
- [ ] `plan/HANDOFF-M4.md` 已在本对话内落盘并 commit（硬约束出口门）

---

## 三、M4 的真实缺口（**本棒实测，不是猜的**）

`plan/06` 的 M4 DoD 有 12 条，其中 **9 条已实现并有测试**（生成器确定性 / 白名单硬断言 /
四类植入 / 两层基准 / 探活 / 空分母 / 门槛随 manifest 下发 / 退出码 / 对账单一实现源），
**剩下 3 条是真缺口**：

| # | M4 DoD 条目 | 实测状态 | 缺什么 |
|---|---|---|---|
| 1 | **样例入仓为字节冻结 fixtures** | ⬜ `data/benchmark/` **目录不存在**；`write_cases()` / `check_cases_frozen()` 已实现但**没有入库产物**，也没有常驻守门"入库件与生成器一致" | 生成 `data/benchmark/cases.json` 入仓；加"入库件 == 生成器输出"的 `--check` 式守门（参照 `gen_samples.py` 的形态）；`.gitattributes` 已声明 `data/benchmark/**` 为冻结路径，补文件即可 |
| 2 | **覆盖登记"总数/采样数"双数** | ⬜ `manifest.json` 的 `coverage.{label,nutrition,claim}` 里 `total_rules`/`verified_rules` **已双数**，但 `sampled_in_truth` 仍是 `null`、`sample_list` 仍是 `[]`，note 写着"（M4 回填采样数与清单）" | 从冻结真值库实算 `sampled_in_truth` 与 `sample_list` 回填；**必须与真值库同源**（手写清单会漂移） |
| 3 | **指标写入 README 表格** | ⬜ README 的基准章节只有"测什么"表，**没有实测指标值**（检出率/误报率/一致率/端点数/锚点率） | 把四套件实测值写进 README（数值须来自 `bench` 实际输出，不得手抄） |

**这三条的共性**：都不是"判定逻辑没写"，而是**"产物没入仓 / 台账没回填 / 指标没上文档"**——
典型的"做了没记"。M4 的核心风险因此不是正确性，而是**冻结与对账的完整性**。

---

## 四、既定口径清单（K 清单，动了会打挂基准）

> 后续任何改数据/加类目/改接口的动作，**先对照本表，改完重跑基准确认不回退**。
> 完整版见 `plan/07-交付对标与决策记录.md` §四。**M2 新增 K25–K27 与 K10 修订**。

| K | 口径 |
|---|---|
| K1 | 三态 `compliant`/`noncompliant`/`not_provided` + `skipped`（原文写了例外）/`unknown`（未观测）；**无条件义务缺失 = noncompliant**；无适用项 → `not_assessed`（绝不输出 compliant） |
| K2 | **双重门控**：`status`（数值）门控判定路径，`clause_status`（条款号）只管可证性 |
| K3 | 门控作用域三值 `label`/`nutrition`/`claim`，各只校验自己引用的条目 |
| K4 | 零生效维度不参与聚合 + `dimension_excluded` 原因码 |
| K5 | 数值口径一处定义：限值只在 `ruleset-nutrition.json`；**零政策字面量门禁**扫 `src/pflc/`（含 GUI）与 `tools/`，含 docstring/注释；token **运行时实算**。**豁免口径**：整数形态且 < 20 才豁免，**非整数一律不豁免**，且必须配"真实规则包下 token 集非空"的非空转守门测试 |
| K5b | **数值基准**：GB/T 理化指标**以干物质计**，标签保证值是 as-fed → 引擎对 `basis=dry_matter` **先换算再比**；缺水分 → `unknown` + `basis_undetermined`，绝不直接比、绝不猜水分 |
| K5c | **数值渲染**：一律 `format_decimal()`（定点、无 E 记号）；**禁 `str(Decimal.normalize())`** |
| K6 | 规则包冻结：禁手改，改走 `transcribe_clauses.py --force` → `gen_rulesets.py --force`；`--check` 位级一致 |
| K7 | 退出码三语义：`0` 达标/无不符合 · `1` 未达标/检出不符合/门控拦截 · `2` 用法或未知名错误 · `3` 缺 GUI 依赖 |
| K8 | 溯源完整性硬约束：导出前断言"溯源行数 == 明细行数"且引用 id 可解析，不满足**拒导** |
| K9 | 报告双轨**单一渲染源** `report_sections()`；机读产物逐字节可复现、**禁活动外链** |
| **K10** | GUI 零判定逻辑 AST 三条齐上（不 import 规则层 + 无 `BinOp` 算术 + **无政策数值字面量**）。**字面量判据（M2 修正）**：与**本轮规则包限值同形**即违规（根治判据，须断言 token 集非空）；结构性豁免收紧为"整数且 <20、非整数不豁免"，与 K5 同口径。**同一处豁免口径在引擎与界面两侧都要对齐**（M1 只修了引擎侧，M2 发现界面侧仍是 `abs<100` = 假门） |
| K11 | 单件与批量共用 `check_card` 分派点 |
| K12 | 失败件 ≠ 违规：解析失败记 `scan_error`/`failed`，**不改退出码**，失败隔离 |
| K13 | 两轮对账配对主键 = 稳定身份键（`file:<相对路径>`）；delta 返回**违规条目级**键 |
| K14 | 基准分样本驱动 + 规则驱动两层；每套件配探活；期望锚定冻结真值 |
| K15 | 验收门槛随 manifest 下发（缺失 → exit 2，不回落代码默认值） |
| K16 | 空分母 `not_enabled=true` + notes 声明 + exit 1 |
| K17 | 覆盖登记"规则包总数 / 已核对数 / 采样数 / 清单"**双数** + "抽样覆盖非穷举"声明 |
| K18 | 假品牌名白名单硬断言；真实品牌数据与合成基准严格隔离 |
| K19 | 免责声明强制出现在每份报告与 GUI"关于"页 |
| K20 | 全本地零上传：核心层零第三方依赖、无网络库 |
| K21 | 冻结态自检断言数据目录落在 exe 目录内；非冻结态返回 `None` |
| K22 | 编码三层加固：CI `PYTHONUTF8=1` + 入口 `reconfigure` + 子进程显式 `encoding=`；**覆盖所有会打印的入口含 `tools/` 脚本** |
| K23 | 惰性导入 `try` 包住**从 import 到调用完成**整条路径，缺依赖走 exit 3 |
| K24 | 字节冻结分层：文本行尾（`eol=lf` + CR 守门）+ 冻结数据无 CR 守门。**CR 门禁按扩展名豁免二进制件**（PNG/PDF 的 0x0D 是合法内容字节），豁免须配非空转测试 |
| **K25** | **宣称词表单一来源**：词表只从规则包 `claim.target` 实算（`claim_vocabulary()`）；`parse_label(claim_words=...)` 是**参数**，解析层不留硬编码词表、不读文件；**判定层在唯一分派点按本轮规则包对齐**（不足则按 `raw_text` 重抽），防"假 skipped"。词表含 pending 条目的词面 |
| **K26** | **字段降级口径**：有值但无法映射（单位不认识 / 日期非法）一律**丢弃该字段 + 明确原因码**，绝不"标个非法还当已提供"——否则存在性规则会把真实缺陷判成 `compliant`（假合规）；原文片段留 `evidence` 可核 |
| **K27** | **解析层字段表纪律**：别名表只放该字段**真正**的词面（产品类型词"全价"不进生命阶段表）；单位匹配**最长优先**（`2kg` ≠ `2 g`） |

---

## 五、本机环境坑（只写实测过的）

| 坑 | 实测事实与处置 |
|---|---|
| Python 通道 | `py -0p` → **3.8-64** 与 **3.12-64** 两条。项目底线 3.8；所有一次性脚本只能用 **3.8 语法**。发布构建固定用 `py -3.12`（PyInstaller 6.x） |
| **`Path.write_text(newline=)` 是 3.10+ 参数** | 3.8 上直接 `TypeError`。本项目**已多次踩中** → 一律用 `open(..., newline="\n")` 或 `write_bytes` |
| **`py -X utf8 -m pytest -q` 偶发 access violation** | M2 实测：3.8 全量收集时**偶发**"Windows fatal exception: access violation"（pytest 断言重写器里崩）。**逐文件跑全绿、连续三次全量也全绿** → 是偶发（与 handoff 记的"pyc 偶发损坏"同源）。处置：**先清 `__pycache__` + `.pytest_cache` 再跑**；单次崩了别急着改代码，复跑确认 |
| 中文控制台编码 | 跑命令一律 `py -X utf8`；入口已加 `_ensure_utf8_stdio()` 探针 |
| **Git Bash `/tmp` 与 Windows Python 路径不通** | `curl` 落到 `/tmp/x.html` 后 Windows Python 读不到 → 临时文件一律用**工作区相对路径** `.tmp/` |
| pip 被系统代理污染 | `NO_PROXY="*" no_proxy="*" py -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <pkg>` |
| 大文件 curl 同步超时 | 用 `-C -` 断点续传 + `run_in_background` 后台任务 |
| pip 安装后 `pflc.exe` 不在 PATH | 用 `python -m pflc.cli`（README 已统一此形态） |
| **`py` 启动器无视已激活 venv** | README 的 venv 段落一律写 `python -m pip ...` |
| PySide6 版本上限 | 3.8 实测可解析最高 **6.6.3.1**（6.7+ 元数据要求 ≥3.9）；`gui` extra 写 `>=6.5,<6.7` |
| PyInstaller 分档 | 打 GUI 必须 **≥6**；只打 CLI 的老解释器用 `>=5.13,<6` |
| offscreen 中文字体 | Qt 6 起不随附字体且 offscreen 不扫系统字体目录 → `load_cjk_font()` 显式 `addApplicationFont`；字体路径由 `WINDIR`/`SystemRoot` 推导，**不写死盘符** |
| Qt 控件父级唯一 | 同一控件 `addTab` 多次会被 Qt 重新父化，页签数塌掉 → 每页签独立控件（已有守门测试） |
| **解析器同一指标只取首个出现** | 夹具里同一指标写两行 → 第二行被忽略。构造测试/夹具时**别重复写同一指标** |
| **`Decimal.normalize()` 产出 E 记号** | `Decimal("30").normalize()` → `Decimal("3E+1")`。一律走 `format_decimal()` |

---

## 六、关键命令速查

```bash
# --- 测试与守门（每次收尾必跑）---
py -X utf8 -m pytest -q                              # 全量（应 229 passed）
py -3.12 -X utf8 -m pytest -q                        # 双解释器验证
py -X utf8 tools/transcribe_clauses.py --check       # 期望 TRANSCRIBE_OK
py -X utf8 tools/gen_rulesets.py --check             # 期望 FROZEN_RULESET_OK
py -X utf8 tools/gen_samples.py --check              # 期望 FROZEN_SAMPLES_OK
py -X utf8 tools/audit_desensitize.py --selftest     # 期望 阳性 4 / 阴性 5 / 放行 1 / 豁免边界 6
py -X utf8 tools/audit_desensitize.py --tracked      # 期望 HARD 0 / REVIEW 0 → DESSENSITIZE_AUDIT_OK
py -X utf8 tools/smoke_cli.py                        # 期望 SMOKE_CLI_OK

# --- 数据层（改数据后必跑）---
py -X utf8 tools/transcribe_clauses.py --force       # 改 spec.json 后重转录
py -X utf8 tools/gen_rulesets.py --force             # 重生成规则包
py -X utf8 tools/gen_samples.py --force              # 重生成夹具

# --- 数据状态与端到端 ---
py -X utf8 -m pflc.cli diagnostics                   # 规则/数据状态（应 exit 0）
py -X utf8 -m pflc.cli check data/samples/label-demo-ok.txt -v
py -X utf8 -m pflc.cli check data/samples/label-demo-edge.txt -v   # M2 边界夹具（应 exit 1）
py -X utf8 -m pflc.cli bench                         # 四套件（应 exit 0 达标）
py -X utf8 -m pflc.cli report data/samples/label-demo-missing.txt --out output/

# --- 演示物料（M5 重生成）---
py -X utf8 tools/make_demo_assets.py --out docs/demo
```

**环境变量**：`PFLC_DATA_DIR` 可把数据目录指到别处（测试与验收用）。

---

## 六·补、一条**已知的、本棒未引入**的历史审计发现（如实记录，不掩盖）

`tools/audit_desensitize.py --all`（含历史模式）实测 **HARD 1 / REVIEW 2**，**全部来自历史提交**，
**与 M2 的改动无关**：

| 命中 | 位置 | 性质 |
|---|---|---|
| `user_name_signature` HARD | 提交 `a214320` 的 `plan/HANDOFF-M2.md` | M1 那版 HANDOFF 的"启动命令"示例里带了本机用户名的绝对路径 |
| `generic_email` REVIEW | 提交 `a214320` / `e4ebc2c` | 同上，原文快照的转载站点邮箱 |

**处置现状**：`e4ebc2c`（M1 收尾"手记路径脱敏"）**已把该文件改干净**——工作区与 `--tracked`
实测 **HARD 0 / REVIEW 0**；`plan/HANDOFF-M3.md`（本棒新增）实测 **零命中**。
但 **git 历史是不可变的**，`a214320` 的树里那份旧文本仍在，故 `--all` 会一直报它。

**为什么本棒不动它**：修它需要 **git 历史重写**（`filter-branch`/`filter-repo` + 强推），
这是**破坏性且需用户授权**的操作，且本项目**尚未接远端**（未推送 = 无外泄面）。
故如实记为"已知历史项"，留待**首推前**由用户决定是否重写历史。

**口径纪律**：本项目声明的 DoD 审计门是 `--tracked`（见 `plan/06` M0/M1/M2 DoD 与
`plan/00` 各实录表）——该门**当前全绿**。`--all` 是更强的自查模式，其 HARD 已在此如实登记，
**不得把它当作"已修"或"不存在"**。

---

## 七、绝对禁止（M0–M6 全程）

- **不得虚报 CI**：无远端时 DoD 只能写"**本地等价校验通过**（未接远端，CI 待首推验证）"；**未推送 = 未跑 CI**。
- **不得编造标准内容**：核对没覆盖的条款**不建规则**（宁缺勿造）；数值拿不到就 `pending`，**绝不臆造**。
- **不得手改冻结产物**：规则包/夹具/条文块改了走生成器重生成。
- **不得把"没做"记成"不用做"**：无条件义务缺失 = 不符合。
- **不得把"解析不到"当"合规"或"违规"**：显式降级 + 原因码。
- **不得在仓库树内跑冻结态验收**：CWD 上溯会命中仓库 `data/`，"内嵌数据"验了个寂寞。
- **不得在公开文档写姊妹项目的领域具体名词**：一律用"方向级描述"。
- **里程碑收尾不写 HANDOFF 就结束对话**：实测必然漏。
- **不得让门禁"看起来绿"而实际空转**：任何豁免口径（数值 token / CR 二进制 / 分母为零 /
  审计豁免 / GUI 字面量）必须配**非空转守门测试**，且**同类口径要一次对齐全部实例**
  （M2 实测：引擎侧修了、界面侧漏了 = 假门）。
- **不得只验豁免函数本身**：要验"调用方有没有真的调它"（M2 实测的死豁免）。

---

## 八、参考文档索引

| 文档 | 用途 |
|---|---|
| `plan/00-README总览.md` | 项目总览 + **M0/M1/M2 实录** |
| `plan/02-需求解读.md` | 痛点→能力转译、**FR-01…FR 清单**、边界与非目标 |
| `plan/03-架构与技术选型.md` | 分层架构、**D1–D18 关键设计决策**（含 **D5b 数值基准**） |
| `plan/04-模块详设.md` | 逐模块接口与判定语义、**§2.2 字段抽取策略表**（M2 已回填最终口径） |
| `plan/05-数据计划.md` | 数据先行、规则包冻结形态、**渠道实录（含 M1 瓦片旁路）** |
| `plan/06-里程碑.md` | M0–M6 目标/DoD/风险降级（**M1/M2 已标 ✅ 并回填实测结果**；M3 待回填） |
| `plan/07-交付对标与决策记录.md` | 评分对标、**决策记录（含 M1/M2 勘误各条）**、**K1–K27 既定口径**、反模式清单 |
| `data/README.md` | 数据台账（依据三态 + 渠道实录 + sha256 表 + M1 末态 + 勘误表） |
| `docs/技术报告.md` | 规则化方法、三态框架、基准设计、**§十 M1/M2 实测值与勘误** |
| `tests/test_m2_parse.py` | M2 解析层守门（四缺口正负例 / FR-01 字段矩阵 / 边界确定性 / 夹具覆盖门） |
| `tests/test_m1_data.py` | M1 数据层守门（原文逐字包含 / 双 sha256 / 干基换算 / 门禁非空转） |
