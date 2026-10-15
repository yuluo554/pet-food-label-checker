# HANDOFF-M4：合成标签基准（冻结与对账收口）

> 交接快照。上一棒 = M3（规则引擎三模块，已完成并验证）。
> **新对话怎么开**：`/goal 读取 "<项目绝对路径>\plan\HANDOFF-M4.md" 继续完成任务`
> （启动命令里的绝对路径由用户侧拼出；**库内一律只写相对路径** `plan/HANDOFF-M4.md`。）

---

## 一、当前进度（M0–M3 已完成并验证）

| 项 | 状态 |
|---|---|
| 规则包 | ✅ **45 条**（`label` 8 / `nutrition` 32 / `claim` 5），**43 `verified` + 2 `pending`** |
| 解析层 | ✅ **FR-01 全覆盖**（M2 收口；四处缺口 + 两处假门已修，逐处配变异验证） |
| 判定引擎 | ✅ **三类判定齐备**（`presence` / `threshold` / `claim_support`）+ 双重门控 + 维度聚合 + 分派表结构性守门（M3 新增） |
| 测试 | ✅ **231 项**，Python 3.8.8 与 3.12.10 双解释器全绿 |
| 基准 | ✅ **四套件全部达标**（detection 检出率 1.00 / 误报 0.00；overall 1.00；boundary 60/60；traceability 43/43） |
| 守门 | ✅ 六道全绿：`TRANSCRIBE_OK` / `FROZEN_RULESET_OK` / `FROZEN_SAMPLES_OK` / `DESSENSITIZE_AUDIT_OK`（HARD 0 / REVIEW 0）/ `SMOKE_CLI_OK` |
| 文档 | ✅ `plan/00`–`07` 已回填 M3 实录；`README.md` / `docs/技术报告.md` / `data/README.md` 同步 |

**M3 末态**：`py -X utf8 -m pflc.cli diagnostics` → **exit 0**（label 8/8 · nutrition 30/32 · claim 5/5）；
`py -X utf8 -m pflc.cli bench` → **exit 0**（四套件达标）；
`py -X utf8 -m pflc.cli check data/samples/label-demo-ok.txt` → **exit 0**。

### M3 本棒做了什么（**新增代码只有 2 条测试**）

M3 的 DoD 条目在 M0 骨架与 M2 收口解析层时**已全部实现并有测试**，M3 是**收口**：
逐条实测核对 + 回填证据 + 补一条缺失的结构性守门。**未新增判定逻辑**。

| M3 新增 | 内容 |
|---|---|
| `test_every_kind_has_a_distinct_dispatch_implementation` | `set(_JUDGES) == set(KINDS)` + 三实现互不相同（防复制粘贴）+ **夹具真的驱动了全部 kind**（防空转） |
| `test_dispatch_guard_rejects_unimplemented_kind` | 非空转自检：从 `_JUDGES` 摘掉一个 kind → 判定路径必须报 `EngineError` |

**变异验证 2 处**：① `claim_support` 与 `presence` 指向同一实现 → 4 failed；
② 摘掉 `threshold` 实现 → 17 failed。测试总数 **229 → 231**。

---

## 二、下一里程碑（M4）：判定逻辑已就绪，**真正的工作是"产物入仓 / 台账回填 / 指标上文档"**

**M4 目标**：一条命令复现评测，四套件达标，指标进 README。

`plan/06` 的 M4 DoD 有 12 条（其中末条 `plan/HANDOFF-M5.md` 是 M4 自身的出口门）。
**本棒逐条实测核对**（不沿用上一棒结论），结论：
**7 条达成**（#2/#3/#4/#6/#8/#9/#10），**4 条未达成**（#1/#5/#7/#11）。
其中 **#5 一条含 2 个独立缺口**（`overall` 无探活、冻结真值库未被读），故 **DoD 口径下缺 5 条**；
另有 **1 条超出 DoD 字面的加固发现**（白名单载入侧零校验）。其中 **2 条是上一棒（M3 交接）未发现的**。

