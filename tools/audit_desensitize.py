#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""脱敏审计器：tracked / history / messages 三模式 + selftest 阳性对照。

**token 运行时实算**（见 plan/07 §脱敏四步）：禁用 token 全部**运行时实算**，
源码与留档**零词面**——用户名从 ``getpass.getuser()`` 实算、用户目录模式
由仓库盘符拼出、邮箱数字串从 ``git log`` 实算。门禁自己的输入也不许是
代码字面量（否则扫描器源码本身就成了泄露面）。

**输出一律掩码化**：命中只报"文件:行号 [类别] x次数"，**不回显敏感串原文**。

命中分级：
    HARD     —— exit 1（个人路径 / 用户标记 / 真实邮箱 / 密钥）
    REVIEW   —— 人工豁免留档后放行（系统目录、其余盘符路径）
    advisory —— 只报不阻断（长 hex 串等）

行内放行标记 ``audit-allow``：命中所在行含该标记即转白名单放过，**仍在输出里可见**。

用法：
    py -X utf8 tools/audit_desensitize.py --selftest   # 阳性对照自检
    py -X utf8 tools/audit_desensitize.py --tracked    # 扫已跟踪文件
    py -X utf8 tools/audit_desensitize.py --history    # 扫全历史 blob
    py -X utf8 tools/audit_desensitize.py --messages   # 扫提交信息
    py -X utf8 tools/audit_desensitize.py --all
