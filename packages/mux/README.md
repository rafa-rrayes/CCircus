# mux

Selection & routing for Circuit Circus. Because SHDL has no tri-state, *all*
data routing happens through multiplexers — never a shared driver. Every
component is a netlist of the six primitives.

```shdl
use mux::{Mux2, BusMux2, Decoder3to8, PriorityEnc8};
```

| Component      | Ports                                       | Notes |
|----------------|---------------------------------------------|-------|
| `Mux2`         | `(D0, D1, S) -> (O)`                         | 2:1 mux, 1 bit |
| `Mux4`         | `(D[4], S[2]) -> (O)`                        | 4:1 mux (tree of 2:1) |
| `Mux8`         | `(D[8], S[3]) -> (O)`                        | 8:1 mux |
| `MuxN`         | `<W=4,S=2>(D[W*2^S], Sel[S]) -> (O[W])`      | 2^S-input, W-bit-wide mux (one-hot) |
| `BusMux2`      | `<N=8>(A[N], B[N], S) -> (O[N])`             | 2:1 select between two buses |
| `Demux2`       | `(D, S) -> (O0, O1)`                         | 1:2 demux |
| `Demux4`       | `(D, S[2]) -> (O[4])`                        | 1:4 demux |
| `Demux8`       | `(D, S[3]) -> (O[8])`                        | 1:8 demux |
| `Decoder2to4`  | `(A[2], EN) -> (O[4])`                       | 2→4 one-hot, enable-gated |
| `Decoder3to8`  | `(A[3], EN) -> (O[8])`                       | 3→8 one-hot |
| `DecoderN`     | `<N=3>(A[N], EN) -> (O[2^N])`                | generic n→2ⁿ one-hot |
| `Encoder8to3`  | `(D[8]) -> (O[3])`                           | binary encoder (one-hot → index) |
| `PriorityEnc8` | `(D[8]) -> (O[3], Valid)`                    | priority encoder + valid flag |

Bit 1 is the LSB. Decoder/demux line `j` is the one-hot output for address
`j-1`. `Encoder8to3` assumes a one-hot input; `PriorityEnc8` returns the index
of the highest set bit and a `Valid` flag.

Dependencies: none. Verify with `cc.py check mux`.
