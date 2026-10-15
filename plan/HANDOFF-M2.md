# HANDOFF-M2：标签文本导入器（解析层收口）

> 交接快照。上一棒 = M1（数据先行），已完成并验证。
> **新对话怎么开**：`/goal 读取 "<项目绝对路径>\plan\HANDOFF-M2.md" 继续完成任务`
> （启动命令里的绝对路径由用户侧拼出；**库内一律只写相对路径** `plan/HANDOFF-M2.md`。）

---

## 一、当前进度（M1 已完成并验证）

| 项 | 状态 |
|---|---|
| 规则包 | ✅ **45 条**（`label` 8 / `nutrition` 32 / `claim` 5），**43 `verified` + 2 `pending`** |
| 条文块 | ✅ `data/knowledge/clauses/{label,nutrition,claim}.json` + `sources.json`（转录器产出，`--check` 位级一致） |
| 原文快照 | ✅ `data/knowledge/raw/`（标签规定 3 件 + 两标准各 9 件），sha256 从文件实算并登记 |
| 转录器 | ✅ `tools/transcribe_clauses.py`（**原文逐字包含断言**，禁手抄）+ `data/knowledge/transcription/spec.json` |
| 测试 | ✅ **185 项**，Python 3.8.8 与 3.12.10 双解释器全绿 |
| 基准 | ✅ **四套件全部达标**（detection 检出率 1.00 / 误报 0.00；overall 1.00；boundary 60/60；traceability 43/43） |
| 守门 | ✅ `TRANSCRIBE_OK` / `FROZEN_RULESET_OK` / `FROZEN_SAMPLES_OK` / `DESSENSITIZE_AUDIT_OK` / `SMOKE_CLI_OK` |
| 文档 | ✅ `plan/00`–`07` 已回填 M1 实录与勘误；`data/README.md` 台账三态改 ✅；`README.md` / `docs/技术报告.md` 同步 |

**M1 末态**：`py -X utf8 -m pflc.cli diagnostics` → **exit 0**（nutrition 30 生效 / 2 未生效）；
`py -X utf8 -m pflc.cli bench` → **exit 0**（四套件达标）；
`py -X utf8 -m pflc.cli check data/samples/label-demo-ok.txt` → **exit 0**。

### M1 的两处数据获取（M0 曾判定"不可得"，实际都拿到了）

- **字形转曲线 ≠ 数据不可得**：20 号公告附件包 PDF 确实无文本层；但**换个来源就有**——
  FAO FAOLEX 库扫描件含 Adobe Paper Capture 隐藏 OCR 层，`pdftotext` 提取汉字 10,858 个，
  26 条 + 附录 1–9 完整；另以 feed-china 转载正文交叉校验**条款编号序列一致**。
- **JS 增强页取不到载荷 ≠ 数据不可得**：`openstd.samr.gov.cn` 全文预览把每页切 10×10 瓦片，
  瓦片图在 `viewGbImg?fileName=<bg>`；预览页带 `Referer` + `JSESSIONID` 可直连；
  **同一 cookie 会话连续请求只有第一个成功** → 每张精灵图新建独立会话；
  拼回整页后**逐格 OCR**（整页 OCR 会把表格线当笔画、`≥` 识别成 `之`/`ss`，数值直接丢失）。

### M1 实测勘误 7 处（M0 骨架猜错 → M1 纠正）

① 零政策字面量豁免口径使**门禁空转**（真实限值全 < 100 被整包放过）；
② **干物质 vs 标示状态基准不同**（正确性关键）；③ 单字指标名（钙/磷）解析不到；
④ `Decimal.normalize()` 产出 `3E+1`；⑤ `additives` 义务类型应为条件触发；
⑥ 20 号公告官方 URL 实测可达（M0 的 404 是 URL 选错）；⑦ 冻结数据 CR 门禁误报二进制件。

逐条处置见 `data/README.md` §七 与 `plan/07` 决策表 M1 各条。

---

## 二、下一里程碑（M2）待办

**目标**：贴文本 → 结构化 `LabelCard`，确定性可复现（`plan/06` M2）。

**M2 是"收口"而非"从零建"**：M0 已写好解析层骨架、M1 修了单字指标名与数值渲染两处缺陷。
M2 要做的是**把解析层补到 FR-01 全覆盖，并用测试把每类字段的正负例钉死**。

### 任务清单

