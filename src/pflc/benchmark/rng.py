"""确定性伪随机数发生器（splitmix64）。

**为什么不用 stdlib ``random``**：``random.Random(seed)`` 的序列在 CPython
各版本间**不承诺一致**（实现细节可变），而合成基准必须"跨机器、跨版本、
逐字节可复现"。自研 splitmix64 是纯整数运算，行为完全由本文件定义。

参考：SplitMix64 是公认的简洁 64 位混合函数，状态推进即输出。
"""

from __future__ import annotations

from typing import List

_MASK64 = (1 << 64) - 1
_GOLDEN_GAMMA = 0x9E3779B97F4A7C15


def _mix64(z: int) -> int:
    """SplitMix64 的混合函数（finalizer）。"""
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9 & _MASK64
    z = (z ^ (z >> 27)) * 0x94D049BB133111EB & _MASK64
    return (z ^ (z >> 31)) & _MASK64


class SplitMix64:
    """确定性 RNG：同一 seed 序列在任何平台/版本上完全一致。"""

    def __init__(self, seed: int) -> None:
        self._state = seed & _MASK64

    def next_u64(self) -> int:
        self._state = (self._state + _GOLDEN_GAMMA) & _MASK64
        return _mix64(self._state)

    def randbelow(self, n: int) -> int:
        """取 ``[0, n)`` 内的整数（n > 0）。无偏取模由拒绝采样保证。"""
        if n <= 0:
            raise ValueError("n 必须为正整数")
        limit = (1 << 64) - ((1 << 64) % n)
        while True:
            value = self.next_u64()
            if value < limit:
                return value % n

    def choice(self, items: List[str]) -> str:
        """从列表里确定性取一个元素。"""
        if not items:
            raise ValueError("items 不可为空")
        return items[self.randbelow(len(items))]

    def shuffled(self, items: List[str]) -> List[str]:
        """确定性洗牌（Fisher-Yates，用自研 RNG）。"""
        out = list(items)
        for i in range(len(out) - 1, 0, -1):
            j = self.randbelow(i + 1)
            out[i], out[j] = out[j], out[i]
        return out
