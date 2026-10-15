# 10-15-pet-food-label-checker 项目计划总览

**项目**：宠物食品标签合规比对器（猫犬粮，法规工具，Windows 桌面 + CLI 双形态，强制标示项清单化核验 + 营养限值判定 + 宣称用语核查 + 合成标签基准）
**方法论**：ai-tool-project-sprint（法规条款库 + 版本化规则集 + 合成标签真值基准 + 条款锚点可溯源 + 离线交付）
**项目系列**：同系列新题（不参赛，发 GitHub；前作名称与业务领域按脱敏纪律不入公开仓，见「决策记录」品牌隔离项）
**命名约定**：本地目录 `10-15-pet-food-label-checker`（`10-15`=2026-10-15 日期标签）；**GitHub 仓库名 = `pet-food-label-checker`（纯净名，去日期前缀）**，沿用系列惯例 `yuluo554/<kebab-name>`；署名 `yuluo554`（LICENSE/pyproject 一致）。
**定位宣言（v1）**：养宠人面对"天然粮/无谷粮"营销话术和国标保证值无从核验——把《宠物饲料标签规定》强制标示项和 GB/T 31216/31217 营养限值做成**规则引擎**，逐项判定 + 附条款锚点，内置合成标签基准可复现评测，比"AI 点评配料表"**可验证**——LLM 聊天给不了持久条款规则库、逐项三态结论与可复现基准，本工具是养宠人选购核验与从业者自查的防线。

## 文档索引

| 文档 | 内容 | 状态 |
|---|---|---|
| [01-题目文档.md](01-题目文档.md) | 项目题全文 v1（介绍/任务/材料/评分/锚点/边界，十段式） | ✅ v1 定稿 2026-10-14 |
| [02-需求解读.md](02-需求解读.md) | 痛点→能力转译表、FR 清单带优先级（P0/P1/P2）、边界与非目标、用户旅程、验收口径 | ✅ M0 落盘 2026-10-15 |
| [03-架构与技术选型.md](03-架构与技术选型.md) | 分层架构、技术选型表、18 条关键设计决策（D1–D18）、LLM 决策、目录结构、风险对策 | ✅ M0 落盘 2026-10-15 |
| [04-模块详设.md](04-模块详设.md) | 统一中间表示、解析层、规则层、判定引擎、报告层、编排层、CLI、GUI、打包逐模块接口与语义 | ✅ M0 落盘 2026-10-15 |
| [05-数据计划.md](05-数据计划.md) | 数据先行原则、data/ 结构、规则包冻结形态、合成基准真值语义、台账纪律、渠道实录 | ✅ M0 落盘 2026-10-15 |
| [06-里程碑.md](06-里程碑.md) | M0–M6 逐里程碑目标/任务/DoD/风险降级、收尾固定顺序、可演示命令 | ✅ M0 落盘 2026-10-15 |
| [07-交付对标与决策记录.md](07-交付对标与决策记录.md) | 提交材料与评分标准逐项对标、决策记录、**K1–K30 既定口径清单**、诚实口径、反模式清单 | ✅ M0 落盘 2026-10-15（K25–K27 为 M2 新增；K28 为 M3 新增；**K29–K30 为 M4 新增**） |
| [data/README.md](../data/README.md) | 数据台账：依据查证记录（三态+URL+基准日）、数据源可获取性、合成数据纪律 | ✅ 出题阶段落盘 2026-10-14，M0 扩充 |

## 决策记录

