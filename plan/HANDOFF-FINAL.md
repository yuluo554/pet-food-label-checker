# HANDOFF-FINAL：末态基线 / 发布执行记录 / 复跑手册 / 遗留项

> M6 出口门。本文件是本项目的**收官快照**——任何人在任何时间拿到这个仓库，
> 读这一份就能知道"现在是什么状态、怎么复跑、还剩什么没做"。
>
> 生成于 2026-10-15（M6 收棒）。**库内一律相对路径**；对外坐标见 §一「发布坐标」。

---

## 一、发布坐标（末态）

| 项 | 值 |
|---|---|
| 公开仓库 | <https://github.com/yuluo554/pet-food-label-checker> |
| 可见性 | **PUBLIC**（三清完成后才切） |
| Release | `v0.1.0` · <https://github.com/yuluo554/pet-food-label-checker/releases/tag/v0.1.0> |
| 发布基线提交 | `ef76135`（= tag `v0.1.0` 指向的提交）<br>**注**：本棒做过**两次**历史重写（见 §四），早期提交的 SHA 已变；以本节为准 |
| 提交总数 | 17（`git rev-list --count HEAD`） |
| 附件（ASCII 名） | `pflc-gui-windows-x64-0.1.0.zip`（165 文件 / 110.9 MB）<br>`pflc-cli-windows-x64-0.1.0.zip`（23 文件 / 16.5 MB） |
| sha256 留档 | `docs/DIST-sha256-M6.txt`（zip sha256 + 文件数 + **树 sha256**） |
| topics | 8 个（`pet-food` / `label-compliance` / `rules-engine` / `china-regulation` / `python` / `pyside6` / `offline` / `food-safety`），已回读确认 |

**附件 sha256**（与真下载核对一致）：

```
d9b63eab69a06155bbe6069ed9c6d678096bf8e8d56fdf28a8825748d8f7381d  pflc-cli-windows-x64-0.1.0.zip
33fe4d6128c839857b59bc72808f87ef63bf416ac86ccc1425bab87636a2dcd4  pflc-gui-windows-x64-0.1.0.zip
```

---

## 二、末态基线（全部实测）

| 项 | 值 | 怎么核 |
|---|---|---|
| 全量测试 | **297 passed**（Python 3.8.8 / 3.12.10 各一遍） | `py -X utf8 -m pytest -q` · `py -3.12 -X utf8 -m pytest -q` |
| 规则包 | **45 条**（`label` 8 / `nutrition` 32 / `claim` 5；**43 `verified` + 2 `pending`**） | `py -X utf8 -m pflc.cli diagnostics` |
| 基准 | 四套件全达标，期望锚定冻结真值库（`truth_source=frozen`） | `py -X utf8 -m pflc.cli bench` |
| 守门标记 | `TRANSCRIBE_OK` · `FROZEN_RULESET_OK` · `FROZEN_CASES_OK` · `FROZEN_SAMPLES_OK` · `DESSENSITIZE_AUDIT_OK` · `SMOKE_CLI_OK` · **`RELEASE_PACK_OK`** · **`VERIFY_FROZEN_OK`**（两树） · **`DEMO_ASSETS_OK`** | 见 §三 复跑手册 |
| 冻结产物 | `dist/pflc/`（GUI 110.9 MB）+ `dist/pflc-cli-dist/`（CLI 16.5 MB），两树均 `VERIFY_FROZEN_OK` | 同上 |
| CI | **7/7 全绿**（当前基线 `ef76135`：run `38707310951` / `38707331035`） | `gh run list` |
| 脱敏 | `--tracked` HARD 0 / REVIEW 0；`--all` **HARD 0** | 见 §三 |

---

## 三、复跑手册（从零到"全绿"的完整命令序列）

> **执行通道**：一律 `py -X utf8`。本机裸 `python` 是 Windows Store 桩
> （`python -c "print(1)"` → **exit 49，无输出**）——用它跑变异脚本会"看似没生效"。

### 3.1 首次上手（干净环境）

```bash
git clone git@github.com:yuluo554/pet-food-label-checker.git
cd pet-food-label-checker
py -m venv .venv                 # 3.8 或 3.12 都可以
.venv\Scripts\activate           # Linux/macOS: source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"     # 测试面
python -m pytest -q                   # 期望 287 passed / 2 skipped（无 gui/dist 时）
```

### 3.2 全套守门（每次收尾必跑）

```bash
py -X utf8 -m pytest -q                        # 297 passed（本机装齐 gui+demo+build 时）
py -3.12 -X utf8 -m pytest -q                  # 双解释器验证

py -X utf8 tools/transcribe_clauses.py --check   # TRANSCRIBE_OK
py -X utf8 tools/gen_rulesets.py --check         # FROZEN_RULESET_OK
py -X utf8 tools/gen_cases.py --check            # FROZEN_CASES_OK
py -X utf8 tools/gen_samples.py --check          # FROZEN_SAMPLES_OK
py -X utf8 tools/audit_desensitize.py --selftest # 阳性 4 / 阴性 5 / 放行 1 / 豁免边界 6
py -X utf8 tools/audit_desensitize.py --tracked  # HARD 0 / REVIEW 0 → DESSENSITIZE_AUDIT_OK
py -X utf8 tools/smoke_cli.py                    # SMOKE_CLI_OK
py -X utf8 tools/check_demo_reproducible.py      # DEMO_ASSETS_OK（需 gui + demo extra）
```

