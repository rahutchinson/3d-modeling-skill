// Lid: slips over the tray. Prints as rendered — top face on the bed, so
// the chamfer lands on the lid's visible top edge. No support.
include <../params.scad>
use <../lib/profiles.scad>

assert(lid_outer_w <= BED_X && lid_outer_d <= BED_Y,
       str("lid exceeds bed: ", lid_outer_w, " x ", lid_outer_d));
echo(str("lid outer: ", lid_outer_w, " x ", lid_outer_d, " x ", lid_outer_h,
         "   clearance/side: ", lid_clear));

// Everything the gauge sweeps is an argument: a caller's -D override only
// reaches this module through its arguments, never through params.scad
// (see lib/profiles.scad for why).
module lid(clear = lid_clear, h = lid_h, label = "") {
    iw = outer_w + 2*clear;  id = outer_d + 2*clear;
    ow = iw + 2*wall;        od = id + 2*wall;
    difference() {
        chamfered_prism(size = [ow, od], r = corner_r + clear + wall,
                        h = lid_top_t + h, chamfer = bottom_chamfer);
        translate([0, 0, lid_top_t])
            linear_extrude(h + eps)
                rounded_rect(size = [iw, id], r = corner_r + clear);
        // label engraved into the bed face (prints as a recess in layer 1)
        if (label != "")
            translate([0, 0, -eps])
                linear_extrude(2*layer_h + eps)
                    mirror([1, 0, 0]) text(label, size = 5, halign = "center", valign = "center");
    }
}

lid();