1. **FR-01 字段覆盖核对**（逐字段正负例，见 `plan/04` §2.2 表）
   - 现有字段：`product_name` / `category` / `life_stage` / `guaranteed` / `ingredients` /
     `additives` / `net_content` / `producer` / `product_dates` / `claims` —— 已有实现；
   - **M2 要补的缺口（M1 实测发现，见 §三）**：
     * **宣称词表硬编码在 `parse/__init__.py`**（`_CLAIM_WORDS`）——按 `plan/04` §2.2，
       宣称词表**应来自规则包**。M1 已把宣称规则录入 `ruleset-claim.json`（5 条），
       **解析层却仍在读自己那份硬编码词表**：两份口径必然漂移（规则包加一条宣称，
       解析层不认它 → 该宣称永远不会被抽出来 → 永远判"未宣称"= 假 skipped）。
       **这是 M2 的头号任务**；
     * **生命阶段歧义过宽**：`_extract_life_stage` 命中多个别名即记 `mapping_uncertain`。
       实测"测试粮A 猫粮 幼年"这类正常文本，因"全价"（别名 `全阶段`）与"幼年"同时命中
       → 判成歧义。而"全价"是**产品类型词**不是生命阶段词，把它放进阶段别名表是错的；
     * **净含量未知单位**应记 `mapping_uncertain`（`plan/04` §2.2 明写），当前实现里
       单位不匹配直接落 `not_found`，把"有值但单位不认识"和"根本没写"混为一谈；
     * **日期合法性**校验（`plan/04` §2.2 明写"日期合法性"）当前只做正则匹配，
       不校验月份 ≤12、日 ≤31。
2. **确定性守门**：同一文本 → 同一档案逐字节一致（已有 `test_same_text_same_card_bytes`，
   M2 需覆盖**新增字段**与**边界输入**：空文本、纯噪声、超长行、全角/半角混排）。
3. **夹具生成器与 README 常驻回归门**：`data/samples/*.txt` 已由 `tools/gen_samples.py` 产出
   （M1 已按 as-fed 口径重写），README 引用的路径须全部存在（已有守门测试）。
   **M2 需确认夹具覆盖 FR-01 的每个字段**（当前 4 份夹具偏重缺失/越限场景）。
4. **解析层回归测试**：每类字段正负例（含原因码断言）。
5. `plan/HANDOFF-M3.md` 落盘并 commit（硬约束出口门）。

### DoD（逐项 checklist）

- [ ] 字段抽取覆盖 FR-01 全部字段；缺失如实 `not_provided` + **原因码**
- [ ] **同一文本 → 同一档案（逐字节一致）**守门测试（含新增字段与边界输入）
- [ ] 合法性校验生效：数值超范围 → `out_of_range`；类别/阶段歧义 → `mapping_uncertain`；
      **净含量未知单位 → `mapping_uncertain`**；日期非法 → 明确原因码
- [ ] **宣称词表改为从规则包读取**（单一口径），并有测试证明"规则包加一条 → 解析层能抽出"
- [ ] 生命阶段不再因"全价"这类产品类型词误判歧义
- [ ] 夹具覆盖 FR-01 每字段；README 引用路径全部存在（常驻回归门）
- [ ] `py -X utf8 -m pytest -q` 全绿（3.8 与 3.12 双解释器）
- [ ] 五道守门全绿（`transcribe_clauses` / `gen_rulesets` / `gen_samples` / `audit_desensitize` / `smoke_cli`）
- [ ] `plan/HANDOFF-M3.md` 已在本对话内落盘并 commit（硬约束出口门）

### 风险与降级路径

- 若"宣称词表从规则包读取"改动影响 `parse` → `rules` 的依赖方向（解析层不该依赖规则层）：
  **正解是把词表作为 `parse_label()` 的显式参数**，由编排层（`pipeline`）从规则包取出后传入——
  解析层保持"纯函数、不读文件"，分层不破。
- 若某字段在真实标签里无法稳定抽取：**如实落 `not_provided` + 原因码**，
  绝不加启发式猜测（那会让"没解析到"看起来像"合规"）。

---

## 三、M1 实测发现的 M2 缺口（**本棒实测，不是猜的**）

用当前解析层跑实测，暴露出两个真缺口：

```
$ py -X utf8 -c "from pflc.parse import parse_label; ..."
# 输入："测试粮A 猫粮 幼年 / 产品名称：测试粮A全价幼猫粮 / ..."
category: 猫粮                    ← 正常
life_stage: 未提供(mapping_uncertain)   ← ★ 缺口一：被"全价"误判歧义
claims: ['全价']                  ← ★ 缺口二：产品类型词被当成宣称
```

| # | 缺口 | 后果 | 修法 |
|---|---|---|---|
| 1 | 生命阶段别名表混入产品类型词（`全价` → `全阶段`） | 正常标签被判"阶段歧义"→ 营养维度**整维度 `not_assessed`**（一条规则都不适用） | 从阶段别名表移除产品类型词；"全价"归入产品类别/类型识别，不进阶段 |
| 2 | 宣称词表硬编码在解析层，与规则包**两份口径** | 规则包加宣称 → 解析层不认 → 永远"未宣称" → 假 `skipped` | 词表改为**参数**，由 `pipeline` 从规则包传入 |
| 3 | 净含量未知单位落 `not_found` | "写了但单位不认识"被混同为"根本没写" | 单位不匹配 → `mapping_uncertain` |
| 4 | 日期不校验合法性 | `2026-13-45` 会被当成有效日期 | 校验月 ≤12 / 日 ≤31，非法记明确原因码 |

