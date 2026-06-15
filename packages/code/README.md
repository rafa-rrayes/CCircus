# code

Encoding, decoding & error-correcting codes — combinational XOR / logic
networks. Built on the six SHDL primitives plus `gates::{XorN, OrN}`; the
internal adders are raw-gate full adders, so the only dependency is `gates`.

```shdl
use code::{BinToGray, HammingEncode, SevenSegDecoder, ParityGen};
```

| Component         | Ports                                       | Notes |
|-------------------|---------------------------------------------|-------|
| `BinToGray`       | `<N=8>(B[N]) -> (G[N])`                      | Gray = B XOR (B>>1) |
| `GrayToBin`       | `<N=8>(G[N]) -> (B[N])`                      | prefix-XOR inverse |
| `BinToBcd`        | `<N=8>(B[N]) -> (Bcd[12])`                   | combinational double-dabble |
| `BcdToBin`        | `<D=2>(Bcd[4*D]) -> (B[7])`                  | weighted-sum BCD→binary |
| `BcdAdder`        | `(A[4], B[4], Cin) -> (S[4], Cout)`         | one-digit decimal add (+6 fix) |
| `SevenSegDecoder` | `(Hex[4]) -> (Seg[7])`                       | hex digit → 7-seg pattern |
| `ParityGen`       | `<N=8>(D[N]) -> (P)`                         | even parity = XOR of all bits |
| `ParityCheck`     | `<N=8>(D[N], P) -> (Err)`                    | `Err = XorN(D) XOR P` |
| `HammingEncode`   | `(D[4]) -> (Code[7])`                        | Hamming(7,4) encoder |
| `HammingDecode`   | `(Code[7]) -> (D[4], Err)`                   | Hamming(7,4) SEC decoder |

Bit 1 is the LSB throughout. All components are combinational; tests use
vector tables with a 64-step settle budget.

## Encodings

**BCD (packed).** Each decimal digit is a 4-bit nibble, little-endian by digit:
`Bcd[1:4]` = ones, `Bcd[5:8]` = tens, `Bcd[9:12]` = hundreds. `BinToBcd` covers
an 8-bit value (0..255 → 3 digits) via a combinational double-dabble
(shift-and-add-3) pipeline of 8 stages; only the ones and tens nibbles can
reach ≥5, so the +3 fix is applied there. `BcdToBin` at `D=2` reads
`Bcd[1:4]` (ones) + `Bcd[5:8]` (tens) and returns `tens*10 + ones` as a 7-bit
binary value (`tens*10 = (tens<<3) + (tens<<1)`, summed by raw-gate adders).

**Seven-segment (hex font).** `Seg[1]=a, Seg[2]=b, Seg[3]=c, Seg[4]=d,
Seg[5]=e, Seg[6]=f, Seg[7]=g`, active-high (common-cathode). The integer read
back from `Seg` is `a + 2b + 4c + 8d + 16e + 32f + 64g`. Standard hex font:

| v | pattern (a b c d e f g) | Seg int |
|---|--------------------------|---------|
| 0 | 1 1 1 1 1 1 0 | 63  |
| 1 | 0 1 1 0 0 0 0 | 6   |
| 2 | 1 1 0 1 1 0 1 | 91  |
| 3 | 1 1 1 1 0 0 1 | 79  |
| 4 | 0 1 1 0 0 1 1 | 102 |
| 5 | 1 0 1 1 0 1 1 | 109 |
| 6 | 1 0 1 1 1 1 1 | 125 |
| 7 | 1 1 1 0 0 0 0 | 7   |
| 8 | 1 1 1 1 1 1 1 | 127 |
| 9 | 1 1 1 1 0 1 1 | 111 |
| A | 1 1 1 0 1 1 1 | 119 |
| b | 0 0 1 1 1 1 1 | 124 |
| C | 1 0 0 1 1 1 0 | 57  |
| d | 0 1 1 1 1 0 1 | 94  |
| E | 1 0 0 1 1 1 1 | 121 |
| F | 1 0 0 0 1 1 1 | 113 |

Each segment is the OR of the value-minterms that light it (a 4→16 minterm
decoder feeds a `gates::OrN<16>` per segment, GND-padded for non-members).

**Hamming(7,4).** Parity-bit positions 1, 2, 4; data positions 3, 5, 6, 7.
`Code[j]` is the bit at position `j` (`Code[1]`=LSB). Data maps
`D[1]→pos3, D[2]→pos5, D[3]→pos6, D[4]→pos7`. Parity:
`p1 = d1^d2^d4`, `p2 = d1^d3^d4`, `p4 = d2^d3^d4`. The decoder forms the
syndrome `s1 = c1^c3^c5^c7`, `s2 = c2^c3^c6^c7`, `s4 = c4^c5^c6^c7`; the
syndrome value `s1 + 2*s2 + 4*s4` is the flipped position (0 = clean). Each
data bit is XORed with `(syndrome == its position)` to correct a single error,
and `Err = s1 | s2 | s4`.

Dependencies: `gates`. Verify with `cc.py check code`.
