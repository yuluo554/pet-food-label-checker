# RELEASE-M6：发布留档（逐项命令 + 结论）

> M6 DoD 第 3 条要求的留档。每项都写**实跑命令**与**实测结论**；
> 没做的如实标"未做"，跑红的照录红（不回填美化）。
> 生成日期：2026-10-15 · 末态基线见 §六。

---

## 一、脱敏四步

"四步"= ① 工作区/已跟踪文件 · ② 全历史 blob · ③ 提交元数据邮箱 · ④ 构建产物本体。
前三步由 `tools/audit_desensitize.py` 覆盖，第四步是 M6 新增的独立通路
（审计按扩展名跳过二进制，`dist/` 又在 `.gitignore` 内，两道都看不到它）。

### 步 ①–③：审计器三模式

```bash
py -X utf8 tools/audit_desensitize.py --selftest   # 阳性对照
py -X utf8 tools/audit_desensitize.py --tracked
py -X utf8 tools/audit_desensitize.py --history
py -X utf8 tools/audit_desensitize.py --messages
py -X utf8 tools/audit_desensitize.py --all
```

| 步 | 命令 | 结论 |
|---|---|---|
| 对照 | `--selftest` | `selftest 通过（阳性 4 项 / 阴性 5 项 / 放行 1 项 / 豁免边界 6 项）`——证明扫描器真的在扫 |
| ① | `--tracked` | **HARD 0 / REVIEW 0 → `DESSENSITIZE_AUDIT_OK`** |
| ② | `--history` | **HARD 0**；REVIEW 仅 `generic_email`（见下） |
| ③ | `--messages` | **HARD 0 / REVIEW 0** |
| 全 | `--all` | `汇总：HARD 0 / REVIEW 13 → DESSENSITIZE_AUDIT_OK` |

> **纪律提醒**：`--tracked` 按 `git ls-files` 枚举，**看不到尚未 `git add` 的新文件**
> （M4 踩过）。故上述命令一律在 `git add -A` 之后跑。

### 步 ④：构建产物本体扫描（M6 新增）

```bash
py -X utf8 tools/make_release.py --dist dist --out release --check
```

三件事一起做：**确定性**（两次打包 sha256 一致）、**回读保真**（解出条目与源树逐字节相同）、
**产物本体脱敏扫描**。

| 情形 | 结论 |
|---|---|
| 目录通路 `scan_tree_body`（dist 两棵树） | **0 条 HARD** |
| zip 通路 `scan_zip_body`（最终发货字节流） | **0 条 HARD** |

**判据形态说明**（同时是踩坑记录）：按**字面量**匹配，且 ASCII 与 **UTF-16LE** 两种编码都编码一遍。
不用文本正则的原因：exe/dll/pyd 里既有窄字符串也有宽字符串，把字节当文本解码会漏 UTF-16
（每字符夹 NUL）；而"去掉 NUL 再匹配"会把本就相邻的字符拼成**假阳性**。

**实测的误报对照**：`dist/pflc/_internal/PySide6/Qt6Gui.dll` 里含 `ASUSTek COMPUTER INC`
（显卡厂商串）。裸子串判据会把它当用户名命中——故用户名判据带**边界环视**（后随字符非字母数字）。
注意：该串其实**不含** `Users\<用户名>`，靠前缀即可排除；真正的边界由
`Users\<用户名>Other` 这类样本负责（`tests/test_release.py` 两条测试分工明确）。

### 未豁免的 REVIEW 命中（如实登记）

`--history` 有 13 条 REVIEW，**全部是同一个值**：原文快照
`data/knowledge/raw/moa-20-2018-annex3/reprint-feedchina.txt` 里**转载站点自己的公开联系邮箱**。

为什么历史模式消不掉它：豁免表 `EXEMPTIONS` 绑定的是**路径 glob**，而历史模式的
location 是 `history:<sha>`——没有路径可比。**这是设计如此**（豁免只作用于 tracked 模式），
不是漏修。该文件在 `--tracked` 模式下**已被正确豁免**（实测 REVIEW 0）。