> **上一棒漏报的两条，是本棒实测新发现**。本棒把它们如实登记，
> 而不是照抄上一棒给的三条——**交接文档的口径也要被核对，不能当既定事实**。

---

## 三、M4 真实缺口（**全部本棒实测，非猜测**）

> 分两组：**A. DoD 口径内的 5 条**（#1–#5，对应 `plan/06` 未勾掉的 4 条，其中 #5 一条拆 2 缺口）；
> **B. 超出 DoD 字面的加固发现 1 条**（#6）。

**A. DoD 口径内的 5 条缺口**（对应 `plan/06` 未勾掉的 4 条，其中 #5 一条拆两缺口）

### #1 基准 fixtures 未入仓 + 无"入库件 == 生成器输出"常驻守门

| 项 | 实测状态 |
|---|---|
| 目录 | ⬜ `data/benchmark/` **不存在**（`data/` 下只有 `knowledge/` `rules/` `samples/`） |
| 生成器 | ✅ `write_cases()` / `load_cases()` / `check_cases_frozen()` 都已实现 |
| 入库产物 | ⬜ **没有**（`cases.json` 未落盘） |
| 常驻守门 | ⬜ **没有**——`check_cases_frozen()` 只在 `tests/test_benchmark.py` 里被调用，**没有 CLI / 没有 tools 脚本**；`grep -rn "cases.json\|data/benchmark" tools/ src/` 零命中 |

**缺什么**：① 生成 `data/benchmark/cases.json` 入仓；② 加"入库件 == 生成器输出"的 `--check` 式守门，
**参照 `tools/gen_samples.py` 的形态**（`--force` / `--check` + `FROZEN_*_OK` 标记）。
`.gitattributes` **已**声明 `data/benchmark/** -text`（`test_gitattributes_declares_frozen_paths_as_text_free` 已锁），
`tests/test_gates.py::test_frozen_data_has_no_cr` 也已把 `data/benchmark` 列入冻结目录扫描——**补文件即可生效**。

### #2 覆盖登记"总数/采样数"双数

| 项 | 实测状态 |
|---|---|
| `total_rules` / `verified_rules` | ✅ 已双数（label 8/8 · nutrition 32/30 · claim 5/5） |
| `sampled_in_truth` | ⬜ 仍是 **`null`**（三个维度全是） |
| `sample_list` | ⬜ 仍是 **`[]`**（三个维度全是） |
| `note` | 仍写着"（M4 回填采样数与清单）" |

**缺什么**：从**冻结真值库实算** `sampled_in_truth` 与 `sample_list` 回填，**必须与真值库同源**
（手写清单必然漂移）。

**本棒实测的实算口径**（已跑通，可直接用）：真值库 `generate_cases(data/rules)` 产出
**16 个用例**（`compliant` 4 / `missing` 4 / `overlimit` 4 / `unsupported_claim` 4）；
按 `expected_findings` 的 key 归集规则 id，得
`label` 3 条（`LABEL-002/003/006`）、`claim` 3 条（`CLAIM-001/003/004`）、`nutrition` 4 条（如 `NUT-CAT-009`/`NUT-DOG-003`/…）。

> **口径坑（本棒实测）**：`expected_findings` **只记非 pass 的期望**，
> `compliant` 类用例的 `expected_findings` 是 **`{}`**。所以
> "**被真值库采样到的规则**"若只按 `expected_findings` 算，会**漏掉合规类用例实际覆盖到的规则**
> （合规用例同样逐条判了全部生效规则）。回填时要想清楚口径，并在 `note` 里写清
> "采样数"的定义（是"有显式期望的规则数"还是"被用例触达的规则数"）——
> **两个口径给出的数不同，写不清就是又一个假台账**。

