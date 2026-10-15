# data/ 数据台账

**基准日**：2026-10-14（出题阶段查证）/ 2026-10-15（M0 骨架期复核）/ **2026-10-15（M1 数据先行：全文获取 + 逐条核对）**
**纪律**：未挂原文核对不得落库/生效/进入核查路径；数值规则条数不预设硬数字，以全文录入逐条核对后的条目为准。

---

## 一、依据查证记录（逐条三态 + URL + 基准日）

| 依据 | 三态 | 说明与来源 |
|---|---|---|
| 农业农村部公告第 20 号（2018-04-27 发布施行，《宠物饲料管理办法》《宠物饲料标签规定》《宠物饲料卫生规定》等 6 件规范性文件；2018-06-01 新制度施行） | ✅（转载源 + 官方库扫描件） | foodmate 全文转载已实测可读（HTTP 200，43,414 字节）：https://law.foodmate.net/show-194580.html ；**官方页实测可达**：https://www.moa.gov.cn/govpublic/XMYS/201805/t20180504_6141413.htm （HTTP 200，51,037 字节），但其附件为 `.ceb` 打包件，正文仍未内联 |
| **《宠物饲料标签规定》（20 号公告 附件 3）** | ✅ **M1 已获取并核对** | 两条独立来源交叉校验：<br>① **FAO FAOLEX 库扫描件** `https://faolex.fao.org/docs/pdf/chn176389.pdf`（7,843,144 字节，34 页，`%PDF-1.6`，含 Adobe Paper Capture 隐藏 OCR 文本层）——`pdftotext` 提取汉字 10,858 个，含 **26 条 + 附录 1–9**；<br>② **feed-china 转载正文** `https://www.feed-china.cn/wap/industrytrends/1865.html`（干净 HTML，26 条，无附录）。<br>**两源的条款编号序列一致**（第一–第二十六条 + 第四十一/四十六条为引用他条），条款号核对成立 |
| 农业农村部公告第 210 号（2019-09-02，标签过渡期延长） | ✅（转载源） | foodmate 全文转载已实测可读（HTTP 200，38,610 字节）：https://law.foodmate.net/show-197783.html ；标签强制标示自 2020-03-01 全量执行 |
| GB/T 31216—2014《全价宠物食品 犬粮》 | ✅ **M1 已获取并核对** | 国家标准全文公开系统检索页：现行、无版本迭代（API 实测 `{"STATE":"现行","ISSUE_DATE":"2014-09-03"}`）。**全文经瓦片精灵图旁路获取**（详见 §二 渠道实录）：`hcno=A8758F9C4633B2CCBEE9C82CC3F4A4D1`，7 页，含表 2 主要理化指标（干基）、表 3 水分、表 4 卫生指标 |
| GB/T 31217—2014《全价宠物食品 猫粮》 | ✅ **M1 已获取并核对** | 同上，`hcno=9496ABE283E8EB1FF58DF961B2DBAC9B`，7 页，含表 1 主要理化指标（干基）、表 2 水分、表 3 卫生指标 |
| AAFCO 营养限值表 | ⬜ | 官网数值表付费，不可直连 → 降级扩展项（人工整理 JSON + 逐条注来源），不承诺官方数值全表 |
| Merck Veterinary Manual（小动物营养） | ✅ | 直连可读：https://www.merckvetmanual.com/management-and-nutrition/nutrition-small-animals/nutritional-requirements-and-related-diseases-of-small-animals （散点数值叙述，非完整官方表，仅辅助对照） |
| DogFoodAdvisor | ⬜ | 403 反爬，阻断 |
| Royal Canin US 产品页（Guaranteed Analysis 实测值） | ✅ | 真值样例参照源，引用时记抓取日期 |
| Orijen US 产品页（同上） | ✅ | 同上 |
| 国内品牌官网 | ⬜ | 无官网，走电商页，标待获取 |
| GitHub 开源空白检索 | ⬜（软论据） | "dog food analyzer"/"aafco"/"cat food calculator" 仅零星低星喂食量计算器，无标签合规规则引擎类；中文侧仅 1★ 非规则引擎项目（基准日 2026-10-14） |

