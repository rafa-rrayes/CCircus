# arith

Arithmetic & comparison for Circuit Circus — adders whose carry you can watch
ripple, faster adders that visibly settle sooner, and the building blocks of a
datapath. Everything is composed from the six SHDL primitives plus a few gates
from `gates`; there is no behavioral arithmetic.

```shdl
use arith::{RippleAdder, ALU};
```

| Component         | Ports                                          | Notes |
|-------------------|------------------------------------------------|-------|
| `HalfAdder`       | `(A, B) -> (Sum, Cout)`                        | half adder |
| `FullAdder`       | `(A, B, Cin) -> (Sum, Cout)`                   | the arithmetic unit cell |
| `RippleAdder`     | `<N=8>(A[N], B[N], Cin) -> (Sum[N], Cout)`     | carry-ripple; depth ∝ N |
| `CarryLookahead`  | `<N=8>(A[N], B[N], Cin) -> (Sum[N], Cout)`     | flat generate/propagate carries; few levels |
| `CarrySelect`     | `<N=16>(A[N], B[N], Cin) -> (Sum[N], Cout)`    | speculative high half, selected by low carry |
| `CarrySave`       | `<N=8>(A[N], B[N], C[N]) -> (S[N], Cy[N])`     | 3:2 compressor row (no horizontal carry) |
| `Subtractor`      | `<N=8>(A[N], B[N], Bin) -> (Diff[N], Bout)`    | borrow subtractor (two's complement) |
| `AddSub`          | `<N=8>(A[N], B[N], Sub) -> (R[N], Cout)`       | add (Sub=0) / subtract (Sub=1) |
| `Incrementer`     | `<N=8>(A[N]) -> (O[N], Cout)`                  | A + 1 |
| `Decrementer`     | `<N=8>(A[N]) -> (O[N], Bout)`                  | A − 1; `Bout` = underflow at A=0 |
| `Negate`          | `<N=8>(A[N]) -> (O[N])`                        | two's-complement negation `~A + 1` |
| `EqComparator`    | `<N=8>(A[N], B[N]) -> (Eq)`                    | equality |
| `MagComparator`   | `<N=8>(A[N], B[N]) -> (Lt, Eq, Gt)`           | unsigned magnitude compare |
| `ArrayMultiplier` | `<N=8>(A[N], B[N]) -> (P[2N])`                | unsigned array multiplier (product width 2N) |
| `Divider`         | `<N=8>(A[N], B[N]) -> (Q[N], R[N])`           | restoring unsigned divide (B≠0) |
| `ALU`             | `<N=8>(A[N], B[N], Op[3]) -> (Y[N], Cout, Zero)` | 8-op ALU with flags |

## Conventions

Bit 1 is the LSB; buses are 1-indexed. All arithmetic is **two's complement**:
`A - B = A + ~B + 1`, so subtraction, `AddSub`, and `Negate` invert the operand
and inject a carry. `Cout` on the subtract path is a *no-borrow* indicator
(1 ⇒ `A ≥ B` unsigned); `Bout` is its inverse. Results wrap mod 2ᴺ.

These circuits are combinational but **deep** — an 8-bit array multiplier or
restoring divider is dozens of gate levels — so test vectors use a generous
`steps` budget (128–256) to let every output settle.

## ALU operation encoding

`Op[1]` is the LSB. `Cout` is meaningful for the arithmetic ops (100–111);
`Zero` is set when `Y == 0`.

| `Op` | Operation     | `Op` | Operation        |
|------|---------------|------|------------------|
| 000  | `Y = A AND B` | 100  | `Y = A + B`      |
| 001  | `Y = A OR B`  | 101  | `Y = A − B`      |
| 010  | `Y = A XOR B` | 110  | `Y = A + 1`      |
| 011  | `Y = NOT A`   | 111  | `Y = A − 1`      |

Dependencies: `gates`. Verify with `cc.py check arith`.
