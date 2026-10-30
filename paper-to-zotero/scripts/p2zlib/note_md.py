"""One Zotero note outside Zotero: Markdown with a front matter, converted from and to the note's HTML, losing nothing.

    to_md(html, meta=None) -> md         note HTML -> Markdown; meta (key, version, parent, ...) opens its front matter
    to_note(md) -> (html, meta)          Markdown -> note HTML; the front matter's other keys come back as meta
    set_meta(md, meta) -> md             change front matter keys only (a value None removes the key)
    same(html_a, html_b) -> bool         the two hold the same note in the editor's model

Front matter: a first line `---`, then `key: value` lines (the value runs to the end of the line), then `---`; no first
`---`, no front matter. `schema` and `citation-items` carry the note's wrapper <div data-schema-version
data-citation-items>; any other key is the caller's and passes through.

Markdown carries the subset: headings, paragraphs, nested lists (to-dos are "[ ] text" items, as the editor stores
them), quotes, code blocks, rules (`***`), GFM tables with one header row, $…$ and $$…$$ math, bold, italic, code,
links, hard breaks. Everything else stays HTML inside the Markdown, as CommonMark allows.

The editor's model (`Block`, the runs of a paragraph) is what "the same" means: blocks with their attributes, and
inside a paragraph runs of text, each with the set of marks it carries, merged and with whitespace collapsed as the
editor collapses it on load. Two HTMLs the editor loads alike have one model, and the reader writes from the model,
so reading is stable by construction. Each block written is checked: rendered back with to_note, its model must be
the original's. A paragraph or heading that fails is written again with _ for emphasis, then with its marks as HTML
tags, then as its own HTML; a list, quote, table or code block that still fails is kept whole as HTML (`fallbacks`
names each one). The model is a small one: when unsure whether the editor treats two forms alike, it keeps them
apart, which costs a block written as HTML, never content.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from html import escape
from html.parser import HTMLParser

# ── front matter ──────────────────────────────────────────────────────────────────────────────────────────────────
FIRST, LAST = ("key", "version", "parent", "collections", "related"), ("schema", "citation-items")
META_LINE = re.compile(r"([A-Za-z0-9_-]+):(?: (.*))?$")


def split_meta(md: str) -> tuple[dict, str]:
    """-> (front matter as a dict of strings, the body). A malformed front matter is a ValueError."""
    if not (md.startswith("---\n") or md == "---"):
        return {}, md
    lines, meta = md.split("\n"), {}
    for n, line in enumerate(lines[1:], 1):
        if line == "---":
            return meta, "\n".join(lines[n + 1:])
        m = META_LINE.match(line)
        if not m:
            raise ValueError(f"front matter line {n + 1} is not `key: value`: {line!r}")
        meta[m.group(1)] = m.group(2) or ""
    raise ValueError("front matter opened with --- has no closing ---")


def join_meta(meta: dict, body: str) -> str:
    keys = [k for k in FIRST if k in meta] + [k for k in meta if k not in FIRST + LAST] + [k for k in LAST if k in meta]
    lines = []
    for k in keys:
        v = meta[k]
        v = ",".join(map(str, v)) if isinstance(v, (list, tuple)) else "" if v is None else str(v)
        if "\n" in v:
            raise ValueError(f"front matter value of {k} holds a line break")
        lines.append(f"{k}: {v}" if v else f"{k}:")
    return ("---\n" + "\n".join(lines) + "\n---\n" if lines else "") + body


def set_meta(md: str, meta: dict) -> str:
    old, body = split_meta(md)
    new = {**old, **meta}
    return join_meta({k: v for k, v in new.items() if v is not None}, body)


# ── HTML as a tree ────────────────────────────────────────────────────────────────────────────────────────────────
VOID = {"area", "br", "col", "hr", "img", "input", "wbr"}


class El:
    def __init__(self, tag, attrs):
        self.tag, self.attrs, self.kids = tag, dict((k, v or "") for k, v in attrs), []


class _Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = [El("", [])]

    def handle_starttag(self, tag, attrs):
        el = El(tag, attrs)
        self.stack[-1].kids.append(el)
        if tag not in VOID:
            self.stack.append(el)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1].kids.append(data)


def parse(html: str) -> El:
    p = _Parser()
    p.feed(html)
    p.close()
    return p.stack[0]


def unwrap(root: El) -> tuple[list, dict]:
    """The note's content and its wrapper's attributes: the editor keeps its metadata on body > div[data-schema-version]."""
    elements = [k for k in root.kids if not (isinstance(k, str) and not k.strip())]
    if len(elements) == 1 and isinstance(elements[0], El) and elements[0].tag == "div" \
            and "data-schema-version" in elements[0].attrs:
        return elements[0].kids, elements[0].attrs
    return root.kids, {}


def tidy(nodes):
    """The editor's own shape, in place: a Better Notes to-do checkbox becomes the "[ ] " / "[x] " the editor stores."""
    for i, n in enumerate(nodes):
        if isinstance(n, El):
            if n.tag == "input" and n.attrs.get("type") == "checkbox":
                nodes[i] = "[x] " if "checked" in n.attrs else "[ ] "
            else:
                tidy(n.kids)
    return nodes


