# HANDOFF-M1：数据先行

> 交接快照。上一棒 = M0（计划先行 + 可运行骨架），已完成并验证。
> **新对话怎么开**：`/goal 读取 "<项目绝对路径>\plan\HANDOFF-M1.md" 继续完成任务`
> （启动命令里的绝对路径由用户侧拼出；**库内一律只写相对路径** `plan/HANDOFF-M1.md`。）

---

## 一、当前进度（M0 已完成并验证）

| 项 | 状态 |
|---|---|
| 计划文档 | ✅ `plan/00`–`07` 齐备（00 总览含 M0 实录） |
| 工程骨架 | ✅ `pyproject.toml`（extras: dev/gui/build）、`LICENSE`（MIT, yuluo554）、`.gitattributes`、`.gitignore`、`README.md` |
| 核心层 | ✅ `src/pflc/`：`model` / `parse` / `rules` / `engine` / `report` / `pipeline` / `cli` / `gui` / `benchmark` / `packaging` / `data_paths` |
| 工具脚本 | ✅ `tools/`：`gen_rulesets.py` / `gen_samples.py` / `audit_desensitize.py` / `verify_frozen.py` / `smoke_cli.py` / `make_demo_assets.py` / `pflc.spec` |
| 测试 | ✅ `tests/` 167 项，Python 3.8.8 与 3.12.10 双解释器全绿 |
| CI | ✅ `.github/workflows/ci.yml`（windows×{3.8,3.12} + ubuntu×3.12，`fetch-depth: 0`，`PYTHONUTF8=1`） |
| 文档 | ✅ `docs/技术报告.md`、`docs/demo/`（6 PNG + 1 GIF）、`docs/DIST-sha256-M0.txt` |
| 数据 | 🔶 规则包已生成但**规则条目数为 0**（待 M1 录入）；`data/samples/` 4 份合成夹具 ✅ |

**M0 末态**：`python -m pflc.cli diagnostics` → exit 1，提示"当前无生效规则：规则包待数据录入并逐条挂原文核对"。这是**如实状态**，不是缺陷。

---

## 二、下一里程碑（M1）待办

**目标**：把"法规条款 + 国标限值"变成**已核对、可生效**的规则包。

### 任务清单

1. **《宠物饲料标签规定》全文获取**（M0 未解决，见 §三 环境事实）
   - 20 号公告页正文**未内联**附件 3 全文；页内附件链接指向 `.ceb`/PDF 打包件，该 PDF **无文本层**（实测：25,331,751 字节 / 95 页 / `pdftotext` 汉字数 0 / `pdffonts` 无字体 / `pdfimages` 无位图 → Foxit 打印驱动**字形转曲线**）；
   - **另寻渠道**：foodmate 站内 HTML 转载页（按标题检索）、其他权威转载站、有条件时补官方源；
   - 拿到后入仓 `data/knowledge/raw/`（`.gitattributes` 已标 `-text`）+ 登记双 sha256。

2. **GB/T 31216—2014 / GB/T 31217—2014 数值表录入**
   - std.samr.gov.cn 全文预览需浏览器会话（机器直连拿不到）；
   - **先试"页图精灵图/瓦片直连旁路"再下弃选结论**——JS 增强页取不到载荷 ≠ 数据不可得；
   - 关键技巧：同一会话连续请求精灵图只有第一个成功 → **每张精灵图新建独立 cookie 会话**；已废止标准官方明示不提供阅读服务 → 该版条款号如实 `pending`，**绝不编造**。

3. **写转录器**（脚本转写，**禁手抄**）
   - 按**条文号索引**解析（标准正文是 `X.Y → X.Y.N` 编号树，按条文号切块）；
   - **每一处抽取值断言原文逐字包含**；
   - 产物由生成器落盘，配 `--check` 位级一致守门。

