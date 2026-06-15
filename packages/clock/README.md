# clock

Oscillators, frequency dividers, edge logic, and PWM — the timing layer above
`seq`. Everything except the ring oscillator composes `seq` flip-flops and
counters, whose `init` seeds carry through flattening; the ring oscillator owns
raw inverters because an odd inverter loop has no fixed point to seed.

```shdl
use clock::{RingOscillator, ClockDivideByN, EdgeRising, PwmGenerator};
```

| Component        | Ports                                  | Notes |
|------------------|----------------------------------------|-------|
| `RingOscillator` | `() -> (Clk)`                          | free-running, period = 2·loop length (6 cycles) |
| `ClockDivideBy2` | `(Clk) -> (Out)`                       | toggle FF; halves frequency |
| `ClockDivideByN` | `<N=10>(Clk) -> (Out)`                 | Johnson-counter ÷N square wave; **N even** |
| `PulseGenerator` | `(Trig, Clk) -> (Pulse)`               | one-shot: one pulse per `Trig` rise |
| `EdgeRising`     | `(In, Clk) -> (Edge)`                  | `Edge = In AND NOT prev` |
| `EdgeFalling`    | `(In, Clk) -> (Edge)`                  | `Edge = NOT In AND prev` |
| `Debouncer`      | `<N=8>(In, Clk) -> (Out)`              | adopts a value after N agreeing samples; rejects glitches |
| `PwmGenerator`   | `<N=8>(Duty[N], Clk) -> (Out)`         | `Out` high while counter `< Duty`; duty = `Duty/2^N` |

**Timing note.** The synchronous parts are unit-delay: drive `Clk` 0→1 with
enough `step`s between edges to let the master-slave flip-flops settle. The
`Pulse`/`Edge` outputs go high asynchronously when their input changes and
clear at the next clock edge — sample them in that window.

Dependencies: `seq`. Verify with `cc.py check clock`.