def attr_html(attrs) -> str:
    return "".join(f' {k}="{escape(v).replace(chr(10), "&#10;")}"' for k, v in attrs.items())


def outer(n, pre=False) -> str:
    """A node as HTML with no blank line in it: an HTML block in Markdown ends at the first blank line."""
    if isinstance(n, str):
        s = escape(n, quote=False).replace("\xa0", "&nbsp;")
        return re.sub(r"\n(?=[ \t]*\n)", "&#10;", s) if pre else re.sub(r"[ \t\r\f]*\n[ \t\r\n\f]*", "\n", s)
    if n.tag in VOID:
        return f"<{n.tag}{attr_html(n.attrs)}>"
    inner = "".join(outer(k, pre or n.tag == "pre") for k in n.kids)
    return f"<{n.tag}{attr_html(n.attrs)}>{inner}</{n.tag}>"


# ── the editor's model ────────────────────────────────────────────────────────────────────────────────────────────
BLOCK_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "blockquote", "pre", "hr", "table", "div",
              "thead", "tbody", "tfoot", "tr", "th", "td", "figure", "dl", "dd", "dt", "section", "details", "summary"}
TEXTBLOCKS = {"p", "h1", "h2", "h3", "h4", "h5", "h6"}
FILLED = {"", "li", "blockquote", "th", "td"}            # content block+: the editor fills an empty one with a paragraph
MARKS = {"strong": "strong", "b": "strong", "em": "em", "i": "em", "u": "u", "s": "s", "strike": "strike", "del": "del",
         "sub": "sub", "sup": "sup", "code": "code", "a": "a"}            # the editor parses <b> and <i> as strong, em
RANK = {"strong": 0, "em": 1, "u": 2, "s": 3, "strike": 3, "del": 3, "sub": 4, "sup": 5, "span": 6, "a": 8, "code": 9}
WS = re.compile(r"[ \t\n\r\f]+")


class Attrs(tuple):
    """An element's attributes in their order, compared and hashed without regard to it."""

    def __eq__(self, other):
        return sorted(self) == sorted(other)

    def __hash__(self):
        return hash(tuple(sorted(self)))


def attrs_of(n: El, drop=()) -> Attrs:
    a = {k: v for k, v in n.attrs.items() if k not in drop}
    if n.tag == "ol" and a.get("start") == "1":
        del a["start"]
    return Attrs(a.items())


def mark_of(n: El):
    """(name, attrs) when the element is a mark the editor keeps as a set on text, else None."""
    if n.tag in MARKS:
        return MARKS[n.tag], attrs_of(n, drop=("rel",) if n.tag == "a" else ())
    if n.tag == "span" and set(n.attrs) == {"style"}:
        return "span", attrs_of(n)
    return None


def rank(mark):
    return RANK.get(mark[0], 7), mark