4. **逐条挂条款核对** → 把条文块写入 `data/knowledge/clauses/{label,nutrition,claim}.json`
   - 每条挂 `status`（数值核对）与 `clause_status`（条款号核对）**两个独立状态**；
   - 只有核对通过的条目才写 `verified`——**未核对不得生效**。

5. **重生成规则包**：`py -X utf8 tools/gen_rulesets.py --force` → `--check` 应输出 `FROZEN_RULESET_OK`。

6. **回填数据台账** `data/README.md`：三态改 ✅、登记 sha256、更新 §六 M0 末态快照。

7. **M0 骨架对规则的猜测已被 M1 实测勘误**（若有）：枚举 / 范围 / 决策记录**三处同步**。

### DoD（逐项 checklist）

- [ ] 原文快照入仓且 `.gitattributes` 标 `-text`，双 sha256 台账登记；克隆后 sha256 实测一致
- [ ] 转录器"原文逐字包含断言"通过（0 问题）
- [ ] `status=verified` 条目数 > 0，且每条带**可解析**的条款锚点
- [ ] `py -X utf8 tools/gen_rulesets.py --check` 输出 `FROZEN_RULESET_OK`
- [ ] `py -X utf8 -m pflc.cli diagnostics` 显示 verified/pending 计数与 pending 清单
- [ ] `py -X utf8 -m pytest -q` 全绿（新增核对相关测试）
- [ ] `py -X utf8 tools/audit_desensitize.py --tracked` → `DESSENSITIZE_AUDIT_OK`
- [ ] `data/README.md` 台账与 `plan/00` 状态表回写
- [ ] **`plan/HANDOFF-M2.md` 已在本对话内落盘并 commit**（硬约束出口门）

### 风险与降级路径

若 GB/T 31216/31217 全文**最终不可得**：
- 营养限值维度规则全 `pending` → 该维度 `dimension_excluded`（原因码 `no_effective_rules`），报告显式写明"本次未参与聚合"；
- **绝不编造数值**；
- 此路径下 M3–M4 仍可对**标签规定 + 宣称**两维度完整交付，M6 可发布并如实标注覆盖面。

---

## 三、既定口径清单（K 清单，动了会打挂基准）

> 后续任何改数据/加类目/改接口的动作，**先对照本表，改完重跑基准确认不回退**。
> 完整版见 `plan/07-交付对标与决策记录.md` §四。