---

## 二、发布物形态决策（HANDOFF-M6 §三.1 要求先定的那件事）

**决策：两棵树各打一个 zip，分两个 Release 附件。**

| 附件（ASCII 名） | 内容 | 本机实测 |
|---|---|---|
| `pflc-gui-windows-x64-0.1.0.zip` | 桌面版 `pflc.exe`（内嵌 PySide6） | 165 文件 / 110.9 MB |
| `pflc-cli-windows-x64-0.1.0.zip` | 命令行版 `pflc-cli.exe`（**特意不含 Qt**） | 23 文件 / 16.5 MB |

**为什么不合成一个大包**：两棵树是**独立的发行形态**（K33）。CLI 包对 `gui` 子命令走
**exit 3** 并提示改用桌面版；把 PySide6 塞进 CLI 包会让这句提示变成死代码，还白送约 87 MB。
分开发布让"下哪个"显式化：只要命令行核验的用户不必下 110 MB。

**附件名规则**：纯 ASCII + 点明平台 + 带版本号（DoD 第 8 条）。常驻门
`test_release_asset_names_are_ascii` / `test_release_asset_names_encode_target_platform` 守这两条。

### 发布用的是哪一份产物（以及 CI 与本机产物为何不同）

**本机构建的产物**（`dist/`，`py -3.12 -m PyInstaller --clean --noconfirm tools/pflc.spec`）——
它过了冻结态验收（两树 `VERIFY_FROZEN_OK`，含真跑 exe）且与入仓留档**同一棵树**（哈希逐条对上）。

CI 的 package job 会**另建一棵树**，两者文件数不同（本机 CLI 23 / GUI 165；runner 66 / 208）。
实测差异**已被逐文件清单定位**：多出来的 43 个文件**全是 Universal CRT**
（`ucrtbase.dll` + 42 个 `api-ms-win-*.dll`）。原因：

* 本机 Windows 把 UCRT 作为**系统组件**放在 `System32`，PyInstaller 视其为"系统 DLL"**不收**；
* CI 的 windows-latest runner 上这些库的可解析位置不在 `System32`，于是被**收进包**。

**两者都是合法的发行形态**（Windows 10+ 自带 UCRT），差异纯属构建环境。本棒据此做的处置：

1. 把**逐文件清单打进 stdout**，让"文件数对不上"在 CI 日志里**可核**而不是靠猜；
2. 留档增记**树 sha256**，使"这个 zip 从哪棵树打的"可核证；
3. 对账判据区分"同一棵树"与"另一棵树"两种情形（见 §五·②）。

> **已知取舍（如实登记）**：发布的 zip 取自**本机树**，因此**不含** UCRT 那 43 个文件，
> 依赖目标机自带 UCRT（Windows 10 及以上满足）。若将来要覆盖更老的 Windows，
> 应在 CI 构建并从 CI 产物发布（届时留档改记 CI 树的摘要）。


---

## 三、提交元数据邮箱检查

```bash
git log --format="%ae%n%ce" --all | sort -u
git config user.email
```

| 时点 | 实测 |
|---|---|
| 重写前 | 私人邮箱（QQ 域名，出现在**全部 12 个提交**的作者+提交者字段；词面故意不在此复写——写它就是又把它公开了一次） |
| 重写后 | `282769740+yuluo554@users.noreply.github.com`（GitHub noreply 形态） |
| 本地 `user.email` | 已同步改为 noreply，防后续提交写回 |

noreply 正是审计器 `_is_exempt_email()` 已豁免的目标形态——**审计口径与修法同向**，
不是"改完再给审计开豁免"。

### 本棒自己引入又修掉的一处泄露（第二次重写）

**经过**：写本节初版时，把重写**前**的私人邮箱**词面**直接抄进了本文件——
**清它的动作本身又把它公开了一次**。该词面随 `plan/RELEASE-M6.md` 一起被 commit 并 push 到
公开仓库。文档回填后跑 `--tracked` 审计，被 `generic_email/REVIEW` 抓出。