def runs(nodes, pre=False) -> tuple:
    """Inline content as the editor holds it: ("t", text, marks) | ("br",) | ("math", text, marks) |
    ("void", tag, attrs, marks) | ("node", tag, attrs, marks, runs); marks a frozenset of (name, attrs)."""
    items = []

    def walk(ns, marks):
        for n in ns:
            if isinstance(n, str):
                items.append(("t", n, marks))
            elif n.tag == "br":
                items.append(("br",))         # a mark on a hard break shows nothing: none is kept
            elif (m := mark_of(n)) is not None:
                walk(n.kids, marks if pre and m[0] == "code" else excluding(marks | {m}))
            elif n.tag == "span" and n.attrs.get("class") == "math":
                items.append(("math", text_of(n), marks))
            elif n.tag in VOID:
                items.append(("void", n.tag, attrs_of(n), marks))
            else:
                items.append(("node", n.tag, attrs_of(n), marks, runs(n.kids, pre)))

    walk(nodes, frozenset())
    out = []
    for it in items:
        if it[0] == "t":
            marks, s = it[2], it[1]
            if pre:
                s = s.replace(" \xa0", "  ")  # the editor writes a double space as " &nbsp;"; in a code block it is "  "
                if not out and s.startswith("\n"):
                    s = s[1:]                 # a browser drops the newline that opens a <pre>
            else:
                s = WS.sub(" ", s)
                if s.startswith(" ") and (not out or out[-1][0] == "br" or out[-1][0] == "t" and out[-1][1].endswith(" ")):
                    s = s[1:]
            if not s:
                continue
            if out and out[-1][0] == "t" and out[-1][2] == marks:
                out[-1] = ("t", out[-1][1] + s, marks)
            else:
                out.append(("t", s, marks))
        else:
            out.append(it)
    if not pre and out and out[-1][0] == "t":
        s = out[-1][1].rstrip(" ")
        out[-1:] = [("t", s, out[-1][2])] if s else []
    return tuple(out)


def marks_of(item) -> frozenset:
    return item[3] if item[0] in ("void", "node") else item[2]


def excluding(marks: frozenset) -> frozenset:
    """The code mark excludes every other mark (marks.js): text in code carries code alone."""
    return frozenset(m for m in marks if m[0] == "code") if any(m[0] == "code" for m in marks) else marks


def text_of(n) -> str:
    return n if isinstance(n, str) else "".join(text_of(k) for k in n.kids)


@dataclass
class Block:
    """A block as the editor holds it, with what it came from (an element, or the inline nodes of a paragraph the
    HTML left implicit): `kids` are child Blocks, or runs for a paragraph, heading or code block."""
    tag: str
    attrs: tuple
    kids: tuple
    src: object = field(compare=False, repr=False)

    @property
    def key(self):
        return (self.tag, self.attrs, tuple(k.key for k in self.kids) if self.container else self.kids)

    @property
    def container(self):
        return self.tag not in TEXTBLOCKS and self.tag not in ("pre", "hr")

    def html(self) -> str:
        if isinstance(self.src, list):
            return "<p>" + "".join(outer(n) for n in self.src) + "</p>"
        return outer(self.src)


def blocks(nodes, parent="") -> tuple:
    """The blocks of a container: inline nodes between blocks form a paragraph; whitespace between blocks is nothing."""
    out, run = [], []

    def flush():
        if any(not (isinstance(n, str) and not WS.sub("", n)) for n in run):
            out.append(Block("p", (), runs(run), list(run)))
        run.clear()

    for n in nodes:
        if isinstance(n, El) and n.tag in BLOCK_TAGS:
            flush()
            out.append(block(n))
        else:
            run.append(n)
    flush()
    if not out and parent in FILLED:
        out.append(Block("p", (), (), []))
    return tuple(out)


def block(n: El) -> Block:
    t = n.tag
    if t in TEXTBLOCKS:
        return Block(t, attrs_of(n), runs(n.kids), n)
    if t == "pre":
        return Block(t, attrs_of(n), runs(n.kids, pre=True), n)
    if t == "hr":
        return Block(t, attrs_of(n), (), n)
    if t == "table":                          # rows, whatever groups them (the editor writes no <thead>)
        rows = []
        for k in n.kids:
            if isinstance(k, El) and k.tag in ("thead", "tbody", "tfoot"):
                rows += [block(r) for r in k.kids if isinstance(r, El)]
            elif isinstance(k, El):
                rows.append(block(k))
        return Block(t, attrs_of(n), tuple(rows), n)
    if t == "tr":
        return Block(t, attrs_of(n), tuple(block(c) for c in n.kids if isinstance(c, El)), n)
    if t in ("ul", "ol"):
        items = [block(k) if isinstance(k, El) else Block("p", (), runs([k]), [k])
                 for k in n.kids if not (isinstance(k, str) and not WS.sub("", k))]
        return Block(t, attrs_of(n), tuple(items), n)
    return Block(t, attrs_of(n), blocks(n.kids, t), n)