**顺序约束**：manifest 由 `tools/gen_rulesets.py` 产出，而真值库由规则包产出（`generate_cases` 读 `load_pack`）→
回填是**第二轮**：规则包 → 真值库 → 回填 coverage → 重冻结 manifest。
改完必须 `gen_rulesets.py --check` 仍 `FROZEN_RULESET_OK`、且**位级一致**（否则冻结链断了）。
注意 `gen_rulesets.py` 若只读 `spec.json` 而不读真值库，回填需要新增数据源或新增生成步骤——**先看代码再定形态**。

### #3 指标未写入 README

| 项 | 实测状态 |
|---|---|
| README 基准章节 | ✅ 有"测什么"表（`detection`/`overall`/`boundary`/`traceability` 四行） |
| 实测指标值 | ⬜ **没有**——README 只写"四套件**全部达标**"，**无任何数值** |

**缺什么**：把四套件实测值写进 README（检出率 / 误报率 / 一致率 / 端点数 / 锚点率）。
**数值须取自 `py -X utf8 -m pflc.cli bench` 的实际输出，不得手抄**（手抄 = 下一个漂移源）。
本棒实测输出（供对照，正式回填时**以当时的 bench 输出为准**）：
`detection`：`violation_cases=12` / `detected=12` / `detection_rate=1.0` / `false_positive_rate=0.0` / `clean_cases=4`；
`overall`：`cases=16` / `matched=16` / `accuracy=1.0`；
`boundary`：`rules=30` / `checked=60` / `passed=60` / `rate=1.0`；
`traceability`：`effective_rules=43` / `resolvable=43` / `rate=1.0`。

### #4 🔴 **`overall` 套件没有探活测试**（本棒新发现；上一棒漏报）

**M4 DoD 原话**："**每套件配探活测试**（注入缺陷 → 必须报未达标）"。实测 **4 个套件只有 3 个有探活**：

| 套件 | 探活测试 | 状态 |
|---|---|---|
| `detection` | `test_probe_detection_suite_fails_when_engine_detection_is_blinded` + `test_probe_detection_suite_fails_when_rule_disabled` | ✅ |
| `boundary` | `test_probe_boundary_suite_fails_when_engine_comparison_is_broken` | ✅ |
| `traceability` | `test_probe_traceability_suite_fails_when_anchor_missing` | ✅ |
| **`overall`** | **无** | ⬜ |

**本棒的变异证明（这是"假门"的实证，不是推测）**：
把 `run_overall` 的比较改成恒真（`if True:`）→ **231 项测试全绿**；
把 `run_overall` 的 `result.passed` 改成恒 `True` → **231 项测试全绿**。
对照组：同样手法改 `run_boundary` 的 `passed` → **立刻 1 项失败**（`test_probe_boundary_...`）。
→ **`overall` 的达标判定当前不可证伪 = 永绿门**。

**缺什么**：补一条 `overall` 探活（注入缺陷 → `overall` 必须报未达标）。

> **口径提醒（本棒的第二次实测）**：`overall` 是**样本驱动**套件，它读真值库的 `expected_overall`。
> 因此能证伪它的是"**引擎的聚合结论算错了**"或"**真值库的期望被篡改**"，
> 而**不是**改规则数值（两边一起变）。补探活时注入方向要对——
> 参照 `test_probe_boundary_suite_...` 的 docstring 里"boundary 是规则驱动，故注入引擎缺陷而非数据缺陷"
> 的那段论证，`overall` 要反过来想清楚哪种注入真的能证伪它。

### #5 🔴 **冻结真值库根本没被读**（本棒新发现；上一棒漏报）

**(a) `bench` 不读 `data/benchmark/cases.json`**：`runner._sample_cases()` 直接
`generate_cases(rules_dir)["cases"]` —— **每次跑基准都现场重算真值**，
`load_cases()` / `check_cases_frozen()` 在整个 `src/` 与 `tools/` 里**零调用**。

后果：M4 把 `cases.json` 落盘后，**基准仍然不会用它**——"期望锚定冻结真值库"（K14）就只是**名义上的**。
**缺什么**：让基准真的以入库件为期望来源（并保留"入库件 == 生成器输出"的守门），
否则 #1 的落盘只产出"一个没人读的冻结文件"。

