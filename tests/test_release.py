"""发布通路的常驻守门测试（M6）。

守三件事，缺一件都不足以说"发布物可用"：

  1. **打包确定性**：两次独立打包的 zip sha256 必须一致。不验它，"确定性打包"
     就只是 DoD 里的一句话（M6 DoD 第 7 条）；
  2. **回读保真**：解出来的条目与源树逐字节相同、集合完全一致；条目名与时间戳
     符合声明口径；
  3. **产物本体扫描真的在扫**：发行包是要发给陌生人的东西，而 ``dist/`` 在
     ``.gitignore`` 内、``audit_desensitize.py --tracked`` **看不到它**。
     故这条扫描是发行侧唯一的脱敏门——它必须配阳性/阴性对照，否则就是又一道
     "看起来绿"的门（本项目已三次踩中子串假门）。

与 ``tests/test_verify_frozen.py`` 的分工：那里守"冻结产物验收脚本"，
这里守"发布打包与产物脱敏扫描"。
"""

from __future__ import annotations

import importlib.util
import json
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"

sys.path.insert(0, str(TOOLS))


def _load_release():
    """加载 make_release 模块（工具不是包，用 importlib 挂载）。"""
    spec = importlib.util.spec_from_file_location("make_release_probe",
                                                  TOOLS / "make_release.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["make_release_probe"] = module
    spec.loader.exec_module(module)
    return module


def _load_audit():
    if "audit_desensitize" in sys.modules:
        return sys.modules["audit_desensitize"]
    spec = importlib.util.spec_from_file_location("audit_desensitize",
                                                  TOOLS / "audit_desensitize.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["audit_desensitize"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def release():
    return _load_release()


@pytest.fixture()
def fake_dist(tmp_path: Path) -> Path:
    """合成一棵最小发行树（两级目录 + 嵌套数据 + 二进制件）。"""
    dist = tmp_path / "pflc-cli-dist"
    (dist / "_internal" / "data" / "samples").mkdir(parents=True)
    (dist / "pflc-cli.exe").write_bytes(b"MZ\x00\x01\x02binary")
    (dist / "_internal" / "data" / "samples" / "a.txt").write_text(
        "hello\n", encoding="utf-8")
    (dist / "_internal" / "data" / "samples" / "b.bin").write_bytes(b"\x00\xff\xfe")
    return dist


# --------------------------------------------------------------------------
# 一、打包确定性
# --------------------------------------------------------------------------


def test_pack_is_byte_deterministic(release, fake_dist, tmp_path):
    """**两次独立打包必须产出同一个 sha256**（DoD 第 7 条的核心判据）。"""
    a = tmp_path / "a.zip"
    b = tmp_path / "b.zip"
    ra = release.build_zip(fake_dist, "pflc-cli-windows-x64", a)
    rb = release.build_zip(fake_dist, "pflc-cli-windows-x64", b)
    assert ra["sha256"] == rb["sha256"], "两次打包字节不同 = 打包不确定"
    assert a.read_bytes() == b.read_bytes()


def test_determinism_assertion_is_not_vacuous(release, fake_dist, tmp_path):
    """**非空转对照**：换掉固定时间戳必须改变 zip 字节。

    否则"两次一致"可能只是因为我们根本没把时间戳写进去（而 zip 恰好在同一
    秒内建了两次）——那这条判据就是空的。
    """
    fixed = release.FIXED_DATE_TIME
    a = tmp_path / "a.zip"
    ra = release.build_zip(fake_dist, "base", a)
    try:
        release.FIXED_DATE_TIME = (2001, 2, 3, 4, 5, 6)
        b = tmp_path / "b.zip"
        rb = release.build_zip(fake_dist, "base", b)
    finally:
        release.FIXED_DATE_TIME = fixed
    assert ra["sha256"] != rb["sha256"], (
        "改时间戳后 zip 仍一样 = 时间戳没真的写进去，确定性判据空转")


def test_zip_uses_stored_and_fixed_timestamp(release, fake_dist, tmp_path):
    """压缩方式与时间戳是**声明过的口径**，逐条目核。"""
    target = tmp_path / "x.zip"
    release.build_zip(fake_dist, "base", target)
    with zipfile.ZipFile(target) as zf:
        assert zf.namelist(), "空 zip = 判据空转"
        for info in zf.infolist():
            assert info.compress_type == zipfile.ZIP_STORED
            assert info.date_time == release.FIXED_DATE_TIME


def test_zip_entries_are_sorted_and_prefixed(release, fake_dist, tmp_path):
    """条目名字典序 + 统一顶层包目录（解压即得干净目录）。"""
    target = tmp_path / "x.zip"
    release.build_zip(fake_dist, "base", target)
    with zipfile.ZipFile(target) as zf:
        names = zf.namelist()
    assert names == sorted(names), "条目未排序 = 顺序不确定"
    assert all(n.startswith("base/") for n in names), names


# --------------------------------------------------------------------------
# 二、回读保真
# --------------------------------------------------------------------------


def test_readback_matches_source_tree(release, fake_dist, tmp_path):
    """对照组：忠实打包时回读**不得**报错（证明判据不是"见 zip 就红"）。"""
    target = tmp_path / "x.zip"
    release.build_zip(fake_dist, "base", target)
    assert release.verify_zip_readback(target, fake_dist, "base") == []


def test_readback_missing_file_is_detected(release, fake_dist, tmp_path):
    """源树多一个文件而 zip 没打进去 → 必须报出来。"""
    target = tmp_path / "x.zip"
    release.build_zip(fake_dist, "base", target)
    (fake_dist / "_internal" / "data" / "samples" / "c.txt").write_text(
        "late\n", encoding="utf-8")
    problems = release.verify_zip_readback(target, fake_dist, "base")
    assert any("条目集合与源树不符" in p for p in problems), problems


def test_readback_detects_corrupted_entry(release, fake_dist, tmp_path):
    """内容被改写（**长度不变**）→ 逐字节比对必须抓到。

    篡改**必须等长**：否则"只比长度"的退化实现也能抓到它，这条测试就不再
    证明"逐字节比对"有效（变异验证实测过——首版用了不等长篡改，把实现退化成
    比长度后测试仍绿）。
    """
    target = tmp_path / "x.zip"
    release.build_zip(fake_dist, "base", target)

    # 重写 zip，把某条目换成**等长**但不同字节的内容
    with zipfile.ZipFile(target) as zf:
        items = [(i.filename, zf.read(i.filename)) for i in zf.infolist()]
    tampered = False
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_STORED) as zf:
        for name, data in items:
            info = zipfile.ZipInfo(name, release.FIXED_DATE_TIME)
            info.compress_type = zipfile.ZIP_STORED
            if name.endswith("/a.txt"):
                assert len(data) > 0
                data = b"X" * len(data)      # 等长篡改
                tampered = True
            zf.writestr(info, data)
    assert tampered, "未命中待篡改条目 = 判据空转"

    problems = release.verify_zip_readback(target, fake_dist, "base")
    assert any("字节不同" in p for p in problems), problems


# --------------------------------------------------------------------------
# 三、产物本体扫描（发行侧唯一的脱敏门）
# --------------------------------------------------------------------------


def _user_signature():
    """本机用户名路径签名（运行时实算，源码里不留词面）。"""
    audit = _load_audit()
    tokens = audit.compute_tokens()
    return "C:" + "\\" + "Users" + "\\" + tokens["user_name"][0]


def test_body_scan_clean_tree_passes(fake_dist):
    """对照组：干净树**不得**报命中（防"见文件就红"）。"""
    release = _load_release()
    assert release.scan_tree_body(fake_dist) == []


def test_body_scan_catches_ascii_signature(tmp_path):
    """阳性对照（ASCII）：注入本机用户名路径 → 必须命中 HARD。"""
    release = _load_release()
    dist = tmp_path / "d"
    (dist / "sub").mkdir(parents=True)
    (dist / "sub" / "leak.txt").write_bytes(
        _user_signature().encode("ascii"))
    hits = release.scan_tree_body(dist)
    assert any("user_name_signature" in h and "HARD" in h for h in hits), hits


def test_body_scan_catches_utf16_signature(tmp_path):
    """阳性对照（UTF-16LE）：Windows 二进制里的路径多是 UTF-16。

    只测 ASCII 会漏掉一半形态——exe/dll 里的宽字符串就是这么存的。
    """
    release = _load_release()
    dist = tmp_path / "d"
    dist.mkdir()
    (dist / "leak.bin").write_bytes(_user_signature().encode("utf-16-le"))
    hits = release.scan_tree_body(dist)
    assert any("utf-16-le" in h for h in hits), hits


def test_body_scan_boundary_excludes_longer_user_dir(tmp_path):
    """阴性对照（**真边界**）：``Users\\<用户名><更多字母>`` 不得命中。

    变异验证抓出过首版这条测试是假门：样本用的是 ``ASUSTek COMPUTER INC``，
    它**根本不含**针 ``Users\\ASUS``——判据靠**前缀**就把它排除了，边界环视
    整段空转（把环视删掉测试仍绿）。真正需要边界的是"以用户名为前缀的
    更长目录名"，故这里用 ``Users\\<user>Other`` 这类样本。

    不改它，"别误报同名前缀"就只是注释里的一句话。
    """
    release = _load_release()
    user = _load_audit().compute_tokens()["user_name"][0]
    dist = tmp_path / "d"
    dist.mkdir()
    # 以用户名为前缀的更长路径段 —— 只有边界环视能排除它
    (dist / "x.txt").write_bytes(
        ("Users" + "\\" + user + "Other").encode("ascii"))
    assert release.scan_tree_body(dist) == [], (
        "以用户名为前缀的更长目录名被误报 = 边界环视失效")


def test_body_scan_vendor_string_is_not_false_positive(tmp_path):
    """阴性对照：``Qt`` 二进制里的常见厂商/版权串不得命中。

    这是实测场景：``dist/pflc/_internal/PySide6/*.dll`` 里存在
    ``ASUSTek COMPUTER INC``（显卡厂商串）。**注意**：该串不含针
    ``Users\\<用户名>``，靠前缀即可排除——故它只证明"扫描不是见 ASUS 就报"，
    真正的边界判据在 ``test_body_scan_boundary_excludes_longer_user_dir``。
    """
    release = _load_release()
    dist = tmp_path / "d"
    dist.mkdir()
    (dist / "Qt6Gui.dll").write_bytes(b"ASUSTek COMPUTER INC\x00\x00padding")
    assert release.scan_tree_body(dist) == []


def test_body_scan_noreply_email_is_not_flagged(tmp_path):
    """阴性对照：noreply 邮箱（已脱敏的目标形态）不得命中。"""
    release = _load_release()
    dist = tmp_path / "d"
    dist.mkdir()
    (dist / "x.txt").write_bytes(b"1234567@users.noreply.github.com")
    assert release.scan_tree_body(dist) == []


def test_body_scan_is_not_vacuous(tmp_path):
    """**非空转自检**：字面量集为空时必须报错，不能静默判"干净"。

    判据源没接上（比如 token 实算失败）时，扫描器会"零命中 = 全绿"——
    这正是本项目最忌讳的失效模式。
    """
    release = _load_release()
    dist = tmp_path / "d"
    dist.mkdir()
    (dist / "x.txt").write_bytes(b"anything")
    original = release.sensitive_literals
    try:
        release.sensitive_literals = lambda tokens: []
        problems = release.scan_tree_body(dist)
    finally:
        release.sensitive_literals = original
    assert any("空转" in p for p in problems), problems


def test_zip_body_scan_catches_injected_leak(fake_dist, tmp_path):
    """zip 通路同样有效（扫真正要发出去的那个字节流）。"""
    release = _load_release()
    (fake_dist / "leak.txt").write_bytes(_user_signature().encode("ascii"))
    target = tmp_path / "x.zip"
    release.build_zip(fake_dist, "base", target)
    hits = release.scan_zip_body(target)
    assert any("user_name_signature" in h for h in hits), hits


# --------------------------------------------------------------------------
# 四、发布附件名与留档
# --------------------------------------------------------------------------


def test_release_asset_names_are_ascii():
    """**附件名必须纯 ASCII**（DoD 第 8 条）：非 ASCII 名会进 URL 与
    ``Content-Disposition``，不同客户端下载后名字不一致。"""
    release = _load_release()
    assert release.PACKAGES, "发布物清单为空 = 判据空转"
    for _dist_name, base in release.PACKAGES:
        assert base.isascii(), "附件基名非 ASCII：%s" % base
        assert " " not in base, "附件名含空格：%s" % base


def test_release_asset_names_encode_target_platform():
    """附件名必须点明平台——否则用户不知道下哪个（两个 zip 的差别就在这）。"""
    release = _load_release()
    for _dist_name, base in release.PACKAGES:
        assert "windows" in base, "附件名未点明平台：%s" % base


def test_release_packages_cover_both_dist_trees():
    """两棵发行树**都要**有发布物：CLI 是独立形态（特意不含 Qt，K33），
    只发 GUI 会把"命令行用户白下 110 MB"变成唯一的选项。"""
    release = _load_release()
    dirs = sorted(name for name, _ in release.PACKAGES)
    assert dirs == ["pflc", "pflc-cli-dist"], dirs


def test_shipped_release_ledger_matches_archives(tmp_path):
    """入仓留档与**真打出来的 zip** 对账（留档若与产物脱节就不可核证）。

    无 dist（干净 clone / CI 未构建）时跳过——这不是"跳过即通过"：
    CI 的 package job 会真构建并跑 ``make_release.py --check``。
    """
    release = _load_release()
    if not (ROOT / "dist" / "pflc-cli-dist").is_dir():
        pytest.skip("本机无 dist 产物（需先 PyInstaller 构建）")

    ledger = ROOT / "docs" / "DIST-sha256-M6.txt"
    if not ledger.is_file():
        pytest.skip("尚未生成 M6 发布物留档")

    declared = release.parse_ledger(ledger)
    assert declared, "留档里没解析出记录 = 判据空转"

    for dist_name, base in release.PACKAGES:
        dist = ROOT / "dist" / dist_name
        if not dist.is_dir():
            continue
        name = "%s-%s.zip" % (base, release.package_version())
        assert name in declared, "留档缺少 %s" % name
        target = tmp_path / name
        record = release.build_zip(dist, base, target)
        assert record["sha256"] == declared[name][0], (
            "留档哈希与真打的 zip 不一致（产物变了没更新留档，或打包器变了）：%s"
            % name)
        assert record["file_count"] == declared[name][1], (
            "留档文件数与真打的 zip 不一致：%s（留档 %d / 实际 %d）"
            % (name, declared[name][1], record["file_count"]))


def test_release_tool_has_ok_marker():
    """形态一致性：打包器必须打 ``*_OK`` 标记，供脚本判读成败。"""
    text = (TOOLS / "make_release.py").read_text(encoding="utf-8")
    assert 'OK_MARKER = "RELEASE_PACK_OK"' in text


def test_make_release_is_wired_into_ci():
    """**发布打包必须在 CI 上真跑**：本地一直绿 ≠ CI 验过。

    判据解析 workflow 的 run 步骤（注释行不会被解析成步骤）——
    本项目实测过"整段注释掉仍被字串判据判为在跑"的假门。
    """
    workflow = ROOT / ".github" / "workflows" / "ci.yml"
    if not workflow.is_file():
        pytest.skip("CI workflow 尚未创建")
    try:
        import yaml
    except ImportError:
        pytest.skip("未安装 pyyaml（dev extra 应包含它）")

    data = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    run_steps = []
    for job in data.get("jobs", {}).values():
        for step in job.get("steps", []):
            if step.get("run"):
                run_steps.append(str(step["run"]))
    joined = "\n".join(run_steps)
    assert "make_release.py" in joined, (
        "CI 的 run 步骤里没有发布打包（注释掉不算）")

    # 非空转对照：那条 run 步骤必须真的在跑打包器且带 --check
    assert any("make_release.py" in s and "--check" in s for s in run_steps), (
        "CI 里的打包步骤没带 --check —— 确定性/回读/脱敏三条判据在 CI 上没跑")
