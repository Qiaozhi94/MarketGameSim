"""T601: Deterministic PRNG using blake2b (代理策略 §10.1-§10.2).

0.1.1 only needs uniform [0, 1) distribution.  Other distributions (normal,
power-law) come in 0.1.2.

Do NOT use ``SeedSequence`` (NumPy, not stdlib).
"""

from __future__ import annotations

import hashlib


def uniform(seed_bytes: bytes, counter: int) -> float:
    """Deterministic uniform [0, 1) from a blake2b digest.

    Semantic key: ``seed_bytes || counter.to_bytes(8, 'big')``.
    The 32-byte digest is interpreted as an unsigned 256-bit integer
    divided by ``2**256``, giving a uniformly distributed float in [0, 1).
    """
    key = seed_bytes + counter.to_bytes(8, "big")
    digest = hashlib.blake2b(key, digest_size=32).digest()
    n = int.from_bytes(digest, "big")
    return n / (2**256)
