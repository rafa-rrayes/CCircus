# Circuit Circus

The official [SHDL](https://github.com/rafa-rrayes/SHDL) package index: a
curated collection of gate-level circuit libraries, hosted as a static index
that the `shdl` CLI installs from.

```bash
pip install pyshdl          # the SHDL toolchain, including the `shdl` CLI
shdl new myproject && cd myproject
shdl add arith              # vendors arith (and its deps) into shdl_modules/
shdl build && shdl test
```

## Consuming the index

The published site is this repository, byte for byte, at
**<https://rafa-rrayes.github.io/CCircus/>**:

| URL | What |
|---|---|
| `registry.json` | root index — every package, latest version inlined |
| `index/<name>.json` | one package's full version history |
| `archives/<name>-<version>.tar.gz` | immutable, versioned package archive |
| `packages/<name>/` | browsable source of truth |

Schemas, the archive recipe, the semver grammar, and the admission rules are
pinned in [`INDEX_FORMAT.md`](INDEX_FORMAT.md). Package manifests are
specified in [`MANIFEST_FORMAT.md`](MANIFEST_FORMAT.md). The catalog of what
exists (and what is planned) is [`CATALOG.md`](CATALOG.md).

Any static mirror works the same way — point the CLI elsewhere with
`shdl add --index URL`, `SHDL_INDEX_URL=...`, or `[registry] url` in
`shdl.toml` (a local checkout works too: `SHDL_INDEX_URL=file:///path/to/CCircus`).

## Publishing a package

1. Build the package under `packages/<name>/` — [`BUILD_GUIDE.md`](BUILD_GUIDE.md)
   is the walkthrough, `packages/gates/` the worked reference.
2. Verify: `uv run python tools/cc.py check <name>` until `OK: 0 problem(s)`.
3. Generate the index: `python tools/cc.py gen-index` (pure stdlib — no
   toolchain needed).
4. Commit the package **plus** the regenerated `registry.json`,
   `index/<name>.json`, and the new archive, then open a PR.

CI re-runs the whole admission pipeline on every PR: index freshness
(`gen-index --check`), append-only `archives/`, archive size caps, and a full
build+test sweep of every package against the published toolchain. Published
versions are immutable forever — changing a package means bumping its
version.

## Local development

- `tools/cc.py` — build/test/check packages, generate the index.
- `uv run ccircus` — the local FastAPI browse site (not part of the published
  index).
