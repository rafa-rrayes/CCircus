# Circuit Circus — Essential Libraries & the Top 100 Circuits

*The curated seed of the SHDL circuit index: the libraries every SHDL user
expects to install, and the most essential circuits inside each one.*

This is the **standard library** of Circuit Circus — the gate-level equivalent
of what `numpy`/`requests` are to PyPI. Everything here is plain `.shdl`
source: a netlist of the six SHDL primitives, parameterized for reuse, and
verifiable cycle-by-cycle against the oracle (and, soon, a `.shtb` testbench).

---

## 1. How the index works

A **library** is a package of related SHDL components. A **circuit** is one
component inside it.

```
shdl add arith                      # install a library from Circuit Circus
```
```shdl
use arith::{RippleAdder, ALU};      # import circuits from it
top component MyDatapath(...) -> (...) {
    add: RippleAdder<16>;
    ...
}
```

Conventions for everything in this catalog:

- **Component names** are `PascalCase` SHDL identifiers (`FullAdder`, `Mux4`).
- **Widths are parameters**, never hardcoded: `RippleAdder<N = 8>`. One
  definition serves every width via generators (`>i[N]{ ... }`).
- **Ports** follow the repo idiom: `Name<P>(inputs) -> (outputs)`, buses as
  `A[N]`, e.g. `FullAdder(A, B, Cin) -> (Sum, Cout)`.
- Each circuit ships with a testbench and a known-good trace; nothing enters
  the index unverified.

## 2. The ground rules that shape this catalog

SHDL is **pure two-valued gate logic** — six primitives (`AND OR NOT XOR`,
`__VCC__ __GND__`), unit delay, one gate-level per cycle. That constrains what
can legitimately live in the index, and the catalog is built to respect it:

- **No tri-state / high-Z.** There are no tri-state buffers, open-drain nets,
  or bidirectional buses. Every "bus select" is a **multiplexer**, never a
  shared driver. (This is why `mux` is a foundational library, not `tristate`.)
- **All state is feedback.** Latches and flip-flops are cross-coupled gates;
  there is no implicit register primitive. Every memory element here is built
  from ordinary gates and is fully deterministic from its `init` seed.
- **No magic arithmetic.** `+`/`*` are not operators — adders and multipliers
  are explicit gate netlists, and their propagation depth is observable. That
  is the whole point: a learner *watches* the carry ripple.
- **Everything is width-parameterized** and inlined at flatten time, so a
  library author writes the structure once.

## 3. The libraries

Nine libraries, in dependency order. Build them in roughly this order too —
each leans only on the ones above it, and the lower four are already proven by
circuits sitting in the `shdlc` repo's `examples/`.

| # | Library  | What it provides                                   | Depends on        | Circuits |
|---|----------|----------------------------------------------------|-------------------|---------:|
| 1 | `gates`  | Universal & wide gates above the six primitives    | —                 | 12 |
| 2 | `mux`    | Selection & routing: mux, demux, decoder, encoder  | `gates`           | 13 |
| 3 | `arith`  | Adders, subtractors, comparators, multiply, ALU    | `gates`, `mux`    | 16 |
| 4 | `shift`  | Logical/arithmetic shifters, rotators, barrel net  | `mux`             | 7  |
| 5 | `seq`    | Latches, flip-flops, registers, counters           | `gates`           | 18 |
| 6 | `mem`    | RAM, ROM, FIFO, stack, register file, CAM          | `seq`, `mux`      | 8  |
| 7 | `clock`  | Oscillators, dividers, edge logic, PWM             | `seq`, `gates`    | 8  |
| 8 | `code`   | Gray/BCD, parity, Hamming ECC, 7-segment           | `gates`, `arith`  | 10 |
| 9 | `cpu`    | Processor building blocks & demonstration CPUs     | all of the above  | 8  |
|   |          |                                                    | **Total**         | **100** |

A ✦ in the tables below marks a circuit that already exists (in whole or in
seed form) in `shdlc/examples/` and can be promoted into the index immediately.

---

## 4. The Top 100 circuits

### 1 · `gates` — universal & wide gates

The derived and reduction gates everything else is written in terms of. Built
straight on the six primitives.