**处置**：

1. 把本文件的词面改为掩码描述（本节现在这个样子）；
2. 再跑一次 `git filter-repo --replace-text`（表达式表从 git 历史实算词面，不写死）
   把该词面从**全历史**清掉；
3. `git push --force origin main` + `git push --force origin v0.1.0`
   （`filter-repo` 会移除 remote，需重新 `git remote add`——这是它的既有行为）。

**force-push 后的残余对象（如实登记，不当作"已修"）**：旧提交已不在任何 ref 上，
但 GitHub 仍保留**不可达对象**——按 SHA 直连**仍能匿名读到**该 blob（实测：
`GET /repos/.../contents/plan/RELEASE-M6.md?ref=<旧SHA>` 返回 200 且内容含该词面）。
删仓重建可清除，但需要 `delete_repo` 权限（本机 token 无此 scope）。

**该残余是否构成泄露面——实测判定为"非增量"**：同一邮箱**早已公开**在该账号的**其他公开仓库**
的提交元数据里（匿名 API 实测：`structural-strengthening-checker` / `dsh-prompt-polisher` /
`dsh-pipeline` / `siteguard` 四个公开仓的作者邮箱均为它）。故本仓库的这个残余
**不新增任何暴露面**，删仓重建的隐私收益为零。

**结论**：残余**存在**，但**不增量**。要彻底清除需 `delete_repo` 权限或联系 GitHub Support。
本棒选择"如实登记 + 把词面从可达历史与该文件清掉 + 后续不再复写词面"，
而不是"删仓重建"——后者在当前权限下做不到，且收益为零。
**教训（值得写进反模式清单）：清理敏感信息时，留档里绝不能复写被清理的词面本身。**

---

## 四、转公开三清（破坏性操作，执行时机与前置）

| 清 | 项 | 结论 |
|---|---|---|
| 一清 | 全历史 0 硬门 | ✅ 重写后 `--all` → **HARD 0**（原 HARD 3） |
| 二清 | 坏 blob 已修 | ✅ 两处本机用户名路径替换为中性占位符 |
| 三清 | 失败 run 已删 | ✅ 首跑失败 run 在**首次推送前**不存在；首跑红后按"照录不抹除"对待（见 §五） |

### 重写实施

工具：`tools/rewrite_history_m6.py`（自带前置断言：**缺备份 / 有远端即拒跑**）。
重写引擎：`git filter-repo 2.47.0`。

```bash
py -X utf8 tools/rewrite_history_m6.py            # 演练（只打印将执行的动作）
py -X utf8 tools/rewrite_history_m6.py --apply    # 真跑
```

清掉的内容：
* `plan/HANDOFF-M2.md` 的 `C:\Users\<用户>\AppData\...\Python38`；
* `plan/HANDOFF-M5.md` 的 `/c/Users/<用户>/AppData/.../WindowsApps/python`；
* 全部提交的作者/提交者邮箱（12 个提交）。

**两个实施细节值得记**：

1. **邮箱改写走 `--email-callback`，不用 `.mailmap`**。mailmap 每行都要写成
   `<新邮箱> <旧邮箱>`——把私人邮箱**原样写进一个仓库文件**；那文件要么入仓（自曝，
   等于没脱敏），要么留工作区（下一个人 `git add -A` 就带上）。callback 的目标邮箱
   算在 `.tmp/`（`.gitignore` 内）的临时脚本里，零残留。实测重写后工作区**无 `.mailmap`**。
2. **时机**：本棒开工时 `git remote -v` 为空 = 旧副本无人持有 → **无强推面**。
   先在一次性 clone 上演练（`.tmp/rw-probe2`），确认 HARD 3→0 且邮箱形态正确，才动真仓库。
   前置备份：`git bundle create .tmp/backup-pre-m6.bundle --all`（12 rev / 9 MB，
   `git bundle verify` 报 "records a complete history"）。

原 HARD 3 的具体形态（重写前如实记录）：

