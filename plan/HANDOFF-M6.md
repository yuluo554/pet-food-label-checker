# HANDOFF-M6：发布（GitHub 公开仓库 + Release 附产物）

> 交接快照。上一棒 = M5（桌面交付，已完成并验证）。
> **新对话怎么开**：`/goal 读取 "<项目绝对路径>\plan\HANDOFF-M6.md" 继续完成任务`
> （启动命令里的绝对路径由用户侧拼出；**库内一律只写相对路径** `plan/HANDOFF-M6.md`。）

---

## 一、当前进度（M0–M5 已完成并验证）

| 项 | 状态 |
|---|---|
| 规则包 | ✅ **45 条**（`label` 8 / `nutrition` 32 / `claim` 5），**43 `verified` + 2 `pending`** |
| 解析层 | ✅ FR-01 全覆盖（M2 收口） |
| 判定引擎 | ✅ 三类判定齐备 + 双重门控 + 维度聚合 + 分派表结构性守门 |
| 基准 | ✅ **四套件全部达标**（detection 12/12 误报 0.0 · overall 16/16 · boundary 60/60 · traceability 43/43） |
| 冻结真值库 | ✅ 入仓 `data/benchmark/cases.json`（16 用例）；基准**真的读它**（`truth_source=frozen`） |
| **桌面交付** | ✅ **M5 完成**：onedir **双树**（`dist/pflc/` GUI 110.9 MB / `dist/pflc-cli-dist/` CLI 16.5 MB），两树 `VERIFY_FROZEN_OK` |
| 测试 | ✅ **274 项**，Python 3.8.8 与 3.12.10 双解释器全绿 |
| 守门 | ✅ 六道 OK 标记门 + **`VERIFY_FROZEN_OK`**（新）+ **`DEMO_ASSETS_OK`**（新） |
| 文档 | ✅ `plan/00`–`07` 已回填 M5 实录；`README.md` / `docs/技术报告.md` / `data/README.md` / `docs/demo/README.md` 同步 |

**M5 末态**：
`py -X utf8 -m pytest -q` → **274 passed**（3.8 / 3.12 各一遍）；
`py -X utf8 tools/verify_frozen.py --dist dist/pflc-cli-dist --selftest` → **`VERIFY_FROZEN_OK`**；
`py -X utf8 tools/verify_frozen.py --dist dist/pflc --selftest` → **`VERIFY_FROZEN_OK`**；
`py -X utf8 tools/check_demo_reproducible.py` → **`DEMO_ASSETS_OK`**；
`py -X utf8 -m pflc.cli bench` → 四套件达标（`truth_source=frozen`）。

### M5 本棒做了什么

**M5 的题眼不是"写界面"（界面 M0 起就在），而是"发行态名不副实"**——
一构建就撞出 **4 个真缺陷**，全部属"源码态绿、发行态红"这一族：

| # | 缺陷 | 为什么源码态看不见 | 修法 |
|---|---|---|---|
| 1 🔴 | **spec 入口点打断包语义**：直接指向 `src/pflc/cli.py` → 冻结后 `ImportError: attempted relative import`。**构建成功、exit 0、无警告** | 源码态跑 `python -m pflc.cli`（有包上下文） | 新增 `tools/entry_cli.py` / `entry_gui.py`；配 spec 入口门（AST 解析 Analysis 脚本） |
| 2 🔴 | **禁区扫描判据恒绿**：只匹配 `len(parts) <= 2`，6.x 把数据放 `_internal/data/`（三级深）→ 门永远看不到禁区目录 | 判据深度是隐式假设，无真实 6.x 布局就无反例 | 扫描面改"负载根下 `data/**` 任意深度"；配 6.x 树 + 干净树两组对照 |
| 3 🟡 | **CLI 包白送 87 MB 且降级提示成死代码**：两树共用 hiddenimports | 体积与提示分流都不是功能断言 | 拆 `_BENCH_HIDDEN` / `_GUI_HIDDEN`；实测 **112→17 MB**，`gui` 子命令 exit 3 实测生效 |
| 4 🟡 | **降级提示未按形态分流**：对冻结态用户也提示 `pip install`（他没 pip） | 原测试只看退出码 | 按 `is_frozen()` 分流 + **双向**断言 |

