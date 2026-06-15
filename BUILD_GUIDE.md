# Circuit Circus — Package Build Guide

*Read this once, then build your package. The `gates` package
(`packages/gates/`) is the worked reference — read it alongside this guide.*

Your job: produce one Circuit Circus package — a `<name>.shdl` module, a
`package.json` manifest, a `tests/<name>.tests.json` file, and a short
`README.md` — where **every exported component compiles and passes its test
vectors**. The catalog (`CATALOG.md`) is the spec for what to build and the
exact ports of each circuit. The manifest format (`MANIFEST_FORMAT.md`) is the
spec for the files. This guide is *how* to write correct SHDL and verify it.

---

## 0. Definition of done

```bash
# from the CCircus repo root — cc.py finds the sibling ../shdlc toolchain
# (or an installed PySHDL; or set SHDLC_ROOT to a checkout)
uv run python tools/cc.py check <name>
#  →  [build] <name>: M/M components compiled
#     [test]  <name>: K/K cases green
#     OK: 0 problem(s)
```

`OK: 0 problem(s)` is the bar. Do not report done until you see it. Iterate:
write → `cc.py check` → read the failure → fix → repeat.

## 1. SHDL in one page (the only syntax you need)

The six primitives — and the **only** gates that exist — are `AND(A,B)->(O)`,
`OR(A,B)->(O)`, `NOT(A)->(O)`, `XOR(A,B)->(O)`, and the power pins
`__VCC__()->(O)` (constant 1) and `__GND__()->(O)` (constant 0). Everything
else is composition.

```shdl
"""Triple-quoted docstring at the top of the module (optional)."""

use otherpkg::{CompA, CompB};        # import from a dependency package

# A component: params <…>, inputs (…), outputs -> (…)
component Name<N = 8>(A[N], B[N], Cin) -> (Sum[N], Cout) {
    inv: NOT;                        # an instance: id: Type;  (or Type<args>)
    >i[N]{ fa{i}: FullAdder; }       # a generator: repeat for i = 1..N

    connect {
        S -> inv.A;                  # wire: source -> dest;
        >i[N]{                       # generators work in connect too
            A[{i}] -> fa{i}.A;                       # {i} interpolates the index
            when {i == 1} { Cin          -> fa{i}.Cin; }   # compile-time conditional
            else          { fa{i-1}.Cout -> fa{i}.Cin; }   # {i-1}: index arithmetic
            fa{i}.Sum -> Sum[{i}];
        }
        fa{N}.Cout -> Cout;
    }
}
```

Hard rules — these are the ones that bite:

- **Bit 1 is the LSB.** Buses are **1-indexed**: `A[1]` is the low bit, `A[N]`
  the high bit. Generators `>i[N]{}` run `i = 1..N` inclusive; `>i[2:N]{}` runs
  `i = 2..N`.
- **Slices are 1-based inclusive:** `In[:4]` = bits 1..4, `In[5:8]` = bits 5..8,
  `In[3:3]` = bit 3.
- **Concatenation is MSB-first:** `{In[5:8], In[:4]}` puts the high nibble on
  top. **Replication:** `8{In[8]}` = eight copies of bit 8.
- **`{i}` is index interpolation**, `{i-1}`, `{i+1}`, `{2*i}` are allowed.
  `when {COND}` / `else` is a *compile-time* conditional over params/indices,
  not a runtime mux — use it to fold loop boundaries (first/last stage).
- An instance passes params through: `add: RippleAdder<N>;` or `<16>` or `<N+1>`.
- **`component` vs `top component`:** library modules use plain `component` (no
  `top`). The verifier instantiates each export as top by name, using its
  **default params**, so *every parameterized component must have working
  defaults* (e.g. `<N = 8>`).
- Fan-out is free; an unused instance output needs no consumer. Every *input*
  of every instance must be driven.

## 2. The model: unit-delay, one gate level per cycle

Every gate computes from the previous cycle's values; a result ripples forward
**one level per cycle**. Consequences you must design around:

- **Combinational depth costs cycles.** A signal through *d* gate levels needs
  *d* `step`s to settle. The test harness advances a `steps` budget (default
  64) before checking outputs — set it ≥ your circuit's depth. For a ripple
  chain of width N, depth ≈ 2N; use `steps` ≈ `2*N + 8` or just a safe 64–128.
- **State = feedback.** There is no register primitive. Latches/flip-flops are
  cross-coupled gates that depend on their own previous output.

## 3. Feedback & `init` — read this before building any latch/FF/counter

A feedback loop holds a value only if **its power-on state is a fixed point**.
You must seed it with an `init` block, and the rules are strict (see
`examples/srLatch.shdl`):

