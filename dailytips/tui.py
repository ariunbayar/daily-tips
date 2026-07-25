"""The resident curses UI.

Memory discipline: the index holds only (path, title, tags) per tip; exactly one
body -- the tip on screen -- is resident at a time, dropped as soon as the
selection moves.
"""

import curses
import os

from . import render, store

LIST_WIDTH = 34
SPLIT_AT = 88  # below this many columns, list and reader take turns

HELP = [
    ("j / k, ↓ ↑", "move selection"),
    ("g / G", "first / last tip"),
    ("enter, l, →", "open reader (narrow terminals)"),
    ("esc, h, ←", "back to the list"),
    ("space / b", "scroll reader"),
    ("t", "jump to today's tip"),
    ("/", "filter tips"),
    ("n", "new tip in $EDITOR"),
    ("e", "edit the selected tip"),
    ("r", "reload from disk"),
    ("?", "this help"),
    ("q", "quit"),
]

ATTRS = {}


def init_colors():
    """Map render styles onto curses attributes, degrading without colour."""
    ATTRS[render.PLAIN] = curses.A_NORMAL
    ATTRS[render.STRONG] = curses.A_BOLD
    ATTRS[render.DIM] = curses.A_DIM
    ATTRS[render.HEADER] = curses.A_DIM
    if not curses.has_colors():
        ATTRS[render.TITLE] = curses.A_BOLD
        ATTRS[render.TAG] = curses.A_DIM
        ATTRS[render.CODE] = curses.A_NORMAL
        ATTRS[render.BULLET] = curses.A_BOLD
        return
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_GREEN, -1)
    curses.init_pair(2, curses.COLOR_CYAN, -1)
    curses.init_pair(3, curses.COLOR_YELLOW, -1)
    ATTRS[render.TITLE] = curses.color_pair(1) | curses.A_BOLD
    ATTRS[render.TAG] = curses.color_pair(2) | curses.A_DIM
    ATTRS[render.CODE] = curses.color_pair(2)
    ATTRS[render.BULLET] = curses.color_pair(3)


def put(win, y, x, text, attr, limit):
    """Write clipped to ``limit`` columns; curses errors on the last cell."""
    if y < 0 or x >= limit or not text:
        return x
    text = text[: limit - x]
    try:
        win.addstr(y, x, text, attr)
    except curses.error:
        pass
    return x + len(text)