---

## 二、数据源可获取性记录（当场验证，含阻断原因）

| 数据源 | 结果 | 阻断原因 / 处置 |
|---|---|---|
| `moa.gov.cn` 官方公告页 | ✅ HTTP 200 / 51,037 字节 | **M0 记的"404"是候选 URL 选错**；官方页实测可达。但附件仍是 `.ceb` 打包件，附件 3 全文未内联 → 全文改用 FAO 库扫描件 + feed-china 转载（两源交叉校验） |
| `law.foodmate.net/show-194580.html`（20 号公告） | ✅ HTTP 200 / 43,416 字节 | 正文可读；**附件 3 全文未内联** |
| `law.foodmate.net/show-197783.html`（210 号公告） | ✅ HTTP 200 / 38,610 字节 | 入仓作版本对照依据 |
| `file2.foodmate.net/law/hll201902121526.pdf`（20 号公告附件包） | ⚠️ **HTTP 200 但无文本层** | 25,331,751 字节 / 95 页 / `%PDF-1.7`；`pdftotext` 汉字数 **0**、`pdffonts` 无字体、`pdfimages` 无位图 → Foxit 打印驱动**字形转曲线**，**不可直接提取**。已弃用，改走 FAO 库 + feed-china 两源 |
| **`faolex.fao.org/docs/pdf/chn176389.pdf`** | ✅ **HTTP 200 / 7,843,144 字节** | 34 页 `%PDF-1.6`；`pdffonts` 显示 `HiddenHorzOCR` CID 字体（Adobe Paper Capture 隐藏 OCR 层）→ `pdftotext -enc UTF-8 -layout` 提取汉字 **10,858** 个，26 条 + 附录 1–9 完整。**字形转曲线 ≠ 数据不可得**：同一份文件换个来源就有文本层 |
| **`www.feed-china.cn/wap/industrytrends/1865.html`** | ✅ HTTP 200 / 71,298 字节 | 干净 HTML 转载（26 条正文，HTML 实体已解码）；与 FAO 扫描件交叉校验条款编号序列 |
| **`std.samr.gov.cn` GB/T 31216/31217 检索** | ✅ API 直连可用 | `https://std.samr.gov.cn/gb/search/gbQueryPage?searchText=GB%2FT%2031216&pageSize=10&pageNumber=1` → JSON（现行、发布日期、实施日期） |
| **`openstd.samr.gov.cn` GB/T 31216/31217 全文预览** | ✅ **M1 已获取** | 见下方"瓦片精灵图旁路"实录 |
| `aafco.org` 数值表 | 付费墙 | AAFCO 对照降级扩展项，人工整理 JSON + 注来源 |
| `dogfoodadvisor.com` | 403 | 反爬阻断，弃用 |
| `merckvetmanual.com` | ✅ 可读 | 仅辅助对照 |
| `royalcanin.com` / `orijen.com` 产品页 | ✅ 可读 | 公开实测保证值，仅作录入核对参照 |

### 渠道实录（M1 新增）：GB/T 全文的"瓦片精灵图旁路"

**问题**：`std.samr.gov.cn` 全文预览需浏览器会话；`showGb` 页把每页切成 10×10 网格瓦片，
瓦片图存在 `viewGbImg?fileName=<bg>`，页面用 `background-position` 指到精灵图偏移。
**直连预览页拿不到内容**（浏览器渲染出空白，curl 却能拿到含瓦片布局的 HTML）。

**实测解法（可复现）**：
1. 预览页**可直连**，但需要 `Referer` 指向 `newGbInfo` 页并持有 `JSESSIONID`；
2. 页面 HTML 里每个 `<div class="page" bg="...">` 给出该页的精灵图令牌；
3. **同一 cookie 会话连续请求 `viewGbImg` 只有第一个成功** → **每张精灵图新建独立会话**；
4. 取回的 `image/webp`（如 2320×8528）按 span 的 class 行列 + `background-position` 偏移切片拼回整页；
5. 整页 PNG 经**逐格 OCR**（先按长直线定位网格、抹掉网格线、再逐格 `tesseract --psm 7`）读出数值——
   整页 OCR 会把表格线当笔画、`≥` 识别成 `之`/`ss`，数值直接丢失。

