"""Recursive-descent parser for the embedded-Ruby subset (REDERIVATION_PLAN.md
C8 stage 1). Replaces the five independent regex readers listed in the plan
(`story_state/extract.py`, `transpiler.py`'s `_RubyLocal`/array/argmax,
`beat_floor/script.py`, `beat_floor/condition.py`,
`chapter_manifest/conditions.py`) with one shared grammar.

Two public entry points:

* `parse_program(source)` -- a whole 355/655 script block (zero or more
  Ruby statements).
* `parse_expression(source)` -- a single expression, for a 111 type-12
  condition script or a 122 type-4 variable-operation operand.

Both raise `RubyParseError` (never a partial/guessed AST -- CLAUDE.md
Sec4.5) the moment they hit something outside the subset.

Bare-identifier disambiguation (Local vs. zero-arg Call): real Ruby decides
this per-identifier, at parse time, by whether the name has appeared as an
assignment target earlier in the same scope. This parser does the same with
one flat "known locals" set per parse (not full block scoping -- `if`/`for`/
`while` in Ruby don't introduce new scopes either, so this matches). A bare
name is parsed as `Local` if already known, else as a zero-arg `Call`
(receiver=None); assigning to a bare zero-arg `Call` immediately rewrites it
to `Local` and adds the name to the known-locals set (see `_finish_assign`).
A `for` loop's induction variable is added directly when the header is
parsed.

Statement-modifier `if`/`unless` (`stmt if cond`) parse to an `If`/`Unless`
node with a single-statement body and `postfix=True`, per ast.py's
docstring convention -- not a separate node kind.
"""
from __future__ import annotations

import dataclasses

from rpg2gba.ruby_subset import ast
from rpg2gba.ruby_subset.lexer import RubyParseError, Token, tokenize

__all__ = ["parse_program", "parse_expression", "script_block_source", "RubyParseError"]

_ASSIGN_OPS = {"+=", "-=", "*=", "/=", "%="}
_OPASSIGN_OP_CHAR = {"+=": "+", "-=": "-", "*=": "*", "/=": "/", "%=": "%"}
_BLOCK_TERMINATORS = {"elsif", "else", "end"}


