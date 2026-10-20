# OpenSCAD Conventions & Code Organization

Modeled on the author's freezer-organizer project plus distilled community practice
(2026-08 research pass). Tags: [measured] = the author's prints/projects,
[community] = distilled external research, [rule of thumb] = general
knowledge awaiting local confirmation.

## Project layout

```
project/
├── params.scad     # SINGLE source of truth for every dimension
├── parts/          # one printable part per file
├── lib/            # shared modules (profiles.scad, joints.scad, …)
├── stl/            # rendered output (gitignored ok)
├── viz/            # optional HTML visualization of the assembly
├── Makefile        # every render target, incl. tests/coupons/gauges
└── README.md       # design rationale + version history (v3 → v4 → v5)
```

This matches the community-standard split of config / lib / parts /
assembly. [measured + community]

## params.scad rules

- Units: **millimetres**, always.
- Every real-world measurement lives in params.scad — "measure once,
  edit this file, re-render all parts."
- Group with Customizer sections: `/* [Freezer interior — MEASURE THESE] */`.
  Full Customizer syntax: `// [min:step:max]` → slider,
  `// [val1:Label 1, val2:Label 2]` → dropdown, `/* [Hidden] */` →
  suppress derived/internal values from the GUI. [community]
- Annotate provenance inline: `// MEASURED: 30 in` vs
  `// ⚠ STILL PLACEHOLDER — confirm`. Placeholders are loud, never silent.
- Printer envelope constants (BED_X/Y/Z) live in params.scad; parts
  should `assert()` their fit against them (see verification file).
- Comments explain *why* a value was chosen, not just what it is.
- Load params with `include <params.scad>` (imports variables); load
  libraries with `use <lib.scad>` (imports modules/functions ONLY — a
  `use` of a config file leaves its variables undefined, and `include`
  of a library file executes any top-level demo geometry in it).
  [community, consensus]

## Standard file header

Adaptive curve resolution + shared epsilon, at the top of params.scad:

```openscad
$fa = $preview ? 12 : 2;     // coarse preview, fine render
$fs = $preview ? 2.0 : 0.2;
eps = 0.01;                  // boolean-overlap fudge (see geometry file)
```

Never set a global `$fn` — it over-facets small holes and under-facets
large radii. Reserve `$fn` for exact N-gons (`$fn=6` hex socket) and
per-object overrides. [community, consensus]

## Module & parameter design

- Call modules with **named arguments** (`bin(cols=2, rows=1)`) —
  positional calls break silently when a signature gains a parameter.
  [community, consensus]
- Group related dimensions into vectors (`size=[w,d,h]`) for deep call
  stacks; keep top-level params scalar so the Customizer can see them.
  [community]
- Default origin convention: **Z=0 on the print bed**, XY centered for
  symmetric parts. Pick one and keep it project-wide. [community]
- `children()` builds layout operators — a module that positions
  arbitrary geometry it's handed (grid spreads, shells, cutter masks):

  ```openscad
  module grid_spread(count=[3,2], spacing=[20,15]) {
      for (x=[0:count.x-1], y=[0:count.y-1])
          translate([x*spacing.x, y*spacing.y, 0]) children();
  }
  ```
  Decouples layout logic from part geometry. [community, consensus]
- Library files can end with a self-test guard so opening them directly
  shows a demo render without leaking geometry into importers:
  `if ($preview && $parent_modules == 0) demo_part();` [community]
- Two schools on positioning: vanilla explicit `translate()` math
  (no deps, transparent) vs BOSL2 attachables (`anchor=`/`attach(TOP)`,
  survives dimension changes without coordinate rework). The author's projects
  are vanilla so far; consider BOSL2 for assembly-heavy designs.
  [community — both contested-by-preference, neither wrong]

## Parametric patterns

- **One source, many sizes**: a single part file takes `-D` overrides
  (e.g. `-D cols=2 -D rows=1`) and the Makefile enumerates the family.
  [measured]
- Variant heights/tests via `-D` too: `-D tier_h=$(COUPON_H)` for a
  short coupon, `-D 'render_tier="top"'` for variants. [measured]
- A `PART="name"` selector variable + `if/else` at file bottom is the
  community equivalent for multi-part files driven by
  `-D 'PART="lid"'`. [community]
- Shared geometry (joint profiles, stack interfaces) goes in `lib/`,
  included by every part that mates with it — mating parts must derive
  both sides from the same profile module. [measured]
- Pair every hardware/mating feature as **solid + cutter modules**
  (`motor_solid()` / `motor_cutter(clearance)`): the cutter carries the
  clearances and screw paths, so a dimension change updates every
  mounting hole in every mating part. [community, consensus — see
  openscad-geometry.md]

## Makefile rules

- Pattern rule renders `parts/%.scad → stl/%.stl`, depending on
  params.scad and lib files so edits re-render dependents. [measured]
- Better: use OpenSCAD depfiles so make tracks each part's actual
  includes automatically: `$(OPENSCAD) -M -d stl/$*.d -o $@ $<` plus
  `-include $(wildcard stl/*.d)`. [community]
- Named targets for every part, plus `test`, `coupon`, and `gauge`
  targets (see test-first.md).
- Print-critical warnings live as Makefile comments next to the target
  (e.g. "PRINT WITHOUT SUPPORT — residue in the 2 mm pocket reads as
  too tight"). [measured]
- CI option: headless render on push (GitHub Actions + `openscad -o`),
  export PNGs via `--camera` and diff against golden images with
  ImageMagick `compare` to catch geometric regressions. [community]

## Libraries worth reaching for (2024–2026 state)

- **BOSL2** — de facto standard: attachables, edge rounding/chamfer
  masks, `threading.scad`, VNF engine. Cost: big parse footprint,
  its own idiom. [community, consensus]
- **Round-Anything** — `polyRound()`: per-corner radii on 2D polygons,
  fast. [community]
- **NopSCADlib** — printer/hardware components (motors, bearings,
  fasteners) + BOM export. [community]
- **dotSCAD** — generative/math (bezier, voronoi, noise). [community]
- **threadlib** or BOSL2 threading for threads.
- **Avoid**: MCAD (unmaintained, deprecated syntax), BOSL1, Dan
  Kirshner threads.scad (slow CSG threads) — all superseded.
  [community, consensus]

## README rules

- Records design *history with reasons*, not just current state: what
  v3 did, why v4 replaced it, why v5 replaced that. Rejected approaches
  and why are kept — they prevent re-litigating old decisions. [measured]
- ASCII top-view diagrams for layouts; tables for the size family
  (cells / outer size / capacity / mass / loaded weight). [measured]
