# Design for Printing (FDM, 0.4 mm nozzle)

Rules for geometry that prints well. Provenance tags: [measured] =
the user's own prints (see printer.md lab notebook), [community] = distilled
external research, [rule of thumb] = general FDM knowledge awaiting
local confirmation.

## Orientation comes first

- Pick the print orientation **while designing**, not after. Strength,
  surface quality, and support needs all follow from it.
- Perforated/honeycomb faces print flat on the bed, never upright —
  upright turns every hole into a horizontal bridge. [measured]
- Layer lines are the weak direction: don't put tensile or snap loads
  across layers. [rule of thumb]
- If a part can't print in one good orientation, split it into panels
  that each print flat and join them — but count the cost (parts,
  filament, assembly) and re-check whether the constraint is real
  (freezer v3 panelized for a height limit that no longer existed).
  [measured]

## Bridges, overhangs, support

- Short bridges (≲ 20–25 mm) over a handle or slot are fine; long or
  repeated perimeter bridges are not. [measured: v4 honeycomb walls]
- Never put support inside a small pocket whose fit matters — residue
  can't be cleaned out and falsifies the fit test. Design the pocket to
  print support-free or reorient. [measured]
- ~45° self-supporting overhang; chamfer instead of fillet on the
  underside of features — a 45° chamfer holds a constant printable
  angle, while a downward fillet starts tangent-to-horizontal and
  extrudes into mid-air. [community, consensus]

## Fillets vs chamfers (when — the how lives in openscad-geometry.md)

- **Fillet internal corners under load**: a sharp 90° internal corner
  concentrates stress and initiates layer cleavage; a radius of even
  1× nozzle diameter (0.4–1.0 mm) spreads the load across perimeters.
  [community, consensus]
- **Chamfer bottom (bed-contact) edges**, 0.5–1.5 mm at 45°: absorbs
  elephant-foot squish so outer dimensions stay accurate, and unlike a
  fillet it stays self-supporting. [community, consensus]
- **Chamfer overhung edges** for the same self-supporting reason.
- **Skip rounding** on cosmetic top edges and radii < 0.4 mm — pure
  render/STL bloat with no benefit. [community]

## Walls & stiffness

- Tune stiffness in order: wall thickness → infill/lightening gap →
  solid border width around lightened faces. [measured: freezer bins]
- Walls in whole perimeter multiples of the 0.4 mm nozzle
  (0.8 / 1.2 / 1.6 / 2.0). [rule of thumb]

## Clearances & fits

- **Never trust a clearance you haven't printed.** Gauge-sweep it
  (see test-first.md). Current stacking-fit data lives in printer.md.
- Sliding/stacking fit estimate pending gauge results: 0.6–0.8 mm on
  large (>80 mm) mating faces. [measured, provisional]
- Parts that neighbor each other in an enclosure need a deliberate gap
  parameter so they don't bind (freezer uses `bin_gap = 6`,
  plus per-axis slack params). [measured]
- Community starting points for small-feature fits, expressed as
  multiples of nozzle diameter so they survive a nozzle swap:
  press ≈ 0.10 mm, snug ≈ 0.375×nozzle (~0.15 mm), sliding ≈
  0.875×nozzle (~0.35 mm). These are for pegs/bores — large
  perimeter-length mating faces (rims, stacking pockets) need much
  more; gauge them (printer.md has the measured freezer data).
  [community — unverified locally, gauge before trusting]

## Part sizing

- State bed margin explicitly for the largest family member; don't
  design to the last millimetre of the 220 × 220 × 250 envelope.
- Estimate print time and filament mass in the design table — an
  ~20 h part changes how much validation you do first.