class _Parser:
    def __init__(self, source: str):
        self.source = source
        self.tokens: list[Token] = tokenize(source)
        self.pos = 0
        self.known_locals: set[str] = set()

    # -- token stream helpers ------------------------------------------

    def _peek(self, offset: int = 0) -> Token:
        idx = min(self.pos + offset, len(self.tokens) - 1)
        return self.tokens[idx]

    def _at_end(self) -> bool:
        return self._peek().kind == "EOF"

    def _advance(self) -> Token:
        tok = self.tokens[self.pos]
        if tok.kind != "EOF":
            self.pos += 1
        return tok

    def _check_op(self, text: str) -> bool:
        tok = self._peek()
        return tok.kind == "OP" and tok.text == text

    def _check_kw(self, text: str) -> bool:
        tok = self._peek()
        return tok.kind == "NAME" and tok.text == text

    def _expect_op(self, text: str) -> Token:
        if not self._check_op(text):
            self._fail(f"unsupported_syntax:expected_{text!r}")
        return self._advance()

    def _expect_kw(self, text: str) -> Token:
        if not self._check_kw(text):
            self._fail(f"unsupported_syntax:expected_keyword_{text}")
        return self._advance()

    def _fail(self, reason: str) -> None:
        tok = self._peek()
        raise RubyParseError(reason, self.source, tok.start)

    def _skip_newlines(self) -> None:
        while self._peek().kind == "NEWLINE":
            self._advance()

    def _skip_terminator(self) -> None:
        """Consume at least the boundary between statements/clauses: one or
        more NEWLINEs, or nothing if we're already at a body-terminator
        keyword or EOF (an empty clause)."""
        if self._peek().kind == "NEWLINE":
            self._skip_newlines()
            return
        if self._at_end() or (self._peek().kind == "NAME" and self._peek().text in _BLOCK_TERMINATORS):
            return
        self._fail("unsupported_syntax:expected_statement_terminator")

    # -- program / statements -------------------------------------------

    def parse_program(self) -> ast.Program:
        start = self._peek().start
        self._skip_newlines()
        statements = self._parse_body(frozenset())
        if not self._at_end():
            self._fail("unsupported_syntax:trailing_tokens")
        end = self._peek().start
        return ast.Program(span=(start, end), statements=statements)

    def _parse_body(self, terminators: frozenset[str]) -> tuple[ast.Node, ...]:
        statements: list[ast.Node] = []
        self._skip_newlines()
        while True:
            if self._at_end():
                break
            tok = self._peek()
            if tok.kind == "NAME" and tok.text in terminators:
                break
            # A brace-block body (`_parse_brace_block`) has no keyword
            # terminator -- its only stop condition is the closing `}`,
            # which is an OP token, not a NAME, so the check above never
            # catches it. Every other body-parsing site (if/while/etc.,
            # the top-level Program) uses keyword terminators exclusively
            # and never has a legitimate bare `}` at statement-start (a
            # hash literal's own closing `}` is consumed internally by
            # `_parse_hash_lit`, never surfacing here) -- safe to stop
            # unconditionally on this token.
            if tok.kind == "OP" and tok.text == "}":
                break
            statements.append(self._parse_statement())
            self._skip_newlines()
        return tuple(statements)

    def _parse_statement(self) -> ast.Node:
        tok = self._peek()
        if tok.kind == "NAME":
            if tok.text == "if":
                return self._parse_if()
            if tok.text == "unless":
                return self._parse_unless()
            if tok.text == "for":
                return self._parse_for()
            if tok.text == "while":
                return self._parse_while()
            if tok.text == "return":
                return self._parse_jump(ast.Return)
            if tok.text == "break":
                return self._parse_jump(ast.Break)
            if tok.text == "next":
                return self._parse_jump(ast.Next)

        start = tok.start
        expr = self._assign()

        if self._check_kw("if"):
            self._advance()
            cond = self._assign()
            return ast.If(span=(start, cond.span[1]), cond=cond,
                           then_body=(expr,), postfix=True)
        if self._check_kw("unless"):
            self._advance()
            cond = self._assign()
            return ast.Unless(span=(start, cond.span[1]), cond=cond,
                               then_body=(expr,), postfix=True)
        return expr

    def _parse_jump(self, cls: type) -> ast.Node:
        tok = self._advance()
        value = None
        nxt = self._peek()
        stops_now = (
            nxt.kind in ("NEWLINE", "EOF")
            or (nxt.kind == "NAME" and nxt.text in _BLOCK_TERMINATORS)
        )
        if not stops_now:
            value = self._assign()
        end = value.span[1] if value is not None else tok.end
        return cls(span=(tok.start, end), value=value)

    def _parse_if(self) -> ast.If:
        start = self._expect_kw("if").start
        cond = self._assign()
        self._skip_terminator()
        then_body = self._parse_body(frozenset({"elsif", "else", "end"}))
        elifs: list[tuple[ast.Node, tuple[ast.Node, ...]]] = []
        while self._check_kw("elsif"):
            self._advance()
            econd = self._assign()
            self._skip_terminator()
            ebody = self._parse_body(frozenset({"elsif", "else", "end"}))
            elifs.append((econd, ebody))
        else_body = None
        if self._check_kw("else"):
            self._advance()
            self._skip_terminator()
            else_body = self._parse_body(frozenset({"end"}))
        end_tok = self._expect_kw("end")
        return ast.If(span=(start, end_tok.end), cond=cond, then_body=then_body,
                       elifs=tuple(elifs), else_body=else_body)

    def _parse_unless(self) -> ast.Unless:
        start = self._expect_kw("unless").start
        cond = self._assign()
        self._skip_terminator()
        then_body = self._parse_body(frozenset({"else", "end"}))
        else_body = None
        if self._check_kw("else"):
            self._advance()
            self._skip_terminator()
            else_body = self._parse_body(frozenset({"end"}))
        end_tok = self._expect_kw("end")
        return ast.Unless(span=(start, end_tok.end), cond=cond, then_body=then_body,
                           else_body=else_body)

    def _parse_for(self) -> ast.For:
        start = self._expect_kw("for").start
        var_tok = self._peek()
        if var_tok.kind != "NAME" or not var_tok.text[0].islower():
            self._fail("unsupported_syntax:for_loop_var")
        self._advance()
        self.known_locals.add(var_tok.text)
        self._expect_kw("in")
        iterable = self._assign()
        self._skip_terminator()
        body = self._parse_body(frozenset({"end"}))
        end_tok = self._expect_kw("end")
        return ast.For(span=(start, end_tok.end), var=var_tok.text,
                        iterable=iterable, body=body)

    def _parse_while(self) -> ast.While:
        start = self._expect_kw("while").start
        cond = self._assign()
        self._skip_terminator()
        body = self._parse_body(frozenset({"end"}))
        end_tok = self._expect_kw("end")
        return ast.While(span=(start, end_tok.end), cond=cond, body=body)

    # -- expressions, loosest to tightest --------------------------------

    def parse_expression(self) -> ast.Node:
        self._skip_newlines()
        expr = self._assign()
        self._skip_newlines()
        if not self._at_end():
            self._fail("unsupported_syntax:trailing_tokens")
        return expr

    def _assign(self) -> ast.Node:
        left = self._ternary()
        tok = self._peek()
        if tok.kind == "OP" and tok.text == "=":
            self._advance()
            target = self._finish_assign_target(left)
            value = self._assign()
            return ast.Assign(span=(left.span[0], value.span[1]), target=target, value=value)
        if tok.kind == "OP" and tok.text in _ASSIGN_OPS:
            self._advance()
            target = self._finish_assign_target(left)
            value = self._assign()
            return ast.OpAssign(span=(left.span[0], value.span[1]), target=target,
                                 op=_OPASSIGN_OP_CHAR[tok.text], value=value)
        return left

    def _finish_assign_target(self, node: ast.Node) -> ast.Node:
        if isinstance(node, ast.Call) and node.receiver is None and not node.args:
            self.known_locals.add(node.name)
            return ast.Local(span=node.span, name=node.name)
        if isinstance(node, (ast.Local, ast.GlobalVar, ast.InstanceVar, ast.Index)):
            if isinstance(node, ast.Local):
                self.known_locals.add(node.name)
            return node
        if isinstance(node, ast.Call) and not node.args:
            return node  # attribute assignment: receiver.name = value
        if isinstance(node, (ast.Const, ast.ScopedConst)):
            # No event script in the corpus assigns a constant; refuse rather
            # than hand the evaluator a target it has no semantics for.
            self._fail("unsupported_syntax:constant_assignment")
        self._fail("unsupported_syntax:invalid_assignment_target")

    def _ternary(self) -> ast.Node:
        cond = self._range()
        if self._check_op("?"):
            self._advance()
            then_ = self._ternary()
            self._expect_op(":")
            else_ = self._ternary()
            return ast.Ternary(span=(cond.span[0], else_.span[1]), cond=cond,
                                then=then_, else_=else_)
        return cond

    def _range(self) -> ast.Node:
        lo = self._or()
        tok = self._peek()
        if tok.kind == "OP" and tok.text in ("..", "..."):
            exclusive = tok.text == "..."
            self._advance()
            hi = self._or()
            return ast.RangeLit(span=(lo.span[0], hi.span[1]), lo=lo, hi=hi,
                                 exclusive=exclusive)
        return lo

    def _or(self) -> ast.Node:
        left = self._and()
        while self._check_op("||") or self._check_kw("or"):
            self._advance()
            right = self._and()
            left = ast.BinOp(span=(left.span[0], right.span[1]), op="||",
                              left=left, right=right)
        return left

    def _and(self) -> ast.Node:
        left = self._equality()
        while (self._check_op("&&") or self._check_kw("and")):
            self._advance()
            right = self._equality()
            left = ast.BinOp(span=(left.span[0], right.span[1]), op="&&",
                              left=left, right=right)
        return left

    def _equality(self) -> ast.Node:
        left = self._relational()
        while True:
            tok = self._peek()
            if tok.kind == "OP" and tok.text in ("==", "!=", "<=>"):
                self._advance()
                right = self._relational()
                left = ast.BinOp(span=(left.span[0], right.span[1]), op=tok.text,
                                  left=left, right=right)
                continue
            break
        return left

    def _relational(self) -> ast.Node:
        left = self._additive()
        while True:
            tok = self._peek()
            if tok.kind == "OP" and tok.text in ("<", "<=", ">", ">="):
                self._advance()
                right = self._additive()
                left = ast.BinOp(span=(left.span[0], right.span[1]), op=tok.text,
                                  left=left, right=right)
                continue
            break
        return left

    def _additive(self) -> ast.Node:
        left = self._multiplicative()
        while True:
            tok = self._peek()
            if tok.kind == "OP" and tok.text in ("+", "-"):
                self._advance()
                right = self._multiplicative()
                left = ast.BinOp(span=(left.span[0], right.span[1]), op=tok.text,
                                  left=left, right=right)
                continue
            break
        return left

    def _multiplicative(self) -> ast.Node:
        left = self._unary()
        while True:
            tok = self._peek()
            if tok.kind == "OP" and tok.text in ("*", "/", "%"):
                self._advance()
                right = self._unary()
                left = ast.BinOp(span=(left.span[0], right.span[1]), op=tok.text,
                                  left=left, right=right)
                continue
            break
        return left

    def _unary(self) -> ast.Node:
        tok = self._peek()
        if (tok.kind == "OP" and tok.text == "!") or (tok.kind == "NAME" and tok.text == "not"):
            self._advance()
            operand = self._unary()
            return ast.UnaryOp(span=(tok.start, operand.span[1]), op="!", operand=operand)
        if tok.kind == "OP" and tok.text == "-":
            self._advance()
            operand = self._unary()
            return ast.UnaryOp(span=(tok.start, operand.span[1]), op="-", operand=operand)
        return self._postfix()

    # -- postfix chain: `.method(args)`, `::Const`, `[index]`, trailing block

    def _postfix(self) -> ast.Node:
        node = self._primary()
        while True:
            tok = self._peek()
            if tok.kind == "OP" and tok.text == ".":
                self._advance()
                name_tok = self._peek()
                if name_tok.kind != "NAME":
                    self._fail("unsupported_syntax:expected_method_name")
                self._advance()
                args: tuple[ast.Node, ...] = ()
                end = name_tok.end
                if self._check_op("("):
                    args, end = self._parse_paren_args()
                node = ast.Call(span=(node.span[0], end), receiver=node,
                                 name=name_tok.text, args=args)
                node = self._maybe_attach_block(node)
                continue
            if tok.kind == "OP" and tok.text == "::":
                self._advance()
                name_tok = self._peek()
                if name_tok.kind != "NAME" or not name_tok.text[0].isupper():
                    self._fail("unsupported_syntax:expected_scoped_const")
                self._advance()
                node = ast.ScopedConst(span=(node.span[0], name_tok.end),
                                        scope=node, name=name_tok.text)
                continue
            if tok.kind == "OP" and tok.text == "[":
                self._advance()
                args = self._parse_arg_list("]")
                end_tok = self._expect_op("]")
                node = ast.Index(span=(node.span[0], end_tok.end), receiver=node, args=args)
                continue
            break
        return node

    def _maybe_attach_block(self, call: ast.Call) -> ast.Call:
        # Not exercised by the CH01-CH05 corpus (no `.each { }` / `do...end`
        # call sites); implemented for AST completeness per the C8 brief.
        if self._check_op("{"):
            block = self._parse_brace_block()
            return ast.Call(span=(call.span[0], block.span[1]), receiver=call.receiver,
                             name=call.name, args=call.args, block=block)
        if self._check_kw("do"):
            block = self._parse_do_block()
            return ast.Call(span=(call.span[0], block.span[1]), receiver=call.receiver,
                             name=call.name, args=call.args, block=block)
        return call

    def _parse_brace_block(self) -> ast.Block:
        start = self._expect_op("{").start
        params = self._parse_pipe_params()
        body = self._parse_body(frozenset())
        # `}` shares lexing with generic OP; body parsing stops only at
        # keywords, so consume up to the matching brace by re-checking here.
        end_tok = self._expect_op("}")
        return ast.Block(span=(start, end_tok.end), params=params, body=body)

    def _parse_do_block(self) -> ast.Block:
        start = self._expect_kw("do").start
        params = self._parse_pipe_params()
        self._skip_terminator()
        body = self._parse_body(frozenset({"end"}))
        end_tok = self._expect_kw("end")
        return ast.Block(span=(start, end_tok.end), params=params, body=body)

    def _parse_pipe_params(self) -> tuple[str, ...]:
        if not self._check_op("|"):
            return ()
        self._advance()
        params: list[str] = []
        while not self._check_op("|"):
            tok = self._peek()
            if tok.kind != "NAME":
                self._fail("unsupported_syntax:block_param")
            params.append(tok.text)
            self._advance()
            if self._check_op(","):
                self._advance()
        self._advance()  # closing '|'
        return tuple(params)

    def _parse_paren_args(self) -> tuple[tuple[ast.Node, ...], int]:
        self._expect_op("(")
        args = self._parse_arg_list(")")
        end_tok = self._expect_op(")")
        return args, end_tok.end

    def _parse_arg_list(self, closer: str) -> tuple[ast.Node, ...]:
        args: list[ast.Node] = []
        self._skip_newlines()
        if self._check_op(closer):
            return ()
        args.append(self._assign())
        self._skip_newlines()
        while self._check_op(","):
            self._advance()
            self._skip_newlines()
            if self._check_op(closer):
                break  # trailing comma
            args.append(self._assign())
            self._skip_newlines()
        return tuple(args)

    # -- primary ----------------------------------------------------------

    def _primary(self) -> ast.Node:
        tok = self._peek()

        if tok.kind == "INT":
            self._advance()
            return ast.Int(span=(tok.start, tok.end), value=int(tok.text))
        if tok.kind == "FLOAT":
            self._advance()
            return ast.Float(span=(tok.start, tok.end), value=float(tok.text))
        if tok.kind == "STRING":
            self._advance()
            return ast.Str(span=(tok.start, tok.end), value=tok.str_value,
                            interpolated=tok.str_interpolated, raw=tok.str_raw)
        if tok.kind == "SYMBOL":
            self._advance()
            return ast.Sym(span=(tok.start, tok.end), name=tok.text)
        if tok.kind == "GVAR":
            self._advance()
            return ast.GlobalVar(span=(tok.start, tok.end), name=tok.text)
        if tok.kind == "IVAR":
            self._advance()
            return ast.InstanceVar(span=(tok.start, tok.end), name=tok.text)

        if tok.kind == "OP" and tok.text == "(":
            self._advance()
            self._skip_newlines()
            inner = self._assign()
            self._skip_newlines()
            end_tok = self._expect_op(")")
            return _reparent(inner, (tok.start, end_tok.end))

        if tok.kind == "OP" and tok.text == "[":
            self._advance()
            elements = self._parse_arg_list("]")
            end_tok = self._expect_op("]")
            return ast.ArrayLit(span=(tok.start, end_tok.end), elements=elements)

        if tok.kind == "OP" and tok.text == "{":
            return self._parse_hash_lit()

        if tok.kind == "OP" and tok.text == "::":
            self._advance()
            name_tok = self._peek()
            if name_tok.kind != "NAME" or not name_tok.text[0].isupper():
                self._fail("unsupported_syntax:expected_top_level_const")
            self._advance()
            return ast.Const(span=(tok.start, name_tok.end), name=name_tok.text,
                              top_level=True)

        if tok.kind == "NAME":
            if tok.text == "true":
                self._advance()
                return ast.Bool(span=(tok.start, tok.end), value=True)
            if tok.text == "false":
                self._advance()
                return ast.Bool(span=(tok.start, tok.end), value=False)
            if tok.text == "nil":
                self._advance()
                return ast.Nil(span=(tok.start, tok.end))
            if tok.text in ("if", "unless", "for", "while", "do", "end",
                             "elsif", "else", "and", "or", "not", "in",
                             "then", "return", "break", "next"):
                self._fail("unsupported_syntax:unexpected_keyword")

            self._advance()
            if tok.text[0].isupper() and not self._check_op("("):
                node: ast.Node = ast.Const(span=(tok.start, tok.end), name=tok.text)
                return node
            if self._check_op("("):
                args, end = self._parse_paren_args()
                call = ast.Call(span=(tok.start, end), receiver=None,
                                 name=tok.text, args=args)
                return self._maybe_attach_block(call)
            if tok.text in self.known_locals:
                return ast.Local(span=(tok.start, tok.end), name=tok.text)
            return ast.Call(span=(tok.start, tok.end), receiver=None,
                             name=tok.text, args=())

        self._fail("unsupported_syntax:unexpected_token")

    def _parse_hash_lit(self) -> ast.HashLit:
        start = self._expect_op("{").start
        pairs: list[tuple[ast.Node, ast.Node]] = []
        self._skip_newlines()
        while not self._check_op("}"):
            key_tok = self._peek()
            if key_tok.kind == "NAME" and self._peek(1).kind == "OP" and self._peek(1).text == ":":
                self._advance()
                self._advance()
                key: ast.Node = ast.Sym(span=(key_tok.start, key_tok.end), name=key_tok.text)
            else:
                key = self._assign()
                self._expect_op("=>")
            value = self._assign()
            pairs.append((key, value))
            self._skip_newlines()
            if self._check_op(","):
                self._advance()
                self._skip_newlines()
        end_tok = self._expect_op("}")
        return ast.HashLit(span=(start, end_tok.end), pairs=tuple(pairs))


def _reparent(node: ast.Node, span: tuple[int, int]) -> ast.Node:
    """A parenthesized expression keeps its inner node but widens its span
    to cover the parens, so `(expr)`'s span matches the source text."""
    return dataclasses.replace(node, span=span)


def parse_program(source: str) -> ast.Program:
    return _Parser(source).parse_program()


def parse_expression(source: str) -> ast.Node:
    return _Parser(source).parse_expression()


def script_block_source(commands: list[dict], start: int) -> tuple[str, int]:
    """Reconstruct one 355/655 block's Ruby source.

    `commands[start]` must be a code-355 command; its `parameters[0]` line
    is joined with every immediately-following code-655 continuation's
    `parameters[0]`, one raw line each, `"\\n"`-joined. Returns
    `(source, index_after_last_655)`.
    """
    cmd = commands[start]
    if cmd.get("code") != 355:
        raise ValueError(f"script_block_source: commands[{start}] is not code 355")
    parts = [str((cmd.get("parameters") or [""])[0])]
    i = start + 1
    n = len(commands)
    while i < n and commands[i].get("code") == 655:
        params = commands[i].get("parameters") or [""]
        parts.append(str(params[0]))
        i += 1
    return "\n".join(parts), i