| 日期 | 决策 | 结论 |
|---|---|---|
| 2026-10-14 | 选题 | 宠物食品标签合规比对器 v1（不参赛，发 GitHub）：猫犬粮标签规定 + 国标营养限值规则引擎 |
| 2026-10-14 | 法规查证 | 《宠物饲料管理办法》等 6 件规范性文件 = **农业农村部公告第 20 号**（2018-04-27 发布施行，2018-06-01 新制度施行）；moa.gov.cn 官方候选 URL 实测 404 ⬜，**foodmate 全文转载 ✅ 已实测可读**（含 6 附件：《管理办法》《生产许可条件》《标签规定》《卫生规定》等）；**农业农村部公告第 210 号**（2019-09-02，标签过渡期延长）✅ https://law.foodmate.net/show-197783.html。时间线：标签强制标示经 210 号延长后自 **2020-03-01** 全量执行 |
| 2026-10-14 | 国标查证 | **GB/T 31216—2014《全价宠物食品 犬粮》/ GB/T 31217—2014《猫粮》均现行、无版本迭代**（std.samr.gov.cn 检索页实测 ✅）；全文预览需浏览器会话，机器直连拿不到 ⬜ → **处理路径：M1 数据先行，经浏览器录入全文数值表，逐条挂条款核对后转 verified 方可生效** |
| 2026-10-14 | **弃"AAFCO 全表作首期底座"** | AAFCO 官网数值表**付费** ⬜（不可直连获取）；Merck Veterinary Manual ✅ 直连但为散点数值叙述非完整表；DogFoodAdvisor 403 反爬 ⬜ → **AAFCO 横向对照降级为扩展项**（人工整理 JSON + 逐条注来源），不承诺官方数值全表，首期底座只用国标 + 部令公告 |
| 2026-10-14 | **弃"卫生规定限量包入首期"** | 《宠物饲料卫生规定》限量表估条数最多（预检⑤估 40–60 条），但预检⑤基于文件结构评估、**未逐条核对全文 ⬜**；全文未录入前不建规则包 → 留扩展，需全文录入后另立规则包 |
| 2026-10-14 | **版本素材预检（①）—— 通过** | "旧版标签（2020-03-01 前）vs 新版标签 vs 附加标签"三态对照 ✅ 成立（20 号公告 + 210 号公告过渡规则为证）——天然版本化素材；GB/T 31216/31217 仅 2014 一版无迭代 → **版本对照锚在法规层（标签过渡规则）而非国标层**，三态对照包留扩展 |
| 2026-10-14 | 开源空白核定 | GitHub 检索 "dog food analyzer"/"aafco"/"cat food calculator" 仅零星低星喂食量计算器，无标签合规规则引擎类；中文侧仅 1★ 非规则引擎项目（基准日 2026-10-14，软论据 ⬜） |
| 2026-10-14 | 招牌模式选用 | 复用系列：versioned ruleset（法规 × 规则包）+ 三态判定（符合/不符合/未提供）+ 条款锚点可溯源 + 合成真值基准 + "未挂原文核对不得生效"纪律 |
| 2026-10-14 | 定性/定量配比 | 首期以**标示项齐全性 + 数值限值判定 + 宣称条件核查**为确定性内核；文本语义类复杂情形（配料是否确为"天然"等）不硬判，只做结构化核查 |
| 2026-10-14 | 交付形态 | 桌面 exe（PySide6 + PyInstaller onedir）+ CLI 双形态（沿用系列惯例）；纯本地零联网 |
| 2026-10-14 | LLM 使用 | **不使用**（纯确定性规则 + 结构化输入；标签导入首期只做贴文本的确定性解析，OCR 留扩展）→ 零 API 依赖、基准可离线复现 |
| 2026-10-14 | 首期范围 | 标签文本导入（贴文本）+ 强制标示项检查 + 营养限值判定（GB/T 31216 犬 / 31217 猫，按生命阶段）+ 宣称用语核查 + 合成标签基准；扩展项：AAFCO/FEDIAF 对照、旧版标签三态对照包、卫生规定限量包、图片 OCR |
| 2026-10-14 | 数值口径 | **数值规则条数不预设硬数字**（预检⑤粗估：GB 两标准各约 20–30 条数值规则、标签规定约 15–25 条、卫生规定最多，均 ⬜ 未逐条核对）→ 题面统一写"以全文录入逐条核对后的条目为准"；**限值数值一处定义（规则包）、多处引用** |
| 2026-10-14 | 隐私红线 | 全本地零上传；演示与基准一律合成标签；**假品牌名白名单**（"测试粮A/B"等）统一登记，禁止真实品牌标签入库为基准样例；真值样例引用 Royal Canin/Orijen 公开实测保证值仅作录入核对参照并记抓取日期，与合成基准严格隔离 |
| 2026-10-14 | 品牌隔离 | 不复制姊妹项目代码；公开文档不提其余项目业务领域 |
| 2026-10-14 | 待核对项（⬜ 闭环路径） | ①GB/T 31216/31217 全文数值表 → M1 浏览器录入 + 挂条款核对；②moa 官网 20 号/210 号原文 → 有条件时补官方源快照，当前以 foodmate 转载为全文依据（转载来源如实标注）；③卫生规定限量条目 → 扩展期全文录入；④国内品牌保证值样例 → 电商页待获取 |

## 承诺-证据台账

| 承诺项 | 素材来源 | 交付物内可达性 | 核验方式 | 状态 |
|---|---|---|---|---|
| 强制标示项检查引擎 | 《宠物饲料标签规定》（**M1 已获取全文并核对**：FAO 库扫描件 + feed-china 转载交叉校验） | 标示项规则随包（条款锚点入包） | 合成标签基准逐项核验；结论挂条款锚点 | ✅ **8 条 verified** |
| 营养限值判定引擎 | GB/T 31216—2014 / 31217—2014（**M1 已获取全文并核对**：瓦片精灵图旁路 + 逐格 OCR） | 版本化规则包随包（数值一处定义） | 按生命阶段逐项判定；合成标签真值对账 | ✅ **30 条 verified / 2 条 pending**（牛磺酸：限值随水分形态分支） |
| 宣称用语核查引擎 | 《宠物饲料标签规定》限定用语条款（第二十条） | 宣称规则随包 | "天然/无谷"等宣称条件齐备性核查 | ✅ **5 条 verified**（引擎通路 M3 复核） |
| 标签文本导入器 | 贴文本入口（确定性解析，无 LLM） | 核心层零第三方依赖 | 同一文本同一档案；缺失字段如实标 `未提供` | ✅ **M2 完成**（FR-01 全覆盖，229 项测试） |
| 合成标签基准 | 程序化生成 + 假品牌名白名单 | 基准零外部依赖、零 API | 一条命令复现；指标口径进 README | ✅ **M4 完成**（16 用例冻结真值库入仓；四套件达标；指标进 README + 行级守门） |
| 旧版标签三态对照包 | 20 号 + 210 号公告过渡规则（✅ 素材成立） | 对照规则留扩展 | 旧版/新版/附加标签三态结论差异 | ⬜ 扩展 |
| AAFCO 横向对照 | 人工整理 JSON + 逐条注来源（官方表付费 ⬜） | 扩展数据不入首期底座 | 每条注来源 | ⬜ 扩展 |
| 桌面 + CLI 双形态 | PySide6 + PyInstaller（沿用系列惯例） | Release 附 exe | 界面只渲染引擎结果、零判定逻辑 | ⬜ M5 |