> **判断口径**：这不必然要求改架构——"真值库 == 生成器输出"本身是可接受的（生成器是唯一真值源）；
> 但那样 **#1 的守门就不是可有可无的**：它是"冻结"这件事的**唯一证据**。
> 二者必须至少落实一个，不能两个都悬空。

---

**B. 超出 DoD 字面的加固发现（1 条）**

### #6 🟡 `load_cases()` 载入侧不校验品牌白名单

白名单只在**生成侧**生效（`build_label_text()` → `assert_brand_allowed()`）。
本棒实测：手工构造含**真实品牌名**的 `cases.json` 交给 `load_cases()` → **原样载入、不报错**。

后果：一旦"入库件被手改"或"未来支持外部真值库"，真实品牌数据可以**不经过白名单**进入基准真值
——这与 K18"真实品牌数据与合成基准严格隔离"直接冲突。**与 #1 同批处理最省事**（补入库件守门时，
顺带断言"入库件里所有品牌名都在白名单内"）。

> **DoD 计数**：上表 M4 DoD 第 2 条"白名单硬断言"**字面上只要求生成侧**（实测已达成）；
> 本条是**同一口径的第二个实例**——**把口径一次对齐全部实例**（M2 的教训：引擎侧修了、界面侧漏了 = 假门）。

---

## 四、既定口径清单（K 清单，动了会打挂基准）

> 后续任何改数据/加类目/改接口的动作，**先对照本表，改完重跑基准确认不回退**。
> 完整版见 `plan/07-交付对标与决策记录.md` §四。**M3 新增 K28**。

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
| K10 | GUI 零判定逻辑 AST 三条齐上（不 import 规则层 + 无 `BinOp` 算术 + **无政策数值字面量**）。**字面量判据**：与**本轮规则包限值同形**即违规（根治判据，须断言 token 集非空）；结构性豁免收紧为"整数且 <20、非整数不豁免"，与 K5 同口径。**同一处豁免口径在引擎与界面两侧都要对齐** |
| K11 | 单件与批量共用 `check_card` 分派点 |
| K12 | 失败件 ≠ 违规：解析失败记 `scan_error`/`failed`，**不改退出码**，失败隔离 |
| K13 | 两轮对账配对主键 = 稳定身份键（`file:<相对路径>`）；delta 返回**违规条目级**键 |
| K14 | 基准分样本驱动 + 规则驱动两层；每套件配探活；**期望锚定冻结真值** — ⚠️ **实测两条未落实**：`overall` 无探活（§三 #4）、冻结真值库未被读（§三 #5） |
| K15 | 验收门槛随 manifest 下发（缺失 → exit 2，不回落代码默认值） |
| K16 | 空分母 `not_enabled=true` + notes 声明 + exit 1 |
| K17 | 覆盖登记"规则包总数 / 已核对数 / 采样数 / 清单"**双数** + "抽样覆盖非穷举"声明 — ⚠️ **采样数/清单未回填**（§三 #2） |
| K18 | 假品牌名白名单硬断言；真实品牌数据与合成基准严格隔离 — ⚠️ **载入侧无校验**（§三 #6，超出 DoD 字面） |
| K19 | 免责声明强制出现在每份报告与 GUI"关于"页 |
| K20 | 全本地零上传：核心层零第三方依赖、无网络库 |
| K21 | 冻结态自检断言数据目录落在 exe 目录内；非冻结态返回 `None` |
| K22 | 编码三层加固：CI `PYTHONUTF8=1` + 入口 `reconfigure` + 子进程显式 `encoding=`；**覆盖所有会打印的入口含 `tools/` 脚本** |
| K23 | 惰性导入 `try` 包住**从 import 到调用完成**整条路径，缺依赖走 exit 3 |
| K24 | 字节冻结分层：文本行尾（`eol=lf` + CR 守门）+ 冻结数据无 CR 守门。**CR 门禁按扩展名豁免二进制件**，豁免须配非空转测试 |
| K25 | **宣称词表单一来源**：词表只从规则包 `claim.target` 实算（`claim_vocabulary()`）；`parse_label(claim_words=...)` 是**参数**，解析层不留硬编码词表、不读文件；**判定层在唯一分派点按本轮规则包对齐**（不足则按 `raw_text` 重抽），防"假 skipped" |
| K26 | **字段降级口径**：有值但无法映射（单位不认识 / 日期非法）一律**丢弃该字段 + 明确原因码**，绝不"标个非法还当已提供" |
| K27 | **解析层字段表纪律**：别名表只放该字段**真正**的词面；单位匹配**最长优先**（`2kg` ≠ `2 g`） |
| **K28** | **判定 kind 分派表结构性断言**：`set(_JUDGES) == set(KINDS)` + 三实现互不相同 + **夹具真的驱动全部 kind** + 非空转自检。**"键存在"不是证据，断言要落在运行路径上** |