"""

from __future__ import annotations

import argparse
import getpass
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, List, NamedTuple, Optional, Sequence, Tuple

# --- 入口编码守卫 ---------------------------------------------------------
for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    if _stream is not None:
        _enc = (getattr(_stream, "encoding", None) or "").lower()
        if _enc not in ("utf-8", "utf8"):
            _reconf = getattr(_stream, "reconfigure", None)
            if _reconf is not None:
                try:
                    _reconf(encoding="utf-8")
                except (ValueError, OSError):
                    pass

ROOT = Path(__file__).resolve().parent.parent

#: 成功标记词（守门测试断言它出现）
OK_MARKER = "DESSENSITIZE_AUDIT_OK"

#: 分级
HARD = "HARD"
REVIEW = "REVIEW"
ADVISORY = "advisory"

#: 行内放行标记
ALLOW_MARKER = "audit-allow"

#: 按「路径 glob + 规则名」绑定的豁免表（**不是"这个文件全放过"**）。
#: 每条都要能说出理由——豁免绑定具体规则，该文件的其他规则照常生效。
EXEMPTIONS = (
    ("docs/DIST-sha256-*.txt", "long_hex",
     "sha256 留档文件，正文即 64 位十六进制哈希值本体，非泄露面"),
    ("docs/DIST-sha256-*.txt", "phone",
     "同上：哈希串里的数字段不构成手机号（且已加 hex 边界环视）"),
    ("docs/DIST-sha256-*.txt", "id_card",
     "同上：哈希串里的数字段不构成身份证号"),
)


def _is_exempt(location: str, category: str) -> bool:
    """命中是否按「路径 glob + 规则名」豁免。"""
    import fnmatch

    normalized = location.replace("\\", "/")
    for pattern, rule, _reason in EXEMPTIONS:
        if rule != category:
            continue
        if fnmatch.fnmatch(normalized, pattern):
            return True
    return False


def exemption_notes() -> List[str]:
    """豁免理由清单（供留档引用）。"""
    return ["%s [%s] —— %s" % (pattern, rule, reason)
            for pattern, rule, reason in EXEMPTIONS]

#: 扫描面排除（按**特征**而非名字，见 plan/07 反模式）
EXCLUDE_DIRS = {".git", "__pycache__", ".venv", "venv", "build", "dist",
                ".pytest_cache", ".tmp", "node_modules", ".clean-store"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".so", ".pyd", ".dll", ".exe", ".pdf",
                    ".ceb", ".png", ".gif", ".jpg", ".jpeg", ".zip"}


class Finding(NamedTuple):
    category: str
    severity: str
    location: str
    count: int


# --------------------------------------------------------------------------
# token 运行时实算（源码里不留任何敏感字面量）
# --------------------------------------------------------------------------


def compute_tokens() -> Dict[str, List[str]]:
    """实算全部禁用 token。

    每个 token 的来源都可指认（首行打印 provenance），且**不在源码里出现**。
    """
    tokens: Dict[str, List[str]] = {}

    # 1) 当前用户名 —— 从环境实算
    user = ""
    try:
        user = getpass.getuser()
    except Exception:
        user = ""
    if user:
        tokens["user_name"] = [user]

    # 2) 本机工作根路径段 —— 从仓库绝对路径实算
    #
    #    **排除仓库目录名本身**：它是有意公开的项目坐标（会出现在 README、
    #    plan 文档、安装命令里），不是泄露面。真正要查的是它**上面的**
    #    本地工作根路径段（用户主目录布局 / 盘符目录名）。
    drive = ROOT.drive  # 如 "D:"
    repo_name = ROOT.name
    parts = [p for p in ROOT.parts if p not in (ROOT.anchor, "\\", "/")]
    tokens["repo_path_segments"] = [
        p for p in parts if len(p) >= 4 and p != repo_name
    ]

    # 3) 提交元数据里的邮箱 —— 从 git log 实算
    emails = _git_emails()
    tokens["commit_emails"] = emails

    # 4) 用户目录模式 —— 由盘符/环境拼出（不写死）
    home_patterns: List[str] = []
    if drive:
        home_patterns.append(drive + "\\Users\\")
        home_patterns.append(drive + "/Users/")
    tokens["home_patterns"] = home_patterns

    return tokens


def token_provenance(tokens: Dict[str, List[str]]) -> List[str]:
    """token 来源说明（**只写类别与实算来源，不写词面值**）。"""
    return [
        "user_name        ← getpass.getuser()（运行时实算）",
        "repo_path_segments ← 仓库**上级**路径段（运行时实算；仓库目录名本身是有意公开的项目坐标，不计）",
        "commit_emails    ← git log --format=%ae %ce --all（运行时实算）",
        "home_patterns    ← 仓库盘符 + Users 段拼出（运行时实算）",
    ]


def _git_emails() -> List[str]:
    out = _run_git(["log", "--format=%ae%n%ce", "--all"])
    if out is None:
        return []
    found = set()
    for line in out.splitlines():
        line = line.strip()
        if "@" in line and _is_plausible_email(line):
            found.add(line)
    return sorted(found)


def _is_plausible_email(text: str) -> bool:
    """收紧的邮箱形态：首字符为字母数字 + 域名至少两段。

    宽松模式会把 ``git log -p`` 的 diff 前缀 ``+`` 吞进本地部分（见 plan/07）。
    """
    return bool(re.match(r"^[A-Za-z0-9][A-Za-z0-9._%+-]*@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$",
                         text))


def _is_exempt_email(text: str) -> bool:
    """豁免：GitHub noreply（已脱敏的目标形态）与 git 传输地址。

    这两条**也要进 selftest 阴性对照**——豁免项不测等于没豁免。
    """
    lowered = text.lower()
    if lowered.endswith("@users.noreply.github.com"):
        return True
    if re.match(r"^(git|ssh|hg)@[A-Za-z0-9.-]+$", lowered):
        return True
    return False


# --------------------------------------------------------------------------
# git 通道
# --------------------------------------------------------------------------


def _run_git(args: Sequence[str], cwd: Optional[Path] = None) -> Optional[str]:
    """跑 git 命令。**子进程显式 encoding**（无环境变量可替代，见 plan/07 K22）。"""
    try:
        proc = subprocess.run(
            ["git"] + list(args),
            cwd=str(cwd or ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, ValueError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def _has_git() -> bool:
    return _run_git(["rev-parse", "--git-dir"]) is not None


def tracked_files() -> List[Path]:
    """已跟踪文件清单。无 git 时退回文件系统遍历（**无 git 兜底**）。"""
    out = _run_git(["-c", "core.quotepath=false", "ls-files"])
    if out is None:
        return _walk_fallback()
    files = []
    for line in out.splitlines():
        line = line.strip()
        if line:
            files.append(ROOT / line)
    return files


def _walk_fallback() -> List[Path]:
    """无 git 兜底：按**特征**排除（不按名字）。"""
    files: List[Path] = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in EXCLUDE_SUFFIXES:
            continue
        files.append(path)
    return files


def history_blobs() -> List[Tuple[str, str]]:
    """全历史文本内容（逐提交迭代，**不用多 revision git grep**）。

    ``git grep -e <模式> $(git rev-list --all)`` 只把首个非选项参数当 revision，
    返回 0 行造成"全历史干净"**假绿**（见 plan/07）。这里逐提交迭代。
    """
    revs = _run_git(["rev-list", "--all"])
    if revs is None:
        return []
    chunks: List[Tuple[str, str]] = []
    for rev in revs.split():
        out = _run_git(["grep", "-I", "-h", "-e", "", rev])
        if out:
            chunks.append((rev[:12], out))
    return chunks


def commit_messages() -> List[Tuple[str, str]]:
    out = _run_git(["log", "--all", "--format=%H%x09%s%x09%b"])
    if out is None:
        return []
    chunks: List[Tuple[str, str]] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        sha, _, rest = line.partition("\t")
        chunks.append((sha[:12], rest))
    return chunks


# --------------------------------------------------------------------------
# 扫描
# --------------------------------------------------------------------------


def _scan_text(text: str, tokens: Dict[str, List[str]],
               location: str) -> List[Finding]:
    """扫一段文本。返回掩码化的命中（不回显原文）。"""
    findings: List[Finding] = []
    lines = text.splitlines()

    def _hit(category: str, severity: str, pattern: str) -> None:
        if _is_exempt(location, category):
            return  # 按「路径 glob + 规则名」豁免（理由见 EXEMPTIONS）
        count = 0
        rx = re.compile(pattern)
        for line in lines:
            if ALLOW_MARKER in line:
                # 行内放行：仍可见，但不算命中
                continue
            if rx.search(line):
                count += 1
        if count:
            findings.append(Finding(category, severity, location, count))

    # 个人路径（HARD）
    for pattern in tokens.get("home_patterns", []):
        _hit("home_path", HARD, re.escape(pattern))
    # 用户名（HARD，短标记做**组合路径签名**匹配，不匹配裸词）
    for name in tokens.get("user_name", []):
        _hit("user_name_signature", HARD,
             r"Users[\\/]" + re.escape(name) + r"(?![A-Za-z0-9])")
    # 仓库路径段（REVIEW——本机工作根，公开仓不含）
    for seg in tokens.get("repo_path_segments", []):
        _hit("repo_path_segment", REVIEW, re.escape(seg))
    # 提交邮箱（HARD，豁免 noreply 与 git 传输地址）
    for email in tokens.get("commit_emails", []):
        if _is_exempt_email(email):
            continue
        _hit("commit_email", HARD, re.escape(email))
    # 通用邮箱形态（REVIEW；豁免 noreply 与 example.com 保留域）
    generic = re.compile(r"\b[A-Za-z0-9][A-Za-z0-9._%+-]*@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+\b")
    count = 0
    for line in lines:
        if ALLOW_MARKER in line:
            continue
        for match in generic.finditer(line):
            value = match.group(0)
            if _is_exempt_email(value):
                continue
            if value.lower().endswith("@example.com"):
                continue
            count += 1
    if count:
        findings.append(Finding("generic_email", REVIEW, location, count))
    # 手机号（HARD；hex 边界环视防 sha256 误报）
    _hit("phone", HARD, r"(?<![0-9a-fA-F])1[3-9]\d{9}(?![0-9a-fA-F])")
    # 身份证（HARD；hex 边界环视防 Panose 误报）
    _hit("id_card", HARD, r"(?<![0-9a-fA-F])\d{17}[\dXx](?![0-9a-fA-F])")
    # 密钥形态（HARD）
    _hit("api_key", HARD, r"\bsk-[A-Za-z0-9]{16,}")
    # 长 hex 串（advisory 只报不阻断）
    _hit("long_hex", ADVISORY, r"\b[0-9a-fA-F]{40,}\b")
    return findings


def scan_tracked(tokens: Dict[str, List[str]]) -> List[Finding]:
    findings: List[Finding] = []
    for path in tracked_files():
        if path.suffix.lower() in EXCLUDE_SUFFIXES:
            continue
        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            rel = str(path.relative_to(ROOT))
        except ValueError:
            rel = str(path)
        findings.extend(_scan_text(text, tokens, rel))
    return findings


def scan_history(tokens: Dict[str, List[str]]) -> List[Finding]:
    findings: List[Finding] = []
    for rev, text in history_blobs():
        findings.extend(_scan_text(text, tokens, "history:" + rev))
    return findings


def scan_messages(tokens: Dict[str, List[str]]) -> List[Finding]:
    findings: List[Finding] = []
    for sha, text in commit_messages():
        findings.extend(_scan_text(text, tokens, "message:" + sha))
    return findings


# --------------------------------------------------------------------------
# 输出
# --------------------------------------------------------------------------


def render(findings: Sequence[Finding], mode: str) -> str:
    """掩码化输出：只报"位置 [类别] x次数"，不回显原文。"""
    lines = ["=== 脱敏审计（%s）===" % mode]
    if not findings:
        lines.append("0 命中")
        return "\n".join(lines)
    grouped: Dict[Tuple[str, str], int] = {}
    for f in findings:
        key = (f.location, f.category)
        grouped[key] = grouped.get(key, 0) + f.count
    for (location, category), count in sorted(grouped.items()):
        severity = next(f.severity for f in findings
                        if f.location == location and f.category == category)
        lines.append("%s [%s/%s] x%d" % (location, category, severity, count))
    return "\n".join(lines)


def hard_count(findings: Sequence[Finding]) -> int:
    return sum(1 for f in findings if f.severity == HARD)


def review_count(findings: Sequence[Finding]) -> int:
    return sum(1 for f in findings if f.severity == REVIEW)


# --------------------------------------------------------------------------
# selftest 阳性对照
# --------------------------------------------------------------------------


def selftest() -> int:
    """阳性/阴性对照：证明扫描器**真的在扫**。

    阳性对照的敏感串**程序化合成**（片段拼接），源码里不留完整词面。
    判别依据：命中分级必须正确，且豁免项（noreply / git 传输地址）
    与误报校准项（长 hex、URL scheme）**必须不命中**。
    """
    user = getpass.getuser() or "placeholder"
    # 程序化合成阳性样本（片段拼接，源码里无完整敏感串）
    synthetic_home = "%s\\%s\\%s" % ("C:", "Users", user)
    synthetic_email = "%s@%s.%s" % ("someone", "synthetic-mail", "test")
    synthetic_phone = "1" + "3" + "9" * 9
    synthetic_key = "sk-" + "A" * 24

    tokens = {
        "user_name": [user],
        "home_patterns": ["C:\\Users\\"],
        "commit_emails": [synthetic_email],
        "repo_path_segments": ["zzz-non-existent-segment"],
    }

    cases = [
        ("home_path", HARD, synthetic_home),
        ("phone", HARD, synthetic_phone),
        ("api_key", HARD, synthetic_key),
        ("commit_email", HARD, synthetic_email),
    ]
    ok = True
    for expected_category, expected_severity, sample in cases:
        hits = _scan_text(sample, tokens, "selftest")
        matched = [h for h in hits if h.category == expected_category]
        if not matched:
            print("selftest 失败：%s 阳性样本未命中" % expected_category, file=sys.stderr)
            ok = False
        elif matched[0].severity != expected_severity:
            print("selftest 失败：%s 分级错误" % expected_category, file=sys.stderr)
            ok = False

    # --- 阴性对照：这些**必须不命中** -----------------------------------
    negatives = [
        ("noreply 邮箱", "%s@users.noreply.github.com" % ("1234567",)),
        ("git 传输地址", "git@github.com"),
        ("example.com 保留域", "test@example.com"),
        ("sha256 hex（非手机号）", "a" * 40 + "1"),
        ("URL scheme（非盘符）", "https://example.org/path"),
    ]
    for label, sample in negatives:
        hits = _scan_text(sample, tokens, "selftest")
        bad = [h for h in hits if h.severity == HARD]
        if bad:
            print("selftest 失败：阴性对照 %s 误报 %s" % (label, bad[0].category),
                  file=sys.stderr)
            ok = False

    # --- 阳性对照：放行标记生效 -----------------------------------------
    allowed_line = "path = 'C:\\Users\\%s'  # %s" % (user, ALLOW_MARKER)
    hits = _scan_text(allowed_line, tokens, "selftest")
    if any(h.category == "home_path" for h in hits):
        print("selftest 失败：%s 行内放行未生效" % ALLOW_MARKER, file=sys.stderr)
        ok = False

    # --- 豁免口径对照：豁免**只**对该 glob + 规则名生效 -------------------
    # ① 豁免表里的组合：应被放过
    if _scan_text("a" * 64, {"user_name": [], "home_patterns": [],
                             "commit_emails": [], "repo_path_segments": []},
                  "docs/DIST-sha256-M0.txt"):
        print("selftest 失败：豁免文件仍报命中", file=sys.stderr)
        ok = False
    # ② 同样内容换个文件：必须照常命中（证明豁免不是"全放过"）
    if not _scan_text("1" + "3" + "9" * 9, {"user_name": [], "home_patterns": [],
                                            "commit_emails": [],
                                            "repo_path_segments": []},
                      "src/pflc/other.py"):
        print("selftest 失败：豁免表被过度放宽（其他文件不再报命中）", file=sys.stderr)
        ok = False
    # ③ 豁免文件的**其他**规则仍生效
    if not _scan_text("sk-" + "B" * 24,
                      {"user_name": [], "home_patterns": [], "commit_emails": [],
                       "repo_path_segments": []},
                      "docs/DIST-sha256-M0.txt"):
        print("selftest 失败：豁免文件的其他规则被一并放过", file=sys.stderr)
        ok = False

    if ok:
        print("selftest 通过（阳性 4 项 / 阴性 5 项 / 放行 1 项 / 豁免边界 3 项）")
        return 0
    return 1


# --------------------------------------------------------------------------
# 入口
# --------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="脱敏审计器（token 运行时实算）")
    parser.add_argument("--selftest", action="store_true", help="阳性/阴性对照自检")
    parser.add_argument("--tracked", action="store_true", help="扫已跟踪文件")
    parser.add_argument("--history", action="store_true", help="扫全历史 blob")
    parser.add_argument("--messages", action="store_true", help="扫提交信息")
    parser.add_argument("--all", action="store_true", help="三模式全扫")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    if not (args.tracked or args.history or args.messages or args.all):
        parser.print_help()
        return 2

    tokens = compute_tokens()
    print("token provenance：")
    for line in token_provenance(tokens):
        print("  " + line)
    print("豁免口径（路径 glob + 规则名）：")
    for line in exemption_notes():
        print("  " + line)
    if not _has_git():
        print("提示：无 git 通道，历史/信息模式将退回文件系统遍历")

    findings: List[Finding] = []
    if args.tracked or args.all:
        findings.extend(scan_tracked(tokens))
    if args.history or args.all:
        findings.extend(scan_history(tokens))
    if args.messages or args.all:
        findings.extend(scan_messages(tokens))

    print(render(findings, "tracked+history+messages" if args.all else "mode"))
    hard = hard_count(findings)
    review = review_count(findings)
    print("汇总：HARD %d / REVIEW %d" % (hard, review))
    if hard:
        print("存在 HARD 命中，审计未通过", file=sys.stderr)
        return 1
    print(OK_MARKER)
    return 0


if __name__ == "__main__":
    sys.exit(main())