**验证方式**（新对话可复现）：

```bash
py -X utf8 -c "
import sys; sys.path.insert(0,'src')
from pflc.parse import parse_label
c = parse_label('测试粮A 猫粮 幼年\n产品名称：测试粮A全价幼猫粮\n原料组成：鸡肉\n净含量：2kg\n')
print('life_stage =', c.life_stage.render())   # 期望：幼年（当前：mapping_uncertain）
print('claims     =', c.claim_names())          # 期望：不含产品类型词
"
```

---

## 四、既定口径清单（K 清单，动了会打挂基准）

> 后续任何改数据/加类目/改接口的动作，**先对照本表，改完重跑基准确认不回退**。
> 完整版见 `plan/07-交付对标与决策记录.md` §四。M1 新增/修订的条目**加粗标出**。

| K | 口径 |
|---|---|
| K1 | 三态 `compliant`/`noncompliant`/`not_provided` + `skipped`（原文写了例外）/`unknown`（未观测）；**无条件义务缺失 = noncompliant**；无适用项 → `not_assessed`（绝不输出 compliant） |
| K2 | **双重门控**：`status`（数值）门控判定路径，`clause_status`（条款号）只管可证性 |
| K3 | 门控作用域三值 `label`/`nutrition`/`claim`，各只校验自己引用的条目 |
| K4 | 零生效维度不参与聚合 + `dimension_excluded` 原因码 |
| K5 | 数值口径一处定义：限值只在 `ruleset-nutrition.json`；**零政策字面量门禁**扫 `src/pflc/`（含 GUI）与 `tools/`，含 docstring/注释；token **运行时实算**。**豁免口径（M1 勘误）**：整数形态且 < 20 才豁免，**非整数一律不豁免**，且必须配"真实规则包下 token 集非空"的非空转守门测试 |
| **K5b** | **数值基准**：GB/T 理化指标**以干物质计**，标签保证值是 as-fed → 引擎对 `basis=dry_matter` **先换算再比**；缺水分 → `unknown` + `basis_undetermined`，绝不直接比、绝不猜水分 |
| **K5c** | **数值渲染**：一律 `format_decimal()`（定点、无 E 记号）；**禁 `str(Decimal.normalize())`** |
| K6 | 规则包冻结：禁手改，改走 `transcribe_clauses.py --force` → `gen_rulesets.py --force`；`--check` 位级一致 |
| K7 | 退出码三语义：`0` 达标/无不符合 · `1` 未达标/检出不符合/门控拦截 · `2` 用法或未知名错误 · `3` 缺 GUI 依赖 |
| K8 | 溯源完整性硬约束：导出前断言"溯源行数 == 明细行数"且引用 id 可解析，不满足**拒导** |
| K9 | 报告双轨**单一渲染源** `report_sections()`；机读产物逐字节可复现、**禁活动外链** |
| K10 | GUI 零判定逻辑 AST 三条齐上；**唯一取数入口 = `pflc.pipeline`** |
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

---

## 五、本机环境坑（只写实测过的）

| 坑 | 实测事实与处置 |
|---|---|
| Python 通道 | `py -0p` → **3.8-64**（`C:\Users\<USER>\AppData\Local\Programs\Python\Python38`）与 **3.12-64**。项目底线 3.8；所有一次性脚本只能用 **3.8 语法**。发布构建固定用 `py -3.12`（PyInstaller 6.x） |
| **`Path.write_text(newline=)` 是 3.10+ 参数** | 3.8 上直接 `TypeError`。本项目**已三次踩中** → 一律用 `open(..., newline="\n")` 或 `write_bytes` |
| 中文控制台编码 | 跑命令一律 `py -X utf8`；入口已加 `_ensure_utf8_stdio()` 探针 |
| **Git Bash `/tmp` 与 Windows Python 路径不通** | `curl` 落到 `/tmp/x.html` 后 Windows Python 读不到 → 临时文件一律用**工作区相对路径** `.tmp/` |
| pip 被系统代理污染 | `NO_PROXY="*" no_proxy="*" py -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <pkg>` |
| 大文件 curl 同步超时 | 用 `-C -` 断点续传 + `run_in_background` 后台任务 |
| pip 安装后 `pflc.exe` 不在 PATH | 用 `python -m pflc.cli`（README 已统一此形态） |
| **`py` 启动器无视已激活 venv** | README 的 venv 段落一律写 `python -m pip ...` |
| pyc 偶发损坏 | 全程 `PYTHONDONTWRITEBYTECODE=1`；出怪错先清 `__pycache__` 再跑 |
| PySide6 版本上限 | 3.8 实测可解析最高 **6.6.3.1**（6.7+ 元数据要求 ≥3.9）；`gui` extra 写 `>=6.5,<6.7` |
| PyInstaller 分档 | 打 GUI 必须 **≥6**；只打 CLI 的老解释器用 `>=5.13,<6` |
| offscreen 中文字体 | Qt 6 起不随附字体且 offscreen 不扫系统字体目录 → `load_cjk_font()` 显式 `addApplicationFont`；字体路径由 `WINDIR`/`SystemRoot` 推导，**不写死盘符** |
| Qt 控件父级唯一 | 同一控件 `addTab` 多次会被 Qt 重新父化，页签数塌掉 → 每页签独立控件（已有守门测试） |
| **解析器同一指标只取首个出现** | 夹具里同一指标写两行 → 第二行被忽略。构造测试/夹具时**别重复写同一指标**（M1 实测踩过：加"水分"行把目标值顶掉） |
| **`Decimal.normalize()` 产出 E 记号** | `Decimal("30").normalize()` → `Decimal("3E+1")`。一律走 `format_decimal()` |

