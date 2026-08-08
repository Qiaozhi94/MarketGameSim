"""T301, T302: Complete deterministic random distributions (代理策略 §10).

Implements:

* :func:`blake2b_uniform` -- semantic-key-based [0, 1) uniform via blake2b.
* :func:`standard_normal` -- Marsaglia polar (no math.triangular).
* :func:`gamma_draw` -- Marsaglia-Tsang, alpha >= 1 path + alpha < 1 boost.
* :func:`lognormal_draw` -- exp(mu + sigma * z).
* :func:`dirichlet_draw` -- independent gamma mechanism keys per component.
* :func:`uniform_range` -- uniform over [a, b].
* :func:`discrete_choice` -- half-open interval, integer compare.

All return ``(value, next_draw_index)`` so the caller can chain draws
with explicit counter management.  All use Decimal (precision 28) per
代理策略 §9 for non-trivial arithmetic.

Stdlib only (KR-005).
"""

from __future__ import annotations

import hashlib
from decimal import Decimal, getcontext

getcontext().prec = 28

_TWO_POW_53 = 2**53
_TWO_POW_53_PLUS_1 = _TWO_POW_53 + 1


def _encode_field(s: str) -> bytes:
    """Length-prefixed UTF-8 encoding (代理策略 §10.1, no delimiter collisions)."""
    b = s.encode("utf-8")
    return len(b).to_bytes(2, "big") + b


def blake2b_uniform(
    master_seed: int,
    agent_id: str,
    mechanism: str,
    decision_index: int,
    draw_index: int,
) -> Decimal:
    """Open-interval uniform [0, 1) from semantic key (代理策略 §10.1-§10.2).

    Takes the top 53 bits of a 64-bit blake2b digest, then maps to
    (Decimal(v) + 1) / (2^53 + 1) -- strictly in (0, 1).
    """
    key = (
        _encode_field(str(master_seed))
        + _encode_field(agent_id)
        + _encode_field(mechanism)
        + _encode_field(str(decision_index))
        + _encode_field(str(draw_index))
    )
    digest = hashlib.blake2b(key, digest_size=8).digest()
    v = int.from_bytes(digest, "big") >> 11
    return (Decimal(v) + 1) / Decimal(_TWO_POW_53_PLUS_1)


def standard_normal(
    master_seed: int,
    agent_id: str,
    mechanism: str,
    decision_index: int,
    draw_index: int,
) -> tuple[Decimal, int]:
    """Marsaglia polar standard normal (代理策略 §10.3.1)."""
    while True:
        u1 = blake2b_uniform(master_seed, agent_id, mechanism, decision_index, draw_index)
        u2 = blake2b_uniform(master_seed, agent_id, mechanism, decision_index, draw_index + 1)
        draw_index += 2
        x = Decimal(2) * u1 - Decimal(1)
        y = Decimal(2) * u2 - Decimal(1)
        s = x * x + y * y
        if s > 0 and s < 1:
            z = x * ((Decimal(-2) * _ln(s) / s).sqrt())
            return z, draw_index


def gamma_draw(
    alpha: Decimal,
    master_seed: int,
    agent_id: str,
    mechanism: str,
    decision_index: int,
    draw_index: int,
) -> tuple[Decimal, int]:
    """Marsaglia-Tsang Gamma(alpha, 1) (代理策略 §10.3.1).

    For alpha < 1: use boost (gamma(alpha+1) * U^(1/alpha)).
    For alpha >= 1: rejection sampling with normal proposal.
    """
    one = Decimal(1)
    if alpha < one:
        g, draw_index = gamma_draw(
            alpha + one, master_seed, agent_id, mechanism, decision_index, draw_index
        )
        u = blake2b_uniform(master_seed, agent_id, mechanism, decision_index, draw_index)
        draw_index += 1
        return g * _exp(_ln(u) / alpha), draw_index

    d = alpha - Decimal(1) / Decimal(3)
    c = Decimal(1) / (Decimal(9) * d).sqrt()
    while True:
        z, draw_index = standard_normal(
            master_seed, agent_id, mechanism, decision_index, draw_index
        )
        v = (Decimal(1) + c * z) ** 3
        if v <= 0:
            continue
        u = blake2b_uniform(master_seed, agent_id, mechanism, decision_index, draw_index)
        draw_index += 1
        z2 = z * z
        log_u = _ln(u)
        accept = log_u < Decimal("0.5") * z2 + d - d * v + d * _ln(v)
        if accept:
            return d * v, draw_index


def lognormal_draw(
    center: int,
    dispersion: Decimal,
    master_seed: int,
    agent_id: str,
    mechanism: str,
    decision_index: int,
    draw_index: int,
) -> tuple[Decimal, int]:
    """Lognormal via exp(mu + sigma * z) (代理策略 §10.3 table)."""
    z, draw_index = standard_normal(master_seed, agent_id, mechanism, decision_index, draw_index)
    mu = _ln(Decimal(center))
    sigma = dispersion
    return _exp(mu + sigma * z), draw_index


def dirichlet_draw(
    alpha: list[Decimal],
    master_seed: int,
    agent_id: str,
    mechanism: str,
    decision_index: int,
) -> tuple[list[Decimal], int]:
    """Dirichlet via independent gamma keys per component (代理策略 §10.3.2)."""
    draws: list[Decimal] = []
    for i, a in enumerate(alpha):
        mech = f"{mechanism}_{i}"
        g, _ = gamma_draw(a, master_seed, agent_id, mech, decision_index, 0)
        draws.append(g)
    total = sum(draws, Decimal(0))
    if total == 0:
        n = Decimal(len(draws))
        return [Decimal(1) / n for _ in draws], 0
    return [g / total for g in draws], 0


def uniform_range(
    low: Decimal,
    high: Decimal,
    master_seed: int,
    agent_id: str,
    mechanism: str,
    decision_index: int,
    draw_index: int,
) -> tuple[Decimal, int]:
    """``low + u × (high - low)`` in [low, high) (代理策略 §10.3 table)."""
    u = blake2b_uniform(master_seed, agent_id, mechanism, decision_index, draw_index)
    return low + u * (high - low), draw_index + 1


def discrete_choice(
    weights_bp: dict[int, int],
    master_seed: int,
    agent_id: str,
    mechanism: str,
    decision_index: int,
    draw_index: int,
) -> tuple[int, int]:
    """Discrete distribution via half-open interval and integer compare (代理策略 §10.3.5).

    ``weights_bp``: integer bp dict, sum = 10000.  ``x = floor(u * 10000)``,
    then iterate keys in **numeric** ascending order, accumulating, return
    key where ``x < cum``.
    """
    total = sum(weights_bp.values())
    if total != 10_000:
        raise ValueError(f"weights_bp must sum to 10000, got {total}")
    u = blake2b_uniform(master_seed, agent_id, mechanism, decision_index, draw_index)
    x = int(u * 10_000)  # u in (0, 1) so x in [0, 9999]
    cum = 0
    for k in sorted(weights_bp.keys()):
        cum += weights_bp[k]
        if x < cum:
            return k, draw_index + 1
    raise RuntimeError("unreachable: cumulative weight did not return")


# --------------------------------------------------------------------------- #
# Decimal helpers (代理策略 §9: precision 28, no math module)
# --------------------------------------------------------------------------- #


def _ln(x: Decimal) -> Decimal:
    return x.ln()


def _exp(x: Decimal) -> Decimal:
    return x.exp()


def _sqrt(x: Decimal) -> Decimal:
    return x.sqrt()