## 里程碑（初稿）

| 里程碑 | 内容 | 状态 |
|---|---|---|
| M0 | 计划先行 + 可运行骨架（plan/ 00–07、工程骨架、核心层、测试、CI） | ✅ 2026-10-15（本地等价校验通过，未接远端，CI 待首推验证） |
| M1 | **数据先行**：获取 GB/T 31216/31217 全文数值 + 标签规定条款逐条挂原文核对（未核对不得落库）+ 依据索引 + 台账 | ✅ **2026-10-15**（45 条规则：43 verified / 2 pending；四套件达标；本地等价校验通过，未接远端） |
| M2 | 标签文本导入器：贴文本 → 结构化标签档案（缺失标 `未提供`，可复现） | ✅ **2026-10-15**（FR-01 全覆盖；229 项测试双解释器全绿；本地等价校验通过，未接远端） |
| M3 | 规则引擎：强制标示项检查 + 营养限值判定（按生命阶段）+ 宣称用语核查，三态结论 + 条款锚点 | ✅ **2026-10-15**（三模块齐备 + 分派表结构性守门；231 项测试双解释器全绿；本地等价校验通过，未接远端） |
| M4 | 合成标签基准：程序化生成合规/违规样例 + 植入真值 + 一条命令复现评测 | ✅ **2026-10-15**（真值库入仓 + 四套件达标 + 指标进 README；255 项测试双解释器全绿；本地等价校验通过，未接远端） |
| M5 | 桌面交付：PySide6 界面 + PyInstaller 打包 + 报告导出 + 技术报告 | ⬜ |
| M6 | 发布：git tag + GitHub Release 附产物（exe/演示 GIF）+ **发布留档三件套**，发布 GitHub 公开仓库 | ⬜ |

**里程碑 DoD 纪律**：每个里程碑收尾时在 [data/README.md](../data/README.md) 台账回填实测证据；M6 DoD = git tag + GitHub Release 附产物 + 发布留档三件套。
**出口门硬约束**：每个里程碑 DoD 达成后，**必须在本对话内写完下一阶段的 `plan/HANDOFF-M<next>.md` 才允许结束对话**——"下个对话再补"是实测必然漏的反模式。

## M0 实录（2026-10-15）

**产出**：`plan/` 计划文档 00–07 齐备；工程骨架（`pyproject.toml` / `LICENSE` / `.gitattributes` / `.gitignore` / `README.md`）；核心层 `src/pflc/`（model / parse / rules / engine / report / pipeline / cli / gui / benchmark / packaging / data_paths）；`tools/` 六个脚本（gen_rulesets / gen_samples / audit_desensitize / verify_frozen / smoke_cli / make_demo_assets）+ `pflc.spec`；`tests/` 169 项；`.github/workflows/ci.yml`（四矩阵）；`docs/`（技术报告 + 演示物料 + sha256 留档）。

**本地等价校验（未接远端，CI 待首推验证）**——逐条实跑并留退出码：

| 通路 | 结果 |
|---|---|
| `pytest` 全量（Python 3.8.8） | ✅ 169 passed |
| `pytest` 全量（Python 3.12.10） | ✅ 169 passed |
| `tools/gen_rulesets.py --check` | ✅ `FROZEN_RULESET_OK` |
| `tools/gen_samples.py --check` | ✅ `FROZEN_SAMPLES_OK` |
| `tools/audit_desensitize.py --selftest` | ✅ 阳性 4 / 阴性 5 / 放行 1 |
| `tools/audit_desensitize.py --tracked` | ✅ HARD 0 / REVIEW 0 → `DESSENSITIZE_AUDIT_OK` |
| `tools/smoke_cli.py`（7 条退出码契约） | ✅ `SMOKE_CLI_OK` |
| 演示物料两次独立生成 sha256 逐个一致 | ✅ 6 PNG + 1 GIF → `DEMO_ASSETS_REPRODUCIBLE` |
| `compileall`（3.8 语法底线） | ✅ exit 0 |

**不可本机实跑、待首推验证的通路**：CI 四矩阵中的 **ubuntu×3.12**（Linux 通路：系统库/路径/编码差异）。windows 两矩阵在本机以 3.8/3.12 双解释器等价覆盖。

