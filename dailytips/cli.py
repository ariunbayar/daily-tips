"""Argument handling.

Hand-rolled rather than argparse: this is a resident process, and argparse costs
memory that never comes back once imported.
"""

import os
import sys

from . import render, store

USAGE = """usage: tips [options] [command]

  (no command)      open the browser UI
  today             print today's tip and exit
  list              list every tip
  search WORDS      print tips matching WORDS
  new TITLE         create a tip and open $EDITOR
  path              print the tips directory

options:
  --dir PATH        tips directory (default: $DAILY_TIPS_DIR or
                    ~/.local/share/daily-tips/tips)
  --date YYYY-MM-DD show the tip for another day
  --no-color        plain output, no escape sequences
  -h, --help        this message
"""


def today_ordinal():
    """Proleptic Gregorian ordinal for the local date."""
    from datetime import date

    return date.today().toordinal()


def parse_date(text):
    parts = text.split("-")
    if len(parts) != 3:
        raise SystemExit("--date must look like YYYY-MM-DD")
    from datetime import date

    try:
        return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError as exc:
        raise SystemExit(f"bad date: {exc}")


def header_for(ordinal):
    from datetime import date

    return date.fromordinal(ordinal).strftime("%A %d %B %Y").lower()


def emit(lines, color):
    sys.stdout.write(render.to_ansi(lines, color, indent="  ") + "\n")


def index_lines(tips, today=None):
    out = []
    for tip in tips:
        marker = "▸ " if tip.path == today else "  "
        spans = [(marker, render.BULLET), (tip.title, render.PLAIN)]
        if tip.tags:
            spans.append(("  " + " ".join("#" + t for t in tip.tags), render.TAG))
        out.append(spans)
    return out


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    directory = None
    color = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
    when = None
    rest = []

    while argv:
        arg = argv.pop(0)
        if arg in ("-h", "--help"):
            sys.stdout.write(USAGE)
            return 0
        elif arg == "--no-color":
            color = False
        elif arg == "--dir":
            if not argv:
                raise SystemExit("--dir needs a path")
            directory = os.path.expanduser(argv.pop(0))
        elif arg == "--date":
            if not argv:
                raise SystemExit("--date needs a date")
            when = parse_date(argv.pop(0))
        elif arg.startswith("-") and arg != "-":
            raise SystemExit(f"unknown option: {arg}\n\n{USAGE}")
        else:
            rest.append(arg)

    directory = directory or store.tips_dir()
    ordinal = when.toordinal() if when else today_ordinal()
    command = rest[0] if rest else None
    args = rest[1:]

    if command == "path":
        sys.stdout.write(directory + "\n")
        return 0

    if command == "new":
        if not args:
            raise SystemExit("new needs a title")
        title = " ".join(args)
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(
            directory, f"{store.next_number(directory):04d}-{store.slugify(title)}.md"
        )
        if os.path.exists(path):
            raise SystemExit(f"{path} already exists")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(f"# {title}\ntags:\n\n")
        sys.stdout.write(path + "\n")
        editor = os.environ.get("EDITOR")
        if editor and sys.stdout.isatty():
            os.execvp(editor, [editor, path])
        return 0

    paths = store.paths(directory)
    if not paths:
        sys.stderr.write(f"no tips in {directory}\n")
        sys.stderr.write('add one with:  tips new "your tip title"\n')
        return 1

    if command == "list":
        emit(index_lines(store.iter_tips(directory, want_body=False),
                         store.of_the_day(paths, ordinal)), color)
        return 0

    if command == "search":
        if not args:
            raise SystemExit("search needs something to look for")
        needle = " ".join(args).lower()
        hits = [t for t in store.iter_tips(directory) if t.matches(needle)]
        if not hits:
            sys.stderr.write(f"nothing matches '{needle}'\n")
            return 1
        emit(index_lines(hits), color)
        return 0

    if command in (None, "today"):
        chosen = store.of_the_day(paths, ordinal)
        if command is None and sys.stdout.isatty() and not when:
            from . import tui

            tui.start(directory, ordinal)
            return 0
        width = 78
        if sys.stdout.isatty():
            try:
                width = min(os.get_terminal_size().columns - 4, 78)
            except OSError:
                pass
        sys.stdout.write("\n")
        emit(render.tip(store.parse(chosen), width, header_for(ordinal)), color)
        sys.stdout.write("\n")
        return 0

    raise SystemExit(f"unknown command: {command}\n\n{USAGE}")