**另做实一道"声称已有其实没有"的门**：`packaging.py` docstring 声称"三处守门"，
其中"spec 文本"那道**并不存在**——本棒补上。

**又抓到一次假门（与 M4 同族）**：新增的 CI 门首版判据 `"--dist dist/pflc" in joined`
被 `dist/pflc-cli-dist` **子串包含** → 注释掉 GUI 验收步仍绿。变异验证当场抓出，
改成正则锚定完整参数。**这是本项目第三次"子串判据"假门**。

**变异验证 10 处**（全部确认变红，均留对照组），明细见 `plan/06` §M5 实录。

**新增机制**：`tools/verify_frozen.py` 的验收由构建期写下的 `_datas_report.json`
（白名单版本 + 逐份 sha256 + **该树的 `kind`/`exe_names`**）驱动，报告缺失即报错。

---

## 二、下一里程碑（M6）：发布

**M6 目标**：GitHub 公开仓库 + Release 附产物。

> ⚠️ **M6 的第一件事是"转公开三清"，属于破坏性操作，须用户授权**。
> 本棒（M5）**未接远端**（`git remote -v` 为空），故 M6 从"建远端 / 首推"开始。

`plan/06` 的 M6 DoD 共 13 条。**本棒对 M6 现状做了初测**（只登记事实，不替代 M6 收棒的逐条核对）：

| M6 DoD | 初测状态 |
|---|---|
| 干净环境验证（新 clone + 全新 venv 按 README 逐条跑通） | ⬜ **未做**。本机无干净环境；README 已含 `.[dev]` / `.[gui]` / `.[gui,build]` / `.[dev,gui,build,demo]` 四条安装通路 |
| **测试面 = 安装面** | 🔶 已有 `test_dev_extras_cover_test_imports` + `test_ci_extras_cover_every_milestone_gate`；**M5 新增的 `Pillow`（demo extra）与 `PyInstaller`（build extra）也算"测试真 import 的库"**（`check_demo_reproducible.py` / spec 用了），M6 需复核这两条是否落在 README 安装通路里 |
| 脱敏四步 + 构建产物本体扫描 + 提交元数据邮箱检查，留档 `plan/RELEASE-M6.md` | ⬜ **未做**。本棒 `--tracked` 实测 HARD 0 / REVIEW 0（见 §五）；**但 `dist/` 在 `.gitignore` 内，构建产物本体扫描需另立通路**（不能只扫已跟踪文件） |
| 转公开三清（全历史 0 硬门 / 坏 blob 已修 / 失败 run 已删）→ 再切 visibility | ⬜ **未做**。历史审计 `--all` 仍报 `a214320` 的旧文本（见 §六） |
| CI 首跑绿（四矩阵 + **`package` job**）；`gh run list` 对账 push 数 = run 数 | ⬜ **未做**。**M5 首次为 CI 加了 `package` job（真构建 + 两树冻结验收 + 演示物料可复现），它从未在 CI 上跑过** |
| 产物与发布源码同基线（`git diff <基线>..HEAD -- src/ tools/*.spec` 为空） | ⬜ 未做 |
| 发布 zip 打包确定性（ZIP_STORED + 条目 sort + 固定 date_time） | ⬜ **未做**。注意：本棒的 `dist/` 是 PyInstaller 直接产物，**不是**发布 zip |
| Release 附件 ASCII 名 + sha256 留档；真下载附件复核 | ⬜ 未做 |
| README「下载即用」+「已知环境问题」节；GIF 演示；mermaid 架构图 | 🔶 **M5 已补两件**：「已知环境问题」节已有（7 条）；GIF 演示已嵌入并已重生成真实判定态；mermaid 架构图已有。**「下载即用」节待 M6 补**（需真实 Release 链接） |
| topics 配置 + 回读确认 | ⬜ 未做 |
| 发布后全新 clone 复核 | ⬜ 未做 |
| `plan/HANDOFF-FINAL.md` | ⬜ M6 出口门 |