def model(html: str) -> tuple[tuple, dict]:
    content, wrapper = unwrap(parse(html))
    return blocks(tidy(content), ""), wrapper


def same(a: str, b: str) -> bool:
    return [x.key for x in model(a)[0]] == [x.key for x in model(b)[0]]


# ── writing: Markdown -> note HTML ────────────────────────────────────────────────────────────────────────────────
_MD = None


def math_block(state, start, end, silent):
    """$$…$$ on one line, or from a line opening with $$ to one ending with $$: the formula is everything between
    the two, line breaks included. Lines are read the way `fence` reads them, so a list item's indent or a quote's >
    stays out of the formula (mdit-py-plugins 0.6.1 keeps it in)."""
    if state.sCount[start] - state.blkIndent >= 4:
        return False
    pos, mx = state.bMarks[start] + state.tShift[start], state.eMarks[start]
    if not state.src.startswith("$$", pos):
        return False
    first = state.src[pos + 2:mx]
    if first.rstrip().endswith("$$") and len(first.rstrip()) >= 2:
        content, last = first.rstrip()[:-2], start
    else:
        last = start + 1
        while last < end:
            p, m = state.bMarks[last] + state.tShift[last], state.eMarks[last]
            if p >= m or state.sCount[last] < state.blkIndent:
                return False                  # a blank line, or the container ended
            if state.src[p:m].rstrip().endswith("$$"):
                break
            last += 1
        else:
            return False
        p = state.bMarks[last] + state.tShift[last]
        middle = state.getLines(start + 1, last, state.sCount[start], False)
        closing = state.src[p:state.eMarks[last]].rstrip()[:-2]
        content = "\n".join([first] + ([middle] if last > start + 1 else []) + [closing])
    if silent:
        return True
    state.line = last + 1
    token = state.push("math_block", "math", 0)
    token.block, token.content, token.markup, token.map = True, content, "$$", [start, state.line]
    return True


def md_parser():
    global _MD
    if _MD is None:
        from markdown_it import MarkdownIt
        from markdown_it.common.utils import escapeHtml
        from mdit_py_cjk_friendly import cjk_friendly
        from mdit_py_plugins.dollarmath import dollarmath_plugin
        m = MarkdownIt("commonmark", {"html": True, "xhtmlOut": False}).enable("table")
        m.use(dollarmath_plugin, allow_labels=False, double_inline=True).use(cjk_friendly)
        m.block.ruler.at("math_block", math_block, {"alt": ["paragraph", "reference", "blockquote", "list"]})
        m.normalizeLink = lambda url: url    # links as written: no percent-encoding, file: allowed
        m.validateLink = lambda url: True
        pre = lambda t, i, cls="": f"<pre{cls}>{escapeHtml(t[i].content.removesuffix(chr(10)))}</pre>\n"  # noqa: E731
        m.add_render_rule("fence", lambda s, t, i, o, e: pre(t, i))
        m.add_render_rule("code_block", lambda s, t, i, o, e: pre(t, i))
        m.add_render_rule("math_inline", lambda s, t, i, o, e: f'<span class="math">${escapeHtml(t[i].content)}$</span>')
        m.add_render_rule("math_inline_double",
                          lambda s, t, i, o, e: f'<span class="math">$${escapeHtml(t[i].content)}$$</span>')
        m.add_render_rule("math_block",
                          lambda s, t, i, o, e: f'<pre class="math">$${escapeHtml(t[i].content)}$$</pre>\n')
        _MD = m
    return _MD


def render(body: str) -> str:
    return md_parser().render(body)


def to_note(md: str) -> tuple[str, dict]:
    """The note's HTML, inside the editor's wrapper when the front matter carries one; the other keys as meta."""
    meta, body = split_meta(md)
    schema, items = meta.pop("schema", None), meta.pop("citation-items", None)
    if schema is None and items is None:
        return render(body), meta
    wrapper = {"data-schema-version": schema or "9", **({"data-citation-items": items} if items else {})}
    return f"<div{attr_html(wrapper)}>{render(body)}</div>", meta


