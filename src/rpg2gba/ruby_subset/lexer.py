"""Tokenizer for the embedded-Ruby subset (REDERIVATION_PLAN.md C8 stage 1).

Covers exactly what CH01-CH05's script blocks (355/655), 111 type-12
condition scripts, and 122 type-4 variable-operation operands use --
identifiers, globals/instance vars, scoped constants, symbols, strings
(single/double quoted, `#{...}` interpolation flagged not evaluated),
numbers, and Ruby's statement-terminator newline rules.

Newlines are significant (statement terminators) except inside an open
`()`/`[]`/`{}`, or immediately after a token that implies the statement
continues (a binary operator, `,`, `.`, `::`, `?`, `:`, or a low-precedence
word operator). `;` is always a terminator, folded into the same NEWLINE
token kind so the parser has one thing to check.
"""
from __future__ import annotations

from dataclasses import dataclass


class RubyParseError(ValueError):
    """Raised on anything outside the supported Ruby subset.

    `reason` is a short machine-readable tag (`"unsupported_syntax:heredoc"`,
    `"unterminated_string"`, ...); `source`/`pos` are the offending source
    text and the char offset the tokenizer/parser was at when it gave up.
    Never partially recovered from -- callers get a clean failure, not a
    guessed AST (CLAUDE.md Sec4.5).
    """

    def __init__(self, reason: str, source: str, pos: int):
        self.reason = reason
        self.source = source
        self.pos = pos
        line = source.count("\n", 0, pos) + 1
        col = pos - (source.rfind("\n", 0, pos))
        snippet = source[max(0, pos - 20):pos + 20]
        super().__init__(
            f"{reason} at line {line} col {col} (near {snippet!r})"
        )


@dataclass(frozen=True)
class Token:
    kind: str  # NAME, GVAR, IVAR, CONST_NAME (unused; case decided by parser),
    # INT, FLOAT, STRING, SYMBOL, OP, NEWLINE, EOF
    text: str
    start: int
    end: int
    # For STRING tokens only: the decoded value (None if interpolated), the
    # raw source text between quotes (undecoded, kept for interpolated
    # strings), and whether `#{...}` interpolation was seen.
    str_value: str | None = None
    str_raw: str = ""
    str_interpolated: bool = False


_KEYWORDS = frozenset({
    "if", "elsif", "else", "end", "unless", "for", "in", "while", "do",
    "true", "false", "nil", "and", "or", "not", "return", "break", "next",
    "then",
})

# Tokens after which a raw newline does NOT terminate the statement --
# Ruby "continues the line". Matched against the *previous* token's text
# (operators, comma, dot, scope, ternary parts) or kind-derived keyword text
# for the low-precedence word operators.
_CONTINUATION_TEXT = frozenset({
    "+", "-", "*", "/", "%", "==", "!=", "<", "<=", ">", ">=", "<=>",
    "&&", "||", "=", "+=", "-=", "*=", "/=", "%=", ",", ".", "::", "?", ":",
    "and", "or", "not", "in", "=>",
})

_ESCAPES = {
    "n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"', "'": "'",
    "0": "\0", "s": " ", "e": "\x1b", "#": "#",
}

_IDENT_START = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_"
)
_IDENT_CONT = _IDENT_START | set("0123456789")
_DIGITS = set("0123456789")


