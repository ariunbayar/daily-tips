# daily-tips

A small curses app for a personal collection of tips: one is picked as *today's
tip*, and you can browse, filter and edit the rest without leaving the terminal.

Your tips are **not** stored in this repository. They live in
`~/.local/share/daily-tips/tips`, so the app can be public while the collection
stays private.

```
 daily tips                                                                 5/5
  Jump back to the previous directory │  today's tip
  Reuse the last argument             │
▸ Find what is holding a file open    │  Find what is holding a file or port open
  Prefer git switch and git restore   │  #linux  #debugging
  Measure memory honestly             │
                                      │  When a filesystem will not unmount or a
                                      │  port is already bound, ask the kernel
                                      │  who is responsible rather than guessing.
                                      │
                                      │  │ fuser -v /mnt/data
                                      │  │ ss -lptn 'sport = :8080'
 j/k move  t today  / filter  n new  ? help  q quit
```

## Install

Requires Python 3.8+ and nothing else — standard library only.

```
git clone git@github.com:ariunbayar/daily-tips.git
ln -s "$PWD/daily-tips/bin/tips" ~/.local/bin/tips
```

Run `tips` with no arguments to open the browser.

## Keys

| key | what it does |
| --- | --- |
| `j` `k`, `↓` `↑` | move the selection, or scroll the reader |
| `g` / `G` | first / last tip |
| `enter`, `l`, `→` | open the reader (narrow terminals only) |
| `esc`, `h`, `←` | back to the list, or clear the filter |
| `space` / `b` | page through the reader |
| `t` | jump to today's tip |
| `/` | filter by title, tag or body |
| `n` | create a tip and open `$EDITOR` |
| `e` | edit the selected tip |
| `r` | reload from disk |
| `?` | key help |
| `q` | quit |

Terminals at least 88 columns wide show the list and reader side by side;
narrower ones switch between the two.

## Commands

For scripting and shell startup files, everything also works without the UI:

```
tips today                  # print today's tip and exit
tips today --date 2026-08-01
tips list
tips search memory
tips new "Reuse the last argument"
tips path                   # where tips are kept
```

Useful in `.bashrc`, since it is a one-shot print:

```
tips today
```

Options: `--dir PATH`, `--date YYYY-MM-DD`, `--no-color`, `--help`.
`NO_COLOR` is honoured, and colour is dropped automatically when piped.

## Writing tips

One file per tip, named `NNNN-slug.md`. `tips new` creates them for you:

```markdown
# Reuse the last argument
tags: shell, bash

`!$` expands to the final argument of the previous command. Prose is
soft-wrapped here and reflowed to your terminal width.

```
mkdir -p ~/deploy/releases
cd !$
```

- `**bold**` and `` `code` `` are rendered
- fenced blocks are shown verbatim, not wrapped
```

The title is the first `# ` line, `tags:` is optional, and the rest is the body.

Set `DAILY_TIPS_DIR` to keep the collection somewhere else — a synced folder, or
a private git repo of its own.

## Which tip is today's

Each tip is shown exactly once per cycle of *N* days, where *N* is the number of
tips you have. The order reshuffles every cycle and is derived from the date, so
it is stable: the same day always gives the same tip, on any machine, with no
state file. Cycle boundaries are guarded so a tip closing one cycle cannot
reopen the next.

Adding a tip changes the cycle length and therefore reshuffles future days —
today's tip stays put.

## Notes on footprint

This is meant to be left running, so it is built to stay small:

| | RSS | RssAnon |
| --- | --- | --- |
| bare `python3 -S` (the floor) | 7.2 MB | 2.0 MB |
| `tips`, 5 tips | 9.7 MB | 3.5 MB |
| `tips`, 500 tips | 10.0 MB | 3.7 MB |

- Only `os`, `sys`, `curses` and (briefly) `datetime` are imported. `argparse`,
  `pathlib`, `re`, `shutil`, `textwrap`, `random` and `subprocess` are all
  avoided — the wrapper, inline parser, shuffle and argument handling are
  hand-rolled, which is most of the gap between the floor and the app.
- The in-memory index holds only a path, title and tags per tip. Exactly one
  body — the tip on screen — is resident at a time, which is why 100× the
  content costs 0.2 MB.
- `bin/tips` runs under `python3 -S` to skip `site` processing.

Most of what remains is the interpreter itself; a compiled language would start
near 1–3 MB.

## Licence

MIT.