**M0 发现并处置的问题**：
1. **20 号公告附件包 PDF 无文本层** —— `file2.foodmate.net/law/hll201902121526.pdf`（25,331,751 字节 / 95 页）经 `pdftotext` 提取汉字数 **0**、`pdffonts` 无字体、`pdfimages` 无位图 → Foxit 打印驱动**字形转曲线**文档，**不可直接提取**。**M1 需另寻渠道**获取《宠物饲料标签规定》全文（已记入数据台账）。
2. **Qt 控件父级唯一性** —— GUI 三个结果页签初版复用同一 `QPlainTextEdit`，Qt 重新父化导致页签数从 6 塌成 4。由 `test_main_window_builds_with_all_tabs` 抓出，改为每页签独立控件 + 加结构守门测试。
3. **AST 门禁豁免口径** —— 首版门禁把 `Path / str`（路径拼接）、`"%s" % x`（格式化）、窗口尺寸常量误报为违规。按"任一操作数为字符串字面量 / path-like 名字 / 布局命名常量"三条写死豁免，并配变异验证证明豁免不吞真违规。

**决策记录补充**（详见 [07-交付对标与决策记录.md](07-交付对标与决策记录.md) §三）：LLM 不使用；全链路 Decimal；报告自写最小 writer；splitmix64 自研 RNG；双重门控 + 三作用域；打包辅助模块放包内。

**诚实口径**：M0 的 CI 类 DoD 一律写"**本地等价校验通过**（未接远端，CI 待首推验证）"——**未推送 = 未跑 CI，不得写"CI 绿"**。M6 首推后据实补记真实 CI 结论与 run id。

## M1 实录（2026-10-15）

**产出**：规则包 **45 条**（label 8 / nutrition 32 / claim 5），其中 **43 条 `verified`、2 条 `pending`**；
`clause_status` 45 条全核对。新增 `tools/transcribe_clauses.py`（转录器，**禁手抄**，含原文逐字包含断言）
与 `data/knowledge/transcription/spec.json`（转录规格作为数据）；原文快照入仓
`data/knowledge/raw/`（标签规定 3 件 + 两标准各 9 件）；`tests/test_m1_data.py`（15 项 M1 守门）。

**两处数据获取（M0 判定为"不可得"，M1 实际都拿到）**：

| 目标 | M0 结论 | M1 实测 |
|---|---|---|
| 《宠物饲料标签规定》全文 | 附件包 PDF 无文本层（字形转曲线）→ ⬜ | ✅ **换个来源就有文本层**：FAO FAOLEX 库扫描件（Adobe Paper Capture 隐藏 OCR 层）提取汉字 10,858 个，26 条 + 附录 1–9 完整；另以 feed-china 转载正文交叉校验条款编号序列一致 |
| GB/T 31216/31217 数值表 | 全文预览需浏览器会话 → ⬜ | ✅ **瓦片精灵图旁路成立**：预览页带 Referer + JSESSIONID 可直连；瓦片图经 `viewGbImg?fileName=<bg>` 取回；每张精灵图新建独立会话；拼回整页后**逐格 OCR**（整页 OCR 读不出表格数值）。页图与 OCR 结果同时入仓 |

**本地等价校验（未接远端，CI 待首推验证）**——逐条实跑并留退出码：

| 通路 | 结果 |
|---|---|
| `pytest` 全量（Python 3.8.8） | ✅ 185 passed |
| `pytest` 全量（Python 3.12.10） | ✅ 185 passed |
| `tools/transcribe_clauses.py --check` | ✅ `TRANSCRIBE_OK`（含原文逐字包含断言） |
| `tools/gen_rulesets.py --check` | ✅ `FROZEN_RULESET_OK` |
| `tools/gen_samples.py --check` | ✅ `FROZEN_SAMPLES_OK` |
| `tools/audit_desensitize.py --selftest` | ✅ 阳性 4 / 阴性 5 / 放行 1 / 豁免边界 3 |
| `tools/audit_desensitize.py --tracked` | ✅ HARD 0 / REVIEW 0 → `DESSENSITIZE_AUDIT_OK` |
| `tools/smoke_cli.py`（9 条退出码契约） | ✅ `SMOKE_CLI_OK` |
| `pflc.cli bench`（四套件） | ✅ **全部达标**（detection / overall / boundary / traceability） |
| `pflc.cli diagnostics` | ✅ exit 0（nutrition 30 生效 / 2 未生效） |

**M1 实测勘误 7 处**（M0 骨架对规则的猜测被真实数据证伪）：①零政策字面量豁免口径使**门禁空转**；
②干物质 vs 标示状态**基准不同**；③单字指标名（钙/磷）解析不到；④`Decimal.normalize()` 产出 `3E+1`；
⑤`additives` 义务类型应为条件触发；⑥20 号公告官方 URL 实测可达（M0 记的 404 是 URL 选错）；
⑦冻结数据 CR 门禁误报二进制件。逐条处置见 `data/README.md` §七 与 `plan/07` 决策表 M1 各条。

**如实的不覆盖**（宁缺勿造）：牛磺酸 2 条 pending（限值随水分形态分支，当前门控键表达不了，
强判会造假合规或假违规）；水分表不建规则（三区间完整覆盖全轴，无可判定阈值）；
"全阶段"不建规则（标准未给该行）；卫生指标不建规则（是检测限值非标签标示项）。

**诚实口径**：M1 的 CI 类 DoD 同样写"**本地等价校验通过**（未接远端，CI 待首推验证）"。

## M2 实录（2026-10-15）

