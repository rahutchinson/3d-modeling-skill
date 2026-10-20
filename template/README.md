# <Project name>

One paragraph: what it is, where it lives, what it has to fit.

## Design

- Orientation: tray floor-down, lid top-down; no support anywhere.
- The lid derives its outline from the tray's (`lib/profiles.scad`) so a
  corner-radius change moves both sides of the fit together.
- `lid_clear` is UNVERIFIED until the gauge says otherwise.

## Parts

| part | outer (mm) | print time | mass |
|------|------------|------------|------|
| tray | 83.2 × 53.2 × 31.2 | — | — |
| lid  | 87.0 × 57.0 × 9.2 | — | — |

Bed margin for the largest part: 137 / 167 mm (220 × 220 bed).

## Workflow

1. Measure, edit `params.scad`, replace every ⚠ PLACEHOLDER.
2. `make coupon gauge` → print the coupon plus the five gauges, no support.
3. Pick the gauge that drops on under its own weight with minimal play; set
   `lid_clear`, retag it MEASURED, log the result in the skill's `printer.md`.
4. `make` → print.

`make view` opens the live viewer; share parts as `http://localhost:8765/#tray`.

## Open items

- [ ] inner_w / inner_d / inner_h are placeholders
- [ ] lid_clear unverified

## History

- v1 — initial. (Keep rejected approaches here with the reason they lost.)