---

## 六、关键命令速查

```bash
# --- 测试与守门（每次收尾必跑）---
py -X utf8 -m pytest -q                              # 全量（应 185 passed）
py -3.12 -X utf8 -m pytest -q                        # 双解释器验证
py -X utf8 tools/transcribe_clauses.py --check       # 期望 TRANSCRIBE_OK（含原文逐字包含断言）
py -X utf8 tools/gen_rulesets.py --check             # 期望 FROZEN_RULESET_OK
py -X utf8 tools/gen_samples.py --check              # 期望 FROZEN_SAMPLES_OK
py -X utf8 tools/audit_desensitize.py --selftest     # 期望 阳性 4 / 阴性 5 / 放行 1 / 豁免边界 3
py -X utf8 tools/audit_desensitize.py --tracked      # 期望 HARD 0 / REVIEW 0 → DESSENSITIZE_AUDIT_OK
py -X utf8 tools/smoke_cli.py                        # 期望 SMOKE_CLI_OK

# --- 数据层（改数据后必跑）---
py -X utf8 tools/transcribe_clauses.py --force       # 改 spec.json 后重转录
py -X utf8 tools/gen_rulesets.py --force             # 重生成规则包

# --- 数据状态与端到端 ---
py -X utf8 -m pflc.cli diagnostics                   # 规则/数据状态（应 exit 0）
py -X utf8 -m pflc.cli check data/samples/label-demo-ok.txt -v
py -X utf8 -m pflc.cli bench                         # 四套件（应 exit 0 达标）
py -X utf8 -m pflc.cli report data/samples/label-demo-missing.txt --out output/

# --- 演示物料（M5 重生成）---
py -X utf8 tools/make_demo_assets.py --out docs/demo
```

**环境变量**：`PFLC_DATA_DIR` 可把数据目录指到别处（测试与验收用）。

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
- **不得让门禁"看起来绿"而实际空转**：豁免口径（数值 token / CR 二进制 / 分母为零）
  必须配**非空转守门测试**——M1 实测踩过"豁免口径使门禁整包放过"。

---

## 八、参考文档索引

| 文档 | 用途 |
|---|---|
| `plan/00-README总览.md` | 项目总览 + **M0 实录 + M1 实录** |
| `plan/02-需求解读.md` | 痛点→能力转译、**FR-01…FR 清单**、边界与非目标 |
| `plan/03-架构与技术选型.md` | 分层架构、**D1–D18 关键设计决策**（含 **D5b 数值基准**） |
| `plan/04-模块详设.md` | 逐模块接口与判定语义、**§2.2 字段抽取策略表**（M2 主要依据） |
| `plan/05-数据计划.md` | 数据先行、规则包冻结形态、**渠道实录（含 M1 瓦片旁路）** |
| `plan/06-里程碑.md` | M0–M6 目标/DoD/风险降级（**M1 已标 ✅ 并回填实测结果**） |
| `plan/07-交付对标与决策记录.md` | 评分对标、**决策记录（含 M1 勘误各条）**、**K1–K24 既定口径**、反模式清单 |
| `data/README.md` | 数据台账（**依据三态 + 渠道实录 + sha256 表 + M1 末态 + 勘误表**） |
| `docs/技术报告.md` | 规则化方法、三态框架、基准设计、**§十 M1 实测值** |
| `tests/test_m1_data.py` | M1 数据层守门（原文逐字包含 / 双 sha256 / 干基换算 / 门禁非空转） |