---

## 三、M6 起始待办（按依赖顺序）

1. **先决定发布物是什么**（本棒未定，M6 必须定）：当前 `dist/` 是两棵**独立的树**
   （GUI 110.9 MB / CLI 16.5 MB），而 M6 DoD 写"发布 zip 打包确定性（ZIP_STORED…）"——
   需要决定：是**各打一个 zip**、还是**只发 GUI 树**（CLI 是 GUI 包的附属通路）、
   还是**分两个 Release 附件**。此事影响 DoD 第 7/8 条的判据写法。
2. **构建产物本体扫描**（DoD 第 3 条）：`dist/` 在 `.gitignore` 内，`audit_desensitize.py --tracked`
   **看不到它**。需另立通路扫**产物本体**（exe 与内嵌数据）——注意 M5 已实测的形态：
   `docs/demo/` 的 PNG 里曾烤进本机绝对路径而审计完全看不到（§五）。
3. 接远端 + 首推 → **等 CI 首跑**（四矩阵 + `package` job），对账 `gh run list`。
   **`package` job 是 M5 新加的、从未跑过**，首跑很可能暴露环境差异（PyInstaller 在
   windows-latest 上的行为、`_stripped_env` 在 CI 里的变量集是否够）。
4. 转公开三清（**破坏性，须用户授权**：`filter-repo` + 强推）→ 再切 visibility。
5. 干净环境验证（新 clone + 全新 venv 按 README 逐条跑通）。
6. 补 README「下载即用」节 → topics → 发布 → 真下载附件复核。
7. 回填 `plan/06` M6 DoD、`plan/00` M6 实录、`data/README.md` M6 末态；写 `plan/HANDOFF-FINAL.md`。

---

## 四、既定口径清单（K 清单，动了会打挂基准）

> 后续任何改数据/加类目/改接口的动作，**先对照本表，改完重跑基准确认不回退**。
> 完整版见 `plan/07-交付对标与决策记录.md` §四。**M5 新增 K31–K34**。