# ── reading: note HTML -> Markdown ────────────────────────────────────────────────────────────────────────────────
LINE_START = [  # (pattern at the start of a line, where to put the backslash)
    re.compile(r"(#{1,6})(?=[ \t]|$)"), re.compile(r"(>)"), re.compile(r"([-+*])(?=[ \t]|$)"),
    re.compile(r"\d{1,9}([.)])(?=[ \t]|$)"), re.compile(r"(=)=*[ \t]*$"), re.compile(r"(-)-*[ \t]*$"),
    re.compile(r"([-*_])(?:[ \t]*\1){2,}[ \t]*$"), re.compile(r"(~){3}"), re.compile(r"(\[)[^\]]*\]:"),
]


def escape_line_starts(md: str) -> str:
    out = []
    for line in md.split("\n"):
        for p in LINE_START:
            m = p.match(line)
            if m:
                i = m.start(1)
                line = line[:i] + "\\" + line[i:]
                break
        out.append(line)
    return "\n".join(out)


def esc(s: str, cell=False) -> str:
    """Backslashes only where CommonMark would otherwise read syntax (the starts of lines are escape_line_starts')."""
    s = re.sub(r"\\(?=[!-/:-@\[-`{-~]|$)", r"\\\\", s)
    s = re.sub(r"(?<! )\*|\*(?! )", r"\\*", s)
    s = re.sub(r"_", lambda m: "_" if 0 < m.start() < len(s) - 1 and (s[m.start() - 1] + s[m.start() + 1]).isalnum()
               or s[m.start() - 1:m.start() + 2] == " _ " else "\\_", s)
    s = re.sub(r"([`$])", r"\\\1", s)
    s = re.sub(r"\](?=\()", r"\\]", s)
    s = re.sub(r"<(?=[A-Za-z/!?])", r"\\<", s)
    s = re.sub(r"&(?=#?\w+;)", r"\\&", s)
    if cell:
        s = s.replace("|", "\\|")
    return s.replace("\xa0", "&nbsp;")


def code_span(s: str, cell=False) -> str:
    if cell:
        s = s.replace("|", "\\|")
    ticks = "`" * (max((len(m) for m in re.findall(r"`+", s)), default=0) + 1)
    pad = " " if s[:1] == "`" or s[-1:] == "`" or (s[:1] == " " and s[-1:] == " " and s.strip()) else ""
    return ticks + pad + s + pad + ticks


def dest(url: str) -> str | None:
    url = re.sub(r"\\(?=[!-/:-@\[-`{-~])", r"\\\\", url)
    url = re.sub(r"&(?=#?\w+;)", r"\\&", url)
    depth = 0
    for ch in url:
        depth += {"(": 1, ")": -1}.get(ch, 0)
        if depth < 0:
            break
    if url and depth == 0 and not re.search(r"[\s<>]", url):
        return url
    if re.search(r"[<>\n]", url):
        return None
    return f"<{url}>"


