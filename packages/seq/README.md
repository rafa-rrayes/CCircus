# seq

Latches, flip-flops, registers, and counters — where feedback becomes memory.
Every memory element is a loop of ordinary gates whose `init` block seeds a
fixed point, so traces are deterministic from cycle 0.

```shdl
use seq::{DFlipFlop, Register, SyncCounter};
```

The primitive latches are cross-coupled **raw** AND/OR/NOT gates with a fully
seeded `init` (a seeded loop must own every gate in it). Everything above them
composes **instances** of those primitives, whose seeds carry through
flattening — so registers and counters need no `init` of their own. All
clocked parts are rising-edge master-slave flip-flops; drive a clock in tests
by poking `Clk` 0→1 with `step`s between edges.

| Component        | Ports                                        | Notes |
|------------------|----------------------------------------------|-------|
| `SrLatch`        | `(S, R) -> (Q, Qn)`                          | NOR cross-coupled (active-high) |
| `SrLatchNand`    | `(S, R) -> (Q, Qn)`                          | NAND cross-coupled (active-low) |
| `GatedSrLatch`   | `(S, R, EN) -> (Q, Qn)`                      | enable-gated SR latch |
| `DLatch`         | `(D, EN) -> (Q, Qn)`                         | transparent D latch |
| `DFlipFlop`      | `(D, Clk) -> (Q, Qn)`                        | rising-edge master-slave |
| `JkFlipFlop`     | `(J, K, Clk) -> (Q, Qn)`                     | hold/set/reset/toggle |
| `TFlipFlop`      | `(T, Clk) -> (Q, Qn)`                        | toggle on edge |
| `Register`       | `<N=8>(D[N], Clk) -> (Q[N])`                 | edge-triggered N-bit register |
| `RegisterEn`     | `<N=8>(D[N], LD) -> (Q[N])`                  | transparent load-enable register |
| `ShiftRegSISO`   | `<N=8>(In, Clk) -> (Out)`                    | serial-in / serial-out |
| `ShiftRegSIPO`   | `<N=8>(In, Clk) -> (Q[N])`                   | serial-in / parallel-out |
| `ShiftRegPISO`   | `<N=8>(D[N], LD, Clk) -> (Out)`              | parallel-in / serial-out |
| `UniversalShift` | `<N=8>(D[N], L, R, Mode[2], Clk) -> (Q[N])`  | load / shiftL / shiftR / hold |
| `RippleCounter`  | `<N=4>(Clk) -> (Q[N])`                       | asynchronous ripple up-counter |
| `SyncCounter`    | `<N=4>(Clk, EN) -> (Q[N])`                   | synchronous up-counter w/ enable |
| `UpDownCounter`  | `<N=4>(Clk, Up) -> (Q[N])`                   | direction-controlled counter |
| `RingCounter`    | `<N=4>(Clk) -> (Q[N])`                       | self-starting one-hot ring |
| `JohnsonCounter` | `<N=4>(Clk) -> (Q[N])`                       | twisted-ring (Johnson) counter |

Dependencies: none (the seeded latch loops must own raw primitives). Verify
with `cc.py check seq`.
