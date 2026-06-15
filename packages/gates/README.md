# gates

Universal & wide gates above the six SHDL primitives — the derived and
reduction gates everything else in Circuit Circus is written in terms of.

```shdl
use gates::{Nand, XorN, BitAnd, Majority3};
```

| Component   | Ports                                  | Notes |
|-------------|----------------------------------------|-------|
| `Nand`      | `(A, B) -> (O)`                        | universal gate |
| `Nor`       | `(A, B) -> (O)`                        | universal gate |
| `Xnor`      | `(A, B) -> (O)`                        | 1-bit equality |
| `Buffer`    | `(A) -> (O)`                           | identity / fan-out |
| `AndN`      | `<N=4>(A[N]) -> (O)`                   | AND reduction (N≥2) |
| `OrN`       | `<N=4>(A[N]) -> (O)`                   | OR reduction (N≥2) |
| `XorN`      | `<N=4>(A[N]) -> (O)`                   | XOR / parity reduction (N≥2) |
| `BitAnd`    | `<N=8>(A[N], B[N]) -> (O[N])`          | bitwise bus AND |
| `BitOr`     | `<N=8>(A[N], B[N]) -> (O[N])`          | bitwise bus OR |
| `BitXor`    | `<N=8>(A[N], B[N]) -> (O[N])`          | bitwise bus XOR |
| `BitNot`    | `<N=8>(A[N]) -> (O[N])`                | bus inverter / one's complement |
| `Majority3` | `(A, B, C) -> (O)`                     | 3-input voter (adder carry kernel) |

Dependencies: none. Verify with `cc.py check gates`.
