# Test-First Printing — Coupons & Gauges

Never commit a multi-hour print to an unverified fit. Two instruments:

## Coupon

A short version of the *real part* that still carries **every
functional feature** (e.g. an 80 mm-tall bin that keeps the bottom
band, stack pocket, honeycomb, grip band, rim lip, handle and its
bridge). Implemented as a `-D` height override on the real source, not
a separate model — so the coupon can't drift from the part.

- Print **two** of anything that mates with itself (stacking) so the
  fit can actually be tested.
- Makefile target `coupon:` with `COUPON_H ?= 80` style override.
- Alternative coupon cut when a height override doesn't isolate the
  feature: `intersection()` of the *real part* with a small box around
  the critical joint — same code, same params, minutes to print.
  [community]

## Gauge sweep

For a single unknown dimension (a clearance, a slot width), render a
plate of small pieces sweeping candidate values (e.g. `GAUGE_SLOPS ?=
0.4 0.6 0.8 1.0` on a 30 mm tube) and pick the winner by feel:
full-depth drop under its own weight, minimal side play.

- One variable per sweep. Label each piece with its value in relief.
- **No support anywhere near the tested surfaces** — residue falsifies
  the result. [measured]
- Anything that changes the surface (support, seam position, first-layer
  squish) confounds the measurement; reprint clean before concluding a
  value is wrong.

## Recording results

A test print that isn't recorded is wasted filament. After the user reports
results, write the finding into `printer.md` → lab notebook, with part,
date, and verdict, and update the corresponding param + comment in the
project's params.scad.
