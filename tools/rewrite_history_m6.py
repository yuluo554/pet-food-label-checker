"""M6 转公开三清之一：本地历史重写（filter-repo）。

**为什么必须做**：历史里的两处本机用户名路径与全部提交元数据的私人邮箱，
在切公开 visibility 的那一刻就永久公开了。git 历史不可变，故只能在**推之前**
重写；本项目此刻**尚未接远端**（`git remote -v` 为空）= 无人持有旧副本，
是最安全的时机（重写后无强推风险）。

**本脚本做什么**：
  1. 先断言备份 bundle 存在（重写不可逆，没有备份不许动）；
  2. 把本机用户名路径替换为中性占位符（两种分隔符形态都换）；
  3. 用 `.mailmap` 把全部提交的作者/提交者邮箱换成 GitHub noreply 形态
     （``<id>+<login>@users.noreply.github.com``，这**正是**审计器已豁免的
     目标形态——见 audit_desensitize._is_exempt_email）；
  4. 改本地 git config，避免**后续提交**又把私人邮箱写回去；
  5. 重写后跑审计对账（HARD 必须为 0）。

**注意**：filter-repo 会删掉 `origin` remote（默认行为）。本棒无远端，无影响。

用法：py -X utf8 tools/rewrite_history_m6.py [--apply]
      （不带 --apply 只做演练，打印将执行的动作）
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    if _stream is not None:
        _enc = (getattr(_stream, "encoding", "") or "").lower()
        if _enc not in ("utf-8", "utf8"):
            _reconf = getattr(_stream, "reconfigure", None)
            if _reconf is not None:
                try:
                    _reconf(encoding="utf-8")
                except (ValueError, OSError):
                    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from audit_desensitize import compute_tokens  # noqa: E402

OK_MARKER = "REWRITE_HISTORY_OK"

#: 备份 bundle 路径（重写前必须存在；重写不可逆）
BACKUP = ROOT / ".tmp" / "backup-pre-m6.bundle"

#: GitHub noreply 形态的替代邮箱。id 与 login 运行时从 gh 实算
#: （不在源码里写死身份信息）。
def noreply_email() -> str:
    proc = subprocess.run(
        ["gh", "api", "user", "--jq", ".id, .login"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        raise SystemExit("无法从 gh 取身份（gh api user 失败）：%s"
                         % (proc.stderr or "").strip()[:200])
    lines = [l.strip() for l in proc.stdout.splitlines() if l.strip()]
    if len(lines) < 2:
        raise SystemExit("gh api user 返回不完整：%r" % lines)
    return "%s+%s@users.noreply.github.com" % (lines[0], lines[1])


def _run(args, **kw):
    return subprocess.run(args, cwd=str(ROOT), stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, encoding="utf-8",
                          errors="replace", **kw)


def current_emails() -> list:
    out = _run(["git", "log", "--format=%ae%n%ce", "--all"]).stdout or ""
    return sorted({l.strip() for l in out.splitlines() if l.strip()})


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="本地历史重写（filter-repo）")
    parser.add_argument("--apply", action="store_true", help="真的执行（否则只演练）")
    args = parser.parse_args(argv)

    problems = []

    # --- 前置：备份必须存在 ---------------------------------------------
    if not BACKUP.is_file():
        problems.append("缺备份 bundle：%s（重写不可逆，没备份不许动）" % BACKUP)
    if _run(["git", "remote", "-v"]).stdout.strip():
        problems.append("已有远端 —— 重写会产生强推面，请先确认（本棒预期无远端）")

    tokens = compute_tokens()
    user = (tokens.get("user_name") or [""])[0]
    if not user:
        problems.append("取不到本机用户名 —— 替换表达式无法实算")

    emails_before = current_emails()
    target = noreply_email()
    if target in emails_before:
        print("提示：邮箱已是 noreply 形态，无需改写")

    if problems:
        for p in problems:
            print("问题：%s" % p, file=sys.stderr)
        return 1

    # --- 替换表达式（两种分隔符形态） -----------------------------------
    expressions = (
        "Users\\%s==>Users\\<USER>\n" % user
        + "Users/%s==>Users/<USER>\n" % user
    )
    expr_path = ROOT / ".tmp" / "rewrite-expressions.txt"
    expr_path.parent.mkdir(parents=True, exist_ok=True)
    with open(expr_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(expressions)

    # --- 邮箱改写走 callback，**不落 .mailmap 文件** ---------------------
    #
    # 为什么不用 `--use-mailmap` / `.mailmap`：mailmap 的每一行都是
    # `<新邮箱> <旧邮箱>` —— 把私人邮箱**原样写进一个仓库文件**。那文件要么
    # 入仓（自曝，等于没脱敏），要么留在工作区（下一个人 `git add -A` 就带上）。
    # callback 把目标邮箱算在 `.tmp/`（.gitignore 内）的临时脚本里，零残留。
    callback_path = ROOT / ".tmp" / "rewrite-email-callback.py"
    with open(callback_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write('return b"%s"\n' % target)

    print("将替换的路径形态：%d 条（用户名实算，不打印词面）"
          % len(expressions.splitlines()))
    print("将改写的邮箱：%d 个 -> noreply 形态" % len(emails_before))
    print("表达式表：%s" % expr_path)
    print("邮箱 callback：%s" % callback_path)

    if not args.apply:
        print("（演练模式，未执行；加 --apply 真跑）")
        return 0

    # --- 执行重写 -------------------------------------------------------
    proc = _run([sys.executable, "-X", "utf8", "-m", "git_filter_repo",
                 "--force", "--replace-text", str(expr_path),
                 "--email-callback", str(callback_path)])
    print((proc.stdout or "")[-600:])
    if proc.returncode != 0:
        print("问题：filter-repo 失败（exit %d）" % proc.returncode, file=sys.stderr)
        return 1

    # --- 后续提交不再写回私人邮箱 ---------------------------------------
    _run(["git", "config", "user.email", target])
    _run(["git", "config", "user.name", "yuluo554"])

    # --- 对账：HARD 必须为 0 --------------------------------------------
    emails_after = current_emails()
    print("重写后提交邮箱：%s" % emails_after)
    if any(e != target for e in emails_after):
        problems.append("仍有非 noreply 邮箱残留：%s"
                        % [e for e in emails_after if e != target])

    audit = _run([sys.executable, "-X", "utf8",
                  str(ROOT / "tools" / "audit_desensitize.py"), "--all"])
    out = audit.stdout or ""
    tail = "\n".join(out.strip().splitlines()[-3:])
    print(tail)
    if "HARD 0" not in out:
        problems.append("重写后全历史审计仍有 HARD 命中（见上）")

    if problems:
        for p in problems:
            print("问题：%s" % p, file=sys.stderr)
        return 1
    print(OK_MARKER)
    return 0


if __name__ == "__main__":
    sys.exit(main())
