# Circuit Circus — Manifest Format

*The on-disk contract for a Circuit Circus package. Version 1.*

A **package** is a directory under `packages/` that ships one SHDL module
(`<name>.shdl`) plus a manifest (`package.json`) describing it. The hosted
index that `shdl add <pkg>` resolves against — `registry.json`,
`index/<name>.json`, and the versioned archives — is **generated from these
manifests** by `tools/cc.py gen-index` and specified separately in
`INDEX_FORMAT.md`.

```
CCircus/
├── registry.json                  # generated root index   (INDEX_FORMAT.md §2)
├── index/<name>.json              # generated version files (INDEX_FORMAT.md §3)
├── archives/<name>-<ver>.tar.gz   # immutable archives      (INDEX_FORMAT.md §4)
├── packages/
│   └── <name>/
│       ├── package.json           # the package manifest  (this spec, §1)
│       ├── <name>.shdl            # the SHDL module: all the package's components
│       ├── README.md              # human docs
│       └── tests/
│           └── <name>.tests.json  # test vectors           (this spec, §3)
└── tools/cc.py                    # build + verify + generate the index
```

**Why module = package.** The SHDL flattener resolves `use foo::{Bar}` to a
file `foo.shdl` (the importing file's directory first, then `-I` include
dirs). So a package's components all live in one module file named after the
package, and a consumer writes `use arith::{RippleAdder};` exactly as the
catalog shows. Components within a package reference each other directly (same
module, no `use`). Cross-package use needs the dependency's directory on the
include path — `cc.py` derives that from `dependencies` automatically.

---

## 1. `package.json` — the package manifest

```jsonc
{
  "manifest_format": 1,                 // required — this spec's version
  "name": "arith",                      // required — package id; must equal the dir name
  "version": "0.1.0",                   // required — semver
  "summary": "Adders, comparators, multiply/divide, ALU.",   // required — one line
  "description": "…longer prose…",       // optional
  "license": "GPL-3.0-or-later",        // required
  "authors": ["name <email>"],          // required — at least one
  "homepage": "https://…",              // optional
  "keywords": ["adder", "alu"],         // optional
  "shdl": ">=1.0.0",                    // required — compatible toolchain range
  "module": "arith.shdl",               // required — the module file (== "<name>.shdl")
  "dependencies": {                      // required — package -> semver range ({} if none)
    "gates": "^0.1.0",
    "mux": "^0.1.0"
  },
  "tests": "tests/arith.tests.json",    // optional — path to the test file,
                                        //   relative to the package dir
                                        //   (default: tests/<name>.tests.json)
  "exports": [ /* §2 */ ]               // required — every component the package provides
}
```

Rules:

- `name` **must** equal the directory name and the `module` basename, so
  `use <name>::{…}` resolves on disk.
- **Global uniqueness.** The SHDL module namespace is flat and program-global
  (modules bind by bare filename; components by bare name), so across the
  whole registry **no two packages may export the same component name** and
  **no two packages may have the same module basename** (the latter follows
  from `name == module` but is checked independently). `gen-index` enforces
  both.
- `tests` is honored by `cc.py test`: it names the test file to run, relative
  to the package directory; when absent, `tests/<name>.tests.json` is used.
  The resolved file **must exist** — `gen-index` rejects the tree and
  `cc.py test` counts it as a failure (a typo must not skip verification).
- `dependencies` lists only *other Circuit Circus packages*, mapping name →
  semver range (grammar: `INDEX_FORMAT.md` §6). The six SHDL primitives
  (`AND OR NOT XOR __VCC__ __GND__`) are always available and are never
  dependencies.
- Keep the dependency graph acyclic (the flattener rejects circular imports).

## 2. The `exports` array — one entry per component

Each entry is the public, machine-readable interface of one component. This is
what an index UI lists, what `shdl add` advertises, and what tooling validates
ports against.

```jsonc
{
  "name": "RippleAdder",                       // required — the SHDL component name
  "summary": "Ripple-carry adder; depth ∝ N.", // required — one line
  "params": [{"name": "N", "default": 8}],     // required — [] if not parameterized
  "inputs":  [                                  // required — declared input ports
    {"name": "A",   "width": "N"},              //   width: an int, or a param expression
    {"name": "B",   "width": "N"},              //   string ("N", "2N", "log2N", …)
    {"name": "Cin", "width": 1}
  ],
  "outputs": [                                  // required — declared output ports
    {"name": "Sum",  "width": "N"},
    {"name": "Cout", "width": 1}
  ],
  "stdlib_seed": true                            // optional — promoted from examples/
}
```