**产出**：解析层补到 **FR-01 全覆盖**，修掉 M1 实测发现的**四处缺口** + **两处假门**；
新增 `tests/test_m2_parse.py`（**40 项**）与第 5 份夹具 `data/samples/label-demo-edge.txt`。
测试总数 **187 → 229**（M1 末态实测 187，非交接文档所记 185）。

**M2 是"收口"而非从零建**：M0 已写好解析层骨架、M1 修了单字指标名与数值渲染。
本里程碑把每类字段的正负例钉死，并给每处修复配**变异验证**。

| # | 缺口（M1 实测） | 后果 | 修法 |
|---|---|---|---|
| 1 | 宣称词表硬编码在解析层，与规则包**两份口径** | 规则包加宣称 → 解析层不认 → 永远"未宣称" → 假 `skipped` | 词表经 `claim_vocabulary()` 从规则包实算，作为 `parse_label(claim_words=...)` **参数**传入（解析层保持纯函数、不读文件）；判定层在唯一分派点按本轮规则包对齐（不足则重抽） |
| 2 | 生命阶段别名表混入产品类型词（`全价` → `全阶段`） | 正常标签判"阶段歧义" → 营养维度**整维度 `not_assessed`** | 移除产品类型词；真·全阶段词面保留 |
| 3 | 净含量未知单位落 `not_found` | "写了但单位不认识"混同"根本没写" | 单位按**最长优先**已知表判定（`2kg` ≠ `2 g`）；认不出 → `mapping_uncertain` |
| 4 | 日期不校验合法性 | `2026-13-45` 被当有效日期 | `datetime.date()` 校验 → `out_of_range` 且**丢弃该字段**（不"标个非法还当已提供"= 不造假合规） |

**顺带修掉的两处假门**（都是"看起来有处置、实际空转"）：

1. **脱敏审计的死豁免**：给原文快照声明的 `generic_email` 豁免**是死代码**
   （扫描器内联实现、没调 `_is_exempt`），该文件照报 `REVIEW 1`——与文档记的 `REVIEW 0` 不符。
   已接上豁免表并补**双向**非空转自检（快照放过 / 换文件仍报 / 同文件其他规则仍生效）。
   **教训**：只验豁免函数本身，验不到"扫描器有没有调它"。
2. **GUI 政策字面量门禁的 `abs<100` 豁免**：M1 只修了**引擎**侧的这处勘误（K5），
   **界面侧（AST 断言三）原样留着**——而政策数值天然 <100（实测 0.09–28）→ **整包放过**。
   M2 实测：注入真实限值 `28` 到 `gui/app.py`，门禁**照绿**。已改为"与规则包限值同形即违规"
   （根治判据 + 断言 token 集非空）+ 结构性豁免收紧为"整数且 <20、非整数不豁免"。
   **教训**：同一处勘误修了一边，另一边会原样留着——同类门禁的口径要一次对齐全部实例。

**本地等价校验（未接远端，CI 待首推验证）**——逐条实跑并留退出码：

| 通路 | 结果 |
|---|---|
| `pytest` 全量（Python 3.8.8） | ✅ 229 passed |
| `pytest` 全量（Python 3.12.10） | ✅ 229 passed |
| `tools/transcribe_clauses.py --check` | ✅ `TRANSCRIBE_OK` |
| `tools/gen_rulesets.py --check` | ✅ `FROZEN_RULESET_OK` |
| `tools/gen_samples.py --check` | ✅ `FROZEN_SAMPLES_OK` |
| `tools/audit_desensitize.py --selftest` | ✅ 阳性 4 / 阴性 5 / 放行 1 / 豁免边界 6 |
| `tools/audit_desensitize.py --tracked` | ✅ HARD 0 / **REVIEW 0** → `DESSENSITIZE_AUDIT_OK` |
| `tools/smoke_cli.py`（10 条退出码契约） | ✅ `SMOKE_CLI_OK` |
| `pflc.cli bench`（四套件） | ✅ 全部达标（detection 1.00 / overall 1.00 / boundary 60/60 / traceability 43/43） |
| `pflc.cli diagnostics` | ✅ exit 0（nutrition 30 生效 / 2 未生效） |

**变异验证 6 处**（把被测行为故意弄坏 → 测试必须变红）：① `全价` 加回阶段别名表 → 3 项失败；
② 去掉分派点对齐 → 假 skipped 测试失败；③ 未知单位退回 `not_found` → 2 项失败；
④ 去掉日期校验 → 7 项失败；⑤ 还原死豁免 → selftest 报"豁免是死代码"且 `REVIEW 1`；
⑥ 注入真实限值 `28` 到 GUI → 政策字面量门禁报红（修好前该注入照绿）。

**诚实口径**：M2 的 CI 类 DoD 同样写"**本地等价校验通过**（未接远端，CI 待首推验证）"。

## M3 实录（2026-10-15）

**产出**：判定层**逐条勾掉 DoD 并回填实测证据**（`plan/06` M3 段落全 `[x]`）；
**新增 2 条结构性守门**（`tests/test_engine.py`）——本棒唯一新增代码。测试总数 **229 → 231**。

**M3 是"收口"而非从零建**：M0 已写好判定引擎骨架（三态语义 + 双重门控 + 维度聚合），
M2 在收口解析层时顺带打通了判定层的两处 M2 前置——**宣称词表单一来源**（K25，
`claim_vocabulary()` 从规则包实算 + 唯一分派点按本轮规则包对齐）与**维度对齐**。
故本棒**不重复造判定层**，而是把"已实现"变成"已锁死 + 已记账"。