| 命中 | 位置 | 性质 |
|---|---|---|
| `user_name_signature` HARD | `a214320:plan/HANDOFF-M2.md` | 启动命令示例里的本机用户名绝对路径 |
| `user_name_signature` HARD ×2 | `af65d1a` / `d685a96:plan/HANDOFF-M5.md` | `which python` 实测输出里的同一路径 |

---

## 五、CI 首跑（诚实口径：这一节按实测照录）

### 首跑 run `38702307047`（2026-10-15T07:57:48Z，commit `e3adf48`）

**结果：7 个 job（test×3 + test-gui×3 + package×1），4 绿 3 红。**

| job | 结论 |
|---|---|
| test (windows / py3.8) | ✅ success |
| test (windows / py3.12) | ✅ success |
| test (ubuntu / py3.12) | ❌ **failure** |
| test-gui (windows / py3.8) | ✅ success |
| test-gui (windows / py3.12) | ✅ success |
| test-gui (ubuntu / py3.12) | ❌ **failure** |
| package (windows / py3.12) | ❌ **failure** |

**三个红全是"本机绿、CI 红"一族**（正是"必须真上 CI"的价值所在）：

#### ① test / test-gui（ubuntu）：新门的判据张冠李戴

ubuntu runner 的仓库路径是 `/home/runner/work/<repo>/<repo>`，于是
`repo_path_segments` 含 `home`/`runner`/`work`；而 runner 上**用户名恰好是 `runner`**。
新加的边界阴性对照样本 `Users\runnerOther` 里的 `runner` 会**合法**命中
`repo_path_segment`（REVIEW 级，与边界无关），而测试却断言"命中列表为空"——
把另一条判据的**正确**行为当成了失败。

**修法**：判据只锚 `user_name_signature`，不判"一条都不命中"。

#### ② package：留档对账要求了做不到的事

首版 `test_shipped_release_ledger_matches_archives` 断言"重打一个 zip，哈希必须等于留档"。
**PyInstaller 产物含构建期信息（PE 时间戳等），跨次重建不逐字节可复现**——实测：

* 同一台机器两次构建，`pflc-cli.exe` 的 sha256 不同（`813da5e1…` / `9a355663…`）；
* CI runner 上收集到**更多运行库**：本机 CLI 23 / GUI 165 文件，runner **66 / 208**（两树各多 43 个）。

**修法**：留档增记**树 sha256**（说清"这个 zip 从哪棵树打的"）；对账分两种情形——
**树一致**则 zip 哈希与文件数逐条强对账；**树不一致**（CI/换机重建）则只验结构口径
（附件名齐备 / ZIP_STORED / 条目排序 / 回读保真）。确定性只对"**同一棵树**打两次"成立，
不对"跨次重建"成立——把这两件事分开，判据才既可证伪又不在 CI 上假红。

#### ③ 复审发现的连带问题：REVIEW 级不该阻断

①的根因还牵出第二层：产物扫描当时把 REVIEW 级也当阻断项。`repo_path_segment`
的取值**随构建环境变化**，若 REVIEW 也阻断，同一仓库在不同 runner 上会
**时红时绿**（环境决定的假红）。改为**只 HARD 阻断**，REVIEW/advisory 打到 stderr
供人工看（与 `audit_desensitize` 的分级语义一致）。

### 一处自查修正：首跑 job 数（"计数当轮实测，别抄"）

初版留档把首跑写成"8 个 job，5 绿 3 红"。**这是错的**——复核时用两路独立证据校正为
**7 个 job / 4 绿 3 红**：

1. **workflow 定义**（`py -X utf8` 解析 `ci.yml`）：`test` 3 + `test-gui` 3 + `package` 1 = **7**；
2. **API 实测**（未删的修复 run `38704584927`）：`[.jobs[] | .conclusion] | group_by(.)`
   → `{"success": 7}` = **7**。

**根因 = 抄了一个印象中的数字，没当轮实测**（本项目自己的纪律："计数当轮实测，别抄上一棒"）。
留档口径已全仓同步修正（`plan/00`·`06`·`07`·`HANDOFF-FINAL`·`docs/技术报告`），
并在本节留痕说明修正过程——**"首跑红"要照录，自己的计数错也要照录**。