- `width` is `1` for a single wire, an integer for a fixed bus, or a **string
  expression** in the component's params for a parameterized bus (`"N"`,
  `"2N"`, `"N+1"`, `"log2N"`). The string is documentation/UI metadata; the
  authoritative widths are in the flattened Base SHDL `ports` metadata.
- Every parameterized component **must compile at its declared defaults**, so
  the verifier can instantiate it as `top` with no extra wrapper.

## 3. `tests/<name>.tests.json` — the verification vectors

A package is admitted only if every export builds *and* passes vectors. The
test file drives `cc.py test`. Two case styles:

**Vector table** — for combinational circuits. Reset, poke all inputs, advance
`steps` unit-delay cycles (a budget ≥ the circuit's propagation depth), then
check every output:

```jsonc
{
  "test_format": 1,
  "package": "arith",
  "cases": [
    {
      "component": "RippleAdder",
      "steps": 64,                                  // cycles to settle (default 64)
      "vectors": [
        {"in": {"A": 5, "B": 9, "Cin": 0}, "out": {"Sum": 14, "Cout": 0}},
        {"in": {"A": 200, "B": 100, "Cin": 0}, "out": {"Sum": 44, "Cout": 1}}
      ]
    }
  ]
}
```

**Op sequence** — for sequential / feedback circuits, where timing matters.
An explicit list of `reset` / `poke` / `step` / `expect` ops (the same op
vocabulary as the conformance suite's traces), so a clock can be driven by
hand:

```jsonc
{
  "component": "DFlipFlop",
  "ops": [
    {"op": "reset"},
    {"op": "poke", "signal": "D", "value": 1},
    {"op": "poke", "signal": "Clk", "value": 0}, {"op": "step", "cycles": 2},
    {"op": "poke", "signal": "Clk", "value": 1}, {"op": "step", "cycles": 4},
    {"op": "expect", "signal": "Q", "value": 1}
  ]
}
```

Values are unsigned integers, bit 0 = the port's LSB. Outputs read back
zero-extended. Vectors should cover the interesting cases (boundaries,
carries, every select line, hold-after-load for state), not the full space.

## 4. The generated index — `registry.json`, `index/`, `archives/`

`registry.json` and everything under `index/` and `archives/` are **generated
by `cc.py gen-index` — never hand-edit them**. The manifests under
`packages/` are the single source of truth; the index is their published
digest. Schemas, archive recipe, URL layout, and semver grammar live in
`INDEX_FORMAT.md`. `cc.py gen-index --check` verifies (byte-exactly) that the
committed index matches the manifests; CI runs it on every PR.

## 5. Verifying a package

```bash
# from the CCircus repo root (cc.py finds an installed PySHDL, the sibling
# ../shdlc checkout, or $SHDLC_ROOT):
uv run python tools/cc.py check <pkg>     # build + test one package
uv run python tools/cc.py all             # check every package in packages/
```

`check` flattens+compiles every export (resolving dependency include dirs from
the manifest) and runs the test vectors. Non-zero exit ⇒ something failed.

## 6. Publishing a version

A version, once published, is **immutable forever**: its archive
(`archives/<name>-<version>.tar.gz`) and its entry in `index/<name>.json` are
never modified or deleted (CI enforces append-only `archives/`). Any change
to a package's files therefore requires a version bump:

- **patch** (`0.1.0 → 0.1.1`) — docs/README/test changes, internal
  restructuring; exports and ports identical.
- **minor** (`0.1.0 → 0.2.0`) — new exported components; new params with
  defaults that preserve existing instantiations.
- **major** — removed/renamed exports, changed ports or param defaults;
  anything that can break a `use` site. (For `0.y.z` packages the minor
  position carries breaking changes, matching the caret rule.)

Flow: edit the package → bump `version` → `cc.py check <name>` →
`cc.py gen-index` → commit the package source **plus** the regenerated
`registry.json`, `index/<name>.json`, and the new archive → open a PR.
`BUILD_GUIDE.md` has the full walkthrough; `INDEX_FORMAT.md` §7 lists the
admission rules CI enforces.