def tokenize(source: str) -> list[Token]:
    tokens: list[Token] = []
    i = 0
    n = len(source)
    depth = 0  # open (), [], {}

    def last_significant_text() -> str | None:
        for t in reversed(tokens):
            if t.kind != "NEWLINE":
                return t.text
            return None
        return None

    while i < n:
        ch = source[i]

        if ch in " \t\r":
            i += 1
            continue

        if ch == "#":
            # Comment to end of line (not reached inside strings -- those
            # are consumed whole by the string-lexing branch below).
            while i < n and source[i] != "\n":
                i += 1
            continue

        if ch == "\n" or ch == ";":
            if depth > 0:
                i += 1
                continue
            prev = last_significant_text()
            if prev is not None and prev in _CONTINUATION_TEXT:
                i += 1
                continue
            if tokens and tokens[-1].kind == "NEWLINE":
                i += 1
                continue
            if not tokens:
                i += 1
                continue
            tokens.append(Token("NEWLINE", ch, i, i + 1))
            i += 1
            continue

        if ch in "([{":
            depth += 1
            tokens.append(Token("OP", ch, i, i + 1))
            i += 1
            continue

        if ch in ")]}":
            depth -= 1
            tokens.append(Token("OP", ch, i, i + 1))
            i += 1
            continue

        if ch == '"' or ch == "'":
            tok, i = _lex_string(source, i, ch)
            tokens.append(tok)
            continue

        if ch == "$":
            j = i + 1
            if j >= n or source[j] not in _IDENT_START:
                raise RubyParseError("unsupported_syntax:bare_dollar", source, i)
            while j < n and source[j] in _IDENT_CONT:
                j += 1
            tokens.append(Token("GVAR", source[i:j], i, j))
            i = j
            continue

        if ch == "@":
            j = i + 1
            if j < n and source[j] == "@":
                raise RubyParseError("unsupported_syntax:class_var", source, i)
            if j >= n or source[j] not in _IDENT_START:
                raise RubyParseError("unsupported_syntax:bare_at", source, i)
            while j < n and source[j] in _IDENT_CONT:
                j += 1
            tokens.append(Token("IVAR", source[i:j], i, j))
            i = j
            continue

        if ch == ":":
            nxt = source[i + 1] if i + 1 < n else ""
            if nxt == ":":
                tokens.append(Token("OP", "::", i, i + 2))
                i += 2
                continue
            if nxt in _IDENT_START:
                j = i + 1
                while j < n and source[j] in _IDENT_CONT:
                    j += 1
                if j < n and source[j] in "?!":
                    j += 1
                tokens.append(Token("SYMBOL", source[i + 1:j], i, j))
                i = j
                continue
            if nxt == '"':
                strtok, j = _lex_string(source, i + 1, '"')
                tokens.append(Token(
                    "SYMBOL", strtok.str_value or strtok.str_raw, i, j,
                ))
                i = j
                continue
            tokens.append(Token("OP", ":", i, i + 1))
            i += 1
            continue

        if ch in _DIGITS:
            j = i
            while j < n and source[j] in _DIGITS:
                j += 1
            is_float = False
            if j < n and source[j] == "." and j + 1 < n and source[j + 1] in _DIGITS:
                is_float = True
                j += 1
                while j < n and source[j] in _DIGITS:
                    j += 1
            tokens.append(Token("FLOAT" if is_float else "INT", source[i:j], i, j))
            i = j
            continue

        if ch in _IDENT_START:
            j = i + 1
            while j < n and source[j] in _IDENT_CONT:
                j += 1
            if j < n and source[j] in "?!":
                j += 1
            tokens.append(Token("NAME", source[i:j], i, j))
            i = j
            continue

        # Operators, longest match first.
        three = source[i:i + 3]
        if three in ("<=>", "..."):
            tokens.append(Token("OP", three, i, i + 3))
            i += 3
            continue
        two = source[i:i + 2]
        if two in ("==", "!=", "<=", ">=", "&&", "||", "+=", "-=", "*=",
                    "/=", "%=", "..", "=>"):
            tokens.append(Token("OP", two, i, i + 2))
            i += 2
            continue
        if ch in "+-*/%<>=!?,.[](){}":
            tokens.append(Token("OP", ch, i, i + 1))
            i += 1
            continue

        raise RubyParseError("unsupported_syntax:unrecognized_char", source, i)

    tokens.append(Token("EOF", "", n, n))
    return tokens


def _lex_string(source: str, start: int, quote: str) -> tuple[Token, int]:
    """Lex a single/double quoted string starting at `source[start] == quote`.

    Returns (Token, index-after-closing-quote). Embedded literal newlines
    (from a joined 355/655 block) are content, not terminators -- the whole
    string is consumed here regardless of `\\n` inside it.
    """
    n = len(source)
    i = start + 1
    raw_chars: list[str] = []
    value_chars: list[str] = []
    interpolated = False
    while True:
        if i >= n:
            raise RubyParseError("unterminated_string", source, start)
        c = source[i]
        if c == quote:
            i += 1
            break
        if c == "\\" and i + 1 < n:
            nxt = source[i + 1]
            raw_chars.append(c)
            raw_chars.append(nxt)
            if quote == "'":
                if nxt in ("'", "\\"):
                    value_chars.append(nxt)
                else:
                    value_chars.append("\\")
                    value_chars.append(nxt)
            else:
                value_chars.append(_ESCAPES.get(nxt, nxt))
            i += 2
            continue
        if quote == '"' and c == "#" and i + 1 < n and source[i + 1] == "{":
            interpolated = True
            raw_chars.append("#{")
            i += 2
            brace_depth = 1
            while i < n and brace_depth > 0:
                if source[i] == "{":
                    brace_depth += 1
                elif source[i] == "}":
                    brace_depth -= 1
                    if brace_depth == 0:
                        raw_chars.append("}")
                        i += 1
                        break
                raw_chars.append(source[i])
                i += 1
            else:
                raise RubyParseError("unterminated_interpolation", source, start)
            continue
        raw_chars.append(c)
        value_chars.append(c)
        i += 1

    raw = "".join(raw_chars)
    value = None if interpolated else "".join(value_chars)
    return Token(
        "STRING", source[start:i], start, i,
        str_value=value, str_raw=raw, str_interpolated=interpolated,
    ), i