**结论**：**"JS 增强页取不到载荷" ≠ "数据不可得"**。本项目的 GB/T 数值表就是这么拿到的，
且**页图与 OCR 结果同时入仓**（人可核对原始页，机器可核对 OCR 结果）。

### 渠道坑实录

- Git Bash 的 `/tmp` 与 Windows Python 路径不通 → 临时文件一律用**工作区相对路径** `.tmp/`；
- 大文件同步 `curl` 超时 → `-C -` 断点续传 + 后台任务；
- `pdfimages -list` 在字形转曲线 PDF 上返回 0 行——**"PDF 有 95 页"不等于"能提取文字"**，入库前必须实测汉字数；
- **同一 cookie 会话连续请求精灵图只有第一个成功** → 每张精灵图新建独立会话；
- **整页 OCR 读不出表格数值** → 必须按网格切格逐格 OCR；
- `search.php` 传 GBK 编码关键词才命中（页面是 GBK，`quote(kw)` 直接传 UTF-8 会搜不到）。

---

## 三、入仓原文快照与 sha256 台账（M1）

**登记纪律**：sha256 由 `tools/transcribe_clauses.py` 从文件**实算**（禁手填）；
`.gitattributes` 已把 `data/knowledge/raw/**` 标 `-text` 防克隆时行尾改写。
**验证手段** = 克隆后比对快照实际 sha256 与下表值（`git status` 看不出来）。

| 快照文件 | 字节 | sha256 |
|---|---|---|
| `raw/moa-20-2018-annex3/fao-chn176389.pdf` | 7,843,144 | `9a2a57a51b4e5a7a4a83cab109dd12b4d4ecc4d12a57c1dcf3738bab5b0a83ea` |
| `raw/moa-20-2018-annex3/reprint-feedchina.txt` | 21,684 | `7ee619eef87733fe82ec424d46f881855627ec404002b479ffa237cffae9ecb3` |
| `raw/moa-20-2018-annex3/fao-chn176389.pdftotext.txt` | 45,575 | `e1940a682a9394f360d03e6eaf989d6e769e21c4445782914331c8c3656ecb97` |
| `raw/gb-t-31216-2014/page-04.png` | 34,450 | `b5bc0c7deae073e8ab492795e8d78a455eebebff3fe9285699c7138aebf3fcd3` |
| `raw/gb-t-31216-2014/table-2-理化指标.tsv` | 520 | `775cad199b831e29579e5726543d1c9dd2b07e36979f286047b6285b643268e0` |
| `raw/gb-t-31216-2014/viewer.html` | 65,484 | `a7865013b9c8d53bd6867439f855ca308907cf314c310d34c69bd9bd05fd7d36` |
| `raw/gb-t-31217-2014/page-04.png` | 35,282 | `6e98950fa294790d7d02b04dc4b70b589b2147696ecaac1c40adf6bca71628b5` |
| `raw/gb-t-31217-2014/table-1-理化指标.tsv` | 599 | `0f62c1235b406570b5401dedf49da3c1d31700f3cdacd71ea5e0a8de5714b44f` |
| `raw/gb-t-31217-2014/viewer.html` | 63,893 | `57375a36b5c6bb33743806a3205fb9e7c220510933bdb3e0aff92952caa3a3eb` |

（GB/T 两标准各 7 页页图入仓，上表只列作锚点的主页 `page-04`；全部页图与 sha256 见
`data/knowledge/clauses/sources.json` 的 `snapshot_sha256` 列表。）

---

## 四、规则包覆盖与核对结果（M1 末态）

### 4.1 条文块 → 规则包