| K | 口径 |
|---|---|
| K1 | 三态 `compliant`/`noncompliant`/`not_provided` + `skipped`（原文写了例外）/`unknown`（未观测）；**无条件义务缺失 = noncompliant**；无适用项 → `not_assessed`（绝不输出 compliant） |
| K2 | **双重门控**：`status`（数值）门控判定路径，`clause_status`（条款号）只管可证性 |
| K3 | 门控作用域三值 `label`/`nutrition`/`claim`，各只校验自己引用的条目 |
| K4 | 零生效维度不参与聚合 + `dimension_excluded` 原因码 |
| K5 | 数值口径一处定义：限值只在 `ruleset-nutrition.json`；**零政策字面量门禁**扫 `src/pflc/`（含 GUI）与 `tools/`，含 docstring/注释；token **运行时实算** |
| K6 | 规则包冻结：禁手改，改走 `gen_rulesets.py --force`；`--check` 位级一致 |
| K7 | 退出码三语义：`0` 达标/无不符合 · `1` 未达标/检出不符合/门控拦截 · `2` 用法或未知名错误 · `3` 缺 GUI 依赖 |
| K8 | 溯源完整性硬约束：导出前断言"溯源行数 == 明细行数"且引用 id 可解析，不满足**拒导** |
| K9 | 报告双轨**单一渲染源** `report_sections()`；机读产物逐字节可复现、**禁活动外链**（纯文本 URL 允许） |
| K10 | GUI 零判定逻辑 AST 三条齐上（不 import 规则层 + 无算术 `BinOp` + 无政策数值字面量）；**唯一取数入口 = `pflc.pipeline`**（枚举常量也经它转发） |
| K11 | 单件与批量共用 `check_card` 分派点 |
| K12 | 失败件 ≠ 违规：解析失败记 `scan_error`/`failed`，**不改退出码**，失败隔离 |
| K13 | 两轮对账配对主键 = 稳定身份键（`file:<相对路径>`），**不用内容指纹**；delta 返回**违规条目级**键 |
| K14 | 基准分样本驱动 + 规则驱动两层；每套件配探活；期望锚定冻结真值（不与引擎共用通路） |
| K15 | 验收门槛随 manifest 下发（缺失 → exit 2，不回落代码默认值） |
| K16 | 空分母 `not_enabled=true` + notes 声明 + exit 1 |
| K17 | 覆盖登记"规则包总数 / 已核对数 / 采样数 / 清单"**双数** + "抽样覆盖非穷举"声明 |
| K18 | 假品牌名白名单硬断言（白名单外 → exit 1）；真实品牌数据与合成基准严格隔离 |
| K19 | 免责声明强制出现在每份报告与 GUI"关于"页 |
| K20 | 全本地零上传：核心层零第三方依赖（`dependencies = []` 有测试守门）、无网络库 |
| K21 | 冻结态自检断言数据目录落在 exe 目录内；非冻结态返回 `None` |
| K22 | 编码三层加固：CI `env PYTHONUTF8=1` + 入口 `reconfigure` + 子进程显式 `encoding=`；**覆盖所有会打印的入口含 `tools/` 脚本** |
| K23 | 惰性导入 `try` 包住**从 import 到调用完成**整条路径，缺依赖走 exit 3 |
| K24 | 字节冻结分层：文本行尾（`eol=lf` + CR 守门）+ 冻结数据无 CR 守门 |

---

## 四、本机环境坑（只写实测过的）

| 坑 | 实测事实与处置 |
|---|---|
| Python 通道 | `py -0p` → **3.8.8** 与 **3.12.10** 两条。项目底线 3.8；所有一次性脚本只能用 **3.8 语法**。发布构建固定用 `py -3.12`（PyInstaller 6.x） |
| **`Path.write_text(newline=)` 是 3.10+ 参数** | 3.8 上直接 `TypeError`。本项目**已三次踩中**（tests/conftest、test_benchmark、sha256 留档脚本）→ 一律用 `open(..., newline="\n")` 或 `write_bytes`。写新脚本时先想这条 |
| 中文控制台编码 | 跑命令一律 `py -X utf8`；入口已加 `_ensure_utf8_stdio()` 探针 |
| **Git Bash `/tmp` 与 Windows Python 路径不通** | `curl` 落到 `/tmp/x.html` 后 Windows Python 读不到 → 临时文件一律用**工作区相对路径** `.tmp/` |
| pip 被系统代理污染 | `NO_PROXY="*" no_proxy="*" py -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <pkg>` |
| 大文件 curl 同步超时 | 25 MB PDF 用 `-C -` 断点续传 + `run_in_background` 后台任务 |
| pip 安装后 `pflc.exe` 不在 PATH | 用 `python -m pflc.cli`（README 已统一此形态） |
| **`py` 启动器无视已激活 venv** | README 的 venv 段落一律写 `python -m pip ...` |
| pyc 偶发损坏 | 全程 `PYTHONDONTWRITEBYTECODE=1`；出怪错先清 `__pycache__` 再跑 |
| PySide6 版本上限 | 3.8 实测可解析最高 **6.6.3.1**（6.7+ 元数据要求 ≥3.9）；`gui` extra 写 `>=6.5,<6.7` |
| PyInstaller 分档 | 打 GUI 必须 **≥6**（5.13.2 扫 PySide6 字节码确定性崩）；只打 CLI 的老解释器用 `>=5.13,<6` |
| offscreen 中文字体 | Qt 6 起不随附字体且 offscreen 不扫系统字体目录 → `load_cjk_font()` 显式 `addApplicationFont`；字体路径由 `WINDIR`/`SystemRoot` 推导，**不写死盘符** |
| Qt 控件父级唯一 | 同一控件 `addTab` 多次会被 Qt 重新父化，页签数塌掉 → 每页签独立控件（已有守门测试） |

