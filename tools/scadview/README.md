# scadview — live OpenSCAD viewer

A single-file Python server (stdlib only) plus a three.js page. It renders
any target of the project with the system `openscad`, serves the STL to the
browser, and re-renders when a `.scad` file is saved. Sliders for whitelisted
parameters, a "derived values" panel that probes `params.scad` without
evaluating geometry, deep links per part, and a draft/fine quality tier.

```
cd my-project            # must contain scadview.json
python3 ~/.claude/skills/3d-modeling/tools/scadview/scadview.py
# scadview  http://localhost:8765   (4 targets from scadview.json)
# phone     http://myhost:8765      (or http://192.168.1.20:8765)
```

The `template/` Makefile wraps this as `make view`.

## scadview.json

```json
{
  "port": 8765,
  "params_file": "params.scad",
  "targets": [
    {"name": "tray",  "file": "parts/tray.scad"},
    {"name": "lid",   "file": "parts/lid.scad"},
    {"name": "gauge", "file": "parts/gauge.scad", "defines": ["lid_clear=0.4"]},
    {"name": "assembly", "file": "parts/assembly.scad", "slow": "~20 s"}
  ],
  "params": [
    {"name": "lid_clear", "min": 0.1, "max": 1.0, "step": 0.05,
     "tag": "UNVERIFIED", "note": "lid vs tray, per side; the gauge decides"},
    {"name": "wall", "min": 0.8, "max": 3.2, "step": 0.4}
  ],
  "probe": ["outer_w", "outer_d", "outer_h", "lid_inner_w"]
}
```

| key | meaning |
|-----|---------|
| `port` | default port; `--port` overrides |
| `params_file` | the single-source-of-truth file the probe includes (default `params.scad`) |
| `targets[].name` | shows in the Parts list and in deep links (`/#tray`) |
| `targets[].file` | path relative to the project root |
| `targets[].defines` | extra `-D` flags, e.g. `PART="lid"` or a gauge value |
| `targets[].slow` | `"~20 s"` or `true`: never auto-render, show a button |
| `params[]` | sliders; `min`/`max`/`step` required, `default` read from `params_file` if omitted, `tag` is `UNVERIFIED` / `PLACEHOLDER` / `""`, `note` is the caption |
| `probe[]` | variables from `params_file` shown in the derived-values panel with their delta from the defaults |

Edits to `scadview.json` are picked up without a restart (reload the page).

## Why it is built this way

- **Only whitelisted params are ever passed to `-D`**, and every value is
  coerced to a float, so an arbitrary LAN request can inject a number at
  most, never a flag.
- **Slider defaults come from `params.scad`**, not from the config. If you
  do write a `default` and the file disagrees, the server warns and the
  file wins.
- **The probe is the real answer to "what did this slider do".** Most
  clearance changes are sub-millimetre and invisible in 3D; the numbers
  move exactly.
- **Cache key = source signature + (params, quality)**, kept separate so a
  save purges only prior-source renders and revisiting a slider value hits
  the cache.
- **The last good mesh stays on screen, dimmed,** when a render fails; the
  error text goes in the bar. The canvas is never blanked.
- **Deep links**: `http://localhost:8765/#lid` opens straight onto that
  part. Share a link into the viewer instead of a screenshot.

## API

| path | returns |
|------|---------|
| `/api/targets` | `[{"name","slow"}]` |
| `/api/params` | the slider definitions with resolved defaults |
| `/api/render?t=NAME&q=draft|fine&p=k=v…` | `{ok, ms, echo[], error, key}` |
| `/api/stl?t=NAME&q=…&p=…` | binary STL (409 with the error text on failure) |
| `/api/probe?p=k=v…` | `{ok, values{}}` or `{ok:false, error}` |
| `/api/events` | server-sent `change` events when any `.scad` changes |

## Notes

- Binds `0.0.0.0` by default so you can orbit a part on your phone; pass
  `--host 127.0.0.1` to keep it local.
- `web/vendor/` holds three.js 0.160 (MIT). If a file goes missing it is
  fetched from jsDelivr on startup; otherwise no network is needed.
- OpenSCAD 2021.01 ignores `-D '$preview=true'` for `$fa`/`$fs` ternaries,
  so the draft tier sets `$fa`/`$fs` directly.
- Renders go to `.scadview-cache/` in the project; gitignore it.
