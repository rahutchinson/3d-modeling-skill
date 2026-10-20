# <Project name> — one line on what this is.
#   make          -> every part (stl/)
#   make coupon   -> PRINT FIRST: 15 mm tray slice with every functional feature
#   make gauge    -> lid gauges sweeping lid_clear; print with the coupon, no support
#   make view     -> scadview at http://localhost:8765 (targets in scadview.json)
#
# Material: PETG. Everything prints as rendered; no support anywhere.

OPENSCAD ?= openscad
SCADVIEW ?= $(HOME)/.claude/skills/3d-modeling/tools/scadview/scadview.py

PARTS := tray lid
STLS  := $(PARTS:%=stl/%.stl)
COUPON_H     ?= 15
GAUGE_CLEARS ?= 0.2 0.3 0.4 0.5 0.6

all: $(STLS)

stl:
	mkdir -p $@

# -d writes a depfile so make re-renders a part when params.scad or any
# lib it includes changes, without listing dependencies by hand.
stl/%.stl: parts/%.scad | stl
	$(OPENSCAD) -d stl/$*.d -o $@ $<
-include $(wildcard stl/*.d)

coupon: parts/tray.scad | stl
	$(OPENSCAD) -D part_h=$(COUPON_H) -o stl/tray_coupon.stl $<

# One variable per sweep. Pick the winner by feel, set lid_clear in
# params.scad, flip its tag to MEASURED, and log it in the skill's printer.md.
gauge: $(foreach c,$(GAUGE_CLEARS),stl/gauge_$(c).stl)
stl/gauge_%.stl: parts/gauge.scad | stl
	$(OPENSCAD) -D lid_clear=$* -o $@ $<

view:
	OPENSCAD=$(OPENSCAD) python3 $(SCADVIEW)

clean:
	rm -rf stl

.PHONY: all coupon gauge view clean