---

## 五、关键命令速查

```bash
# --- 测试与守门（每次收尾必跑）---
py -X utf8 -m pytest -q                              # 全量（应 167 passed）
py -3.12 -X utf8 -m pytest -q                        # 双解释器验证
py -X utf8 tools/gen_rulesets.py --check             # 期望 FROZEN_RULESET_OK
py -X utf8 tools/gen_samples.py --check              # 期望 FROZEN_SAMPLES_OK
py -X utf8 tools/audit_desensitize.py --selftest     # 期望 阳性 4 / 阴性 5 / 放行 1
py -X utf8 tools/audit_desensitize.py --tracked      # 期望 HARD 0 / REVIEW 0 → DESSENSITIZE_AUDIT_OK
py -X utf8 tools/smoke_cli.py                        # 期望 SMOKE_CLI_OK

# --- 规则包（M1 主战场）---
py -X utf8 tools/gen_rulesets.py --force             # 重生成（改数据后必跑）
py -X utf8 tools/gen_rulesets.py --check             # 位级一致校验

# --- 数据状态与端到端 ---
py -X utf8 -m pflc.cli diagnostics                   # 规则/数据状态（零生效规则时 exit 1）
py -X utf8 -m pflc.cli check data/samples/label-demo-ok.txt -v
py -X utf8 -m pflc.cli bench                         # 规则为空时 exit 1（NOT_ENABLED）
py -X utf8 -m pflc.cli report data/samples/label-demo-missing.txt --out output/

# --- 演示物料（M5 重生成）---
py -X utf8 tools/make_demo_assets.py --out docs/demo
```

**环境变量**：`PFLC_DATA_DIR` 可把数据目录指到别处（测试与验收用）。

---

## 六、绝对禁止（M0–M6 全程）

- **不得虚报 CI**：无远端时 DoD 只能写"**本地等价校验通过**（未接远端，CI 待首推验证）"；**未推送 = 未跑 CI**。
- **不得编造标准内容**：核对没覆盖的条款**不建规则**（宁缺勿造）；数值拿不到就 `pending`，**绝不臆造**。
- **不得手改冻结产物**：规则包/夹具改了走生成器重生成。
- **不得把"没做"记成"不用做"**：无条件义务缺失 = 不符合。
- **不得把"解析不到"当"合规"或"违规"**：显式降级 + 原因码。
- **不得在仓库树内跑冻结态验收**：CWD 上溯会命中仓库 `data/`，"内嵌数据"验了个寂寞。
- **不得在公开文档写姊妹项目的领域具体名词**：一律用"方向级描述"。
- **里程碑收尾不写 HANDOFF 就结束对话**：实测必然漏。

---

## 七、参考文档索引

| 文档 | 用途 |
|---|---|
| `plan/00-README总览.md` | 项目总览 + M0 实录 |
| `plan/02-需求解读.md` | 痛点→能力转译、FR 清单、边界与非目标 |
| `plan/03-架构与技术选型.md` | 分层架构、**D1–D18 关键设计决策**（改判定语义前必读） |
| `plan/04-模块详设.md` | 逐模块接口与判定语义 |
| `plan/05-数据计划.md` | 数据先行、规则包冻结形态、合成基准真值语义 |
| `plan/06-里程碑.md` | M0–M6 目标/DoD/风险降级 |
| `plan/07-交付对标与决策记录.md` | 评分对标、决策记录、**K1–K24 既定口径**、反模式清单 |
| `data/README.md` | 数据台账（依据三态 + 渠道实录 + M0 末态快照 + M1 待办） |
| `docs/技术报告.md` | 规则化方法、三态框架、基准设计（含待回填项清单） |
