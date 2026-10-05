# Genesis Leaf
### Legend of Legaia · Language Pack Suite — Public Beta

Genesis Leaf is a desktop editor for translating **Legend of Legaia**. You open a
language pack exported from your own copy of the game, write your translation
next to each line, and Genesis Leaf checks it against what the retail game can
really display — how many bytes it may take, how wide the text box is, which
colour and name codes are valid — while showing a pixel-accurate preview in the
game's own font. The whole program is styled after the game's menus.

You need **your own copy of the game**. Genesis Leaf contains no game script and
never modifies your disc.

---

## What it does

- **Live checks.** Every row shows its encoded size against its budget, and
  whether the text fits, grows into the disc's shared free space, or won't fit.
- **Real-font preview.** Dialogue boxes are drawn with the retail glyphs, ink
  colours, name splices and icons, with a red line where the box ends.
- **Made for long jobs.** Navigator and filters, search, undo/redo, a glossary,
  find-and-fix tools, duplicate and clone handling, pack comparison and notes.
- **Safe saves.** The pack is written in exactly the exporter's format and the
  previous file is kept as `.bak`.
- **Test builds.** Hand the pack to the patcher and get a playable disc image
  (and a PPF patch) without leaving the program.
- **Two looks.** The game-menu look is on by default; *Options → Legaia menu UI*
  switches to a plain classic window style (Default or Midnight palette).

## What you need

- Python 3.8 or newer with Tkinter (included in the Windows installer)
- [PyYAML](https://pypi.org/project/PyYAML/) — required
- [Pillow](https://pypi.org/project/Pillow/) — recommended (the game-menu look
  and faster previews)

```
pip install pyyaml pillow
```

## Run

```
python GenesisLeaf.py                      # choose a pack in a file dialog
python GenesisLeaf.py path/to/pack.yaml    # open a pack directly
```

## How it works

A translation starts as a **language pack**: one YAML file holding every line of
text in the game — item names, menus, dialogue — each with a `translation:` field
that you fill in. Lines you leave empty stay in English, so a half-finished pack
is always playable. The disc has a fixed amount of room for each piece of text
(its *budget*), which is why the checks matter.

```
export from your disc  →  edit in Genesis Leaf  →  patch a copy of your disc
   (legaia-patcher)           (this program)          (legaia-patcher)
```

1. **Export** a pack from your disc with the `legaia-patcher` tool (or the
   browser patcher) from the
   [legend-of-legaia-re](https://github.com/AndrewAltimit/legend-of-legaia-re)
   project.
2. **Open** it here, translate, and watch the budget and preview as you type.
3. **Save**, then **build a test disc** from *Tools → Build test ROM*, or apply
   the pack yourself with the patcher. Your original disc is never touched; you
   get a new patched image, or a small PPF patch that is safe to share.

Never share a working pack: it contains the game's own script. Share only the
stripped, translations-only pack the patcher can produce.

The full details of exporting, the pack format, space limits and patching live in
the **legend-of-legaia-re** project — start with its
[translating guide](https://github.com/AndrewAltimit/legend-of-legaia-re/blob/main/docs/guides/translating.md).
The in-program guide (*Help → User guide*) explains the Genesis Leaf side.

## Credits

Stann0x Studio @ 2026. Built on the reverse-engineering work of
[legend-of-legaia-re](https://github.com/AndrewAltimit/legend-of-legaia-re).
Legend of Legaia is a trademark of its publisher; this is an unofficial fan
project and no affiliation is implied.

---

**© 2026 Stann0x Studio. All rights reserved.**
