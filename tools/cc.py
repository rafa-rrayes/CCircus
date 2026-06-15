#!/usr/bin/env python3
"""cc.py — Circuit Circus build & verify tool.

Every package in Circuit Circus is verified the same way: each exported
component is flattened (SHDL -> Base SHDL), compiled to C, loaded through
PySHDL, and simulated against its test vectors. This tool is that loop.

It must run inside (or with access to) the SHDL toolchain environment, since
it imports ``SHDL`` (the PySHDL driver) and ``flattener``. It finds the
toolchain in one of three ways, in order:

  1. an installed ``PySHDL`` package (``pip install PySHDL`` / ``uv add PySHDL``);
  2. a sibling ``shdlc`` checkout next to this repo (the default);
  3. an explicit ``SHDLC_ROOT`` pointing at a toolchain checkout.

    uv run python tools/cc.py check gates              # sibling ../shdlc, or installed PySHDL
    SHDLC_ROOT=/path/to/shdlc uv run python tools/cc.py check gates   # explicit checkout

Subcommands:
    build <pkg> [pkg...]   flatten+compile every exported component (no vectors)
    test  <pkg> [pkg...]   run the package's test vectors
    check <pkg> [pkg...]   build + test
    all                    check every package listed in registry.json

Exit status is non-zero if any component fails to build or any vector fails.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# --- locate the toolchain -------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent          # the CCircus repo root
# Default to a sibling `shdlc` checkout next to this repo; `SHDLC_ROOT`
# overrides. An installed `PySHDL` is used as-is when neither is present.
SHDLC_ROOT = Path(os.environ.get("SHDLC_ROOT", ROOT.parent / "shdlc"))
if SHDLC_ROOT.is_dir() and str(SHDLC_ROOT) not in sys.path:
    sys.path.insert(0, str(SHDLC_ROOT))

try:
    from SHDL import Circuit
    from SHDL.errors import PySHDLError
except Exception as e:  # pragma: no cover - environment guard
    sys.stderr.write(
        f"cc.py: cannot import the SHDL toolchain ({e}).\n"
        f"Install it (pip install PySHDL), or point SHDLC_ROOT at an shdlc\n"
        f"checkout, then re-run:  uv run python {Path(__file__).name} check <pkg>\n"
    )
    raise SystemExit(2)

PKG_DIR = ROOT / "packages"


# --- manifest / dependency resolution ------------------------------------
def load_manifest(pkg: str) -> dict:
    mpath = PKG_DIR / pkg / "package.json"
    if not mpath.is_file():
        raise SystemExit(f"cc.py: no manifest for package {pkg!r} at {mpath}")
    return json.loads(mpath.read_text())


def include_dirs_for(pkg: str, seen: set[str] | None = None) -> list[str]:
    """Transitive dependency package dirs, for the flattener's -I search."""
    seen = seen if seen is not None else set()
    dirs: list[str] = []
    for dep in load_manifest(pkg).get("dependencies", {}):
        if dep in seen:
            continue
        seen.add(dep)
        dirs.append(str(PKG_DIR / dep))
        dirs.extend(include_dirs_for(dep, seen))
    return dirs


def module_path(pkg: str, manifest: dict) -> Path:
    return PKG_DIR / pkg / manifest.get("module", f"{pkg}.shdl")


# --- the verification primitives -----------------------------------------
def _open(pkg: str, manifest: dict, top: str) -> Circuit:
    return Circuit(
        str(module_path(pkg, manifest)),
        top=top,
        include_dirs=include_dirs_for(pkg),
    )


def build_pkg(pkg: str) -> tuple[int, int]:
    """Flatten+compile every export. Returns (passed, total)."""
    manifest = load_manifest(pkg)
    exports = manifest.get("exports", [])
    ok = 0
    for exp in exports:
        name = exp["name"]
        try:
            c = _open(pkg, manifest, name)
            c.close()
            ok += 1
        except (PySHDLError, Exception) as e:  # noqa: BLE001 - report any failure
            print(f"  FAIL build  {pkg}::{name}: {type(e).__name__}: {e}")
    print(f"[build] {pkg}: {ok}/{len(exports)} components compiled")
    return ok, len(exports)


def _replay_ops(c: Circuit, ops: list[dict]) -> list[str]:
    fails: list[str] = []
    for op in ops:
        kind = op["op"]
        if kind == "reset":
            c.reset()
        elif kind == "poke":
            c.poke(op["signal"], op["value"])
        elif kind == "step":
            c.step(op.get("cycles", 1))
        elif kind == "expect":
            got = c.peek(op["signal"])
            if got != op["value"]:
                fails.append(f"{op['signal']}={got} (want {op['value']})")
        else:
            fails.append(f"unknown op {kind!r}")
    return fails


def test_pkg(pkg: str) -> tuple[int, int]:
    """Run test vectors. Returns (passed_cases, total_cases)."""
    manifest = load_manifest(pkg)
    tfile = PKG_DIR / pkg / "tests" / f"{pkg}.tests.json"
    if not tfile.is_file():
        print(f"[test]  {pkg}: no test file ({tfile.name}) — skipped")
        return 0, 0
    spec = json.loads(tfile.read_text())
    passed = total = 0
    for case in spec.get("cases", []):
        comp = case["component"]
        total += 1
        try:
            c = _open(pkg, manifest, comp)
        except Exception as e:  # noqa: BLE001
            print(f"  FAIL  {pkg}::{comp}: build error: {e}")
            continue
        try:
            fails: list[str] = []
            if "ops" in case:  # explicit op sequence (sequential/timing)
                fails = _replay_ops(c, case["ops"])
            else:  # vector table (combinational): reset, poke ins, step, check outs
                steps = case.get("steps", 64)
                for v in case["vectors"]:
                    c.reset()
                    for sig, val in v["in"].items():
                        c.poke(sig, val)
                    c.step(steps)
                    for sig, want in v["out"].items():
                        got = c.peek(sig)
                        if got != want:
                            fails.append(f"in={v['in']} {sig}={got} (want {want})")
            if fails:
                print(f"  FAIL  {pkg}::{comp}: " + "; ".join(fails[:6]))
            else:
                passed += 1
                print(f"  ok    {pkg}::{comp}")
        finally:
            c.close()
    print(f"[test]  {pkg}: {passed}/{total} cases green")
    return passed, total


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    cmd, rest = argv[0], argv[1:]
    if cmd == "all":
        reg = json.loads((ROOT / "registry.json").read_text())
        rest = [p["name"] for p in reg["packages"]]
        cmd = "check"
    if cmd not in {"build", "test", "check"} or not rest:
        print(__doc__)
        return 1

    bad = 0
    for pkg in rest:
        if cmd in {"build", "check"}:
            ok, tot = build_pkg(pkg)
            bad += tot - ok
        if cmd in {"test", "check"}:
            ok, tot = test_pkg(pkg)
            bad += tot - ok
    print(f"\n{'OK' if bad == 0 else 'FAIL'}: {bad} problem(s)")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