---

## 五、本机环境坑（只写实测过的）

| 坑 | 实测事实与处置 |
|---|---|
| Python 通道 | `py -0p` → **3.8-64** 与 **3.12-64** 两条。项目底线 3.8；所有一次性脚本只能用 **3.8 语法**。发布构建固定用 `py -3.12`（PyInstaller 6.x） |
| **`Path.write_text(newline=)` 是 3.10+ 参数** | 3.8 上直接 `TypeError`。本项目**已多次踩中** → 一律用 `open(..., newline="\n")` 或 `write_bytes` |
| **`py -X utf8 -m pytest -q` 偶发 access violation** | 3.8 全量收集时**偶发**崩在 pytest 断言重写器。**逐文件跑全绿、复跑全量也全绿** → 偶发。处置：**先清 `__pycache__` + `.pytest_cache` 再跑**；单次崩了别急着改代码，复跑确认 |
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
| **变异验证要留对照组** | 本棒实测教训：只看到"改坏了测试还绿"还不能下结论，**要同时改一个已知有探活的同类**（如 `boundary`）确认手法本身有效——否则可能只是变异没生效 |

---

## 六、关键命令速查

```bash
# --- 测试与守门（每次收尾必跑）---
py -X utf8 -m pytest -q                              # 全量（应 231 passed）
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

# --- M4 会用到的验证手法（本棒已跑通，可直接复用）---
# 变异验证：改 run_overall / run_boundary 的 passed 判据后跑全量，看是否变红
# 真值库实算：generate_cases(data/rules) → 16 用例（4 类各 4）
```

**环境变量**：`PFLC_DATA_DIR` 可把数据目录指到别处（测试与验收用）。

---

## 七、一条**已知的、本棒未引入**的历史审计发现（如实记录，不掩盖）

`tools/audit_desensitize.py --all`（含历史模式）实测 **HARD 1 / REVIEW 2**，**全部来自历史提交**，
**与 M2/M3 的改动无关**：

| 命中 | 位置 | 性质 |
|---|---|---|
| `user_name_signature` HARD | 提交 `a214320` 的 `plan/HANDOFF-M2.md` | 那版 HANDOFF 的"启动命令"示例里带了本机用户名的绝对路径 |
| `generic_email` REVIEW | 提交 `a214320` / `e4ebc2c` | 同上，原文快照的转载站点邮箱 |

**处置现状**：`e4ebc2c`（M1 收尾"手记路径脱敏"）**已把该文件改干净**——工作区与 `--tracked`
实测 **HARD 0 / REVIEW 0**；`plan/HANDOFF-M3.md` 与 `plan/HANDOFF-M4.md`（本棒新增）实测**零命中**。
但 **git 历史是不可变的**，`a214320` 的树里那份旧文本仍在，故 `--all` 会一直报它。

**为什么本棒不动它**：修它需要 **git 历史重写**（`filter-branch`/`filter-repo` + 强推），
这是**破坏性且需用户授权**的操作，且本项目**尚未接远端**（未推送 = 无外泄面）。
故如实记为"已知历史项"，留待**首推前**由用户决定是否重写历史。

