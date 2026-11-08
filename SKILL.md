---
name: 3d-modeling
description: >
  3D modeling / 3D printing skill for functional parametric parts in OpenSCAD,
  printed on an FDM machine. Use whenever working on OpenSCAD designs,
  parametric models, 3D-printable parts, STL generation, print
  tolerances/clearances, coupons/gauges, or the scadview live viewer.
  Triggers: "openscad", ".scad", "3d print", "STL", "bin", "bracket",
  "clearance", "tolerance", "coupon", "gauge print", "design a part",
  "scadview", "make view".
---

# 3D Modeling (OpenSCAD, FDM printing)

The user designs functional, parametric, 3D-printable parts in OpenSCAD and
prints them on an FDM printer (see `references/printer.md` for which one).
This skill encodes conventions, measured printer data, and a design
language. **Empirical data from the user's own prints outranks general
rules of thumb — check `references/printer.md` before quoting a generic
clearance number.**

## References — read the ones relevant to the task

- `references/printer.md` — printer envelope, materials, and the **lab
  notebook of measured values** (clearances, bridging results). The
  ground truth. Update it whenever a print result confirms or refutes a
  number.
- `references/openscad.md` — project scaffold (params.scad / Makefile /
  parts/ / lib/), coding conventions, module design, libraries
  (BOSL2 etc.), parametric patterns.
- `references/openscad-geometry.md` — CSG strategy (2D-first, epsilon
  overshoot, cutter modules) and fillet/chamfer technique by edge type.
- `references/openscad-verification.md` — preview-vs-render, manifold
  errors, assert/echo guard rails, debug modifiers, cross-sections,
  interference/ray/assembly-path checks, render performance.
- `references/design-for-printing.md` — orientation, bridging, walls,
  joints, clearances: the physics of what prints well on this machine.
- `references/design-language.md` — the user's recurring design motifs
  (modular cell grids, flat-rim stacking, parametric families). Start
  new designs from this vocabulary, not generic defaults.
- `references/test-first.md` — the coupon/gauge methodology: never
  commit a multi-hour print to an unverified fit.
- `tools/scadview/README.md` — the live viewer: config, deep links, API.
- `tools/scadserver/README.md` — the render server: `OPENSCAD=rscad make`
  sends every openscad call to another machine and writes the outputs back.
- `tools/printlog/README.md` — the shared print history: what has been
  printed, failed, or never printed, across every project and machine.
- `template/` — a starter project (params.scad, Makefile, parts/, lib/,
  scadview.json) that already follows every convention above.

## Core workflow for a new part or project

1. Read `design-language.md` and `printer.md` first.
2. Scaffold per `openscad.md` — copy `template/` as the starting point.
   params.scad is the single source of truth; every real-world
   measurement lives there, annotated MEASURED / PLACEHOLDER.
3. Any fit, joint, or clearance that matters → design a coupon or gauge
   sweep per `test-first.md` **before** the full part.
4. Verify per `openscad-verification.md`: a part isn't done until a CLI
   render succeeds, asserts pass, and (for mating parts) interference
   checks run with a positive control.
5. After the user reports print results, record them in `printer.md`
   (measured section) — that's how this skill gets smarter — **and** in
   the print history with `printlog log` (see below).

## Where renders run

If `rscad` is on PATH (see `tools/scadserver/`), put every openscad call
through it: `OPENSCAD=rscad make`, `OPENSCAD=rscad ./tools/check.sh`,
`OPENSCAD=rscad make view`. It ships the project to the render server
and writes the outputs back, so this machine never runs OpenSCAD. The
server's default engine is a current nightly with the Manifold backend
(renders that take CGAL 30+ s finish in well under a second). Pass
`--rscad-engine=2021` (or `RSCAD_ENGINE=2021`) when the legacy CGAL
summary is needed, e.g. the `Volumes:` count for a fused-parts check.
If the server is down, rscad runs a local openscad and says so.

## Print history

If `printlog` is on PATH (see `tools/printlog/`), it is the shared record of
what has actually been printed. It is one server, so every machine and
session sees the same history.

- **Before suggesting a print, or when picking up a project**, run
  `printlog status` in it. That shows which parts were never printed,
  which were printed but have changed since (`changed`), and which failed.
  Don't tell the user to print something they already printed unless it
  is `changed` or `failed`.
- **Prints run on a watched printer (the K1 SE, the A1 mini) log
  themselves.** A start is logged as `printing`, and the end becomes
  `printed` or `failed`. So when the user reports a result, look for that
  entry first (`printlog list`, or `printlog printers` for what's running)
  and add their verdict with `printlog edit <id> --verdict "..."` instead
  of logging a second one. If an auto entry landed under `unmatched` or
  the wrong part, move it with `--set-project/--part`. Name sliced files
  after the part (`<part>.3mf`, `<part>_PETG.gcode`) so the match works.
- **For anything the printers didn't see** (a print from elsewhere, a plan,
  an old print), log it with the part names from `stl/`:
  `printlog log <part>... --status printed|failed|printing|planned`.
  Add `--verdict "<their words>"`, `--material`, `--notes`, and
  `--date YYYY-MM-DD` if it wasn't today. For a gauge, log the variant
  they kept as printed and add `--param` for the value. A result that
  teaches something also goes in `printer.md`; the two complement each
  other.
- **"What have I printed?" / "what's left?"**: `printlog todo --all`,
  `printlog list --all`, or the history page at the server's `/`.
- Correct a wrong entry with `printlog edit <id>` instead of logging a
  second one.

## Showing the user a part: viewer links, not renders

Every project runs `tools/scadview` (`make view` in the template). It
re-renders from the live `.scad` on every request, has sliders for the
whitelisted params, and shows derived values via a probe of params.scad.

- After changing a part, make sure the viewer is running (background
  `make view`) and hand over a **deep link**:
  `http://localhost:<port>/#<target>`. Target names come from
  `/api/targets`; the port is in the project's `scadview.json`.
- Do **not** render PNGs for the user. A PNG is one frozen camera angle
  chosen by you; a link lets them orbit, zoom, and move the sliders, and
  it stays current. Fall back to an image only when the viewer genuinely
  cannot run — and say that is why. Never send both.
- When adding a part, add its target to `scadview.json`; when adding a
  tunable dimension, add it to the `params` list so it gets a slider.

## Inbox distillation (on demand only)

`inbox/` is where the user dumps raw research: reddit threads, articles,
photos of failed prints, loose notes. Do **not** read it during normal
design work. When the user asks to "distill the inbox" (or similar):

1. Read everything in `inbox/`.
2. Extract durable, actionable rules; discard anecdotes that don't
   generalize to the user's printer / materials / functional-parts context.
3. Merge each rule into the correct reference file. Mark provenance:
   `[measured]` (the user's prints), `[community]` (external), `[rule of
   thumb]` (general FDM knowledge). On conflict, measured wins.
4. Ask before deleting the processed inbox files; default is to delete.
