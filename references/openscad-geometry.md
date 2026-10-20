# OpenSCAD Geometry Technique — CSG Strategy, Fillets, Chamfers

Distilled 2026-08 research pass; all [community, consensus] unless
tagged otherwise. FDM-specific *when to fillet* rules live in
design-for-printing.md — this file is the *how*.

## CSG order of operations

- **Build in 2D, extrude once.** 2D booleans (Clipper) are 10–100×
  faster than 3D mesh booleans and extrude to watertight meshes.
  Prefer `linear_extrude(h) difference() { 2D... }` over
  `difference() { cube; cylinder }` whenever the shape is prismatic.
- **Positive body first, then grouped cuts.** Flatten the tree to two
  passes — `difference() { union(){positives} cutters... }` — instead
  of interleaving difference-inside-union-inside-difference. Shallower
  trees render faster and preview cleaner.
- **Epsilon overshoot, always.** Coincident faces in a boolean cause
  preview z-fighting and non-manifold render failures. Every cutter
  extends `eps` (0.01) past the surface it pierces:
  `translate([...,-eps]) cylinder(h = h + 2*eps)`. Every union of
  touching solids overlaps by `eps` — edge-touching or corner-touching
  solids are non-manifold by definition.
- **Negative-space modules.** Model mating hardware twice: a solid for
  visualization and a cutter that carries clearance + screw paths
  (`motor_cutter(clearance=0.2)`). Parents subtract the cutter; a
  clearance change propagates to every mating part.
- **`hull()` is a construction tool** — connecting two cylinders into a
  bracket, lofting convex transitions. Fast and clean, but convex-only:
  it can't make pockets or hollow forms directly.
- **`minkowski()` is usually a trap** under CGAL: O(N·M) face explosion
  sweeping a sphere over a polyhedron, and it grows the part by 2r in
  every direction (pre-shrink the base). Reach for 2D offset or BOSL2
  first; minkowski becomes tolerable under the Manifold backend (see
  verification file) but is still rarely the best tool.

## Fillet/chamfer technique by edge type

| Edge | Technique |
|------|-----------|
| Vertical edges (uniform r) | `offset(r=r) offset(delta=-r)` on the 2D profile, then extrude |
| Vertical edges (per-corner r) | Round-Anything `polyRound([[x,y,r],...])` |
| Top horizontal edges | BOSL2 `edge_profile(TOP) mask2d_round(r)`, or `polyRoundExtrude` |
| Bottom (bed-contact) edges | **chamfer, not fillet** — `mask2d_chamfer` / a 45° cone in the cutter |
| Internal pocket corners | inverse 2D offset: `offset(-r) offset(r)` on the pocket profile |
| Box with everything | BOSL2 `cuboid([w,d,h], rounding=r, teardrop=true)` |

- The double-offset idiom: `offset(r=+r) offset(delta=-r)` rounds
  convex corners; swap signs to round concave ones.
- BOSL2 builds rounded shapes as VNF polyhedra directly (no boolean
  cost), which is why its rounding is fast.
- `hull()` of corner cylinders is a fine dependency-free way to get a
  rounded prism.

## When rounding is waste

Fillets on cosmetic top edges or radii under ~0.4 mm (one nozzle
width) bloat the STL and render time with no functional or visible
benefit. Chamfer or leave sharp. (Strength/printability reasons TO
round are in design-for-printing.md.)