**口径纪律**：本项目声明的 DoD 审计门是 `--tracked`（见 `plan/06` 各里程碑 DoD 与
`plan/00` 各实录表）——该门**当前全绿**。`--all` 是更强的自查模式，其 HARD 已在此如实登记，
**不得把它当作"已修"或"不存在"**。

---

## 八、绝对禁止（M0–M6 全程）

- **不得虚报 CI**：无远端时 DoD 只能写"**本地等价校验通过**（未接远端，CI 待首推验证）"；**未推送 = 未跑 CI**。
- **不得编造标准内容**：核对没覆盖的条款**不建规则**（宁缺勿造）；数值拿不到就 `pending`，**绝不臆造**。
- **不得手改冻结产物**：规则包/夹具/真值库改了走生成器重生成。
- **不得把"没做"记成"不用做"**：无条件义务缺失 = 不符合。
- **不得把"解析不到"当"合规"或"违规"**：显式降级 + 原因码。
- **不得在仓库树内跑冻结态验收**：CWD 上溯会命中仓库 `data/`，"内嵌数据"验了个寂寞。
- **不得在公开文档写姊妹项目的领域具体名词**：一律用"方向级描述"。
- **里程碑收尾不写 HANDOFF 就结束对话**：实测必然漏。
- **不得让门禁"看起来绿"而实际空转**：任何豁免/门控口径必须配**非空转守门测试**，
  且**同类口径要一次对齐全部实例**。
- **不得只验豁免函数本身**：要验"调用方有没有真的调它"。
- **不得把"有测试"当"测试有效"**：本棒实测——`overall` 套件的达标判定**可被改成恒真而 231 项全绿**
  （无探活）。**M4 收尾前必须对本里程碑每个新门做变异验证**（改坏 → 必须变红），
  且**留一个已知有效的对照组**（防"变异根本没生效"）。
- **不得照抄上一棒的结论当事实**：本棒实测发现上一棒（M3 交接）漏报了 2 条缺口
  （`overall` 无探活、冻结真值库未被读）。**交接文档的口径同样要被核对**。

---

## 九、参考文档索引

| 文档 | 用途 |
|---|---|
| `plan/00-README总览.md` | 项目总览 + **M0/M1/M2/M3 实录** |
| `plan/02-需求解读.md` | 痛点→能力转译、**FR-01…FR 清单**、边界与非目标 |
| `plan/03-架构与技术选型.md` | 分层架构、**D1–D18 关键设计决策**（含 **D5b 数值基准**） |
| `plan/04-模块详设.md` | 逐模块接口与判定语义、**§2.2 字段抽取策略表** |
| `plan/05-数据计划.md` | 数据先行、规则包冻结形态、**§4.5 覆盖登记（防"假覆盖"）**、渠道实录 |
| `plan/06-里程碑.md` | M0–M6 目标/DoD/风险降级（**M1/M2/M3 已标 ✅ 并回填实测结果**；M4 待做） |
| `plan/07-交付对标与决策记录.md` | 评分对标、**决策记录（含 M1/M2/M3 各条）**、**K1–K28 既定口径**、反模式清单 |
| `data/README.md` | 数据台账（依据三态 + 渠道实录 + sha256 表 + **M3 末态快照** + 勘误表） |
| `docs/技术报告.md` | 规则化方法、三态框架、基准设计、**§十 M1/M2/M3 实测值与勘误** |
| `src/pflc/benchmark/cases.py` | 真值生成 + 白名单 + `write_cases`/`load_cases`/`check_cases_frozen`（**M4 主战场**） |
| `src/pflc/benchmark/runner.py` | 四套件实现 + 门槛下发 + 退出码（**M4 §三 #4 改这里**） |
| `tools/gen_samples.py` | **`--force` / `--check` 生成器形态的参照模板**（M4 §三 #1 照此写） |
| `tests/test_benchmark.py` | 基准守门（探活 / 位级一致 / 空分母 / 门槛）；**M4 §三 #4 补 `overall` 探活** |