- **Seed every gate output in the loop.** A partially-seeded loop does not
  "settle" — in a deterministic unit-delay network a symmetric state never
  breaks, so it oscillates forever.
- **A seeded loop must own every gate in it.** You **cannot** use a composite
  (e.g. `gates::Nor`) inside a seeded loop, because `init` can only name *this*
  component's gate outputs — the composite's internal nets would be unseeded.
  So build latches from **raw `AND/OR/NOT/XOR`**, not from `gates::*`.

```shdl
top component SRLatch(S, R) -> (Q, Qn) {
    o1: OR;  i1: NOT;     # NOR #1 — every gate owned by the latch
    o2: OR;  i2: NOT;     # NOR #2
    init { o1.O = 1;  i1.O = 0;  o2.O = 0;  i2.O = 1; }   # a fixed point at S=R=0
    connect {
        R -> o1.A;  i2.O -> o1.B;  o1.O -> i1.A;  i1.O -> Q;
        S -> o2.A;  i1.O -> o2.B;  o2.O -> i2.A;  i2.O -> Qn;
    }
}
```

Build registers/counters by composing *instances* of your own sequential
primitives (a `RegisterN` is N `DLatch`/`DFlipFlop` instances) — the instances
carry their own seeds through flattening, so the composite needs no `init` of
its own. Drive a clock in tests by poking `Clk` 0→1 with `step`s between edges.

## 4. Verify-as-you-go

You don't have to wait for the whole package. Probe one component fast:

```bash
# from the CCircus repo root; --project ../shdlc runs in the toolchain env
# flatten only (catches syntax / wiring errors):
uv run --project ../shdlc shdl-flatten packages/<name>/<name>.shdl --top SomeComp \
    -I packages/<dep>   # one -I per dependency package
# or simulate in Python:
uv run --project ../shdlc python -c "
from SHDL import Circuit
c = Circuit('packages/<name>/<name>.shdl', top='SomeComp',
            include_dirs=['packages/<dep>'])
c.reset(); c.poke('A',5); c.poke('B',9); c.poke('Cin',0); c.step(64)
print('Sum', c.peek('Sum'), 'Cout', c.peek('Cout')); c.close()
"
```

`cc.py` derives the `-I` dependency dirs from your manifest's `dependencies`,
so once the manifest is right, `cc.py check <name>` is the single command.

## 5. Files to produce

```
packages/<name>/
├── package.json                 # manifest — see MANIFEST_FORMAT.md §1–2; one export per component
├── <name>.shdl                  # the module: all components, plain `component` (no top)
├── README.md                    # ~15 lines: what the package is, the component list
└── tests/<name>.tests.json      # see MANIFEST_FORMAT.md §3; a meaningful vector set per component
```

Match the `gates` package's shape exactly. Manifest essentials: `name` ==
directory == module basename; `dependencies` lists only the packages you
`use`; `exports` has one entry per component with correct `params`/`inputs`/
`outputs` (use width strings like `"N"`, `"2N"`, `"log2N"` for buses).

## 6. Constraints (do not violate)

- **Pure two-valued logic — no tri-state / high-Z.** No tri-state buffers, no
  shared/bidirectional buses. Every selection is a multiplexer.
- **No behavioral shortcuts.** No `+`/`*` operators, no implicit state. Only
  gates, wires, generators.
- **Defaults must compile.** Every component instantiable as top at its
  default params.
- **Unique names.** Component names are global across the whole registry —
  keep them exactly as the catalog lists them.

## 7. Pattern cheatsheet (all proven in `examples/`)

- **Reduction tree** (AND/OR/XOR over a bus) → chained generator with a `when`
  head: see `gates::AndN`, `examples/comparator.shdl`.
- **Ripple chain** (adder/subtractor/counter carry) → `>i[N]{}` with
  `when {i==1}` seeding the first stage's carry-in: `examples/adderN.shdl`.
- **1-bit 2:1 mux cell** → `O = (A AND ¬S) OR (B AND S)`: `examples/muxN.shdl`.
- **Bit replication / sign-extend / nibble swap** → concat & replication:
  `examples/busOps.shdl`.
- **Latch / gated latch** → cross-coupled raw gates + full `init`:
  `examples/srLatch.shdl`, `examples/dLatch.shdl`.

If a component is marked ✦ in `CATALOG.md`, a working version already exists in
the toolchain's `examples/` (the sibling `../shdlc/examples/`, or `examples/CPU/`
for the processor parts) — read it and adapt it (rename to the catalog's
component name) rather than reinventing it.