| #  | Component   | Ports / Params                      | Description |
|----|-------------|-------------------------------------|-------------|
| 1  | `Nand` ✦    | `(A, B) -> (O)`                     | NAND — universal gate; `AND` then `NOT`. |
| 2  | `Nor` ✦     | `(A, B) -> (O)`                     | NOR — the other universal gate. |
| 3  | `Xnor` ✦    | `(A, B) -> (O)`                     | XNOR — 1-bit equality. |
| 4  | `Buffer`    | `(A) -> (O)`                        | Identity / fan-out buffer (`NOT` twice). |
| 5  | `AndN`      | `<N=4>(A[N]) -> (O)`                | N-input AND as a balanced reduction tree. |
| 6  | `OrN`       | `<N=4>(A[N]) -> (O)`                | N-input OR reduction. |
| 7  | `XorN`      | `<N=4>(A[N]) -> (O)`                | N-input XOR / parity reduction tree. |
| 8  | `BitAnd` ✦  | `<N=8>(A[N], B[N]) -> (O[N])`       | Bitwise AND of two buses. |
| 9  | `BitOr` ✦   | `<N=8>(A[N], B[N]) -> (O[N])`       | Bitwise OR of two buses. |
| 10 | `BitXor` ✦  | `<N=8>(A[N], B[N]) -> (O[N])`       | Bitwise XOR of two buses. |
| 11 | `BitNot`    | `<N=8>(A[N]) -> (O[N])`             | Bus inverter / one's complement. |
| 12 | `Majority3` | `(A, B, C) -> (O)`                  | 3-input majority voter (the adder carry kernel). |

### 2 · `mux` — selection & routing

Because SHDL has no tri-state, *all* data routing happens here.

| #  | Component        | Ports / Params                          | Description |
|----|------------------|-----------------------------------------|-------------|
| 13 | `Mux2` ✦         | `(D0, D1, S) -> (O)`                     | 2:1 multiplexer, 1 bit. |
| 14 | `Mux4`           | `(D[4], S[2]) -> (O)`                    | 4:1 multiplexer. |
| 15 | `Mux8`           | `(D[8], S[3]) -> (O)`                    | 8:1 multiplexer. |
| 16 | `MuxN` ✦         | `<W=8, S=1>(D[…], Sel[S]) -> (O[W])`     | Generic 2^S-input, W-bit-wide mux. |
| 17 | `BusMux2`        | `<N=8>(A[N], B[N], S) -> (O[N])`         | 2:1 select between two N-bit buses. |
| 18 | `Demux2`         | `(D, S) -> (O0, O1)`                     | 1:2 demultiplexer. |
| 19 | `Demux4`         | `(D, S[2]) -> (O[4])`                    | 1:4 demultiplexer. |
| 20 | `Demux8`         | `(D, S[3]) -> (O[8])`                    | 1:8 demultiplexer. |
| 21 | `Decoder2to4`    | `(A[2], EN) -> (O[4])`                   | 2→4 one-hot decoder with enable. |
| 22 | `Decoder3to8`    | `(A[3], EN) -> (O[8])`                   | 3→8 one-hot decoder. |
| 23 | `DecoderN`       | `<N=3>(A[N], EN) -> (O[2^N])`            | Generic n→2ⁿ one-hot decoder. |
| 24 | `Encoder8to3`    | `(D[8]) -> (O[3])`                       | Binary encoder (one-hot → index). |
| 25 | `PriorityEnc8`   | `(D[8]) -> (O[3], Valid)`               | 8→3 priority encoder + valid flag. |

### 3 · `arith` — arithmetic & comparison

The heart of the educational story: adders whose carry you can watch ripple,
and faster adders that visibly settle sooner.

