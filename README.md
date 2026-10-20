# 3d-modeling — a Claude Code skill for functional OpenSCAD parts

A [Claude Code skill](https://docs.claude.com/en/docs/claude-code/skills)
for designing parametric, 3D-printable parts in OpenSCAD and getting them
to print right the first time. It grew out of real projects (freezer bins,
a rainwater stack joint, a rack faceplate, a childproof cabinet latch) and
it encodes what those prints taught, not just general FDM advice.

What's in the box:

| path | what |
|------|------|
| `SKILL.md` | the entry point Claude reads: workflow, when to read what |
| `references/openscad.md` | project scaffold, params.scad rules, module design, Makefile, libraries |
| `references/openscad-geometry.md` | CSG strategy, epsilon overshoot, cutter modules, fillet/chamfer technique by edge |
| `references/openscad-verification.md` | preview vs render, asserts, interference / ray / assembly-path checks, performance |
| `references/design-for-printing.md` | orientation, bridges, walls, clearances |
| `references/design-language.md` | recurring motifs to start new designs from |
| `references/test-first.md` | coupons and gauge sweeps before any long print |
| `references/printer.md` | printer envelope, materials, and a **lab notebook of measured values** |
| `tools/scadview/` | live viewer: orbit any part in a browser, sliders for params, re-renders on save |
| `template/` | a starter project that follows every convention above |
| `inbox/` | drop zone for raw research, distilled into the references on demand |

The core ideas:

- **params.scad is the single source of truth.** Every real-world number
  lives there, tagged MEASURED / PLACEHOLDER / UNVERIFIED. Parts assert
  they fit the bed and echo their outer dimensions.
- **Measured beats rule of thumb.** Every rule carries a provenance tag
  (`[measured]`, `[community]`, `[rule of thumb]`); the lab notebook in
  `printer.md` wins conflicts and is updated after every real print.
- **Test first.** Any fit that matters gets a coupon (a short slice of the
  real part) or a gauge sweep (one variable, several values, labelled)
  before the multi-hour print.
- **Verify in the CLI, not the preview.** Renders must succeed; mating
  parts get an interference check with a positive control, a ray test
  through every hole, and a written assembly path.
- **Show, don't screenshot.** Parts are shared as deep links into the
  running viewer so the reader can orbit and move the sliders.

## Install

Personal (all projects):

```sh
git clone https://github.com/rahutchinson/3d-modeling-skill ~/.claude/skills/3d-modeling
```

Or per project: clone into `<project>/.claude/skills/3d-modeling`. Claude
Code picks up `SKILL.md` by its `name:` and `description:` and loads the
references on demand.

Requirements: [OpenSCAD](https://openscad.org) on `PATH` (2021.01 works;
a 2023+ build with the Manifold backend renders much faster), Python 3.8+
for the viewer (stdlib only), `make`.

## Start a project

```sh
cp -r ~/.claude/skills/3d-modeling/template my-part && cd my-part
make coupon gauge     # print these first
make view             # http://localhost:8765/#tray
make                  # the real parts
```

The template is a tray with a slip-over lid. The lid clearance is the
unknown: `make gauge` renders five labelled lids at different clearances,
you print them with the tray coupon and keep the one that fits, then set
the value in `params.scad` and log it in `references/printer.md`.

## The viewer

`tools/scadview/scadview.py` is a single-file server. It reads a
`scadview.json` in the project (which parts to offer, which params get
sliders, which derived values to show), renders with the system `openscad`,
and serves a three.js page that re-renders on every `.scad` save.

See [tools/scadview/README.md](tools/scadview/README.md) for the config
format and API.

## Make it yours

Two files are personal and meant to be replaced when you fork:

- `references/printer.md` — the machine section is a Creality K1 SE with
  PETG. Put your printer and materials in, keep the lab-notebook format,
  and treat the existing entries as worked examples.
- `references/design-language.md` — the author's motifs. Prune and add.

Everything else is technique and should transfer as is. If you find a
rule that is wrong on your machine, that is exactly what the provenance
tags are for: record what you measured, and measured wins.

To grow the skill: dump raw research (threads, articles, photos of failed
prints) into `inbox/`, then tell Claude to "distill the inbox". Each item
is mined for durable rules, merged into the right reference with a
`[community]` tag, and the inbox is cleared.

## License

MIT. `tools/scadview/web/vendor/` contains three.js 0.160, also MIT.
