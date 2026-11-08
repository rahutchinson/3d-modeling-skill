# printlog — shared print history

What has been printed, what failed, what's queued, and what has never left
the slicer, for every project, from any machine. Two files, stdlib Python
only (SQLite for storage):

| file | runs on | what |
|------|---------|------|
| `server.py` | one always-on box (the render box is a good home) | HTTP + SQLite. History page at `/`, JSON API under `/api/`. |
| `printlog` | any machine | CLI: log prints, sync a project's `stl/` catalog, ask what's outstanding. |

## Server

```sh
./tools/printlog/install-service.sh     # systemd --user unit, enabled + started, port 8791
```

Data lives in `~/.local/share/printlog/prints.db`; back that file up and
you have the whole history. Optional `~/.config/printlog/config.json`:
`{"port": 8791, "bind": "0.0.0.0", "db": "~/.local/share/printlog/prints.db"}`.

Writes need the token in `~/.config/printlog/token`. On first start the
server copies `~/.config/openscad-server/token` if it exists, so one secret
covers both services. Reads (the page and the GET API) are open.

## Client

```sh
curl -sf http://SERVER:8791/install.sh | sh -s -- TOKEN    # ~/.local/bin/printlog
```

If the machine already has `rscad` configured, `printlog` works with no
setup at all: it uses the rscad server's host on the next port and the
rscad token.

```sh
printlog status                    # in a project: sync stl/, show each part's state
printlog todo                      # outstanding parts (this project, or --all)
printlog log pinion latch_left --material PETG --verdict "spins freely"
printlog log collar_g2 --status failed --verdict "too tight" --notes "0.2 mm gap"
printlog log stand --status planned
printlog list [--all] [--part P] [--status S]
printlog edit 12 --status printed --verdict "fits"   ;  printlog rm 12
printlog server                    # counts + synced projects
```

`--json` on `status`, `todo`, `list`, `show` and `server` gives machine-readable output.

### How parts and states work

- The **project** is the nearest dir containing `params.scad`, `Makefile`,
  `scadview.json` or `stl/`; its name is the dir name (`--project` overrides).
- A **part** is a file in the project's `stl/` (`.stl` / `.3mf`) by base
  name. Names matching `*assembly*` or a glob in `.printignore` are
  left out of the catalog. You can still log any path or bare name.
- Each print records the STL's **sha256**. Each part's state comes from
  its latest entry:

  | state | meaning |
  |-------|---------|
  | `never` | in `stl/`, no history |
  | `planned` / `printing` | latest entry says so |
  | `printed` | printed, and the STL is unchanged since |
  | `changed` | printed, but the STL has changed since — the print is of an older version |
  | `failed` | latest attempt failed |

- `status`, `todo` and `log` re-send the project's catalog, so the server
  stays current about which parts exist.
- If the server is down, `log` queues to `~/.local/state/printlog/queue.jsonl`
  and the next successful run sends it.

## API

`GET /api/prints?project=&part=&status=&limit=` · `GET /api/prints/<id>` ·
`POST /api/prints` · `PATCH /api/prints/<id>` · `DELETE /api/prints/<id>` ·
`GET /api/parts?project=&state=a,b` · `POST /api/parts` ·
`GET /api/status` · `GET /printlog` · `GET /install.sh`.
Write calls take `X-Token`.