**本棒唯一新增代码**：

| 测试 | 防的失效模式 |
|---|---|
| `test_every_kind_has_a_distinct_dispatch_implementation` | 新增/改名 kind 常量却忘在 `_JUDGES` 实现 → 该 kind 规则一生效就抛 `EngineError`；或两 kind 指向同一函数（复制粘贴）→ 判定"跑得通"但语义已错。断言 `set(_JUDGES) == set(KINDS)`、实现互不相同、且**夹具真的驱动了全部 kind** |
| `test_dispatch_guard_rejects_unimplemented_kind` | **非空转自检**：只断言"键存在"是假门（分派表可以齐备而判定路径从不查它）。摘掉一个 kind → 判定路径必须报 `EngineError` |

**M3 DoD 逐条实测证据**（完整表见 `plan/06` M3 段落）：

| DoD 条目 | 证据 |
|---|---|
| 标示项（`presence`）：无条件义务缺失 = `noncompliant` | `test_missing_unconditional_obligation_is_noncompliant` |
| **无适用项 → `not_assessed`**（绝不输出 compliant） | `test_no_applicable_rules_marks_not_assessed` |
| 营养限值（`threshold`）：按阶段筛适用 / 全程 `Decimal` / 缺值 → `not_provided` | `test_threshold_*`（4 项，含边界精确值）+ `test_wrong_category_rules_do_not_apply` |
| 宣称核查（`claim_support`）：结构化核查，不做语义硬判 | `test_claim_absent_is_skipped` / `_present_with_support_is_compliant` / `_present_without_support_is_noncompliant` |
| 双重门控 | `test_pending_rules_are_blocked_from_judgment` / `test_clause_status_pending_does_not_block_judgment` / `test_scope_isolation_each_validates_own_entries` |
| 零生效维度不参与聚合 + 原因码 | `test_zero_effective_dimension_is_excluded_not_judged` |
| 义务类型分栏（`obligation` vs `conditional`） | `test_conditional_effect_missing_is_unknown_not_noncompliant` |
| 零政策字面量门禁（引擎/基准/CLI/GUI） | `test_no_banned_numeric_literals_in_engine_sources` + `test_gui_has_no_policy_numeric_literals`（M2 已修界面侧假门）+ 非空转/变异测试 |
| 单件与批量共用 `check_card` 分派点 | `test_check_file_matches_check_card` |
| 失败件 ≠ 违规 + 失败隔离 | `test_scan_dir_reports_failed_items_without_changing_exit_semantics` / `test_scan_dir_isolates_failures_and_continues` |
| 溯源完整性 | `test_every_finding_carries_resolvable_anchor` |

**本地等价校验（未接远端，CI 待首推验证）**——逐条实跑并留退出码：

| 通路 | 结果 |
|---|---|
| `pytest` 全量（Python 3.8.8） | ✅ **231 passed** |
| `pytest` 全量（Python 3.12.10） | ✅ **231 passed** |
| `tools/transcribe_clauses.py --check` | ✅ `TRANSCRIBE_OK` |
| `tools/gen_rulesets.py --check` | ✅ `FROZEN_RULESET_OK` |
| `tools/gen_samples.py --check` | ✅ `FROZEN_SAMPLES_OK` |
| `tools/audit_desensitize.py --selftest` | ✅ 阳性 4 / 阴性 5 / 放行 1 / 豁免边界 6 |
| `tools/audit_desensitize.py --tracked` | ✅ HARD 0 / REVIEW 0 → `DESSENSITIZE_AUDIT_OK` |
| `tools/smoke_cli.py`（10 条退出码契约） | ✅ `SMOKE_CLI_OK` |
| `pflc.cli bench`（四套件） | ✅ 全部达标（detection 1.00 / overall 1.00 / boundary 60/60 / traceability 43/43） |
| `pflc.cli diagnostics` | ✅ exit 0（label 8/8 · nutrition 30/32 · claim 5/5） |

**变异验证 2 处（本棒新增门）**：① `claim_support` 与 `presence` 指向同一实现 → 4 failed；
② 从 `_JUDGES` 摘掉 `threshold` 实现 → 17 failed。
**非空转自检**：夹具去掉 claim 维度时，"exercised 覆盖全部 kind" 断言确实报缺 `claim_support`
（证明该门不是"键齐备"的空转门）。

**M3 实测勘误 0 处**：判定层语义在 M0/M2 已定型，本棒未发现新的口径错误。
**如实登记（非本棒引入）**：`tools/audit_desensitize.py --all`（历史模式）实测 HARD 1 / REVIEW 2，
全部来自**历史提交** `a214320` 的 `plan/HANDOFF-M2.md`（本机用户名的绝对路径 + 转载站点邮箱）。
该文件在 `e4ebc2c` 已改干净——工作区与 `--tracked` 实测 **HARD 0 / REVIEW 0**；
但 **git 历史不可变**，故 `--all` 会一直报它。修它需 **git 历史重写**（破坏性、需授权），
本项目**尚未接远端**（无外泄面），故如实登记为"已知历史项"，留待首推前由用户决定。

