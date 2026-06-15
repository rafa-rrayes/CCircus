# shift

Shifters and rotators for Circuit Circus — pure combinational mux networks, no
clock involved. Each variable shift is a log-depth barrel of three stages,
stage k selecting (via `mux::BusMux2`) between "no shift" and "shift by 2^k"
on bit `Sh[k]` — amounts 1, 2, 4 for the three select bits.

```shdl
use shift::{BarrelShifter, ArithShiftR, BitReverse};
```

| Component       | Ports                                          | Notes |
|-----------------|------------------------------------------------|-------|
| `ShiftLeft`     | `<N=8>(A[N], Sh[3]) -> (O[N])`                 | logical left by Sh |
| `ShiftRight`    | `<N=8>(A[N], Sh[3]) -> (O[N])`                 | logical right by Sh |
| `ArithShiftR`   | `<N=8>(A[N], Sh[3]) -> (O[N])`                 | sign-extending right |
| `BarrelShifter` | `<N=8>(A[N], Sh[3], Dir) -> (O[N])`            | Dir=0 left, Dir=1 right |
| `BarrelRotator` | `<N=8>(A[N], Sh[3]) -> (O[N])`                 | rotate left, no bits lost |
| `FunnelShifter` | `<N=8>(Hi[N], Lo[N], Sh[3]) -> (O[N])`         | shift the 2N window {Hi,Lo} right by Sh |
| `BitReverse`    | `<N=8>(A[N]) -> (O[N])`                         | reverse bit order (pure wiring) |

Bit 1 is the LSB; `Sh` is the shift amount as an integer (0..7 at N=8).
`FunnelShifter` returns `O[i] = {Hi,Lo}[i+Sh]` (Lo is the low half).
`BitReverse` is `O[i] = A[N-i+1]` — no gates.

Dependencies: `mux`. Verify with `cc.py check shift`.