### 复跑与 run/push 对账

**末态：7/7 全绿**（run `38709300215`，commit `8230548`）。

`gh run list` 对账（逐提交配对，实测）：

| 推送 | run id | 结论 |
|---|---|---|
| 首推（15 提交，`e3adf48`） | `38702307047` | ❌ 首跑红 → **已删**（转公开三清之一） |
| `b0e82fb`（修 3 缺陷） | `38704584927` | ✅ |
| `f6503d1`（发布留档） | `38705277036` | ✅ |
| `ef76135`（修自引入泄露） | `38707310951` | ✅ |
| `815b77a`（文档回填） | `38709033624` | ✅ |
| `8230548`（基线 SHA 补记） | `38709300215` | ✅ 7/7 |

**一个如实登记的细节**：run 数（8）**多于** main 分支的推送数（6，含已删的首跑），
因为 **tag 推送也会触发 CI**——`.github/workflows/ci.yml` 的 `on: push` 没有分支过滤，
推 `v0.1.0` 时同样跑一遍（实测 `f6503d1` / `ef76135` / `815b77a` 各有 main 与 tag 两条 run）。
**这不是缺陷**（tag 也指向真实提交，跑一遍 CI 是合理的），但"run 数 = push 数"这个
等式**并不精确成立**——精确的说法是"**每个 main 分支的提交都有对应的绿 run**"，
逐提交配对见上表。

### 残余对象（见 §三末）与 visibility

仓库当前 **PUBLIC**；发布基线 = **tag `v0.1.0`**（权威值用 `git rev-list -n1 v0.1.0` 现取）。
tag 之后的提交只改文档（`plan/` / `docs/` / `README.md`），**`src/` 与 `tools/pflc.spec` 未动**
（`git diff v0.1.0..HEAD -- src/ tools/pflc.spec` 为空），故 zip 与留档仍逐条一致。

上表里的 SHA 是**历史事件记录**（每行对应一次已发生的推送），保持原值；
"当前基线"则一律以 tag 现取，**不写死 SHA**——本棒已做过两次历史重写，写死的值必然过期。

---

## 六、末态基线

| 项 | 实测值 |
|---|---|
| 提交数 | 16（`git rev-list --all --count`） |
| 全量测试 | **297 passed**（Python 3.8.8 与 3.12.10 各一遍） |
| 守门标记 | `TRANSCRIBE_OK` / `FROZEN_RULESET_OK` / `FROZEN_CASES_OK` / `FROZEN_SAMPLES_OK` / `DESSENSITIZE_AUDIT_OK` / `SMOKE_CLI_OK` / **`RELEASE_PACK_OK`**（新） / `VERIFY_FROZEN_OK`（两树） / `DEMO_ASSETS_OK` |
| 脱敏 | `--tracked` HARD 0 / REVIEW 0；`--all` **HARD 0** |
| 冻结产物 | `dist/pflc-cli-dist` 与 `dist/pflc` 两树 `VERIFY_FROZEN_OK` |
| 发布物 | `docs/DIST-sha256-M6.txt`（含 zip sha256 + 文件数 + **树 sha256**） |

**诚实口径**：CI 类的 DoD 据实写。首跑失败已按实照录于 §五（run id + 失败面 + 根因 + 修法），
**未抹除、未回填美化**。复跑结论见下节（在公布 Release 前于本节补记真实 run id 与结论）。

---

## 七、二次迭代（2026-10-20）：安装面缺陷与修复

> 本节记录 M6 之后的一次**实质缺陷修复**。发布物（tag `v0.1.0` 与两个 zip 附件）
> **未动**——本轮不重新打包、不发 Release。

### 7.1 缺陷（实测）

`pip wheel .` 产出的 wheel **一个数据文件都没有**（`data/` 在包外）：
83,083 B / 23 条目 / `data entries: 0`。干净 venv 装完后：