### 3.3 打包与发布（要 build / gui / demo extra）

```bash
python -m pip install -e ".[gui,build,demo]"     # build=PyInstaller, demo=Pillow

py -3.12 -m PyInstaller --clean --noconfirm tools/pflc.spec
py -X utf8 tools/verify_frozen.py --dist dist/pflc-cli-dist --selftest   # VERIFY_FROZEN_OK
py -X utf8 tools/verify_frozen.py --dist dist/pflc --selftest            # VERIFY_FROZEN_OK

# 发布 zip（确定性）+ 三条判据 + 更新留档
py -X utf8 tools/make_release.py --dist dist --out release --check \
    --ledger docs/DIST-sha256-M6.txt                                     # RELEASE_PACK_OK
```

> ⚠️ **别在仓库树内跑冻结态验收**：CWD 上溯会命中仓库 `data/`，
> "内嵌数据"就验了个寂寞（`verify_frozen.py` 自己会切到中立临时目录）。

### 3.4 发布后复核（每次改源码重建产物后）

```bash
gh release download v0.1.0 --repo yuluo554/pet-food-label-checker
# 逐条对账 sha256（表见 docs/DIST-sha256-M6.txt），再在中立目录解压跑：
#   pflc-cli.exe selftest --out selftest.json
#   pflc-cli.exe check <包内 data/samples/label-demo-ok.txt>
#   pflc-cli.exe bench          # 必须看到 truth_source=frozen
```

### 3.5 数据层（**改了必须走生成器**）

```bash
py -X utf8 tools/transcribe_clauses.py --force   # 改 spec.json 后重转录
py -X utf8 tools/gen_rulesets.py --force         # 重生成规则包（内部先产真值库再实算覆盖）
py -X utf8 tools/gen_cases.py --force            # 重生成真值库（入库件）
py -X utf8 tools/gen_samples.py --force          # 重生成夹具
```

> **改完必须重跑基准确认不回退**，并对照 `plan/07` §四 的 **K1–K34 既定口径清单**
> —— 那些口径"动了会打挂基准"。

---

## 四、发布执行记录（M6 当日做了什么）

| 步骤 | 结果 |
|---|---|
| 备份 | `git bundle create .tmp/backup-pre-m6.bundle --all`（12 rev / 9 MB，`verify` 报完整历史） |
| 历史重写 | `tools/rewrite_history_m6.py --apply` → **HARD 3→0**；两处本机用户名路径 + 全部提交邮箱（→ GitHub noreply） |
| 建远端 | 先 **private**（`gh repo create --private`），避免首跑红留进公开历史 |
| 首推 CI | 首跑 **8 job / 5 绿 3 红**（run `38702307047`） |
| 修缺陷 | 3 个真缺陷（全部"本机绿、CI 红"），修完复跑 **7/7 全绿** |
| 三清收尾 | 删失败 run `38702307047` |
| Release | tag `v0.1.0` + Release + 两个 zip 附件 |
| topics | 8 个，已回读 |
| 真下载复核 | sha256 一致 + 中立目录解压 + 冻结态自检 + CLI 五连 → 全过 |
| 切 public | 三清完成后才切 |
| 发布后 clone | 公开 clone：历史 `--all` **HARD 0**、**287 passed**、`DEMO_ASSETS_OK` |
| **第二次历史重写（本棒自己引入的泄露）** | 写 §三「提交元数据邮箱检查」时，把重写**前**的私人邮箱**词面**直接抄进了 `plan/RELEASE-M6.md`——**清它的动作本身又把它公开了一次**。由 `--tracked` 审计在文档回填后抓出（`generic_email/REVIEW`）。处置：改掩码描述 + 再跑一次 `filter-repo` 把该词面从全历史清掉 + force-push（`main` 与 `v0.1.0`） |

**关于"force-push 后残余对象"的实测结论（诚实登记）**：force-push 后旧提交已不在任何 ref 上，
但 GitHub 仍保留**不可达对象**，按 SHA 直连**仍能匿名读到**该 blob（本棒实测：
`contents?ref=<旧SHA>` 返回 200 且含词面）。删仓重建可清除，但需要 `delete_repo` 权限
（本机 token 无此 scope）。

**该残余是否构成泄露面——实测判定为"非增量"**：同一邮箱**早已公开**在该账号的其他公开仓库
的提交元数据里（实测 `structural-strengthening-checker` / `dsh-prompt-polisher` / `dsh-pipeline` / `siteguard`
四个公开仓的作者邮箱均为它，匿名 API 可读）。故本仓库的这个残余**不新增任何暴露面**，
删仓重建的隐私收益为零。**如实登记，不当作"已修"**：结论是"残余存在，但不增量"，
而非"彻底清除"。真要彻底清除需 `delete_repo` 权限或联系 GitHub Support。

