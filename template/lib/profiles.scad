// Shared 2D outlines and prisms. Every module takes its dimensions as
// named arguments — nothing in here reads params.scad, because a `use`d
// file's own includes do NOT see the caller's -D overrides. The caller
// (a part file) includes params.scad and passes the numbers in.

eps = 0.01;

// Rounded rectangle, centred. The double offset rounds convex corners.
module rounded_rect(size = [10, 10], r = 1) {
    rr = max(r, 0);
    offset(r = rr) offset(delta = -rr) square(size, center = true);
}

// Rounded prism, z = 0 on the bed, with a 45° chamfer on the bed edge
// (self-supporting, unlike a downward fillet, and it eats elephant foot).
module chamfered_prism(size = [10, 10], r = 1, h = 10, chamfer = 0.8) {
    c = min(chamfer, h / 2);
    hull() {
        linear_extrude(eps) rounded_rect(size = size - [2*c, 2*c], r = r - c);
        translate([0, 0, c]) linear_extrude(h - c) rounded_rect(size = size, r = r);
    }
}

// Self-test: opening this file directly shows a demo; importers see nothing.
if ($preview && $parent_modules == 0) chamfered_prism(size = [40, 25], r = 5, h = 12);
