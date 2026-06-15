# Circuit Circus — Manifest Format

*The on-disk contract for a Circuit Circus package and for the registry index.
Version 1.*

A **package** is a directory under `packages/` that ships one SHDL module
(`<name>.shdl`) plus a manifest (`package.json`) describing it. The registry
(`registry.json` at the repo root) is the flat index of all packages — the
"simple index" that `shdl add <pkg>` resolves against.

```
CCircus/
├── registry.json                  # the index of all packages
├── packages/
│   └── <name>/
│       ├── package.json           # the package manifest  (this spec, §1)
│       ├── <name>.shdl            # the SHDL module: all the package's components
│       ├── README.md              # human docs
│       └── tests/
│           └── <name>.tests.json  # test vectors           (this spec, §3)
└── tools/cc.py                    # build + verify a package from its manifest
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
  "tests": "tests/arith.tests.json",    // optional — path to the test file
  "exports": [ /* §2 */ ]               // required — every component the package provides
}
```

Rules:

- `name` **must** equal the directory name and the `module` basename, so
  `use <name>::{…}` resolves on disk. Component names are program-global by
  bare name in the flattener, so **no two packages may export the same
  component name**.
- `dependencies` lists only *other Circuit Circus packages*. The six SHDL
  primitives (`AND OR NOT XOR __VCC__ __GND__`) are always available and are
  never dependencies.
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
  "tests": "tests/ripple_adder.json",           // optional — per-component test pointer
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

## 4. `registry.json` — the index

The flat, generated index of every package. `cc.py all` iterates it.

```jsonc
{
  "registry_format": 1,
  "name": "Circuit Circus",
  "homepage": "https://github.com/rafa-rrayes/SHDL",
  "packages": [
    {
      "name": "gates",
      "version": "0.1.0",
      "summary": "Universal & wide gates above the six SHDL primitives.",
      "path": "packages/gates",
      "circuits": 12,
      "dependencies": {}
    }
    // … one entry per package …
  ]
}
```

Each `packages[]` entry mirrors its manifest's `name`, `version`, `summary`,
and `dependencies`, adds the repo-relative `path` and the `circuits` count
(`len(exports)`). It is derivable from the manifests; treat the manifests as
the source of truth and the registry as their digest.

## 5. Verifying a package

```bash
# from the SHDL toolchain checkout's environment (it provides PySHDL):
cd /path/to/shdlc
uv run python /path/to/CCircus/tools/cc.py check <pkg>     # build + test one package
uv run python /path/to/CCircus/tools/cc.py all             # check the whole registry
```

`check` flattens+compiles every export (resolving dependency include dirs from
the manifest) and runs the test vectors. Non-zero exit ⇒ something failed.
