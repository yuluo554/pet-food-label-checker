"""合成标签基准：确定性生成器 + 植入真值 + 四套件评测。

对外入口：
    cases.py     —— 样例生成、真值语义、对账语义（单一实现源）
    runner.py    —— 四套件 runner、门槛下发、空分母防空、退出码语义
    rng.py       —— 自研 splitmix64 确定性 RNG
"""

from .cases import (  # noqa: F401
    BRAND_WHITELIST,
    CASE_COMPLIANT,
    CASE_MISSING,
    CASE_OVERLIMIT,
    CASE_TYPES,
    CASE_UNSUPPORTED_CLAIM,
    BrandWhitelistError,
    assert_brand_allowed,
    build_label_text,
    check_cases_frozen,
    compare_nonpass,
    generate_cases,
    load_cases,
    observed_nonpass,
    write_cases,
)
from .rng import SplitMix64  # noqa: F401
from .runner import (  # noqa: F401
    EXIT_NOT_MET,
    EXIT_OK,
    EXIT_USAGE,
    SUITES,
    BenchConfigError,
    BenchReport,
    SuiteResult,
    load_thresholds,
    render_report,
    run,
)

__all__ = [
    "BRAND_WHITELIST", "CASE_COMPLIANT", "CASE_MISSING", "CASE_OVERLIMIT",
    "CASE_TYPES", "CASE_UNSUPPORTED_CLAIM", "BrandWhitelistError",
    "assert_brand_allowed", "build_label_text", "check_cases_frozen",
    "compare_nonpass", "generate_cases", "load_cases", "observed_nonpass",
    "write_cases", "SplitMix64", "EXIT_NOT_MET", "EXIT_OK", "EXIT_USAGE",
    "SUITES", "BenchConfigError", "BenchReport", "SuiteResult",
    "load_thresholds", "render_report", "run",
]