| K | 口径 |
|---|---|
| K1 | 三态 `compliant`/`noncompliant`/`not_provided` + `skipped`/`unknown`；无条件义务缺失 = noncompliant |
| K2 | **双重门控**：`status`（数值）门控判定路径，`clause_status`（条款号）只管可证性 |
| K3 | 门控作用域三值 `label`/`nutrition`/`claim`，各只校验自己引用的条目 |
| K4 | 零生效维度不参与聚合 + `dimension_excluded` 原因码 |
| K5 | 数值口径一处定义；**零政策字面量门禁**扫 `src/pflc/`（含 GUI）与 `tools/`；豁免：整数且 < 20，非整数不豁免 |
| K5b | **数值基准**：GB/T 理化指标**以干物质计**，标签保证值是 as-fed → `basis=dry_matter` 先换算再比 |
| K5c | **数值渲染**一律 `format_decimal()`；禁 `str(Decimal.normalize())` |
| K6 | 规则包冻结：禁手改，改走生成器；`--check` 位级一致 |
| K7 | 退出码三语义：`0` 达标 · `1` 未达标 · `2` 用法错误 · `3` 缺 GUI 依赖 |
| K8 | 溯源完整性硬约束：不满足**拒导** |
| K9 | 报告双轨**单一渲染源** `report_sections()`；逐字节可复现、禁活动外链 |
| K10 | GUI 零判定逻辑 AST 三条齐上；同一豁免口径在引擎与界面两侧都要对齐 |
| K11 | 单件与批量共用 `check_card` 分派点 |
| K12 | 失败件 ≠ 违规：`scan_error`/`failed`，**不改退出码** |
| K13 | 两轮对账配对主键 = `file:<相对路径>` |
| K14 | 基准分样本驱动 + 规则驱动两层；四套件探活齐备；期望锚定冻结真值库 |
| K15 | 验收门槛随 manifest 下发（缺失 → exit 2，不回落代码默认值） |
| K16 | 空分母 `not_enabled=true` + notes 声明 + exit 1 |
| K17 | 覆盖登记"总数/已核对数/采样数/清单"**双数** + 非穷举声明 |
| K18 | 假品牌名白名单硬断言；真实品牌数据与合成基准严格隔离（**两侧齐备**） |
| K19 | 免责声明强制出现在每份报告与 GUI"关于"页 |
| K20 | 全本地零上传：核心层零第三方依赖、无网络库 |
| K21 | 冻结态自检断言数据目录落在 exe 目录内；非冻结态返回 `None` |
| K22 | 编码三层加固；覆盖所有会打印的入口含 `tools/` |
| K23 | 惰性导入 `try` 包住**从 import 到调用完成**整条路径，缺依赖走 exit 3 |
| K24 | 字节冻结分层：`eol=lf` + CR 守门（按扩展名豁免二进制件） |
| K25 | **宣称词表单一来源**：只从规则包实算；判定层在唯一分派点对齐 |
| K26 | **字段降级口径**：有值但无法映射一律**丢弃 + 原因码** |
| K27 | **解析层字段表纪律**：别名表只放真正词面；单位匹配**最长优先** |
| K28 | **判定 kind 分派表结构性断言**；"键存在"不是证据 |
| K29 | **冻结真值库是基准的期望来源**：入仓 + `--check` 位级守门 + 真有调用方 + **必须随包** |
| K30 | **文档里的实测指标必须可核证**：判据落**结构位置**，不落"文件里出现过这串字" |
| **K31** | **发行态必须与源码态分开验收**：构建成功 ≠ 产物可用。spec 的 Analysis 入口**只准是 `tools/entry_*.py`**（绝对导入进包内 `main`）；直接指向 `src/pflc/*.py` 会以顶层脚本运行 → 冻结态 `ImportError`（**而构建仍 exit 0**） |
| **K32** | **"随包"清单与"有意不随包"清单都显式登记、互不重叠，且豁免项必须在禁区名单里**（只在豁免不在禁区 = 两道门全开 = 放任）；口径一致性在**模块导入期**校验。`samples` 入包、`knowledge` 不入包 |
| **K33** | **构建后验收由构建事实驱动**：构建期写下 `_datas_report.json`（白名单 + 逐份 sha256 + `kind`/`exe_names`）；**报告缺失即报错**。发行产物是**两棵独立的树**（CLI 包特意不含 PySide6，靠 exit 3 分流） |
| **K34** | **脱敏审计扫不到的地方要在源头守**（PNG 里的本机路径）；判据形态要防误报（盘符路径不能用 `":/"` 判，`https://` 会误伤） |

---

## 五、本机环境坑（只写实测过的）

