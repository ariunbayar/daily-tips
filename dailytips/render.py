"""Markdown-ish rendering into styled spans.

Everything renders to lines of ``(text, style)`` spans, which the curses UI turns
into attributes and the plain-output path turns into ANSI escapes. No imports:
the wrapper and inline parser are hand-rolled to keep a resident process small.
"""

PLAIN = 0
TITLE = 1
TAG = 2
CODE = 3
STRONG = 4
BULLET = 5
DIM = 6
HEADER = 7

ANSI = {
    PLAIN: "",
    TITLE: "\033[1;32m",
    TAG: "\033[2;36m",
    CODE: "\033[36m",
    STRONG: "\033[1m",
    BULLET: "\033[33m",
    DIM: "\033[2m",
    HEADER: "\033[2m",
}
RESET = "\033[0m"

MAX_WIDTH = 78


def inline(text, base=PLAIN):
    """Split `code` and **bold** runs out of a line into styled spans."""
    spans = []
    for i, chunk in enumerate(text.split("`")):
        if i % 2:
            if chunk:
                spans.append((chunk, CODE))
            continue
        for j, piece in enumerate(chunk.split("**")):
            if piece:
                spans.append((piece, STRONG if j % 2 else base))
    return spans or [("", base)]


def wrap(spans, width, hang=""):
    """Greedily wrap styled spans to ``width`` visible columns."""
    if width < 8:
        width = 8
    # A word is a list of spans, so `code`-then-punctuation stays one unit and
    # no space is invented at a style boundary that had none.
    words = []
    word = []
    for text, style in spans:
        if style == CODE and " " in text and len(text) <= width:
            word.append((text, style))  # keep short code spans intact
            continue
        for i, part in enumerate(text.split(" ")):
            if i and word:
                words.append(word)
                word = []
            if part:
                word.append((part, style))
    if word:
        words.append(word)

    lines = []
    cur = []
    length = 0
    for word in words:
        size = sum(len(text) for text, _ in word)
        sep = 1 if cur else 0
        if cur and length + sep + size > width:
            lines.append(cur)
            cur = [(hang, PLAIN)] if hang else []
            length = len(hang)
            sep = 0
        if sep:
            cur.append((" ", PLAIN))
            length += 1
        cur.extend(word)
        length += size
    if cur:
        lines.append(cur)
    return lines or [[("", PLAIN)]]


def body(text, width):
    """Render a tip body: fenced code blocks, bullets, paragraphs.

    Soft-wrapped source lines are joined back into their block first, so the
    file can be wrapped for editing and still reflow to the terminal width.
    """
    lines = []
    in_code = False
    pending = None  # (kind, indent, joined text)

    def flush():
        if pending is None:
            return
        kind, pad, joined = pending
        if kind == "bullet":
            wrapped = wrap(inline(joined), width - len(pad) - 2, hang=pad + "  ")
            lines.append([(pad, PLAIN), ("• ", BULLET)] + wrapped[0])
            lines.extend(wrapped[1:])
        else:
            lines.extend(wrap(inline(joined), width))

    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("```"):
            flush()
            pending = None
            in_code = not in_code
            continue
        if in_code:
            lines.append([("│ ", DIM), (raw[:width], CODE)])
            continue
        if not stripped:
            flush()
            pending = None
            lines.append([("", PLAIN)])
            continue
        if stripped[:2] in ("- ", "* "):
            flush()
            pad = " " * (len(raw) - len(raw.lstrip()))
            pending = ("bullet", pad, stripped[2:])
            continue
        if pending is None:
            pending = ("para", "", stripped)
        else:
            pending = (pending[0], pending[1], pending[2] + " " + stripped)
    flush()
    while lines and not any(text for text, _ in lines[-1]):
        lines.pop()
    return lines


def tip(t, width, header=None):
    """A full tip: optional header, title, tags, blank line, body."""
    width = min(width, MAX_WIDTH)
    lines = []
    if header:
        lines.append([(header, HEADER)])
        lines.append([("", PLAIN)])
    lines.extend(wrap([(t.title, TITLE)], width))
    if t.tags:
        lines.append([("  ".join("#" + tag for tag in t.tags), TAG)])
    lines.append([("", PLAIN)])
    if t.body:
        lines.extend(body(t.body, width))
    return lines


def to_ansi(lines, color=True, indent=""):
    """Flatten styled lines into a printable string."""
    out = []
    for line in lines:
        if color:
            parts = []
            for text, style in line:
                code = ANSI[style]
                parts.append(code + text + RESET if code and text else text)
            out.append((indent + "".join(parts)).rstrip())
        else:
            out.append((indent + "".join(text for text, _ in line)).rstrip())
    return "\n".join(out)
