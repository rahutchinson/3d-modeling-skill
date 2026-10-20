// Lid-fit gauge: a short lid at one lid_clear value, labelled. The Makefile
// renders one per value in GAUGE_CLEARS; print the set plus `make coupon`
// and pick the one that drops on under its own weight with minimal play.
// NO SUPPORT anywhere — residue in the skirt falsifies the fit.
include <../params.scad>
use <../lib/profiles.scad>
use <lid.scad>

gauge_h = 6;

lid(clear = lid_clear, h = gauge_h, label = str(lid_clear));
