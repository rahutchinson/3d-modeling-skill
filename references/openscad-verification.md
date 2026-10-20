# OpenSCAD Verification & Performance

How to check a model before printing it, and how to keep renders fast.
Distilled 2026-08 research pass; [community, consensus] unless tagged.

## Preview (F5) vs render (F6) — why preview lies

- **F5 / OpenCSG**: GPU image-space trick — no real mesh is built.
  Fast, but happily displays non-manifold geometry, and coincident
  faces z-fight (flicker).
- **F6 / CGAL or Manifold**: builds the true mesh; this is where
  coplanar faces, zero-thickness walls, and bad polyhedra actually
  fail. **A model isn't verified until F6 (or CLI render) succeeds.**
- Preview flicker on a face is a symptom: some boolean has coincident
  surfaces → add the `eps` overshoot (see openscad-geometry.md).

## Non-manifold errors

A valid solid is a 2-manifold: every edge shared by exactly two faces.
The usual causes, all fixed by `eps` overlaps:
- coplanar faces in a difference/union;
- solids touching along an edge or at a point;
- hand-built `polyhedron()` with flipped face winding.

## Guard rails in code

```openscad
assert(bin_w <= BED_X && bin_d <= BED_Y,
       str("part exceeds bed: ", bin_w, "x", bin_d));
assert(wall >= 2*nozzle_d, "wall thinner than 2 perimeters");
echo(str("outer size: ", bin_w, " x ", bin_d, " x ", tier_h));
```

`assert()` halts the render with a message — put fit-the-bed and
min-wall checks in every part file. `echo()` computed dimensions so
the console doubles as a dimension audit. Perfect fit for the
params.scad-driven workflow.

## Inspection techniques

- Debug modifiers: `#` shows a subtree transparent-pink (inspect a
  cutter in place), `%` renders reference geometry excluded from CSG
  (keep-out zones, the freezer interior), `!` renders ONLY that subtree
  (isolate a sub-part), `*` disables a subtree.
- Cross-sections: `projection(cut=true) translate([0,0,-z]) part();`
  gives a 2D slice at height z — inspect wall thickness and clearance
  gaps. Or difference away a quadrant with a "cutaway box" module for
  a 3D view of internals.
- After export, slicers (Prusa/Orca/Bambu) auto-repair small mesh
  defects — but always eyeball the sliced preview layer-by-layer:
  confirm perimeters are continuous and thin walls didn't vanish.
  [community; matches measured practice]

## Render performance

- The classic bottlenecks: `minkowski()` on 3D solids, a global high
  `$fn`, and deep interleaved CSG trees.
- **Manifold backend** (`openscad --backend=manifold`, or Preferences →
  Features): 10–100× faster than CGAL — multi-threaded, BVH-indexed.
  It changes old advice like "never minkowski" to "minkowski is
  affordable, though rarely optimal". [community, consensus]
  **Check `openscad --version` before assuming any of this.** The
  author's machine ran 2021.01 (checked 2026-08-03), which predates
  Manifold entirely — no `--backend` flag, and no 2023+ language
  features. Upgrading to a current release/nightly is the single biggest
  render-speed win available; until then, the legacy CGAL advice (avoid
  minkowski, keep $fn modest) fully applies, and `assert()`/Customizer
  syntax are the only "new" features safe to assume. [measured]
- `render(convexity=n)` around a heavy subtree caches it as a mesh —
  duplicated/translated instances reuse the cache instead of
  re-evaluating the CSG.
- `if ($preview)` low-poly stand-ins (plain cylinder instead of a
  threaded rod) keep the GUI interactive; the real geometry only runs
  at F6/export.

## Boolean interference checks — two traps [measured, 2026-09-14]

Checking "does part A clear part B" by rendering `intersection(){A; B;}`
and expecting an empty result is the right technique, but it has two
failure modes that both look like a verdict:

1. **An empty render writes NO output file.** `openscad -o x.stl` on an
   empty top-level object prints `Current top level object is empty.` and
   leaves any *previous* `x.stl` untouched — so a script that judges by
   `[ -s x.stl ]` reports the stale file as a collision. `rm -f` the output
   before every run, or grep the log for the "empty" line. (Rainwater v3:
   a passing test was reported as a 55 kB collision, byte-identical to the
   prior run — the identical size was the tell.)
2. **An empty intersection is also what you get when the parts are nowhere
   near each other.** Run a POSITIVE CONTROL: shift one part by more than
   the clearance and confirm the intersection becomes non-empty. Without
   it, a placement bug in the test rig reads as a pass. (Same session:
   the duct was 76 mm from the sockets and "passed" twice.)

Cheap corollary: print the overlap's bounding box when it is non-empty —
the location says whether it is a design collision or a rig transform
error (the keel sitting at y = 17–28 mm said "duct not rotated", not "duct
too big").

## Through-hole ray test [measured, 2026-10, magtag-monitor-mount]

A hole cutter sized to "the plate it goes through" silently goes blind
when other geometry (a gusset, rib, or boss) is later unioned behind it.
This shipped in v1 of the MagTag mount and was only found on the printed
part. Two habits prevent it:
- **Screw cutters include the head and screwdriver path.** Extend the cutter
  well past the part, then clip it with an `intersection()` wherever it must
  not cut, instead of sizing it to one plate.
- **Ray test**: `intersection() { part(); <thin rods along each hole axis> }`
  must render empty ("top level object is empty"). Run the same test on the
  old geometry as a control, to prove the test actually catches the bug.

## Zero-thickness hits [measured, 2026-10, cabinet-lock]

An interference check that reports a hit whose bounding box is flat
(e.g. `z 11.99..12.00`) is not noise. Two causes, both worth fixing:
- **The `eps` union overlap leaking into a mating part.** A shoulder
  started at `hub_z1 - eps` overlapped a stator tooth whose top was at
  exactly `hub_z1`. Mating features should stop a real clearance short
  (`- stop_clr`), not at the shared plane.
- **A true zero-clearance contact.** A pinion face at `z = 4` sat flush
  against the underside of the mating rotor's hub, so the parts would
  have rubbed. Fix it with geometry (here, a 0.5 mm thinner pinion).

Always print the overlap's bbox before deciding which it is.

## Assembly-path check: can it actually go together? [measured, 2026-10, cabinet-lock]

Collision checks prove the parts don't overlap once they're in place.
They say nothing about whether the parts can get there. The cabinet-lock
rotor passed 34 checks and still couldn't be assembled. Its hub sat under
the stator's lip, and its finger was wider than the lip's hole.

For every part that's held captive (behind a lip, a shoulder, or a
snap), write down the insertion path before printing:
- which direction it goes in
- what passes through what
- what has to flex, and by how much

If no path exists, there are three ways out:
- **Print in place.** The gaps must be at least the in-place gap, and
  every downward face over the other part must be 45°. Assert both.
- **Split a part.**
- **Add a keyed entry slot.**

Two related lessons:
- **Re-check controls after adding asserts.** A new guard can block a
  control that works by changing a parameter (e.g. `mesh_clear=-0.8`),
  so the control errors instead of hitting. Make controls move a placed
  part (e.g. `latch_dx`) rather than change a design parameter.
- **Check for fused parts.** A print-in-place STL with N parts must
  report `Volumes: N+1` from OpenSCAD's render. One fewer means two
  parts are fused.