class Reader:
    """Writes the blocks of one note as Markdown, checking each; `fallbacks` lists the blocks kept as HTML, as
    (number of the top-level block, from 1; the element kept)."""

    def __init__(self):
        self.fallbacks, self.at = [], 0

    @staticmethod
    def holds(md: str, b: Block, cell: str | None = None) -> bool:
        """md rendered holds b and nothing else; a cell's paragraph is checked inside a one-column table (cell: th, td)."""
        if cell:
            md = f"| {md} |\n| --- |" if cell == "th" else f"|  |\n| --- |\n| {md} |"
        got = blocks(tidy(unwrap(parse(render(md)))[0]), "")
        if cell:
            try:
                got = got[0].kids[0 if cell == "th" else 1].kids[0].kids if got[0].tag == "table" else ()
            except IndexError:
                return False
        return len(got) == 1 and got[0].key == b.key

    def inline(self, items, style="*", oneline=False, cell=False) -> str | None:
        """Runs as Markdown: style "*" or "_" writes emphasis with that delimiter, "tags" writes every mark as its
        HTML tag (the text inside stays Markdown)."""
        tags, out, stack = style == "tags", [], []

        def close_to(marks):
            keep = 0
            while keep < len(stack) and stack[keep] in marks:
                keep += 1
            while len(stack) > keep:
                out.append(closer(stack.pop()))

        def opener(m):
            name, a = m
            if name == "strong" and not tags:
                return "**"
            if name == "em" and not tags:
                return style
            if name == "a" and not tags:
                return "["
            return f"<{name}{attr_html(dict(a))}>"

        def closer(m):
            name, a = m
            if name in ("strong", "em") and not tags:
                return "**" if name == "strong" else style
            if name == "a" and not tags:
                d, title = dest(dict(a).get("href", "")), dict(a).get("title")
                if d is None or set(dict(a)) - {"href", "title"}:
                    raise ValueError("link not writable as Markdown")
                t = ' "' + title.replace("\\", "\\\\").replace('"', '\\"') + '"' if title else ""
                return f"]({d}{t})"
            return f"</{name}>"

        try:
            for n, it in enumerate(items):
                if it[0] == "br":
                    after = next((x for x in items[n + 1:] if x[0] != "br"), None)
                    close_to(marks_of(after) if after else ())
                    out.append("<br>" if oneline or n == 0 or n == len(items) - 1 else "\\\n")
                    continue
                marks = sorted(marks_of(it), key=rank)
                close_to(marks)
                for m in marks:
                    if m not in stack and m[0] != "code":
                        out.append(opener(m))
                        stack.append(m)
                code = any(m[0] == "code" for m in marks)
                if it[0] == "t":
                    if code and not tags:
                        out.append(code_span(it[1], cell))
                    elif code:
                        out.append("<code>" + esc(it[1], cell) + "</code>")
                    else:
                        out.append(esc(it[1], cell))
                elif it[0] == "math":
                    inner = it[1][1:-1] if len(it[1]) >= 2 and it[1][0] == it[1][-1] == "$" else None
                    if tags or inner is None:
                        out.append('<span class="math">' + esc(it[1], cell) + "</span>")
                    else:
                        out.append("$" + (inner.replace("|", "\\|") if cell else inner) + "$")
                elif it[0] == "void":
                    out.append(f"<{it[1]}{attr_html(dict(it[2]))}>")
                else:
                    inner = self.inline(it[4], style, oneline, cell)
                    if inner is None:
                        return None
                    out.append(f"<{it[1]}{attr_html(dict(it[2]))}>{inner}</{it[1]}>")
            while stack:
                out.append(closer(stack.pop()))
        except ValueError:
            return None
        return "".join(out)

    def leaf(self, b: Block, cell: str | None = None) -> str | None:
        """A paragraph or heading: Markdown, else with _ for emphasis, else with HTML tags for its marks; None when
        none holds it."""
        heading = b.tag != "p"
        if b.attrs:
            return None
        if not b.kids:                        # an empty paragraph has no Markdown, but a cell or a heading can be empty
            return "" if cell else "#" * int(b.tag[1]) if heading else None
        for style in ("*", "_", "tags"):
            s = self.inline(b.kids, style, oneline=heading or bool(cell), cell=bool(cell))
            if s is None:
                continue
            if heading:
                md = "#" * int(b.tag[1]) + " " + re.sub(r"(^|[ \t])(#+[ \t]*)$", r"\1\\\2", s)
            else:
                md = s if cell else escape_line_starts(s)
            if self.holds(md, b, cell):
                return md
        return None

    def code(self, b: Block) -> str | None:
        if b.attrs not in ((), (("class", "math"),)) or any(it[0] != "t" or it[2] for it in b.kids):
            return None
        text = "".join(it[1] for it in b.kids)
        if b.attrs:                           # display math: $$…$$
            if not (len(text) >= 4 and text.startswith("$$") and text.endswith("$$")):
                return None
            return text                       # the formula as it is, line breaks included
        fence = "`" * max(3, max((len(m) for m in re.findall(r"`+", text)), default=0) + 1)
        return f"{fence}\n{text}\n{fence}" if text else f"{fence}\n{fence}"

    def table(self, b: Block) -> str | None:
        rows = b.kids
        if b.attrs or not rows or any(r.tag != "tr" or r.attrs for r in rows):
            return None
        width = len(rows[0].kids)
        if not width or any(len(r.kids) != width for r in rows):
            return None
        lines = []
        for n, r in enumerate(rows):
            cells = []
            for c in r.kids:
                if c.tag != ("th" if n == 0 else "td") or c.attrs or len(c.kids) != 1 or c.kids[0].tag != "p":
                    return None
                md = self.leaf(c.kids[0], cell=c.tag)
                if md is None:
                    return None
                cells.append(md)
            lines.append("| " + " | ".join(cells) + " |")
            if n == 0:
                lines.append("| " + " | ".join("---" for _ in cells) + " |")
        return "\n".join(lines)

    def list(self, b: Block, alt=False) -> str | None:
        allowed = {"start"} if b.tag == "ol" else set()
        if set(dict(b.attrs)) - allowed or any(li.tag != "li" or li.attrs for li in b.kids):
            return None
        start, items = int(dict(b.attrs).get("start", "1")), []
        for k, li in enumerate(b.kids):
            marker = f"{start + k}{')' if alt else '.'} " if b.tag == "ol" else ("* " if alt else "- ")
            body = self.sequence(li.kids)
            lines = body.split("\n")
            items.append(marker.rstrip() if not body else
                         marker + lines[0] + "".join("\n" + (" " * len(marker) + ln if ln else "") for ln in lines[1:]))
        return "\n".join(items)

    def quote(self, b: Block) -> str | None:
        if b.attrs:
            return None
        body = self.sequence(b.kids)
        return "\n".join("> " + ln if ln else ">" for ln in body.split("\n")) if body else ">"

    def write(self, b: Block, alt=False) -> str | None:
        """Markdown for the block, or None when it has none: the caller keeps it as HTML."""
        if b.tag in TEXTBLOCKS:
            return self.leaf(b)
        if b.tag == "pre":
            return self.code(b)
        if b.tag == "hr":
            return None if b.attrs else "***"
        if b.tag in ("ul", "ol"):
            return self.list(b, alt)
        if b.tag == "blockquote":
            return self.quote(b)
        if b.tag == "table":
            return self.table(b)
        return None

    def html(self, b: Block) -> str:
        if b.kids or b.tag != "p":
            self.fallbacks.append((self.at, b.tag))
        return b.html()

    def sequence(self, bs, top=False) -> str:
        """Blocks one after another, each written or kept as HTML. At the top a blank line apart, and each list,
        quote, table or code block is checked whole (kept as HTML when it does not hold; its parts' fallbacks fold
        into it). In a list item or a quote, a paragraph and a block that can interrupt it stay on adjacent lines;
        a lone empty paragraph is "". Two Markdown lists of one kind in a row change their marker (- *, . )), or they
        would merge into one."""
        if not top and [b.key for b in bs] == [("p", (), ())]:
            return ""
        out, prev, prev_alt = [], None, False
        for n, b in enumerate(bs, 1):
            if top:
                self.at = n
            alt = prev is not None and prev[1] and prev[0].tag == b.tag and b.tag in ("ul", "ol") and not prev_alt
            mark = len(self.fallbacks)
            md = self.write(b, alt)
            if top and md is not None and b.tag not in TEXTBLOCKS and not self.holds(md, b):
                del self.fallbacks[mark:]     # a paragraph or heading was checked as it was written
                md = None
            written = md is not None
            if out:
                tight = not top and written and prev[1] and prev[0].tag == "p" and interrupts(b)
                out.append("\n" if tight else "\n\n")
            if not written:
                md = self.html(b)
                if top and not self.holds(md, b):
                    raise ValueError(f"block {n} (<{b.tag}>) does not come back the same even as HTML")
            out.append(md)
            prev, prev_alt = (b, written), alt and written
        return "".join(out)


def interrupts(b: Block) -> bool:
    """The block, written as Markdown, can start right under a paragraph's line: a heading, code block, display math,
    quote or rule; a list whose first item is not empty and, ordered, starts at 1."""
    if b.tag not in ("ul", "ol"):
        return b.tag in ("h1", "h2", "h3", "h4", "h5", "h6", "pre", "blockquote", "hr")
    first = b.kids[0] if b.kids else None
    empty = first is None or [k.key for k in first.kids] == [("p", (), ())]
    return not empty and dict(b.attrs).get("start", "1") == "1"


def to_md(html: str, meta: dict | None = None, fallbacks: list | None = None) -> str:
    content, wrapper = unwrap(parse(html))
    bs = blocks(tidy(content), "")
    reader = Reader()
    body = "" if [b.key for b in bs] == [("p", (), ())] else reader.sequence(bs, top=True)
    if fallbacks is not None:
        fallbacks += reader.fallbacks
    front = dict(meta or {})
    if "data-schema-version" in wrapper:
        front["schema"] = wrapper["data-schema-version"]
    if wrapper.get("data-citation-items"):
        front["citation-items"] = wrapper["data-citation-items"]
    return join_meta(front, body + "\n" if body else "")