| 维度 | 条文块 | 规则条数 | verified | pending | 依据 |
|---|---|---|---|---|---|
| `label` | `clauses/label.json` | 8 | **8** | 0 | 《宠物饲料标签规定》第五/六/九/十四/十五条 |
| `nutrition` | `clauses/nutrition.json` | 32 | **30** | 2 | GB/T 31216—2014 表2、GB/T 31217—2014 表1（**以干物质计**） |
| `claim` | `clauses/claim.json` | 5 | **5** | 0 | 《宠物饲料标签规定》第二十条 |
| **合计** | | **45** | **43** | **2** | |

### 4.2 双门控状态

| 字段 | 语义 | M1 末态 |
|---|---|---|
| `status`（数值核对，**唯一门控判定路径**） | 43 条 `verified` / 2 条 `pending` | 2 条 pending 为牛磺酸（限值随水分形态分支，当前门控键表达不了） |
| `clause_status`（条款号核对，只管可证性） | **45 条全部 `verified`** | 条款号（第 N 条 / 表 N）已逐字核对 |

### 4.3 **如实的不覆盖**（宁缺勿造，逐条给理由）

| 未建规则项 | 理由 |
|---|---|
| **水分表**（犬 表3 / 猫 表2） | 按干(性)/半湿(性)/湿(性)给区间，三区间**完整覆盖全轴**（`x<14.0` ∪ `14.0≤x<60.0` ∪ `x≥60.0`），不存在"落在所有区间之外"的取值 → 不构成可判定的合规阈值；且档案不抽取"产品形态"，无法选定区间 |
| **牛磺酸**（NUT-CAT-015/016，`status=pending`） | 原文该行按水分形态分支（干粮 ≥0.1／湿粮 ≥0.2）。当前 `applies_if` 只支持类别/生命阶段，**无法表达水分形态门控**：只按干粮档判会对湿粮产生**假合规**，只按湿粮档判会对干粮产生**假违规**——两种都是编造结论，故**显式 pending**，在 pending 清单里可见 |
| **"全阶段"生命阶段** | 标准按具体生命阶段（幼年/妊娠期/哺乳期、成年）给限值，**未给"全阶段"行**。拿最严一档去套"全阶段"属无出处的推断 → 不建规则（该维度对该输入记 `not_assessed`） |
| 卫生指标（表4/表3：氟、镉、汞、铅、总砷、黄曲霉毒素等） | 这些是**检测限值**（mg/kg、CFU/g），不是标签"成分分析保证值"的标示项；标签文本里不会出现 → 无观测值可判，不建规则 |
| 附录 1/5/6/7/8/9（示例、能量计算、包装面积计算） | 是**计算方法与示例**，不是"应当标示 X"型义务或数值限值 → 不属于可机器判定的合规条款 |

### 4.4 覆盖登记（防"假覆盖"）

`manifest.json` 的 `coverage` 逐维度登记 **"规则包总数 / 已核对数 / 采样数 / 清单"**（`sampled_in_truth` 与 `sample_list` 待 M4 回填），并显式声明"**抽样覆盖、非逐因素穷举**"。
**判别**：只写分子不写分母就是假覆盖——故 `total_rules` 与 `verified_rules` **双数并列**。

---

## 五、合成数据纪律

- 演示与基准一律使用**合成标签**，程序化生成、带植入真值，可一条命令复现评测；
- **假品牌名白名单**：合成品牌统一使用虚构名称（`测试粮A`–`测试粮F`，登记于 `src/pflc/benchmark/cases.py` 的 `BRAND_WHITELIST`）；**生成器硬断言**品牌名必须命中白名单，否则 exit 1；禁止真实品牌标签入库为基准样例；
- **真值样例参照**：规则包录入核对时，可引用 Royal Canin US / Orijen US 产品页公开 Guaranteed Analysis 实测值作参照，**必须记抓取日期与来源 URL**；该类真实数据仅用于录入核对参照，与合成基准**严格隔离**，不入基准真值库；
- **保证值口径 = 标签标示口径（as-fed）**：国标理化指标是"以干物质计"，引擎先按标示水分换算到干基再比。故合成夹具里的数值是**按水分折回的标示值**，不是标准表里的限值本身；
- 全本地零上传：标签文本、判定结果、基准样例均不出机；规则包未挂原文核对（`status=pending`）不得进入核查路径。