| 坑 | 实测事实与处置 |
|---|---|
| 🔴 **裸 `python` 是 Windows Store 桩，静默不执行** | `python -c "print(1)"` → **exit 49，无任何输出**。**后果**：用它跑变异脚本会"成功返回"却什么都没改——看起像"改坏了还绿"，险些误判成假门。**处置**：一律 `py -X utf8`；**变异验证前先 `py -c "print(1)"` 确认通道可用** |
| Python 通道 | `py -0p` → **3.8-64** 与 **3.12-64**。项目底线 3.8；发布构建固定 `py -3.12`（PyInstaller **6.22.3** 已装） |
| **`Path.write_text(newline=)` 是 3.10+ 参数** | 3.8 上直接 `TypeError`。**已踩中四次**（M5 变异脚本又踩一次 → 变异没注入而 pytest 照样绿，险些误判）→ 一律 `open(..., newline="\n")` 或 `write_bytes` |
| **`ast.unparse` 是 3.9+** | 3.8 上 `AttributeError`。源码片段抽取用 `ast.get_source_segment`（M5 实测） |
| **`py -X utf8 -m pytest -q` 偶发 access violation** | 3.8 全量收集时偶发崩在 pytest 断言重写器。处置：先清 `__pycache__` + `.pytest_cache` 再跑；单次崩了别急着改代码，复跑确认 |
| 中文控制台编码 | 跑命令一律 `py -X utf8`；入口已加 `_ensure_utf8_stdio()` 探针 |
| **Git Bash `/tmp` 与 Windows Python 路径不通** | 临时文件一律用**工作区相对路径** `.tmp/`（已在 `.gitignore`） |
| pip 被系统代理污染 | `NO_PROXY="*" no_proxy="*" py -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <pkg>` |
| 大文件 curl 同步超时 | `-C -` 断点续传 + `run_in_background` |
| **`py` 启动器无视已激活 venv** | README 的 venv 段落一律写 `python -m pip ...` |
| PySide6 版本上限 | 3.8 实测可解析最高 **6.6.3.1**；`gui` extra 写 `>=6.5,<6.7` |
| PyInstaller 分档 | 打 GUI 必须 **≥6**；只打 CLI 的老解释器用 `>=5.13,<6` |
| offscreen 中文字体 | Qt 6 起不随附字体且 offscreen 不扫系统字体目录 → `load_cjk_font()` 显式 `addApplicationFont`；路径由 `WINDIR`/`SystemRoot` 推导 |
| **PyInstaller 6.x 用 `_internal/` 布局** | 数据在 `dist/<name>/_internal/data/`，exe 在 `dist/<name>/`。**判据写死深度会恒绿**（M5 实测，见 K31/K32 族） |
| **构建成功 ≠ 产物可用** | M5 实测：spec 入口点错 → 构建 exit 0、日志无警告，exe 一启动就 `ImportError`。**必须真跑 exe 才能发现** |
| **两个发行树形态不同** | `dist/pflc/` 无 `check`/`bench` 子命令入口；`dist/pflc-cli-dist/` 无 GUI。验收脚本**不能靠猜目录名** |
| **脱敏审计按扩展名跳过二进制** | `EXCLUDE_SUFFIXES` 含 `.png`/`.gif`/`.exe` → 这些文件里的本机路径**它看不到**。M5 实测：`docs/demo/` 的 PNG 曾烤进本机绝对路径而审计全绿 |
| **变异验证要留对照组** | 只看到"改坏了测试还绿"不能下结论——要同时改一个**已知有探活的同类**确认手法有效。**但先确认通道可用**（裸 `python` 坑） |
| **判据别写成"文件里出现过这串字"** | 实测三种假门形态：整段注释掉 / 手改数值 / **子串包含**（`dist/pflc` ⊂ `dist/pflc-cli-dist`）。判据要落**结构位置**；写 `in` 判断时自问"有没有更长字符串把它包含进去" |
| 🔴 **`--tracked` 审计看不到"尚未 `git add` 的新文件"** | `scan_tracked()` 按 `git ls-files` 枚举。**处置**：涉及"新写文档/新加文件"的收棒，**必须先 `git add` 再跑 `--tracked`**（或跑 `--all` 自查） |
| **演示素材生成期要脱敏** | 界面上的绝对路径会被烤进 PNG，而审计看不到 → 生成器替换为占位符 + 硬断言（K34） |

---

## 六、关键命令速查