**首跑 3 个缺陷的根因**（详细版见 `plan/RELEASE-M6.md` §五）：

1. **新门判据张冠李戴**：ubuntu runner 用户名恰好是 `runner`，且仓库路径
   `/home/runner/work/...` 让 `repo_path_segment` 含 `runner`——样本里的
   `runner` 会**合法**命中另一条判据，而测试却断言"命中列表为空"。
2. **留档对账要求了做不到的事**：PyInstaller 产物含构建期 PE 时间戳，
   **跨次重建不逐字节可复现**（实测同机两次构建 exe sha256 不同）。
   确定性只对"**同一棵树**打两次"成立。
3. **REVIEW 级误当阻断项**：`repo_path_segment` 的取值随构建环境变化，
   若阻断会导致同一仓库在不同 runner 上时红时绿。修为**只 HARD 阻断**。

---

## 五、遗留项（**如实登记，不当作"不用做"**）

| # | 项 | 现状与建议 |
|---|---|---|
| L1 | **发布附件的 UCRT 取舍** | 发布的 zip 取自**本机树**，不含 Universal CRT（`ucrtbase.dll` + 42 个 `api-ms-win-*.dll`），依赖目标机自带（Windows 10+ 满足）。CI runner 上 PyInstaller 会收进包，故 CI 产物文件数更多（CLI 66 / GUI 208）。要覆盖更老 Windows 就从 CI 产物发布 |
| L2 | **PyInstaller 产物不可逐字节复现** | 别用"在别处重建一次"核对留档哈希。这正是 M6 把"打包确定性"的范围收窄为"同一棵树打两次"的原因 |
| L3 | **`--history` 的 13 条 REVIEW** | 全部是原文快照里**转载站点自己的公开联系邮箱**（第三方转载页的联系方式，非本项目/本机身份信息）。豁免表绑定**路径 glob**，而历史模式 location 是 `history:<sha>`，无路径可比——**设计如此**，不是漏修。该文件在 `--tracked` 下已正确豁免 |
| L4 | **2 条 `pending` 规则** | 牛磺酸一行限值随**水分形态**分支（干粮 ≥0.1 / 湿粮 ≥0.2）。当前 `applies_if` 只支持类别/生命阶段，**无法表达水分形态门控**——只按一档判会对另一档产生假合规/假违规。**宁缺勿造**，要支持须扩规则模型（属功能扩展，非缺陷） |
| L5 | **未录制视频演示** | 交付物含 GIF（`docs/demo/demo.gif`，6 页签 + 真实判定态）。若将来要视频，用 `tools/make_demo_assets.py` 同族通路录制 |
| L6 | **`docs/DIST-sha256-M0.txt` 为历史留档** | M5 版（`-M5`）与 M6 版（`-M6`）是当前有效版本；M0 版留作沿革。改动物料时**只需更新当前有效版** |
| L7 | **CI 的 Node.js 20 弃用警告** | `actions/checkout@v4` / `actions/setup-python@v5` 被强制跑在 Node 24 上，GitHub 的既有警告，不影响结论。待上游发新版本后可升 v5/v6 |

**没有"未验证"的 DoD**：M6 十三条 DoD 全部有实测证据（见 `plan/06` §M6）。
本表列的是**范围外的已知取舍**，不是"没做完"。

---

## 六、这套项目里"值钱"的几条经验（留给同类项目）

1. **首次上 CI 不可替代**。M6 首跑一次抓出 3 个"本机绿、CI 红"的真缺陷，
   全都是本机多跑几遍发现不了的（runner 的用户名/路径形态、构建环境差异、
   判据在不同环境下的稳定性）。**先 private 跑 CI，绿了再切 public**。
2. **门禁必须变异验证，且对照组要"改行为"不是"改名字"**。
   M6 当场抓出自己写的假门（阴性样本根本不含针，判据靠前缀就排除了，
   边界环视空转）。另：变异脚本的对照组一开始用"重命名测试函数"——
   那只是把测试移出收集集（exit 0），**不产生失败**，是无效对照。
3. **确定性要问清"对什么确定"**。"打包确定性"（同一棵树两次一致）与
   "构建可复现"（跨机跨次一致）是两件事。混为一谈会写出做不到的判据。
4. **豁免表要绑定"文件 + 规则名"，且要验调用方真的在调它**。
   本项目两次踩中豁免死代码（M2 的 `generic_email`、M1 的数值豁免口径）。
5. **审计扫不到的地方要在源头守**。`audit_desensitize --tracked` 看不到
   `.gitignore` 内的 `dist/`，也看不到 PNG 里的烤入文本——两处都另立了源头断言。
6. **破坏性操作前先演练、先备份、先确认没有外泄面**。
   历史重写在一次性 clone 上演练通过才动真仓库；重写时无远端 = 无强推风险。
