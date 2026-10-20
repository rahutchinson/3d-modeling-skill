// <Project name> — one line on what this is and who/what it is for.
// Single source of truth. Units: mm. Measure once, edit this file, `make`.
//
// Frame of reference (every part): z = 0 on the print bed, XY centred.
// Provenance on every real-world number: MEASURED / PLACEHOLDER / UNVERIFIED.

$fa = $preview ? 12 : 2;     // coarse preview, fine render
$fs = $preview ? 2.0 : 0.2;
eps = 0.01;                  // boolean-overlap fudge: every cutter overshoots by this

/* [Printer — EDIT FOR YOUR MACHINE] */
BED_X = 220; BED_Y = 220; BED_Z = 250;   // ⚠ PLACEHOLDER — your build volume
nozzle  = 0.4;
layer_h = 0.2;

/* [Tray interior — MEASURE THESE] */
inner_w = 80;    // ⚠ PLACEHOLDER — the thing that has to fit inside
inner_d = 50;    // ⚠ PLACEHOLDER
inner_h = 30;    // ⚠ PLACEHOLDER
wall    = 1.6;   // 4 perimeters; tune stiffness here first
floor_t = 1.2;   // 6 layers
corner_r = 4;    // vertical-edge radius; the lid derives its own from this
bottom_chamfer = 0.8;   // 45°, absorbs elephant foot so outer dims stay honest

/* [Lid fit — UNVERIFIED, the gauge decides] */
lid_clear = 0.3;   // ⚠ UNVERIFIED per side — `make gauge` sweeps 0.2..0.6
lid_h     = 8;     // skirt height
lid_top_t = 1.2;

/* [Hidden] */
outer_w = inner_w + 2*wall;
outer_d = inner_d + 2*wall;
outer_h = inner_h + floor_t;
lid_inner_w = outer_w + 2*lid_clear;
lid_inner_d = outer_d + 2*lid_clear;
lid_outer_w = lid_inner_w + 2*wall;
lid_outer_d = lid_inner_d + 2*wall;
lid_outer_h = lid_top_t + lid_h;
