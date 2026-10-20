# Design Language

> These are the author's motifs, accumulated across real projects. If you
> fork this skill, prune what doesn't fit and add your own — the point of
> the file is that new designs start from *your* vocabulary, not from
> generic defaults.

Recurring motifs across projects. When starting a new design, reach for
these before inventing new vocabulary — and when a new motif shows up
in a project, add it here.

## Motifs

- **Modular cell grids**: divide the available space into a grid of
  cells; every part is a whole number of cells, so any mix of sizes
  tiles exactly. Grid dimensions chosen to (a) give squarish cells and
  (b) keep the largest useful part inside the print bed with margin.
- **Parametric families, one source file**: small/wide/deep/large are
  the same .scad with different `-D cols/rows`, never copies.
- **Flat-rim stacking**: mating interfaces kept flat and featureless on
  one side (rim) with the geometry on the other (underside pocket), so
  mixed footprints stack — protruding studs were tried and rejected
  because mixed sizes orphan them on shared boundary walls.
- **Uniform tier height**: stacked systems keep one height so tiers
  stay level regardless of footprint mix.
- **Honeycomb/perforation lightening** on large faces, with a solid
  border frame — saves filament and lets cold air (or water, or light)
  through. Print those faces flat.
- **Deliberate slack params**: `bin_gap`, `side_clear`, `depth_clear` —
  neighboring parts never rely on nominal dimensions to not bind.
- **Loud placeholders**: unverified real-world dimensions are marked
  `⚠ PLACEHOLDER` in params.scad and listed as open items in the
  README until measured.
- **Design history preserved**: rejected versions stay documented with
  the reason they lost ("panelizing solved a constraint that no longer
  existed").

## Values

- Functional over decorative; filament mass and print count are
  first-class design metrics (a whole-freezer fill is quoted as
  "18 prints / 3.3 kg").
- Cheap empirical tests over long confident prints.
- Everything re-derivable from params.scad — "measure once, edit this
  file, re-render all parts."