```bash
# --- 执行通道自检（先跑这个）---
py -X utf8 -c "print('channel-ok')"          # 必须打印；裸 python 会 exit 49 静默失败

# --- 测试与守门（每次收尾必跑）---
py -X utf8 -m pytest -q                      # 全量（应 274 passed）
py -3.12 -X utf8 -m pytest -q                # 双解释器验证
py -X utf8 tools/transcribe_clauses.py --check   # TRANSCRIBE_OK
py -X utf8 tools/gen_rulesets.py --check         # FROZEN_RULESET_OK
py -X utf8 tools/gen_cases.py --check            # FROZEN_CASES_OK
py -X utf8 tools/gen_samples.py --check          # FROZEN_SAMPLES_OK
py -X utf8 tools/audit_desensitize.py --selftest # 阳性 4 / 阴性 5 / 放行 1 / 豁免边界 6
py -X utf8 tools/audit_desensitize.py --tracked  # HARD 0 / REVIEW 0 → DESSENSITIZE_AUDIT_OK
py -X utf8 tools/smoke_cli.py                    # SMOKE_CLI_OK
py -X utf8 tools/check_demo_reproducible.py      # DEMO_ASSETS_OK（M5 新增）

# --- 数据层（改数据后必跑）---
py -X utf8 tools/transcribe_clauses.py --force   # 改 spec.json 后重转录
py -X utf8 tools/gen_rulesets.py --force         # 重生成规则包（内部先产真值库再实算覆盖）
py -X utf8 tools/gen_cases.py --force            # 重生成真值库（入库件）

# --- 数据状态与端到端 ---
py -X utf8 -m pflc.cli diagnostics               # 应 exit 0
py -X utf8 -m pflc.cli bench                     # 四套件达标；看 truth_source=frozen
py -X utf8 -m pflc.cli check data/samples/label-demo-ok.txt -v
py -X utf8 -m pflc.cli report data/samples/label-demo-missing.txt --out output/

# --- M5/M6 打包通路 ---
py -3.12 -m PyInstaller --version                # 6.22.3
py -3.12 -m PyInstaller --clean --noconfirm tools/pflc.spec
py -X utf8 tools/verify_frozen.py --dist dist/pflc-cli-dist --selftest   # VERIFY_FROZEN_OK
py -X utf8 tools/verify_frozen.py --dist dist/pflc --selftest            # VERIFY_FROZEN_OK
py -X utf8 tools/make_demo_assets.py --out docs/demo    # 重生成演示物料（改素材后）
```

**环境变量**：`PFLC_DATA_DIR` 可把数据目录指到别处（测试与验收用）。

---

## 七、一条**已知的、非本棒引入**的历史审计发现（如实记录，不掩盖）

`tools/audit_desensitize.py --all`（含历史模式）实测 **HARD 1 / REVIEW 2**，**全部来自历史提交**：

| 命中 | 位置 | 性质 |
|---|---|---|
| `user_name_signature` HARD | 提交 `a214320` 的 `plan/HANDOFF-M2.md` | 那版 HANDOFF 的"启动命令"示例里带了本机用户名的绝对路径 |
| `generic_email` REVIEW | 提交 `a214320` / `e4ebc2c` | 同上，原文快照的转载站点邮箱 |

**处置现状**：工作区与 `--tracked` 实测 **HARD 0 / REVIEW 0**；`plan/HANDOFF-M3/M4/M5/M6.md` 实测**零命中**。
但 **git 历史不可变**，故 `--all` 会一直报它。

**为什么不动它**：修它需要 **git 历史重写**（`filter-branch`/`filter-repo` + 强推），
这是**破坏性且需用户授权**的操作，且本项目**尚未接远端**（未推送 = 无外泄面）。
**这正是 M6「转公开三清」要处理的事**（见 M6 DoD 第 4 条）。

**口径纪律**：本项目声明的 DoD 审计门是 `--tracked`（**当前全绿**）。`--all` 是更强的自查模式，
其 HARD 已在此如实登记，**不得把它当作"已修"或"不存在"**。

---

## 八、绝对禁止（M0–M6 全程）

