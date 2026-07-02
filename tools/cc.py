#!/usr/bin/env python3
"""cc.py — Circuit Circus build, verify & index tool.

Every package in Circuit Circus is verified the same way: each exported
component is flattened (SHDL -> Base SHDL), compiled to C, loaded through
PySHDL, and simulated against its test vectors. This tool is that loop, plus
the generator for the hosted index (INDEX_FORMAT.md).

Subcommands:
    build <pkg> [pkg...]    flatten+compile every exported component (no vectors)
    test  <pkg> [pkg...]    run the package's test vectors
    check <pkg> [pkg...]    build + test
    all                     check every package under packages/
    gen-index [--check] [--out DIR]
                            validate every manifest and (re)generate
                            registry.json, index/*.json and the versioned
                            archives; --check verifies the committed index is
                            byte-identical to a fresh regeneration instead.

``build``/``test``/``check``/``all`` need the SHDL toolchain; they find it as

  1. an installed ``pyshdl`` package (``pip install pyshdl``);
  2. a sibling ``shdlc`` checkout next to this repo (the default);
  3. an explicit ``SHDLC_ROOT`` pointing at a toolchain checkout.

``gen-index`` is pure stdlib — it runs with no toolchain and no C compiler.

Exit status: 0 on success, 1 if any component fails to build, any vector
fails, or ``gen-index --check`` finds drift; 2 on usage or manifest errors.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # the CCircus repo root
PKG_DIR = ROOT / "packages"

REGISTRY_NAME = "Circuit Circus"
REGISTRY_HOMEPAGE = "https://github.com/rafa-rrayes/CCircus"

MANIFEST_REQUIRED = (
    "manifest_format", "name", "version", "summary", "license",
    "authors", "shdl", "module", "dependencies", "exports",
)
EXPORT_REQUIRED = ("name", "summary", "params", "inputs", "outputs")


class CCError(Exception):
    """A diagnosed failure; main() prints it and exits 2."""


# --- the toolchain, imported lazily (build/test only) ----------------------
_TOOLCHAIN: tuple | None = None


def _toolchain() -> tuple:
    """(Circuit, PySHDLError) — installed pyshdl, sibling ../shdlc, or $SHDLC_ROOT."""
    global _TOOLCHAIN
    if _TOOLCHAIN is not None:
        return _TOOLCHAIN
    shdlc_root = Path(os.environ.get("SHDLC_ROOT", ROOT.parent / "shdlc"))
    if shdlc_root.is_dir() and str(shdlc_root) not in sys.path:
        sys.path.insert(0, str(shdlc_root))
    try:
        from SHDL import Circuit
        from SHDL.errors import PySHDLError
    except Exception as e:
        raise CCError(
            f"cannot import the SHDL toolchain ({e}).\n"
            "Install it (pip install pyshdl), or point SHDLC_ROOT at an shdlc\n"
            "checkout, then re-run."
        ) from e
    _TOOLCHAIN = (Circuit, PySHDLError)
    return _TOOLCHAIN


# --- semver (INDEX_FORMAT.md §6; shdl_cli/semver.py is the client twin) ----
def parse_version(s: str) -> tuple[int, int, int]:
    parts = s.split(".")
    if len(parts) != 3:
        raise CCError(f"invalid version {s!r} (want X.Y.Z)")
    nums = []
    for p in parts:
        if not p.isdigit() or (len(p) > 1 and p[0] == "0"):
            raise CCError(f"invalid version {s!r} (want X.Y.Z, no leading zeros)")
        nums.append(int(p))
    return tuple(nums)  # type: ignore[return-value]


def _caret_upper(v: tuple[int, int, int]) -> tuple[int, int, int]:
    x, y, z = v
    if x:
        return (x + 1, 0, 0)
    if y:
        return (0, y + 1, 0)
    return (0, 0, z + 1)


def range_satisfied(spec: str, v: tuple[int, int, int]) -> bool:
    """Does version ``v`` satisfy ``spec`` (comma = AND)? Raises on bad grammar."""
    parts = [p.strip() for p in spec.split(",")]
    if not spec.strip() or not all(parts):
        raise CCError(f"invalid version range {spec!r}")
    for part in parts:
        if part.startswith("^"):
            lo = parse_version(part[1:].strip())
            if not (lo <= v < _caret_upper(lo)):
                return False
        elif part.startswith(">="):
            if not v >= parse_version(part[2:].strip()):
                return False
        elif part.startswith("<="):
            if not v <= parse_version(part[2:].strip()):
                return False
        elif part.startswith(">"):
            if not v > parse_version(part[1:].strip()):
                return False
        elif part.startswith("<"):
            if not v < parse_version(part[1:].strip()):
                return False
        else:
            if v != parse_version(part):
                return False
    return True


# --- manifest / dependency resolution ---------------------------------------
def discover_packages() -> list[str]:
    """Sorted names of every directory under packages/ with a package.json."""
    if not PKG_DIR.is_dir():
        raise CCError(f"no packages directory at {PKG_DIR}")
    return sorted(p.name for p in PKG_DIR.iterdir() if (p / "package.json").is_file())


def load_manifest(pkg: str) -> dict:
    mpath = PKG_DIR / pkg / "package.json"
    if not mpath.is_file():
        raise CCError(f"no manifest for package {pkg!r} at {mpath}")
    try:
        return json.loads(mpath.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise CCError(f"{mpath}: invalid JSON: {e}") from e


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


# --- the verification primitives ---------------------------------------------
def _open(pkg: str, manifest: dict, top: str):
    Circuit, _ = _toolchain()
    return Circuit(
        str(module_path(pkg, manifest)),
        top=top,
        include_dirs=include_dirs_for(pkg),
    )


def build_pkg(pkg: str) -> tuple[int, int]:
    """Flatten+compile every export. Returns (passed, total)."""
    _, PySHDLError = _toolchain()
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


def _replay_ops(c, ops: list[dict]) -> list[str]:
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
    tfile = PKG_DIR / pkg / manifest.get("tests", f"tests/{pkg}.tests.json")
    if not tfile.is_file():
        print(f"[test]  {pkg}: no test file ({tfile.name}) — skipped")
        return 0, 0
    spec = json.loads(tfile.read_text(encoding="utf-8"))
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


# --- tree validation (gen-index, pure stdlib) --------------------------------
def validate_tree() -> dict[str, dict]:
    """Validate every manifest + the cross-package invariants.

    Returns {package name: manifest}, or raises CCError listing every
    violation found (INDEX_FORMAT.md §7, rules 1-6).
    """
    errors: list[str] = []
    manifests: dict[str, dict] = {}
    for pkg in discover_packages():
        try:
            m = load_manifest(pkg)
        except CCError as e:
            errors.append(str(e))
            continue
        missing = [f for f in MANIFEST_REQUIRED if f not in m]
        if missing:
            errors.append(f"{pkg}: manifest missing required fields: {', '.join(missing)}")
            continue
        if m["manifest_format"] != 1:
            errors.append(f"{pkg}: unsupported manifest_format {m['manifest_format']!r}")
        if m["name"] != pkg:
            errors.append(f"{pkg}: manifest name {m['name']!r} != directory name")
        if m["module"] != f"{pkg}.shdl":
            errors.append(f"{pkg}: module {m['module']!r} != {pkg}.shdl")
        if not (PKG_DIR / pkg / m["module"]).is_file():
            errors.append(f"{pkg}: module file {m['module']} does not exist")
        if not m["authors"]:
            errors.append(f"{pkg}: authors must list at least one author")
        try:
            parse_version(m["version"])
        except CCError as e:
            errors.append(f"{pkg}: {e}")
        if not isinstance(m["exports"], list) or not m["exports"]:
            errors.append(f"{pkg}: exports must be a non-empty array")
        else:
            for i, exp in enumerate(m["exports"]):
                missing = [f for f in EXPORT_REQUIRED if f not in exp]
                if missing:
                    errors.append(
                        f"{pkg}: exports[{i}] missing fields: {', '.join(missing)}"
                    )
        manifests[pkg] = m

    # dependency ranges: parse, target exists, satisfied by the on-disk version
    for pkg, m in manifests.items():
        for dep, spec in m.get("dependencies", {}).items():
            if dep not in manifests:
                errors.append(f"{pkg}: dependency {dep!r} is not a package in packages/")
                continue
            try:
                dep_v = parse_version(manifests[dep]["version"])
                if not range_satisfied(spec, dep_v):
                    errors.append(
                        f"{pkg}: dependency {dep} {spec!r} is not satisfied by "
                        f"the on-disk {dep} {manifests[dep]['version']}"
                    )
            except CCError as e:
                errors.append(f"{pkg}: dependency {dep}: {e}")

    # acyclic dependency graph (iterative DFS, 0=white 1=grey 2=black)
    color: dict[str, int] = {}
    for start in manifests:
        if color.get(start):
            continue
        stack: list[tuple[str, list[str]]] = [(start, [start])]
        color[start] = 1
        while stack:
            node, path = stack[-1]
            for dep in manifests[node].get("dependencies", {}):
                if dep not in manifests:
                    continue
                st = color.get(dep, 0)
                if st == 1:
                    cycle = path[path.index(dep):] if dep in path else path
                    errors.append("dependency cycle: " + " -> ".join([*cycle, dep]))
                elif st == 0:
                    color[dep] = 1
                    stack.append((dep, [*path, dep]))
                    break
            else:
                color[node] = 2
                stack.pop()

    # registry-wide uniqueness: exported component names and module basenames
    seen_exports: dict[str, str] = {}
    seen_modules: dict[str, str] = {}
    for pkg, m in manifests.items():
        mod = m["module"]
        if mod in seen_modules:
            errors.append(
                f"module name collision: {pkg} and {seen_modules[mod]} both ship {mod}"
            )
        else:
            seen_modules[mod] = pkg
        for exp in m.get("exports", []):
            name = exp.get("name")
            if not name:
                continue
            if name in seen_exports and seen_exports[name] != pkg:
                errors.append(
                    f"export name collision: {name!r} is exported by both "
                    f"{seen_exports[name]} and {pkg}"
                )
            else:
                seen_exports[name] = pkg

    if errors:
        raise CCError("invalid package tree:\n  " + "\n  ".join(errors))
    return manifests


# --- deterministic archives (INDEX_FORMAT.md §4) -----------------------------
def _archive_members(pkg: str, manifest: dict) -> list[tuple[str, Path]]:
    """Whitelisted (member name, source path) pairs, sorted by member name."""
    pdir = PKG_DIR / pkg
    prefix = f"{pkg}-{manifest['version']}"
    rels = ["package.json", manifest["module"]]
    if (pdir / "README.md").is_file():
        rels.append("README.md")
    tests_dir = pdir / "tests"
    if tests_dir.is_dir():
        for f in sorted(tests_dir.rglob("*")):
            if f.is_symlink():
                raise CCError(f"{pkg}: symlinks are not allowed in packages ({f})")
            if f.is_file():
                rels.append(f.relative_to(pdir).as_posix())
    members = []
    for rel in rels:
        f = pdir / rel
        if f.is_symlink():
            raise CCError(f"{pkg}: symlinks are not allowed in packages ({f})")
        if not f.is_file():
            raise CCError(f"{pkg}: archive member missing on disk: {rel}")
        members.append((f"{prefix}/{rel}", f))
    return sorted(members)


def build_tar(pkg: str, manifest: dict) -> bytes:
    """The package's inner tar stream, built exactly per the determinism recipe.

    The tar layer is byte-deterministic everywhere. The gzip envelope is
    written once at publish time (`_gzip`) and never regenerated: archive
    equality is always judged on these tar bytes, so a platform's zlib
    producing different compressed bytes can never fail a check.
    """
    buf = io.BytesIO()
    with tarfile.open(mode="w", fileobj=buf, format=tarfile.USTAR_FORMAT) as tar:
        for name, path in _archive_members(pkg, manifest):
            data = path.read_bytes()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mtime = 0
            info.mode = 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _gzip(tar_bytes: bytes) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", filename="", mtime=0) as gz:
        gz.write(tar_bytes)
    return buf.getvalue()


def _gunzip(blob: bytes, rel: str) -> bytes:
    try:
        return gzip.decompress(blob)
    except OSError as e:
        raise CCError(f"{rel}: committed archive is not valid gzip: {e}") from e


# --- the index generator (INDEX_FORMAT.md §2-3) -------------------------------
def _json_bytes(obj) -> bytes:
    return (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _version_entry(manifest: dict, archive_rel: str, sha256: str, size: int) -> dict:
    return {
        "summary": manifest["summary"],
        "description": manifest.get("description", ""),
        "license": manifest["license"],
        "authors": manifest["authors"],
        "homepage": manifest.get("homepage", ""),
        "keywords": manifest.get("keywords", []),
        "shdl": manifest["shdl"],
        "module": manifest["module"],
        "dependencies": manifest["dependencies"],
        "archive": archive_rel,
        "sha256": sha256,
        "size": size,
        "exports": manifest["exports"],
    }


def generate_index() -> dict[str, bytes]:
    """{repo-relative path: exact bytes} for every generated file.

    Merges against the committed index/ (published versions are kept
    untouched, the current version is upserted) and hard-errors on any
    attempt to republish a version with different archive bytes.
    """
    manifests = validate_tree()
    outputs: dict[str, bytes] = {}
    registry_pkgs = []
    for pkg, m in sorted(manifests.items()):
        ver = m["version"]
        tar_bytes = build_tar(pkg, m)
        archive_rel = f"archives/{pkg}-{ver}.tar.gz"

        committed_archive = ROOT / archive_rel
        if committed_archive.is_file():
            blob = committed_archive.read_bytes()
            if _gunzip(blob, archive_rel) != tar_bytes:
                raise CCError(
                    f"{pkg} {ver}: package files changed but the version was not "
                    f"bumped — published archives are immutable; bump the version"
                )
        else:
            blob = _gzip(tar_bytes)
        sha = hashlib.sha256(blob).hexdigest()

        index_rel = f"index/{pkg}.json"
        committed_index = ROOT / index_rel
        versions: dict[str, dict] = {}
        if committed_index.is_file():
            try:
                versions = dict(json.loads(committed_index.read_text(encoding="utf-8"))["versions"])
            except (json.JSONDecodeError, KeyError) as e:
                raise CCError(f"{index_rel}: corrupt committed index: {e}") from e
        prior = versions.get(ver)
        if prior is not None and prior["sha256"] != sha:
            raise CCError(
                f"{pkg} {ver}: archive sha256 differs from the published entry in "
                f"{index_rel} — published versions are immutable; bump the version"
            )
        versions[ver] = _version_entry(m, archive_rel, sha, len(blob))
        ordered = dict(sorted(versions.items(), key=lambda kv: parse_version(kv[0])))
        latest = max(ordered, key=parse_version)
        outputs[index_rel] = _json_bytes(
            {"index_format": 2, "name": pkg, "latest": latest, "versions": ordered}
        )
        outputs[archive_rel] = blob

        lv = ordered[latest]
        registry_pkgs.append(
            {
                "name": pkg,
                "version": latest,
                "summary": lv["summary"],
                "keywords": lv["keywords"],
                "circuits": len(lv["exports"]),
                "dependencies": lv["dependencies"],
                "index": index_rel,
                "archive": lv["archive"],
                "sha256": lv["sha256"],
            }
        )
    outputs["registry.json"] = _json_bytes(
        {
            "registry_format": 2,
            "name": REGISTRY_NAME,
            "homepage": REGISTRY_HOMEPAGE,
            "packages": registry_pkgs,
        }
    )
    return outputs


def gen_index(check: bool, out_dir: str | None) -> int:
    outputs = generate_index()
    if check:
        drifted = []
        for rel, blob in sorted(outputs.items()):
            committed = ROOT / rel
            if not committed.is_file():
                drifted.append(f"missing: {rel}")
            elif committed.read_bytes() != blob:
                drifted.append(f"stale:   {rel}")
        if drifted:
            print("index drift — run `python tools/cc.py gen-index` and commit:")
            for line in drifted:
                print(f"  {line}")
            return 1
        print(f"index up to date ({len(outputs)} generated files match)")
        return 0
    root = Path(out_dir) if out_dir else ROOT
    written = kept = 0
    for rel, blob in sorted(outputs.items()):
        dest = root / rel
        if dest.is_file() and dest.read_bytes() == blob:
            kept += 1
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(blob)
        written += 1
        print(f"  wrote {rel}")
    print(f"[gen-index] {written} file(s) written, {kept} unchanged")
    return 0


# --- CLI ----------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="cc.py",
        description="Build, verify and index Circuit Circus packages.",
    )
    sub = ap.add_subparsers(dest="command", required=True)
    for name, doc in (
        ("build", "flatten+compile every exported component (no vectors)"),
        ("test", "run the package's test vectors"),
        ("check", "build + test"),
    ):
        p = sub.add_parser(name, help=doc)
        p.add_argument("packages", nargs="+", metavar="pkg")
    sub.add_parser("all", help="check every package under packages/")
    p_gen = sub.add_parser(
        "gen-index",
        help="regenerate registry.json, index/*.json and archives/ from the manifests",
    )
    p_gen.add_argument(
        "--check",
        action="store_true",
        help="verify the committed index matches a fresh regeneration (no writes)",
    )
    p_gen.add_argument(
        "--out",
        metavar="DIR",
        help="write generated files under DIR instead of the repo root",
    )
    args = ap.parse_args(argv)

    try:
        if args.command == "gen-index":
            return gen_index(args.check, args.out)
        if args.command == "all":
            command, packages = "check", discover_packages()
        else:
            command, packages = args.command, args.packages
        bad = 0
        for pkg in packages:
            if command in {"build", "check"}:
                ok, tot = build_pkg(pkg)
                bad += tot - ok
            if command in {"test", "check"}:
                ok, tot = test_pkg(pkg)
                bad += tot - ok
        print(f"\n{'OK' if bad == 0 else 'FAIL'}: {bad} problem(s)")
        return 0 if bad == 0 else 1
    except CCError as e:
        print(f"cc.py: error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