```
data_dir()  = <venv>\data          is_dir() = False
pflc diagnostics → "manifest：缺失" / "共 0 条"   → exit 1
pflc check <文件> → "整体结论：未评估"            → exit 0   ← 零规则却报成功
pflc bench        → "配置错误：…thresholds 节缺失" → exit 2
```

**为什么 CI 全绿**：三个 job 全部 `pip install -e ".[dev]"`；editable 安装下
`repo_root()` 命中仓库根，`data/` 正常。`grep -rn "pip wheel\|pip install \."`
在 workflow / tests / tools 里 **0 命中** —— 这个形态从来没被验过。

### 7.2 修复（DEC1 = A / DEC2 = A / DEC3 = B / DEC4 = B）

| # | 动作 | 文件 |
|---|---|---|
| 1 | `data/{rules,benchmark,samples}` → `src/pflc/data/`（`data/knowledge` 留在仓库根，仍不随包） | 目录（`git mv`） |
| 2 | `data_dir()` 加**包内分支**，排在 `repo_root()` 之前；冻结态两条分支语义未动 | `src/pflc/data_paths.py` |
| 3 | `build_datas()` / `data_manifest()` / `assert_no_extra_data()` 改按**包内数据根**取源，datas 目标仍是 `data/<name>`（冻结态布局不变）；`assert_no_extra_data` 改为**两棵树都扫** | `src/pflc/packaging.py` |
| 4 | 新增 `[tool.setuptools.package-data] pflc = ["data/*", "data/*/*"]` | `pyproject.toml` |
| 5 | 生成器与测试的路径字面量全量同步；`.gitattributes` 的 `-text` 声明随之改到 `src/pflc/data/**` | `tools/*`、`tests/*`、`.gitattributes` |
| 6 | 新增安装面门禁：`tests/test_packaging_install.py`（5 项）+ CI `install-smoke` job（双平台） | 新增 + `ci.yml` |
| 7 | `check` 的"未评估"改判 exit 1（与 `diagnostics` 口径统一），README 退出码表补该状态 | `src/pflc/cli.py`、`README.md`、`tests/test_cli.py` |
| 8 | `license = "MIT"` + 删 `License ::` classifier；`build-system` 抬到 `setuptools>=77`（SPDX 字符串所需）→ 元数据 **零 warning** | `pyproject.toml` |
| 9 | floor `>=3.8` → `>=3.12`：`gui` 去 `<6.7` 上限、`build` extra 合并单档、CI 矩阵去 3.8、README「已知环境问题」删 3 条 3.8 条目 | `pyproject.toml`、`ci.yml`、`README.md` |
| 10 | `actions/checkout@v4→v5`、`actions/setup-python@v5→v6`（大版本已确认存在）；加 `permissions: contents: read` 与 `concurrency` | `ci.yml` |

### 7.3 验收（实测）

| 项 | 改前 | 改后 |
|---|---|---|
| wheel 数据条目 | 0（83,083 B / 23 条目） | **10**（rules 4 + benchmark 1 + samples 5） |
| 干净安装 `data_dir()` | `<venv>\data`（不存在） | `<venv>\Lib\site-packages\pflc\data`（存在） |
| 干净安装 `diagnostics` | exit 1 / 共 0 条 | **exit 0 / 8 · 32 · 5（共 45）** |
| 干净安装 `bench` | exit 2（配置错误） | **exit 0 / 四套件 `[PASS]` / `truth_source = frozen`** |
| 干净安装 `check`（合规/缺项样例） | 未评估 → exit 0 | **符合 → exit 0 / 不符合 → exit 1** |
| 元数据 warning | 2 条 `SetuptoolsDeprecationWarning` | **0 条** |
| 测试 | 297 passed | **303 passed**（新增 5 项安装面 + 1 项退出码） |

**负控已验**：删掉 `[tool.setuptools.package-data]` 后重跑
`tests/test_packaging_install.py` → **5 项全红**（其中 `test_wheel_carries_data_files`
报"数据条目 0 个（期望 10）"）。

