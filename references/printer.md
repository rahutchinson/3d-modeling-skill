# Printer & Materials — Creality K1 SE

> This file is specific to the author's printer. If you fork this skill,
> replace the Machine and Materials sections with your own numbers and
> start your own lab notebook — but keep the format: one entry per
> empirical finding, newest first, with part, date, and verdict. The
> measured entries below are left in as worked examples; they are PETG
> on a K1 SE with a 0.4 mm nozzle and may not transfer to your setup.

## Machine

- Build volume: **220 × 220 × 250 mm**, 0.4 mm nozzle, enclosed, CoreXY.
- When sizing parts, state the margin to the bed explicitly (e.g. "2×2
  bin clears by 45 / 38 / 45 mm") — parts near the envelope are a design
  smell; leave real margin.

## Materials

- **PETG / ASA** for anything cold or load-bearing (freezer parts:
  PLA goes brittle in the cold). [measured context: freezer-organizer]
- PLA: fine for jigs, gauges, indoor fixtures. TODO: note preferred
  brands/profiles once the user supplies them.

## Lab notebook — measured values

The most valuable section of this skill. One entry per empirical
finding. Newest first. Format: value, part/coupon, date, verdict.

- **Print-in-place in PETG, 0.4 mm gaps: WORKED.** This is the
  cabinet-lock rotor, printed inside its stator, door face down. All gaps
  at rest were at least 0.4 mm:
  - radial on vertical walls
  - 0.8 mm vertical between the parallel 45° lip and shoulder faces
  - every downward face over the other part at 45°

  The only support was a tree under the finger. User verdict: "it worked".
  [measured, 2026-10-13, cabinet-lock]
- **A knob screw clamping a printed post through a door: 0.5 mm proud is
  NOT ENOUGH.** On the cabinet lock, the pinion's post stuck 0.5 mm out
  past a 20 mm door. Tightening the knob still clamped the door, and the
  pinion wouldn't turn.
  - Likely causes: the knob base is dished, or the door finish and
    thickness vary.
  - Now 1.0 mm (unverified). The proud length is also the part's axial
    float, so design clearance for it.

  [measured, 2026-10-13, cabinet-lock]
- **Slip-over clamp slack, 0.6 mm total across a 27 mm span: CONFIRMED
  GOOD.** This is a PETG C-clamp (3 mm walls) that hooks over a monitor's
  top edge. It was printed on its side with all walls vertical and no support.
  User verdict on the 15 mm coupon: "perfect". This is a good starting
  value for friction-free hook-over clamps on rigid objects. It is a third
  kind of fit, different from finger joints (0.15/side) and stacking pockets
  (0.8). [measured, 2026-09, magtag-monitor-mount]
- **Finger-joint clearance, flat-printed panels**: 0.30 mm per side is
  **too loose** — visible play at the corner on the freezer v5 1×1.
  That number was inherited from a v3 guess and never validated. Now
  0.15 mm/side (≈ 0.375 × nozzle, the community "snug" figure), which
  is *unconfirmed* — reprint before trusting.
  **Rule: interlocking joints want far less clearance than large
  perimeter-length mating faces. Don't reuse a stacking-fit number
  (0.8 mm) for a finger/tooth joint — they're two different problems.**
  [measured, 2026-08]
- **Stacking pocket printed flat = a real cantilever**: flat-printing a
  wall panel puts the pocket's lateral locating face at Z = notch_w
  (2.4 mm), so one layer starts ~4 mm out over air, anchored along its
  full length. Printed **with** support: "rough but usable" — it seats,
  but the face is textured. Upright (v4) this same feature was an easy
  radial step, so this is a cost flat printing *added*.
  **Open: whether it can be made support-free.** A 45° self-supporting
  ramp is geometrically possible but trades away pocket engagement
  (the groove must stay ≥ lip-thickness deep for its full depth, so
  ramping it shallow shortens the usable engagement) — needs a gauge
  print of both profiles before choosing. [measured, 2026-08]
- **Elephant foot no longer reaches the pocket when flat-printed**:
  upright, the pocket sat in the first 4 mm of print height, exactly
  where first-layer squish pushes material *into* the groove — a stated
  reason `pocket_slop` needed its own generous knob. Flat, that face is
  2.4 mm up and unaffected by first-layer squish, so the original
  justification for a large `pocket_slop` is **weaker in v5 than it was
  in v4**. 0.8 mm may now be more clearance than needed; worth a
  re-gauge. [inference from measured orientation change, 2026-08]
- **Stacking pocket clearance (`pocket_slop`) = 0.8 mm: CONFIRMED
  GOOD.** User verdict on the printed test: "the .8 work great."
  Supersedes the earlier confounded 0.4 mm result (those coupons had
  support in the groove, whose residue reads as "too tight" — that's
  where the never-support-a-fit-tested-pocket rule came from).
  Caveat: confirmed in the **upright** v4 orientation; v5 prints this
  face flat with support, which is a different surface. [measured, 2026-07]
- **Perforated faces print flat — CONFIRMED.** v4 freezer bins put a
  honeycomb in upright walls, which slices as a horizontal bridge over
  every hole all the way around the perimeter loop; printed rough and
  failed. v5 prints the same panels flat, turning every hole into a
  straight through-cut: **"much better"** on the 1×1, honeycomb and
  handle openings clean. The orientation rule is now measured on both
  sides of the experiment, not just the failure.
  **Rule: perforated/honeycomb faces get printed flat on the bed, not
  upright.** [measured, 2026-07 failure / 2026-08 confirmation]

## TODO (fill from real prints)

- First-layer / elephant-foot compensation that works on this bed.
- Hole diameter shrinkage (design Ø vs measured Ø) for PETG.
- Threaded-insert pocket sizes that work.
- Minimum wall count / thickness where PETG bins stop feeling flexy
  (freezer project tuning order was: `wall`, then `hex_gap`, then
  `face_border`).
