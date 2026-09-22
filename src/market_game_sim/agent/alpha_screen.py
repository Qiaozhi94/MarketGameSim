"""0.4.1 T974 (FR-504 / AC-508): Alpha101 formula screener -- pure time-series subset.

The pure AI market trades a single instrument and has no industry or market-cap
data, so an Alpha101 formula is only usable when every operator is a
time-series or element-wise one and every input is a per-instrument series.
Cross-sectional operators (``rank``, ``scale``, ``IndNeutralize``) degenerate
to constants on one instrument; ``cap`` and ``IndClass.*`` inputs do not exist
here.  Such formulas are rejected at assembly time with a stable reason code.

Screening is closed-world and fail-closed: an operator or input that is not in
the allowed tables below is rejected (``ALPHA_UNKNOWN_OPERATOR`` /
``ALPHA_UNKNOWN_INPUT``), never passed through.  Identifiers are matched
case-insensitively (``Ts_ArgMax`` == ``ts_argmax``), whitespace is ignored.

The screener is a pure function: it parses the formula text into an AST and
walks it; it never evaluates anything and holds no runtime state.  The window
re-definition coefficient of spec Q-502 (``days(N)`` -> ``bars(N)``) is applied
by the evaluator, not here -- screening does not depend on it.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

# Stable reason codes (safe to assert on; never renamed).
SYNTAX_ERROR = "ALPHA_SYNTAX_ERROR"
CROSS_SECTIONAL_OPERATOR = "ALPHA_CROSS_SECTIONAL_OPERATOR"
INDUSTRY_INPUT = "ALPHA_INDUSTRY_INPUT"
MARKET_CAP_INPUT = "ALPHA_MARKET_CAP_INPUT"
UNKNOWN_OPERATOR = "ALPHA_UNKNOWN_OPERATOR"
UNKNOWN_INPUT = "ALPHA_UNKNOWN_INPUT"
ARITY_MISMATCH = "ALPHA_ARITY_MISMATCH"

# Time-series / element-wise operators of the Alpha101 paper, with arity.
TIME_SERIES_OPERATORS: dict[str, int] = {
    "abs": 1,
    "log": 1,
    "sign": 1,
    "delay": 2,
    "delta": 2,
    "correlation": 3,
    "covariance": 3,
    "ts_min": 2,
    "ts_max": 2,
    "ts_argmin": 2,
    "ts_argmax": 2,
    "ts_rank": 2,
    "sum": 2,
    "product": 2,
    "stddev": 2,
    "decay_linear": 2,
    "signedpower": 2,
    "min": 2,
    "max": 2,
}
CROSS_SECTIONAL_OPERATORS = frozenset({"rank", "scale", "indneutralize"})

TIME_SERIES_INPUTS = frozenset({"open", "close", "high", "low", "volume", "vwap", "returns"})
_ADV_INPUT = re.compile(r"adv\d+")
MARKET_CAP_INPUTS = frozenset({"cap"})
INDUSTRY_INPUTS = frozenset({"indclass.sector", "indclass.industry", "indclass.subindustry"})

# Each level costs ~10 Python frames; Alpha101 formulas nest far below this.
_MAX_DEPTH = 64

_TOKEN = re.compile(
    r"\s*(?:"
    r"(?P<num>(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)"
    r"|(?P<ident>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)"
    r"|(?P<op>\|\||&&|<=|>=|==|!=|[-+*/^<>?:,()])"
    r")"
)
_COMPARISON = frozenset({"<", ">", "<=", ">=", "==", "!="})


class AlphaScreenError(ValueError):
    """Formula rejected at assembly; ``code`` is stable and safe to assert on."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True)
class Violation:
    code: str
    name: str
    position: int


@dataclass(frozen=True)
class ScreenResult:
    formula: str
    accepted: bool
    reason_code: str | None
    detail: str
    violations: tuple[Violation, ...]
    operators: frozenset[str]
    inputs: frozenset[str]


@dataclass(frozen=True)
class _Tok:
    kind: str
    text: str
    pos: int


class _SyntaxError(Exception):
    def __init__(self, message: str, pos: int) -> None:
        super().__init__(message)
        self.pos = pos


def _tokenize(src: str) -> list[_Tok]:
    toks: list[_Tok] = []
    i = 0
    while i < len(src):
        if src[i:].strip() == "":
            break
        m = _TOKEN.match(src, i)
        if m is None or m.lastgroup is None:
            j = i
            while j < len(src) and src[j].isspace():
                j += 1
            raise _SyntaxError(f"unexpected character {src[j]!r}", j)
        kind = m.lastgroup
        toks.append(_Tok(kind, m.group(kind), m.start(kind)))
        i = m.end()
    toks.append(_Tok("end", "", len(src)))
    return toks


# AST nodes: ("num",) | ("ident", name, pos) | ("call", name, pos, args) | ("op", children)
_Node = tuple