- **不得虚报 CI**：无远端时 DoD 只能写"**本地等价校验通过**（未接远端，CI 待首推验证）"；**未推送 = 未跑 CI**。
  **M5 新增的 `package` job 从未在 CI 上跑过**——不得写成"CI 已验证发行态"。
- **不得编造标准内容**：核对没覆盖的条款**不建规则**；数值拿不到就 `pending`，**绝不臆造**。
- **不得手改冻结产物**：规则包/夹具/**真值库**改了走生成器重生成。
- **不得把"没做"记成"不用做"**：无条件义务缺失 = 不符合。
- **不得把"解析不到"当"合规"或"违规"**：显式降级 + 原因码。
- **不得在仓库树内跑冻结态验收**：CWD 上溯会命中仓库 `data/`。
- **不得在公开文档写姊妹项目的领域具体名词**：一律用"方向级描述"。
- **里程碑收尾不写 HANDOFF 就结束对话**：实测必然漏。
- **不得让门禁"看起来绿"而实际空转**：任何豁免/门控口径必须配**非空转守门测试**，且同类口径一次对齐全部实例。
- **不得只验豁免函数本身**：要验"调用方有没有真的调它"。
- **不得把"有测试"当"测试有效"**：**每个新门都要做变异验证**（改坏 → 必须变红），且留**已知有效的对照组**。
- **变异验证前先确认执行通道可用**：裸 `python` exit 49 静默不执行，会让变异脚本"看起来没生效"。
- **不得把判据写成"文件里出现过这串字"**：三种实测假门形态——整段注释掉 / 手改数值 / **子串包含**。
  写 `in` 判断时**自问"有没有更长字符串把它包含进去"**。
- **不得照抄上一棒的结论当事实**：交接文档的口径同样要被核对。
- **不得让"源码态绿"当"发行态绿"**：构建成功 ≠ 产物可用（M5 实测：exit 0 而 exe 一启动就崩）。
- **不得把"审计没报"当"没问题"**：审计按扩展名跳过二进制（PNG/exe），**它扫不到的地方要在源头守**。

---

## 九、参考文档索引

| 文档 | 用途 |
|---|---|
| `plan/00-README总览.md` | 项目总览 + **M0–M5 实录** |
| `plan/02-需求解读.md` | 痛点→能力转译、FR 清单、边界与非目标 |
| `plan/03-架构与技术选型.md` | 分层架构、D1–D18 关键设计决策 |
| `plan/04-模块详设.md` | 逐模块接口与判定语义、**§九 打包** |
| `plan/05-数据计划.md` | 数据先行、规则包冻结形态、渠道实录 |
| `plan/06-里程碑.md` | M0–M6 目标/DoD（**M5 已标 ✅ + §M5 实录**；**M6 待做**） |
| `plan/07-交付对标与决策记录.md` | 评分对标、决策记录（含 M5 六条）、**K1–K34 既定口径**、反模式清单 |
| `data/README.md` | 数据台账（三态 + 渠道实录 + sha256 表 + **§十 M5 末态快照**） |
| `docs/技术报告.md` | 规则化方法、三态框架、基准设计、**§十一 桌面交付与冻结态验收** |
| `docs/demo/README.md` | 演示物料说明（M5 重生成 + 脱敏处置） |
| `docs/DIST-sha256-M5.txt` | **当前有效**的演示物料 sha256 留档（M0 版为历史留档） |
| `src/pflc/packaging.py` | 打包白名单 + 豁免表 + 构建后断言（**M5 主战场**） |
| `tools/pflc.spec` | PyInstaller spec（入口 / 双树分流 / datas 报告） |
| `tools/entry_cli.py` / `entry_gui.py` | **包内安全入口**（K31；缺了它冻结态一启动就崩） |
| `tools/verify_frozen.py` | 冻结产物验收（三断言 + 冻结态三连） |
| `tools/check_demo_reproducible.py` | 演示物料可复现性 + 留档对账 |
| `tests/test_verify_frozen.py` | 验收脚本判据的常驻回归（合成 dist 树驱动） |
