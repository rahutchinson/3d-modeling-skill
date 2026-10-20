// Tray: open-top box. Prints as rendered (floor on the bed), no support.
include <../params.scad>
use <../lib/profiles.scad>

part_h = outer_h;   // -D part_h=15 renders a coupon with the full floor/wall/corner set

assert(outer_w <= BED_X && outer_d <= BED_Y && part_h <= BED_Z,
       str("tray exceeds bed: ", outer_w, " x ", outer_d, " x ", part_h));
assert(wall >= 2*nozzle, "wall thinner than 2 perimeters");
assert(corner_r > wall, "corner_r must exceed wall or the inner corner goes sharp");
echo(str("tray outer: ", outer_w, " x ", outer_d, " x ", part_h,
         "   bed margin: ", BED_X - outer_w, " / ", BED_Y - outer_d));

module tray(h = outer_h) {
    difference() {
        chamfered_prism(size = [outer_w, outer_d], r = corner_r, h = h, chamfer = bottom_chamfer);
        // cavity: starts at the floor, overshoots the top by eps
        translate([0, 0, floor_t])
            linear_extrude(h - floor_t + eps)
                rounded_rect(size = [inner_w, inner_d], r = corner_r - wall);
    }
}

tray(h = part_h);