| #  | Component         | Ports / Params                              | Description |
|----|-------------------|---------------------------------------------|-------------|
| 26 | `HalfAdder`       | `(A, B) -> (Sum, Cout)`                     | Half adder. |
| 27 | `FullAdder` ✦     | `(A, B, Cin) -> (Sum, Cout)`                | Full adder — the arithmetic unit cell. |
| 28 | `RippleAdder` ✦   | `<N=8>(A[N], B[N], Cin) -> (Sum[N], Cout)`  | Ripple-carry adder; depth ∝ N. |
| 29 | `CarryLookahead`  | `<N=8>(A[N], B[N], Cin) -> (Sum[N], Cout)`  | CLA — settles in fewer levels than RCA. |
| 30 | `CarrySelect`     | `<N=16>(A[N], B[N], Cin) -> (Sum[N], Cout)` | Carry-select adder. |
| 31 | `CarrySave`       | `<N=8>(A[N], B[N], C[N]) -> (S[N], Cy[N])`  | 3:2 carry-save compressor row. |
| 32 | `Subtractor`      | `<N=8>(A[N], B[N], Bin) -> (Diff[N], Bout)` | Borrow subtractor. |
| 33 | `AddSub`          | `<N=8>(A[N], B[N], Sub) -> (R[N], Cout)`    | Add/subtract on a mode bit (two's-comp). |
| 34 | `Incrementer`     | `<N=8>(A[N]) -> (O[N], Cout)`               | +1. |
| 35 | `Decrementer`     | `<N=8>(A[N]) -> (O[N], Bout)`               | −1. |
| 36 | `Negate`          | `<N=8>(A[N]) -> (O[N])`                      | Two's-complement negation. |
| 37 | `EqComparator` ✦  | `<N=8>(A[N], B[N]) -> (Eq)`                  | Equality comparator. |
| 38 | `MagComparator` ✦ | `<N=8>(A[N], B[N]) -> (Lt, Eq, Gt)`         | Magnitude comparator. |
| 39 | `ArrayMultiplier` | `<N=8>(A[N], B[N]) -> (P[2N])`              | Unsigned array (shift-and-add) multiplier. |
| 40 | `Divider`         | `<N=8>(A[N], B[N]) -> (Q[N], R[N])`         | Restoring (unsigned) divider. |
| 41 | `ALU` ✦           | `<N=8>(A[N], B[N], Op[…]) -> (Y[N], Flags)` | Arithmetic-logic unit with flags. |

### 4 · `shift` — shifters & rotators

Pure combinational mux networks — no clock involved.

| #  | Component        | Ports / Params                                 | Description |
|----|------------------|------------------------------------------------|-------------|
| 42 | `ShiftLeft`      | `<N=8>(A[N], Sh[log2N]) -> (O[N])`             | Logical left shift by a variable amount. |
| 43 | `ShiftRight`     | `<N=8>(A[N], Sh[log2N]) -> (O[N])`             | Logical right shift. |
| 44 | `ArithShiftR`    | `<N=8>(A[N], Sh[log2N]) -> (O[N])`             | Arithmetic (sign-extending) right shift. |
| 45 | `BarrelShifter`  | `<N=8>(A[N], Sh[log2N], Dir) -> (O[N])`        | Log-depth barrel shifter, either direction. |
| 46 | `BarrelRotator`  | `<N=8>(A[N], Sh[log2N]) -> (O[N])`             | Variable rotate (no bits lost). |
| 47 | `FunnelShifter`  | `<N=8>(Hi[N], Lo[N], Sh[log2N]) -> (O[N])`     | Funnel shift across a 2N-bit window. |
| 48 | `BitReverse`     | `<N=8>(A[N]) -> (O[N])`                         | Reverse bit order (pure wiring). |

### 5 · `seq` — latches, flip-flops, registers, counters

Where feedback becomes memory. Each is a loop of ordinary gates with an `init`
seed, so traces are deterministic from cycle 0.

| #  | Component         | Ports / Params                          | Description |
|----|-------------------|-----------------------------------------|-------------|
| 49 | `SrLatch` ✦       | `(S, R) -> (Q, Qn)`                      | NOR cross-coupled set/reset latch. |
| 50 | `SrLatchNand`     | `(S, R) -> (Q, Qn)`                      | NAND (active-low) SR latch. |
| 51 | `GatedSrLatch`    | `(S, R, EN) -> (Q, Qn)`                  | Enable-gated SR latch. |
| 52 | `DLatch` ✦        | `(D, EN) -> (Q, Qn)`                     | Transparent D latch. |
| 53 | `DFlipFlop`       | `(D, Clk) -> (Q, Qn)`                    | Edge-triggered master-slave D-FF. |
| 54 | `JkFlipFlop`      | `(J, K, Clk) -> (Q, Qn)`                | JK flip-flop. |
| 55 | `TFlipFlop`       | `(T, Clk) -> (Q, Qn)`                    | Toggle flip-flop. |
| 56 | `Register`        | `<N=8>(D[N], Clk) -> (Q[N])`            | N-bit edge-triggered register. |
| 57 | `RegisterEn` ✦    | `<N=8>(D[N], LD) -> (Q[N])`             | N-bit register with load enable. |
| 58 | `ShiftRegSISO`    | `<N=8>(In, Clk) -> (Out)`              | Serial-in / serial-out shift register. |
| 59 | `ShiftRegSIPO`    | `<N=8>(In, Clk) -> (Q[N])`             | Serial-in / parallel-out. |
| 60 | `ShiftRegPISO`    | `<N=8>(D[N], LD, Clk) -> (Out)`        | Parallel-in / serial-out. |
| 61 | `UniversalShift`  | `<N=8>(D[N], L, R, Mode[2], Clk) -> (Q[N])` | Load / shift-L / shift-R / hold. |
| 62 | `RippleCounter`   | `<N=4>(Clk) -> (Q[N])`                 | Asynchronous ripple counter. |
| 63 | `SyncCounter`     | `<N=4>(Clk, EN) -> (Q[N])`            | Synchronous up-counter (mod-2ⁿ; mod-M via param). |
| 64 | `UpDownCounter`   | `<N=4>(Clk, Up) -> (Q[N])`           | Direction-controlled counter. |
| 65 | `RingCounter`     | `<N=4>(Clk) -> (Q[N])`                | One-hot rotating counter. |
| 66 | `JohnsonCounter`  | `<N=4>(Clk) -> (Q[N])`                | Twisted-ring (Johnson) counter. |

### 6 · `mem` — addressable storage

Decoder + latch cells + read mux. Larger, but already proven feasible by the
SR16 CPU's RAM and register file.

| #  | Component       | Ports / Params                                         | Description |
|----|-----------------|--------------------------------------------------------|-------------|
| 67 | `RamCell`       | `(D, WE, Sel) -> (Q)`                                  | 1-bit gated storage cell — the RAM unit. |
| 68 | `Ram` ✦         | `<A=4, W=8>(Addr[A], Din[W], WE, Clk) -> (Dout[W])`    | Single-port NxW RAM. |
| 69 | `DualPortRam`   | `<A=4, W=8>(…2 addr/data ports…) -> (…)`               | 1-write / 1-read independent ports. |
| 70 | `RegisterFile` ✦| `<A=3, W=8>(Ra,Rb,Rw, Din[W], WE, Clk) -> (Qa,Qb)`    | 2-read / 1-write register file. |
| 71 | `Rom`           | `<A=4, W=8>(Addr[A]) -> (Dout[W])`                     | Constant-materialized ROM / lookup table. |
| 72 | `Fifo`          | `<W=8, D=8>(Din, Push, Pop, Clk) -> (Dout, Full, Empty)` | Circular-buffer queue. |
| 73 | `Lifo`          | `<W=8, D=8>(Din, Push, Pop, Clk) -> (Dout, Full, Empty)` | Stack (last-in first-out). |
| 74 | `Cam`           | `<W=8, D=8>(Key[W], …) -> (Match, Index)`             | Content-addressable memory (parallel match). |

### 7 · `clock` — timing & edges

Free-running and derived timing. Showcases the model: a ring oscillator is
nothing but an odd loop of inverters.

| #  | Component        | Ports / Params                       | Description |
|----|------------------|--------------------------------------|-------------|
| 75 | `RingOscillator` ✦ | `() -> (Clk)`                      | Odd-length NOT loop; free-running clock. |
| 76 | `ClockDivideBy2` | `(Clk) -> (Out)`                     | ÷2 via a toggling flip-flop. |
| 77 | `ClockDivideByN` | `<N=10>(Clk) -> (Out)`               | Mod-N clock divider. |
| 78 | `PulseGenerator` | `(Trig, Clk) -> (Pulse)`            | One-shot single-cycle pulse. |
| 79 | `EdgeRising`     | `(In, Clk) -> (Edge)`               | Rising-edge detector. |
| 80 | `EdgeFalling`    | `(In, Clk) -> (Edge)`               | Falling-edge detector. |
| 81 | `Debouncer`      | `<N=8>(In, Clk) -> (Out)`           | Counter-based switch debouncer. |
| 82 | `PwmGenerator`   | `<N=8>(Duty[N], Clk) -> (Out)`      | PWM from a counter/threshold compare. |

### 8 · `code` — encoding, decoding & error correction

Combinational XOR/logic networks — great worked examples of "structure you can
read off the gates."

| #  | Component         | Ports / Params                          | Description |
|----|-------------------|-----------------------------------------|-------------|
| 83 | `BinToGray`       | `<N=8>(B[N]) -> (G[N])`                 | Binary → Gray code. |
| 84 | `GrayToBin`       | `<N=8>(G[N]) -> (B[N])`                 | Gray → binary (prefix-XOR). |
| 85 | `BinToBcd`        | `<N=8>(B[N]) -> (Bcd[…])`               | Binary → BCD (double-dabble network). |
| 86 | `BcdToBin`        | `<D=2>(Bcd[…]) -> (B[…])`               | BCD → binary. |
| 87 | `BcdAdder`        | `(A[4], B[4], Cin) -> (S[4], Cout)`     | One-digit decimal (BCD) adder. |
| 88 | `SevenSegDecoder` | `(Hex[4]) -> (Seg[7])`                  | Hex digit → 7-segment display pattern. |
| 89 | `ParityGen`       | `<N=8>(D[N]) -> (P)`                    | Even/odd parity-bit generator. |
| 90 | `ParityCheck`     | `<N=8>(D[N], P) -> (Err)`               | Parity error detector. |
| 91 | `HammingEncode`   | `(D[4]) -> (Code[7])`                   | Hamming(7,4) encoder. |
| 92 | `HammingDecode`   | `(Code[7]) -> (D[4], Err)`              | Hamming(7,4) single-error-correcting decoder. |

### 9 · `cpu` — processor building blocks & demo machines

The payoff: from a single NAND all the way to a working processor. Mostly
compositions of the eight libraries above.

| #  | Component          | Ports / Params                              | Description |
|----|--------------------|---------------------------------------------|-------------|
| 93 | `ProgramCounter`   | `<N=16>(Din[N], Load, Inc, Clk) -> (PC[N])` | PC with load / increment / reset. |
| 94 | `InstructionReg`   | `<N=16>(Din[N], LD, Clk) -> (Instr[N])`     | Instruction register. |
| 95 | `AluControl`       | `(Opcode[…]) -> (AluOp[…])`                 | Opcode → ALU control decode. |
| 96 | `Accumulator`      | `<N=8>(Din[N], Op[…], Clk) -> (Acc[N])`     | Accumulator + ALU front end. |
| 97 | `ControlUnit`      | `(Opcode[…], Flags, Clk) -> (Ctrl[…])`      | FSM / micro-sequenced control unit. |
| 98 | `Datapath8`        | `(…)`                                        | 8-bit datapath: regfile + ALU + bus. |
| 99 | `Cpu4`             | `(Clk, Reset) -> (…)`                        | Minimal 4-bit teaching CPU. |
| 100| `SR16` ✦           | `(Clk, Reset) -> (…)`                        | The showcase 16-bit CPU (from `examples/CPU`). |

---

## 5. Build order & seeding

The libraries are listed top-to-bottom in dependency order, which is also the
recommended authoring order. Two practical notes:

1. **Seed from the repo.** Every ✦ circuit already exists as working `.shdl`
   in `shdlc/examples/` (and `examples/CPU/` for the processor parts). The
   first release of `gates`, `mux`, `arith`, `seq`, and `mem` is largely a
   *promotion-and-test* job: lift the example, give it a testbench, publish.
2. **Everything ships verified.** A circuit is admitted to the index only with
   a `.shtb` testbench and a known-good oracle trace, so the catalog doubles as
   a conformance corpus the flattener and compiler can be regression-tested
   against forever.

## 6. Beyond the Top 100

Deliberately left out of the essential set, as natural "next 100" candidates:
Wallace/Dadda multipliers, Booth recoding, Kogge-Stone/Brent-Kung prefix
adders, floating-point units, CORDIC, LFSR/PRNG, CRC, UART/SPI/I²C controllers,
VGA timing, FIR filters, cache/MMU blocks, and richer CPUs (pipelined, RISC-V
subset). They build cleanly on the nine libraries here.