class _Parser:
    """Recursive descent over the Alpha101 grammar.

    Precedence, loosest first: ``?:`` (right-assoc) < ``||`` < ``&&`` <
    comparison < ``+ -`` < ``* /`` < ``^`` < unary ``-``/``+``.
    """

    def __init__(self, toks: list[_Tok]) -> None:
        self.toks = toks
        self.i = 0
        self.depth = 0

    def peek(self) -> _Tok:
        return self.toks[self.i]

    def take(self) -> _Tok:
        tok = self.toks[self.i]
        self.i += 1
        return tok

    def expect(self, text: str) -> None:
        tok = self.take()
        if tok.kind != "op" or tok.text != text:
            shown = tok.text or "end of formula"
            raise _SyntaxError(f"expected {text!r}, got {shown!r}", tok.pos)

    def at(self, *texts: str) -> bool:
        tok = self.peek()
        return tok.kind == "op" and tok.text in texts

    def parse(self) -> _Node:
        if self.peek().kind == "end":
            raise _SyntaxError("empty formula", 0)
        node = self.ternary()
        tok = self.peek()
        if tok.kind != "end":
            raise _SyntaxError(f"unexpected token {tok.text!r}", tok.pos)
        return node

    def _enter(self) -> None:
        self.depth += 1
        if self.depth > _MAX_DEPTH:
            raise _SyntaxError("formula nested too deeply", self.peek().pos)

    def ternary(self) -> _Node:
        self._enter()
        cond = self.binary(0)
        if self.at("?"):
            self.take()
            then = self.ternary()
            self.expect(":")
            other = self.ternary()
            cond = ("op", (cond, then, other))
        self.depth -= 1
        return cond

    _LEVELS: tuple[frozenset[str], ...] = (
        frozenset({"||"}),
        frozenset({"&&"}),
        _COMPARISON,
        frozenset({"+", "-"}),
        frozenset({"*", "/"}),
        frozenset({"^"}),
    )

    def binary(self, level: int) -> _Node:
        if level == len(self._LEVELS):
            return self.unary()
        node = self.binary(level + 1)
        while self.peek().kind == "op" and self.peek().text in self._LEVELS[level]:
            self.take()
            node = ("op", (node, self.binary(level + 1)))
        return node

    def unary(self) -> _Node:
        if self.at("-", "+"):
            self.take()
            self._enter()
            node = ("op", (self.unary(),))
            self.depth -= 1
            return node
        return self.primary()

    def primary(self) -> _Node:
        tok = self.take()
        if tok.kind == "num":
            return ("num",)
        if tok.kind == "ident":
            name = tok.text.lower()
            if self.at("("):
                self.take()
                args: list[_Node] = []
                if not self.at(")"):
                    args.append(self.ternary())
                    while self.at(","):
                        self.take()
                        args.append(self.ternary())
                self.expect(")")
                return ("call", name, tok.pos, tuple(args))
            return ("ident", name, tok.pos)
        if tok.kind == "op" and tok.text == "(":
            node = self.ternary()
            self.expect(")")
            return node
        shown = tok.text or "end of formula"
        raise _SyntaxError(f"unexpected token {shown!r}", tok.pos)


def _classify_input(name: str) -> str | None:
    if name in TIME_SERIES_INPUTS or _ADV_INPUT.fullmatch(name):
        return None
    if name in MARKET_CAP_INPUTS:
        return MARKET_CAP_INPUT
    if name in INDUSTRY_INPUTS or name.startswith("indclass."):
        return INDUSTRY_INPUT
    return UNKNOWN_INPUT


def _walk(
    node: _Node,
    violations: list[Violation],
    operators: set[str],
    inputs: set[str],
) -> None:
    stack = [node]
    while stack:
        cur = stack.pop()
        kind = cur[0]
        if kind == "ident":
            _, name, pos = cur
            inputs.add(name)
            code = _classify_input(name)
            if code is not None:
                violations.append(Violation(code, name, pos))
        elif kind == "call":
            _, name, pos, args = cur
            operators.add(name)
            if name in CROSS_SECTIONAL_OPERATORS:
                violations.append(Violation(CROSS_SECTIONAL_OPERATOR, name, pos))
            elif name not in TIME_SERIES_OPERATORS:
                violations.append(Violation(UNKNOWN_OPERATOR, name, pos))
            elif len(args) != TIME_SERIES_OPERATORS[name]:
                violations.append(Violation(ARITY_MISMATCH, name, pos))
            stack.extend(args)
        elif kind == "op":
            stack.extend(cur[1])


def screen_formula(formula: str) -> ScreenResult:
    """Screen one Alpha101 formula; never raises.

    ``reason_code`` is the code of the left-most violation (so the result is
    deterministic); ``violations`` lists all of them in source order.
    """
    if not isinstance(formula, str):
        detail = f"formula must be str, got {type(formula).__name__}"
        return ScreenResult(
            repr(formula), False, SYNTAX_ERROR, detail, (), frozenset(), frozenset()
        )
    try:
        try:
            tree = _Parser(_tokenize(formula)).parse()
        except RecursionError:
            raise _SyntaxError("formula nested too deeply", 0) from None
    except _SyntaxError as exc:
        detail = f"{exc} at position {exc.pos}"
        violation = Violation(SYNTAX_ERROR, "", exc.pos)
        return ScreenResult(
            formula, False, SYNTAX_ERROR, detail, (violation,), frozenset(), frozenset()
        )
    violations: list[Violation] = []
    operators: set[str] = set()
    inputs: set[str] = set()
    _walk(tree, violations, operators, inputs)
    violations.sort(key=lambda v: v.position)
    if violations:
        first = violations[0]
        detail = f"{first.code}: {first.name!r} at position {first.position}"
        code: str | None = first.code
    else:
        detail = "pure time-series subset"
        code = None
    return ScreenResult(
        formula,
        not violations,
        code,
        detail,
        tuple(violations),
        frozenset(operators),
        frozenset(inputs),
    )


def screen_formulas(formulas: Iterable[str]) -> tuple[ScreenResult, ...]:
    """Screen a batch; results are in input order, one per formula."""
    return tuple(screen_formula(f) for f in formulas)


def require_accepted(formula: str) -> ScreenResult:
    """Assembly-time gate: return the result or raise :class:`AlphaScreenError`."""
    result = screen_formula(formula)
    if not result.accepted:
        assert result.reason_code is not None
        raise AlphaScreenError(result.reason_code, result.detail)
    return result