---

## 六、规则包形态与门控（M0 定稿，M1 勘误）

### 6.1 目录与文件

```
data/
├── knowledge/
│   ├── raw/                  # 原文快照（.gitattributes 标 -text 防 EOL 改写）
│   │   ├── moa-20-2018-annex3/   # 标签规定：FAO 扫描件 + feed-china 转载 + pdftotext
│   │   ├── gb-t-31216-2014/      # 犬粮：页图 + 数值表 OCR + 预览页 HTML
│   │   └── gb-t-31217-2014/      # 猫粮：同上
│   ├── transcription/spec.json   # 转录规格（数据不是代码：哪条规则取哪处原文）
│   └── clauses/                  # 条文块 + 来源登记（脚本产出，禁手抄）
│       ├── sources.json
│       └── {label,nutrition,claim}.json
├── rules/                    # 版本化规则包（生成器产出，禁手改）
│   ├── ruleset-{label,nutrition,claim}.json
│   └── manifest.json
└── samples/                  # README 可跑输入夹具（生成器产出，位级一致守门）
```

### 6.2 双重门控（每条规则两个独立状态）

| 字段 | 语义 | 作用 |
|---|---|---|
| `status` | **数值**核对状态（`verified`/`pending`） | **唯一门控判定路径**的开关 |
| `clause_status` | **条款号**核对状态（`verified`/`pending`） | 只管可证性展示，**不阻断判定** |

门控还**按计算路径分作用域**（`label`/`nutrition`/`claim`），各只校验自己引用的条目。

### 6.3 冻结与守门

- 规则包是**冻结产物，禁手改**：改需求走 `tools/transcribe_clauses.py --force` → `tools/gen_rulesets.py --force` 整目录重生成；
- **位级一致守门**：`transcribe_clauses.py --check`（含**原文逐字包含断言**）与 `gen_rulesets.py --check` 输出 `TRANSCRIBE_OK` / `FROZEN_RULESET_OK`；
- **零政策字面量门禁（M1 勘误）**：禁用 token 从规则包**运行时实算**，扫描引擎/基准/CLI/GUI 源码含 docstring 与注释。**M0 的"绝对值 < 100 豁免"口径在真实数据下使门禁完全空转**（全部百分比限值都 < 100 → token 集为空 = 假门）；M1 改为**"整数形态且 < 20 才豁免、非整数一律不豁免"**，真实规则包下 token 集非空（11 个），并有"非空转"守门测试锁死。

### 6.4 数值基准（M1 新增，正确性关键）

GB/T 31216/31217 的理化指标表头写明 **"指标（以干物质计）/%"**，而标签上标示的保证值
是**按标示状态（as-fed）**给的。**两者基准不同，直接比会造假结论**：
高水分湿粮的标示百分数换算到干基后显著变大，直接比会误判为不符合。

- 规则条目带 `basis` 字段（`dry_matter` / `as_fed`）；
- 引擎对 `basis=dry_matter` 的规则先做 `干基值 = 标示值 / (1 - 水分% / 100)` 再比；
- **水分未标示 → 记 `unknown` + 原因码 `basis_undetermined`**，绝不拿未换算的值直接比，也绝不猜一个水分；
- 换算过程写进结论的 `note`（"标示值 X 换算为干基 Y（水分 Z%）"），报告里可见。

### 6.5 验收门槛（数据非代码）

`manifest.json` 的 `thresholds`（`min_accuracy` / `max_false_positive` / `max_runtime_sec`）**随规则包下发**，基准层**只读**；缺失即报配置错误（exit 2），**不得回落代码里的默认值**。

---

## 七、M1 末态快照（2026-10-15）

