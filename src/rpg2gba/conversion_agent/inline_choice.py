"""Pure parser for Essentials' inline-choice text escape
``\\ch[var,ifCancel,opt1,opt2,...]`` (REDERIVATION_PLAN.md C8 stage 3, part A
-- lifted out of ``transpiler.py``'s ``_emit_inline_choice``, CLAUDE.md §4.3:
one mint point for this shape).

Essentials' own implementation: ``reference/scripts_dump/059_Messages.rb``.

* ``:1218-1225`` -- ``Kernel.pbMessageDisplay``'s control-code scan splits
  ``\\ch[cmdvariable,cmdIfCancel,opt0,opt1,...]`` on commas via
  ``pbCsvPosInt!``/``pbCsvField!``: the first field is the target variable id
  (an int), the second is ``cmdIfCancel``, every remaining field is one menu
  option's label text, in source order.
* ``:1360-1362`` -- once the message window closes, if any ``\\ch`` commands
  were parsed: ``$game_variables[cmdvariable] = Kernel.pbShowCommands(
  msgwindow, commands, cmdIfCancel)``. The written value is exactly
  ``pbShowCommands``'s return.
* ``:1429-1465`` (``Kernel.pbShowCommands``) -- ``ret=0`` by default; on a
  confirm (Input::C) ``command = cmdwindow.index``, the chosen option's
  **0-based** index. On cancel (Input::B): if ``cmdIfCancel>0``,
  ``command = cmdIfCancel-1`` (still a 0-based option index -- cancel is
  redirected to behave as if that option had been picked); if
  ``cmdIfCancel<0``, ``command = cmdIfCancel`` (that literal negative number,
  which this parser refuses as unrepresentable in a GBA u16 var -- see
  below); if ``cmdIfCancel==0``, neither branch of the ``if`` fires, so the
  loop never breaks on B at all -- **cancel is not possible** when
  ``ifCancel`` is 0, it is simply ignored (matches the transpiler's emitted
  ``dynmultichoice(..., ignore_b_press=TRUE, ...)`` for that case).

So: option *i* (0-based, source order) writes value *i*; a possible cancel
(``ifCancel != 0``) writes ``ifCancel - 1`` -- which is a genuinely different
value from any option's own index only when ``ifCancel - 1`` falls outside
``0..len(options)-1`` (an out-of-range redirect is a real, if odd, authored
shape; an in-range one just means cancel behaves identically to picking that
option, contributing no new value).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["InlineChoice", "InlineChoiceError", "has_inline_choice", "parse_inline_choice"]

# Same marker as transpiler.py's retired _CH_MARK -- the one mint point for
# "does this text contain an inline choice at all."
_MARK = "\\ch["

# Cosmetic color-code carriers inside option labels -- stripped, never an
# error, same disposition as transpiler.py's retired _CH_COLOR_TAG_RE /
# _CH_LEGACY_COLOR_RE.
_COLOR_TAG_RE = re.compile(r"<c2=[0-9a-fA-F]+>")
_LEGACY_COLOR_RE = re.compile(r"\\c\[\d+\]")
# After stripping the two shapes above, any surviving backslash or angle
# bracket is an unrecognized tag -- refuse rather than emit mystery text
# into a menu option (transpiler.py's retired _CH_RESIDUAL_TAG_RE).
_RESIDUAL_TAG_RE = re.compile(r"[\\<>]")


class InlineChoiceError(Exception):
    """Raised by `parse_inline_choice` for any `\\ch[...]` shape this parser
    doesn't model. `message` is the exact detail string a caller should hand
    to its own queue/refusal reporting -- every reason the transpiler's
    retired inline parsing code could queue is reproduced byte-for-byte here
    so `transpiler.py`'s queue messages don't change under this refactor."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class InlineChoice:
    """One parsed `\\ch[var,ifCancel,opt1,opt2,...]` block.

    `prompt_text` is the message text before the `\\ch[` marker (still
    carrying any other control codes -- the caller translates it).
    `options` are the stripped-of-color-codes option labels, in source
    order. `var_id`/`if_cancel` are the two leading integer fields, exactly
    as Essentials names them (`cmdvariable`/`cmdIfCancel`).
    """

    prompt_text: str
    var_id: int
    if_cancel: int
    options: tuple[str, ...]

    def domain(self) -> tuple[int, ...]:
        """Every value `$game_variables[var_id]` can receive, in the order a
        search should try them (option 0 first -- the R10 "main path").

        See this module's docstring for the citations. `if_cancel == 0`
        means cancel is not possible (the B-press branch never fires in
        `pbShowCommands`), so the domain is exactly the option indices.
        Otherwise cancel contributes `if_cancel - 1` too, but only when that
        isn't already one of the option indices (an in-range redirect writes
        a value the option enumeration already covers)."""
        base = tuple(range(len(self.options)))
        if self.if_cancel == 0:
            return base
        cancel_value = self.if_cancel - 1
        if cancel_value in base:
            return base
        return base + (cancel_value,)


def has_inline_choice(text: str) -> bool:
    return _MARK in text


def parse_inline_choice(text: str) -> InlineChoice:
    if text.count(_MARK) != 1:
        raise InlineChoiceError(
            f"inline choice: expected exactly one \\ch[...] marker, "
            f"found {text.count(_MARK)}: {text[:120]!r}"
        )
    mark_idx = text.index(_MARK)
    inner_start = mark_idx + len(_MARK)
    close_idx = text.rfind("]")
    if close_idx < inner_start:
        raise InlineChoiceError(
            f"inline choice: no closing ']' for \\ch[...]: {text[:120]!r}"
        )
    if text[close_idx + 1 :].strip():
        raise InlineChoiceError(
            f"inline choice: trailing text after \\ch[...] block: {text[:120]!r}"
        )
    prompt_text = text[:mark_idx]
    inner = text[inner_start:close_idx]

    fields = [f.strip() for f in inner.split(",")]
    if len(fields) < 3:
        raise InlineChoiceError(
            f"inline choice: too few \\ch[...] fields ({len(fields)}): {inner!r}"
        )
    var_str, if_cancel_str, *option_texts = fields
    try:
        var_id = int(var_str)
        if_cancel = int(if_cancel_str)
    except ValueError:
        raise InlineChoiceError(
            f"inline choice: non-integer var/ifCancel in \\ch[{inner}]"
        ) from None
    if if_cancel < 0:
        raise InlineChoiceError(
            f"inline choice: negative ifCancel ({if_cancel}) is "
            f"unrepresentable in a GBA u16 var — \\ch[{inner}]"
        )

    options: list[str] = []
    for opt in option_texts:
        stripped = _COLOR_TAG_RE.sub("", opt)
        stripped = _LEGACY_COLOR_RE.sub("", stripped)
        stripped = stripped.strip()
        if _RESIDUAL_TAG_RE.search(stripped):
            raise InlineChoiceError(
                f"inline choice: residual unknown tag in option {opt!r} "
                f"after color-code strip — \\ch[{inner}]"
            )
        options.append(stripped)

    return InlineChoice(
        prompt_text=prompt_text, var_id=var_id, if_cancel=if_cancel,
        options=tuple(options),
    )