> 负控首轮曾**假绿**：`pip wheel .` 复用了仓内陈旧的 `build/` 与
> `src/*.egg-info/SOURCES.txt`，清单里仍列着数据文件，wheel 照样带 10 个条目。
> 修法：门禁改为**从干净副本构建**（复制 `pyproject.toml` / `README.md` /
> `LICENSE` / `src/`，排除 `__pycache__` / `*.egg-info` / `build`）。这条已写进测试 docstring。

### 7.4 未做（明确不在本轮范围）

- 未重新打包、未发 Release、未动 tag `v0.1.0` 与两个 zip 附件（sha256 未变）；
- 未改判定逻辑（`engine` / `parse` / `rules` / `report` / `pipeline`）；
- 未改冻结数据的**字节**（只迁位置），四道冻结门原样 OK；
- 新 CI job（`install-smoke`）需推送后才跑 → **待复验**。
---

## 八、v0.2.0 发布（2026-10-20）

> 版本从 `0.1.0` → **`0.2.0`**。按 semver，0.x 的 minor 承担破坏性变更——
> 这里确实有一处：`check` 在"未评估"时由 exit 0 改为 **exit 1**（DEC3 = B）。
> 依赖"exit 0 = 通过"的脚本会受影响，故不按 patch 发。

### 8.1 发布内容

| 项 | 值 |
|---|---|
| tag | `v0.2.0` |
| 附件 | `pflc-gui-windows-x64-0.2.0.zip`（165 文件）<br>`pflc-cli-windows-x64-0.2.0.zip`（23 文件）<br>`pet_food_label_checker-0.2.0-py3-none-any.whl`（96,102 B）<br>`pet_food_label_checker-0.2.0.tar.gz`（163,937 B） |
| 留档 | `docs/DIST-sha256-v0.2.0.txt`（zip 行由 `make_release.py --ledger` 生成；wheel/sdist 为附录手写追加） |
| 上一版 | `v0.1.0` 与 `docs/DIST-sha256-M6.txt` **原样保留**，可复核 |

### 8.2 重打包是真的（不是复用旧产物）

这一版 `build_datas()` 的**源路径**改了（仓库根 `data/` → 包内 `src/pflc/data/`），
所以必须真构建一次才能验证 exe 里仍有数据。实测：

```
python -m PyInstaller --clean --noconfirm tools/pflc.spec     → exit 0
python tools/verify_frozen.py --dist dist/pflc-cli-dist --selftest  → VERIFY_FROZEN_OK
python tools/verify_frozen.py --dist dist/pflc --selftest           → VERIFY_FROZEN_OK
  pflc-cli 自检结论：{"data_dir_in_dist": true, "rules_present": true}
  pflc 自检结论：{"data_dir_in_dist": true, "rules_present": true}
  GUI 探针：页签 6 个 ['标签导入','标示项检查','限值判定','宣称核查','基准评测','关于']
python tools/make_release.py --dist dist --out release --check       → RELEASE_PACK_OK
```

**这正是二次迭代里最值得记的一步**：源码态测试与 wheel 安装都绿，证明不了
exe 里还带数据——`build_datas()` 改源路径后若忘了同步，exe 会打成"没有数据"的树，
而所有源码态测试照样全绿。`verify_frozen` 的 `rules_present` 是这里唯一能抓住它的断言。

### 8.3 留档机制的顺带修正

`tests/test_release.py` 原先把留档路径**写死** `docs/DIST-sha256-M6.txt`。
版本 bump 后旧名字仍在仓里 —— 写死它会让门禁去对**上一版**的哈希，
"看起来在验、其实验错对象"。改为 `_current_ledger()`：优先取
`DIST-sha256-v<版本>.txt`，否则扫 `DIST-sha256-*.txt` 里头部版本号匹配的那份；
并新增断言"留档头部版本 == 包版本"，把"版本 bump 忘了重生成留档"这一点明化。
`make_release.ledger_text()` 的表头也从写死 `（M6）` 改为按版本生成。
