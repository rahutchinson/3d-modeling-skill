# scadserver — render OpenSCAD on a different machine

Two files, stdlib Python only:

| file | runs on | what |
|------|---------|------|
| `server.py` | the render box | HTTP service: takes a project tarball + openscad argv, runs OpenSCAD, returns the outputs. Status page at `/`. |
| `rscad` | any machine | drop-in `openscad` CLI: bundles the project, posts it, writes the outputs back. `OPENSCAD=rscad make`. |

Nothing in a project changes. Every Makefile, `check.sh` and scadview in the
skill already goes through `$(OPENSCAD)` / `$OPENSCAD`, so pointing that at
`rscad` moves the whole render workload to the server. `-D`, `-o`, `-d`
(depfiles), `--export-format`, `.echo` outputs, `.png` renders and
`--summary-file` all work; depfile paths are translated back to the client.

## Server

```sh
# one-time, on the render box
./tools/scadserver/install-service.sh        # systemd --user unit, enabled + started
cat ~/.config/openscad-server/token          # the shared secret clients need
```

Config lives in `~/.config/openscad-server/config.json` (all keys optional):

```json
{
  "port": 8790,
  "workers": 4,
  "timeout": 1800,
  "default_engine": "nightly",
  "engines": {
    "nightly": ["~/.local/bin/openscad-nightly", "--backend=manifold"],
    "2021":    ["~/.local/bin/openscad"]
  },
  "cache_max_mb": 2048
}
```

An engine is just an argv prefix, so several OpenSCAD versions can sit side
by side. Missing binaries are skipped at startup. Successful renders are
cached by a content hash of the sources + argv + engine, so re-running an
unchanged target is a round trip, not a render.

Jobs run in a throwaway directory that is deleted afterwards; the upload is
checked for path escapes and links. Render requests need the token; the
status page and the client download do not.

Endpoints: `GET /` (HTML status), `GET /api/status` (JSON), `GET /api/jobs`
(recent, token), `GET /rscad`, `GET /install.sh`, `POST /api/render` (token).

## Client

```sh
curl -sf http://SERVER:8790/install.sh | sh -s -- TOKEN              # ~/.local/bin/rscad
curl -sf http://SERVER:8790/install.sh | sh -s -- TOKEN --as-openscad # also openscad -> rscad
rscad --rscad-status
```

Then in any project: `OPENSCAD=rscad make`, or just `make` if you took the
`--as-openscad` link. Per call: `--rscad-engine=2021`, `--rscad-timeout=600`,
`--rscad-verbose`, `--rscad-local`. Env: `RSCAD_URL`, `RSCAD_TOKEN`,
`RSCAD_ENGINE`, `RSCAD_TIMEOUT`, `RSCAD_LOCAL=1`, `RSCAD_VERBOSE=1`.

If the server is down, `rscad` runs a local `openscad` from PATH instead
(and says so on stderr), so the laptop still works offline.

### What gets uploaded

The project root is the nearest parent of the current directory containing
`params.scad`, `scadview.json`, a `Makefile` or `.git`. Everything under it is
sent except `.git`, caches, and rendered outputs (`.stl/.3mf/.png/.echo/.d/…`
inside `stl/`, `.scadview-cache/`, `out/`, `build/`, `dist/`); files over 25 MB
are skipped with a note. Add glob patterns to a `.rscadignore` in the root to
exclude more. Input files outside the root are shipped individually, but
their relative `include`s won't resolve, so keep inputs inside the project.
