"""Locating, parsing and choosing tips.

Tips live outside the repo so the collection stays private: they are read from
``$DAILY_TIPS_DIR`` when set, otherwise ``~/.local/share/daily-tips/tips``.

Kept deliberately import-light -- only ``os`` -- and lazy: showing one tip reads
one file, never the whole collection.
"""

import os

# Knuth's LCG constants; used for a self-contained shuffle so that no `random`
# import is needed and the order stays identical across Python versions.
_MULT = 6364136223846793005
_ADD = 1442695040888963407
_MASK = 0xFFFFFFFFFFFFFFFF


def tips_dir():
    """Directory holding the tip files, honouring DAILY_TIPS_DIR."""
    env = os.environ.get("DAILY_TIPS_DIR")
    if env:
        return os.path.expanduser(env)
    share = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(share, "daily-tips", "tips")


class Tip:
    __slots__ = ("path", "title", "tags", "body")

    def __init__(self, path, title, tags, body):
        self.path = path
        self.title = title
        self.tags = tags
        self.body = body

    @property
    def slug(self):
        return os.path.basename(self.path)[:-3]

    def matches(self, needle):
        if needle in self.title.lower() or needle in self.body.lower():
            return True
        return any(needle in tag for tag in self.tags)


def paths(directory=None):
    """Sorted tip file paths. Empty when the directory does not exist."""
    directory = directory or tips_dir()
    try:
        names = sorted(e.name for e in os.scandir(directory) if e.name.endswith(".md"))
    except (FileNotFoundError, NotADirectoryError, PermissionError):
        return []
    return [os.path.join(directory, name) for name in names]


def parse(path, want_body=True):
    """Parse one tip: '# Title', optional 'tags: a, b', then the body.

    With ``want_body`` false only the header is kept, so listing a large
    collection does not hold every body in memory at once.
    """
    with open(path, encoding="utf-8") as handle:
        lines = handle.read().splitlines()

    title = ""
    tags = []
    start = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            if title:
                start = i + 1
                break
            continue
        if not title and stripped.startswith("# "):
            title = stripped[2:].strip()
            start = i + 1
            continue
        if title and stripped[:5].lower() == "tags:":
            tags = [t.strip() for t in stripped[5:].split(",") if t.strip()]
            start = i + 1
            continue
        start = i
        break

    if not title:
        title = os.path.basename(path)[:-3].replace("-", " ")
    body = "\n".join(lines[start:]).strip("\n") if want_body else ""
    return Tip(path, title, tags, body)


def iter_tips(directory=None, want_body=True):
    """Yield tips one at a time so only one body is alive at a time."""
    for path in paths(directory):
        yield parse(path, want_body)


def _order(count, seed):
    """A deterministic permutation of range(count) for the given seed."""
    idx = list(range(count))
    state = seed & _MASK
    for i in range(count - 1, 0, -1):
        state = (state * _MULT + _ADD) & _MASK
        j = (state >> 33) % (i + 1)
        idx[i], idx[j] = idx[j], idx[i]
    return idx


def _guard(count):
    return min(3, count // 3)


def _space_out(order, tail, guard):
    """Push anything the previous cycle just showed out of the opening slots.

    Offenders move into the middle, never into the closing slots: those are what
    the *next* cycle guards against, so leaving them untouched keeps the check
    exact without having to replay every earlier cycle.
    """
    limit = len(order) - guard
    for i in range(guard):
        if order[i] in tail:
            for j in range(guard, limit):
                if order[j] not in tail:
                    order[i], order[j] = order[j], order[i]
                    break
    return order


def _cycle_order(count, cycle):
    """The viewing order for one cycle, spaced against the cycle before it."""
    order = _order(count, cycle)
    guard = _guard(count)
    if cycle < 1 or guard < 1 or count < 2 * guard + 1:
        return order
    return _space_out(order, set(_order(count, cycle - 1)[-guard:]), guard)


def of_the_day(all_paths, ordinal):
    """The tip path for a day, given that day's proleptic Gregorian ordinal.

    Every tip is shown exactly once per cycle of ``len(all_paths)`` days; the
    order is reshuffled each cycle, spaced so a tip shown at the end of one
    cycle does not reappear at the start of the next, and is stable for a day.
    """
    if not all_paths:
        return None
    cycle, pos = divmod(ordinal, len(all_paths))
    return all_paths[_cycle_order(len(all_paths), cycle)[pos]]


def next_number(directory=None):
    """The next free NNNN prefix, so new tips sort after existing ones."""
    highest = 0
    for path in paths(directory):
        head = os.path.basename(path).split("-", 1)[0]
        if head.isdigit():
            highest = max(highest, int(head))
    return highest + 1


def slugify(text):
    out = []
    for char in text.lower():
        if char.isalnum() and char.isascii():
            out.append(char)
        elif out and out[-1] != "-":
            out.append("-")
    return "".join(out).strip("-") or "tip"