| 项 | 状态 |
|---|---|
| 规则包文件 | ✅ 三份 + manifest，**45 条规则**（43 `verified` / 2 `pending`） |
| 生效规则数 | **43**（`pflc diagnostics` → exit 0） |
| 原文快照 | ✅ 已入仓（标签规定 3 件 + 两标准各 9 件），sha256 台账登记 |
| 条文块 | ✅ `clauses/{label,nutrition,claim}.json` + `sources.json`（脚本产出，`--check` 位级一致） |
| 转录器 | ✅ `tools/transcribe_clauses.py`（**原文逐字包含断言**，禁手抄） |
| 夹具 | ✅ 4 份合成标签（`data/samples/`，按 as-fed 口径重写，生成器位级一致守门） |
| 基准四套件 | ✅ **全部达标**（detection / overall / boundary / traceability） |
| 基准真值库 | ⬜ 待 M4（生成器已就绪，`data/benchmark/cases.json` 未落盘） |

**M1 实测勘误（M0 骨架对规则的猜测 → M1 实况）**：

| # | M0 骨架的写法 | M1 实测事实 | 处置 |
|---|---|---|---|
| 1 | 零政策字面量豁免"绝对值 < 100" | 真实国标限值全落在 0.09–28 → **整包豁免，门禁空转** | 改为"整数 <20 豁免 / 非整数不豁免"；加非空转守门测试 |
| 2 | 引擎直接比限值与保证值 | GB/T 表头是"以干物质计"，标签是 as-fed → **不同基准** | 新增 `basis` 字段 + 干基换算 + 缺水分记 `unknown` |
| 3 | 保证值正则指标名 `{2,12}` 字 | 别名表含单字指标（钙/磷）→ **整行解析不到** | 下界改 `{1,12}`；加守门测试 |
| 4 | 报告/夹具用 `str(value.normalize())` | 产出 `3E+1`：人读不出、夹具写回再解析成 `3` | 新增 `format_decimal()`（定点、无 E 记号） |
| 5 | `additives` 写死为无条件义务 | 原文第六条只要求原料组成以两个引导词分列 → **条件触发** | 改为 `conditional`；基准期望从规则包 `effect` 实算 |
| 6 | 20 号公告"官方 URL 404" | 官方页实测 **HTTP 200**（候选 URL 选错） | 台账改正 |
| 7 | 冻结数据 CR 门禁扫全部文件 | 二进制 PNG/PDF 的 0x0D 是合法内容字节 → **误报** | 按扩展名豁免 + 非空转守门测试 |

**M2 待办**：见 `plan/HANDOFF-M2.md`（**已完成**——解析层 FR-01 全覆盖）。

---

## 八、M3 末态快照（2026-10-15）

| 项 | 状态 |
|---|---|
| 规则包文件 | ✅ 三份 + manifest，**45 条规则**（43 `verified` / 2 `pending`）——**M3 未改数据** |
| 生效规则数 | **43**（`pflc diagnostics` → exit 0；label 8/8 · nutrition 30/32 · claim 5/5） |
| 判定维度 | ✅ 三模块齐备（`presence` / `threshold` / `claim_support`），逐项三态结论 + 条款锚点 |
| 分派表结构性守门 | ✅ `_JUDGES` 与 `KINDS` 一一对应 + 实现互不相同 + 夹具驱动全部 kind（**M3 新增**，K28） |
| 基准四套件 | ✅ **全部达标**（detection 1.00 / overall 1.00 / boundary 60/60 / traceability 43/43） |
| 测试 | ✅ **231 项**（M2 末态 229 → +2），3.8 与 3.12 双解释器全绿 |
| 基准真值库 | ⬜ 待 M4（生成器已就绪，`data/benchmark/cases.json` **未落盘**——M4 缺口 1） |
| 覆盖登记采样数 | ⬜ 待 M4（`sampled_in_truth` 仍为 `null`、`sample_list` 仍为 `[]`——M4 缺口 2） |

**M3 实测勘误 0 处**：判定层语义在 M0/M2 已定型，本棒未发现新的口径错误；工作量为
"逐条勾掉 DoD + 回填实测证据 + 补一条缺失的结构性守门"，**未新增判定逻辑**。

**M4 待办**：见 `plan/HANDOFF-M4.md` §三（三处真实缺口：基准 fixtures 入仓 /
覆盖登记双数回填 / 指标进 README）。