class App:
    def __init__(self, screen, directory, ordinal):
        self.screen = screen
        self.directory = directory
        self.ordinal = ordinal
        self.filter = ""
        self.selected = 0
        self.scroll = 0
        self.focus_reader = False
        self.message = ""
        self.body_cache = None  # (path, rendered lines) for the current tip only
        self.reload(keep_selection=False)

    # ---- data -----------------------------------------------------------

    def reload(self, keep_selection=True):
        current = self.current_path() if keep_selection else None
        self.all_paths = store.paths(self.directory)
        self.index = [store.parse(p, want_body=False) for p in self.all_paths]
        self.today = store.of_the_day(self.all_paths, self.ordinal)
        self.apply_filter()
        if current and current in self.visible_paths:
            self.selected = self.visible_paths.index(current)
        elif not keep_selection and self.today in self.visible_paths:
            self.selected = self.visible_paths.index(self.today)
        self.clamp()

    def apply_filter(self):
        needle = self.filter.lower()
        if not needle:
            self.visible = list(self.index)
        else:
            # Titles and tags come from the index; bodies are read and dropped.
            self.visible = [
                t
                for t in self.index
                if needle in t.title.lower()
                or any(needle in tag.lower() for tag in t.tags)
                or store.parse(t.path).matches(needle)
            ]
        self.visible_paths = [t.path for t in self.visible]

    def current(self):
        return self.visible[self.selected] if self.visible else None

    def current_path(self):
        tip = self.current()
        return tip.path if tip else None

    def rendered(self, width):
        """Body lines for the selected tip, holding only this one in memory."""
        tip = self.current()
        if not tip:
            return []
        key = (tip.path, width)
        if not self.body_cache or self.body_cache[0] != key:
            full = store.parse(tip.path)
            header = "today's tip" if tip.path == self.today else None
            self.body_cache = (key, render.tip(full, width, header))
        return self.body_cache[1]

    def clamp(self):
        if not self.visible:
            self.selected = 0
        else:
            self.selected = max(0, min(self.selected, len(self.visible) - 1))
        self.scroll = 0

    # ---- drawing --------------------------------------------------------

    def draw(self):
        self.screen.erase()
        rows, cols = self.screen.getmaxyx()
        split = cols >= SPLIT_AT
        self.draw_header(cols)
        body_rows = rows - 2
        if split:
            self.draw_list(1, 0, body_rows, LIST_WIDTH)
            self.draw_divider(1, LIST_WIDTH, body_rows)
            self.draw_reader(1, LIST_WIDTH + 2, body_rows, cols - LIST_WIDTH - 2)
        elif self.focus_reader:
            self.draw_reader(1, 0, body_rows, cols)
        else:
            self.draw_list(1, 0, body_rows, cols)
        self.draw_status(rows - 1, cols, split)
        self.screen.noutrefresh()
        curses.doupdate()

    def draw_header(self, cols):
        left = " daily tips"
        right = f"{len(self.visible)}/{len(self.index)} "
        pad = max(1, cols - len(left) - len(right))
        put(self.screen, 0, 0, left + " " * pad + right, curses.A_REVERSE, cols)

    def draw_divider(self, top, x, rows):
        for y in range(top, top + rows):
            put(self.screen, y, x, "│", ATTRS[render.DIM], x + 1)

    def draw_list(self, top, left, rows, width):
        if not self.visible:
            put(self.screen, top, left + 1, "no tips", ATTRS[render.DIM], left + width)
            return
        first = max(0, min(self.selected - rows // 2, len(self.visible) - rows))
        for row in range(rows):
            i = first + row
            if i >= len(self.visible):
                break
            tip = self.visible[i]
            chosen = i == self.selected
            attr = curses.A_REVERSE if chosen else ATTRS[render.PLAIN]
            marker = "▸" if tip.path == self.today else " "
            text = f"{marker} {tip.title}".ljust(width - 1)
            put(self.screen, top + row, left, text, attr, left + width)

    def draw_reader(self, top, left, rows, width):
        lines = self.rendered(width - 2)
        self.scroll = max(0, min(self.scroll, max(0, len(lines) - rows)))
        for row in range(rows):
            i = self.scroll + row
            if i >= len(lines):
                break
            x = left + 1
            for text, style in lines[i]:
                x = put(self.screen, top + row, x, text, ATTRS[style], left + width)

    def draw_status(self, row, cols, split):
        if self.message:
            text = " " + self.message
        elif self.filter:
            text = f" filter: {self.filter}   (esc clears)"
        else:
            if split:
                hint = ""
            elif self.focus_reader:
                hint = "esc back  "
            else:
                hint = "enter open  "
            move = "scroll" if self.focus_reader else "move"
            text = f" j/k {move}  {hint}t today  / filter  n new  ? help  q quit"
        put(self.screen, row, 0, text.ljust(cols), ATTRS[render.DIM], cols)

    # ---- input ----------------------------------------------------------

    def prompt(self, label):
        """Read a line at the status bar."""
        rows, cols = self.screen.getmaxyx()
        curses.echo()
        curses.curs_set(1)
        put(self.screen, rows - 1, 0, label.ljust(cols), ATTRS[render.PLAIN], cols)
        self.screen.move(rows - 1, len(label))
        try:
            raw = self.screen.getstr(rows - 1, len(label), 60)
        except curses.error:
            raw = b""
        finally:
            curses.noecho()
            curses.curs_set(0)
        return raw.decode("utf-8", "replace").strip()

    def show_help(self):
        rows, cols = self.screen.getmaxyx()
        self.screen.erase()
        put(self.screen, 0, 1, "keys", ATTRS[render.TITLE], cols)
        for i, (key, what) in enumerate(HELP):
            if i + 2 >= rows:
                break
            put(self.screen, i + 2, 2, key.ljust(14), ATTRS[render.CODE], cols)
            put(self.screen, i + 2, 18, what, ATTRS[render.PLAIN], cols)
        put(self.screen, rows - 1, 1, "any key to return", ATTRS[render.DIM], cols)
        self.screen.refresh()
        self.screen.getch()

    def edit(self, path):
        """Suspend curses and hand the terminal to $EDITOR."""
        editor = os.environ.get("EDITOR")
        if not editor:
            self.message = "set $EDITOR to edit tips here"
            return
        curses.endwin()
        os.system(f'{editor} "{path}"')  # noqa: S605 - user's own $EDITOR
        self.screen.clear()
        curses.doupdate()
        self.body_cache = None
        self.reload()

    def new_tip(self):
        title = self.prompt("title: ")
        if not title:
            self.message = ""
            return
        os.makedirs(self.directory, exist_ok=True)
        path = os.path.join(
            self.directory,
            f"{store.next_number(self.directory):04d}-{store.slugify(title)}.md",
        )
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(f"# {title}\ntags:\n\n")
        self.edit(path)
        if path in self.visible_paths:
            self.selected = self.visible_paths.index(path)

    def move(self, delta):
        if self.visible:
            self.selected = max(0, min(self.selected + delta, len(self.visible) - 1))
            self.scroll = 0

    def handle(self, key):
        rows, _ = self.screen.getmaxyx()
        self.message = ""

        if key in (ord("q"), ord("Q")):
            return False
        if key in (ord("j"), curses.KEY_DOWN):
            if self.focus_reader:
                self.scroll += 1
            else:
                self.move(1)
        elif key in (ord("k"), curses.KEY_UP):
            if self.focus_reader:
                self.scroll = max(0, self.scroll - 1)
            else:
                self.move(-1)
        elif key == ord("g"):
            self.selected, self.scroll = 0, 0
        elif key == ord("G"):
            self.selected, self.scroll = max(0, len(self.visible) - 1), 0
        elif key in (curses.KEY_NPAGE, ord(" ")):
            if self.focus_reader:
                self.scroll += rows - 3
            else:
                self.move(rows - 3)
        elif key in (curses.KEY_PPAGE, ord("b")):
            if self.focus_reader:
                self.scroll = max(0, self.scroll - (rows - 3))
            else:
                self.move(-(rows - 3))
        elif key in (curses.KEY_ENTER, 10, 13, ord("l"), curses.KEY_RIGHT):
            self.focus_reader = True
        elif key in (27, ord("h"), curses.KEY_LEFT):
            if self.filter and not self.focus_reader:
                self.filter = ""
                self.apply_filter()
                self.clamp()
            self.focus_reader = False
        elif key == ord("t"):
            if self.today in self.visible_paths:
                self.selected = self.visible_paths.index(self.today)
                self.scroll = 0
            else:
                self.message = "today's tip is hidden by the filter"
        elif key == ord("/"):
            self.filter = self.prompt("/")
            self.apply_filter()
            self.clamp()
        elif key == ord("n"):
            self.new_tip()
        elif key == ord("e"):
            if self.current():
                self.edit(self.current_path())
        elif key == ord("r"):
            self.body_cache = None
            self.reload()
            self.message = "reloaded"
        elif key == ord("?"):
            self.show_help()
        return True

    def run(self):
        while True:
            self.draw()
            key = self.screen.getch()
            if key == curses.KEY_RESIZE:
                self.body_cache = None
                continue
            if not self.handle(key):
                return


def start(directory, ordinal):
    def bootstrap(screen):
        curses.curs_set(0)
        screen.keypad(True)
        init_colors()
        App(screen, directory, ordinal).run()

    curses.wrapper(bootstrap)