**M3 顺带做的 M4 前置核对（实测新发现 2 条缺口，上一棒交接漏报）**：
M3 收尾时逐条核对 `plan/06` 的 M4 DoD（**未照抄上一棒给的三条结论**），结果发现 M4 缺口是 **5 条**而非 3 条：

| # | M4 缺口 | 实测证据 |
|---|---|---|
| 1 | 基准 fixtures 未入仓 + 无入库件一致性守门 | `data/benchmark/` **不存在**；`check_cases_frozen()` 在 `tools/`/`src/` **零调用** |
| 2 | 覆盖登记采样数未回填 | `sampled_in_truth` 仍 `null`、`sample_list` 仍 `[]` |
| 3 | 指标未写进 README | README 只有"测什么"表，**无实测数值** |
| **4** 🔴 | **`overall` 套件无探活（永绿门）** | **变异证明**：把 `run_overall` 的 `passed` 改成恒真 → **231 项全绿**；对照组改 `run_boundary` → **立刻 1 项失败** |
| **5** 🔴 | **冻结真值库根本没被读 + 载入侧零白名单校验** | `runner._sample_cases()` 每次现场重算；`load_cases()` 对含真实品牌的真值库**原样载入不报错** |

**教训（记入 K 清单与反模式）**：门禁"**有测试**"不等于"**测试有效**"——每个门都要做变异验证，
且**留一个已知有效的对照组**（防"变异根本没生效"造成误判）。**交接文档是线索不是事实，收棒必须自己跑一遍**。

**诚实口径**：M3 的 CI 类 DoD 同样写"**本地等价校验通过**（未接远端，CI 待首推验证）"。
**M3 未做 M4 的事**：M4 的 5 条真实缺口（含上表 2 条新发现）本棒**如实转交**，见 `plan/HANDOFF-M4.md` §三。

---

## M4 实录（2026-10-15）

**产出**：合成标签基准从"能跑"变成"**可核证**"——真值库入仓 + 基准真的读它 + 台账/指标从实算回填 + 5 道新门（全部变异验证）。
完整 DoD 与证据表见 `plan/06-里程碑.md` §M4 段落。

**M4 的题眼是"做了 ≠ 记了 ≠ 可复核"**。上一棒（M3 交接）如实转交了 5 条缺口，
本棒逐条实测核对后**全部关闭**，并另修 1 条超出 DoD 字面的加固项（真值库随包）：

| # | 缺口 | 本棒处置 |
|---|---|---|
| 1 | 真值库未入仓 + 无一致性守门 | `data/benchmark/cases.json`（16 用例）入仓；新增 `tools/gen_cases.py`（`--force`/`--check` + `FROZEN_CASES_OK`）；CI 加该步 |
| 2 | 覆盖登记采样数未回填 | 从**冻结真值库实算**回填（label 3/8 · nutrition 4/32 · claim 3/5）；口径写进 `note` |
| 3 | 指标未进 README | 四套件实测指标 + `truth_source=frozen` 来源声明写入 README |
| 4 🔴 | `overall` 套件无探活（永绿门） | 补探活 + 阳性对照 + 第二条注入方向（真值期望被篡改） |
| 5 🔴 | 冻结真值库根本没被读 | `_sample_cases()` 改为**入库件优先**；不一致 → exit 2 不静默重算 |
| 6 🟡 | 载入侧零白名单校验（超出 DoD 字面） | `load_cases()` 载入即断言品牌白名单（**同一口径一次对齐全部实例**） |

**本棒最重要的一条：两次踩到"假门"并当场修掉。**
① CI 门首版用**子串匹配**——把 `gen_cases.py --check` 整段注释掉仍绿；
② README 指标门首版用**全文件子串匹配**——把 `accuracy=1.0` 手改成 `0.9` 仍绿（别处还有别的 `1.0`）。
两处**只有靠变异验证才暴露**。修法：判据落在**结构位置**（解析 workflow 的 run 步骤 / 定位"实测指标"小节再**行内**逐项核对）。
→ **"文件里出现过这串字"是最容易写出的假门**：它验的是文档排版，不是事实。

**变异验证 7 处（每处均变红，含 1 个对照组）**：`overall.passed` 恒真、`overall` 比较恒真、**对照组 `boundary.passed` 恒真**、
`_sample_cases` 恒回落重算、摘掉载入侧白名单断言、覆盖口径换成"触达"、CI step 注释掉、README 指标手改。

**本地等价校验（未接远端，CI 待首推验证）**：`pytest` **255 项双解释器全绿**（3.8.8 / 3.12.10）；
四道冻结生成器门 `TRANSCRIBE_OK` / `FROZEN_RULESET_OK` / **`FROZEN_CASES_OK`（新）** / `FROZEN_SAMPLES_OK`；
脱敏 `--selftest` 与 `--tracked` 全绿；`SMOKE_CLI_OK`；`bench` 四套件达标（`truth_source=frozen`）；`diagnostics` exit 0。

**M4 实测勘误 1 处**：`gen_rulesets.py` 原先不读真值库，无法回填覆盖登记——
改为在 `generate()` 内**先由规则包生成真值库再实算覆盖**（顺序约束用代码固化，不靠人记得按顺序跑）。

**M4 收棒时自己踩中并修掉的一处**：把 `which python` 的实测路径（含本机用户名）写进**新建的** `plan/HANDOFF-M5.md`，
预提交前三次 `--tracked` **全绿**——因为 `--tracked` 按 `git ls-files` 枚举，**未 `git add` 的新文件对它不可见**；
`git add` 后才报 `user_name_signature HARD 1`。**处置：涉及新建文档的收棒，先 `git add` 再跑 `--tracked`。**
这与本里程碑的"假门"主题同族：**绿 ≠ 验过了**。

**新增口径 K29 / K30**（见 `plan/07`）：K29 冻结真值库是基准期望来源且必须随包；K30 文档实测指标必须可核证（行级守门）。

**M4 未做 M5 的事**：GUI 打包、报告导出留待 M5。
`packaging.assert_no_extra_data` 对 `data/samples` 的既有提示属 M5 打包 scope，本棒未改（已在 `plan/06` M5 DoD 覆盖）。


---

## M5 实录（2026-10-15）

**产出**：桌面交付打通——**真构建**出 onedir 双 exe（GUI + CLI），并在**中立目录 + 剥离环境变量**下
自动验收（冻结态自检 + CLI 五连 + GUI 存活探针）。完整 DoD 与证据表见 `plan/06-里程碑.md` §M5。

**M5 的题眼不是"写界面"（界面 M0 起就在），而是"发行态名不副实"。**
本棒一构建就撞出 **4 个真缺陷**，全部是"源码态绿、发行态红"这一族：

| # | 缺陷 | 为什么源码态看不见 | 修法 |
|---|---|---|---|
| 1 🔴 | **spec 入口点打断包语义**：直接指向 `src/pflc/cli.py` → 冻结后 `ImportError: attempted relative import`。构建**成功**，exe 一启动就崩 | 源码态跑 `python -m pflc.cli`（有包上下文），路径完全不同 | 新增 `tools/entry_cli.py` / `entry_gui.py`（绝对导入进包内 main）+ spec 入口门 |
| 2 🔴 | **禁区扫描判据恒绿**：只匹配 `len(parts) <= 2`，而 6.x 把数据放 `_internal/data/`（三级深）→ 门永远看不到禁区目录 | 没有真实 6.x 布局就没有反例 | 扫描面改"负载根下 `data/**` 任意深度"；配 6.x 树 + 干净树对照组 |
| 3 🟡 | **CLI 包白送 87 MB 且降级提示成死代码**：两树共用 hiddenimports，PySide6 进了 CLI 包 | 体积与提示分流都不是功能断言 | 拆 `_BENCH_HIDDEN`/`_GUI_HIDDEN`；实测 **112 MB → 17 MB**，exit 3 提示实测生效 |
| 4 🟡 | **降级提示未按形态分流**：对冻结态用户也提示 `pip install`（他没 pip） | 原测试只看退出码 | 按 `is_frozen()` 分流 + 双向断言 |

**另做实一道"声称已有其实没有"的门**：`packaging.py` docstring 声称"三处守门"，
其中"spec 文本"那道**并不存在**——本棒补上。

**本棒又抓到一次假门（判据形态问题，与 M4 同族）**：
新增的 CI 门首版判据写 `"--dist dist/pflc" in joined`——而 `dist/pflc` 是
`dist/pflc-cli-dist` 的**子串**，把 GUI 那步整段注释掉后判据照样命中。
变异验证当场抓出，改成**正则锚定完整参数**（`--dist\s+dist/pflc\s+--selftest`）后才真红。
→ **"子串判据"已经是本项目第三次踩到的假门形态**（M4 两次 + 本棒一次），
写判据时默认要问"有没有更长字符串把它包含进去"。

**演示物料重生成**：M0 版是空规则包态（三页判定显示"零生效规则"、基准页纯空白），
本棒重生成为**真实判定态**（真实结论 + 四套件实测值），留档 `docs/DIST-sha256-M5.txt`。
顺带修掉一个审计扫不到的泄漏：**"关于"页会把数据目录绝对路径打在界面上**，
而 PNG 属脱敏审计的二进制豁免 → 本机路径能随素材进公开仓库。处置：生成期替换成
`<数据目录>` + 硬断言（在产素材那一步守，而不是等事后审计——它根本看不到）。

**新增机制**：`tools/verify_frozen.py` 的验收由构建期写下的 `_datas_report.json` 驱动
（白名单版本 + 逐份 sha256 + **这棵树该有哪些 exe**），报告缺失即报错——
避免验收脚本猜目录名，也避免"空报告与合规报告长得一样"。

**M5 末态**：`pytest -q` → **274 passed**（3.8 与 3.12 双解释器）；
`verify_frozen.py --selftest` 两树均 `VERIFY_FROZEN_OK`；`check_demo_reproducible.py` → `DEMO_ASSETS_OK`。
**诚实口径**：CI 类 DoD 写"本地等价校验通过"（未接远端）；本棒新增的 `package` job
**尚未在 CI 上跑过**，只在本机以同样命令序列验过。

**M5 未做 M6 的事**：干净环境验证、Release 附产物、转公开三清留待 M6。
