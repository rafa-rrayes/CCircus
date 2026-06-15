"""catalog.py — the Circuit Circus data layer.

Builds an in-memory index of the SHDL circuit world from two sources:

  1. ``CATALOG.md`` — the curated registry of 9 libraries and 100 circuits
     (names, ports, descriptions, dependency order, ✦ seed markers). This is
     the *intent*: everything that belongs in the index, authored or not.

  2. ``packages/<lib>/`` — the *reality*: real ``.shdl`` source and test
     vectors for libraries that have actually been authored. A circuit that
     has source + a component definition is "published"; everything else in
     the catalog is "planned".

The website and JSON API both read this index. Nothing here imports the SHDL
toolchain — it is pure parsing, so the site runs anywhere.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG_DIR = ROOT / "packages"
CATALOG_MD = ROOT / "CATALOG.md"
INTRO_MD = ROOT / "CircuitCircus.md"
REGISTRY_JSON = ROOT / "registry.json"

DEFAULT_VERSION = "0.1.0"


# --- data model -----------------------------------------------------------
@dataclass
class Circuit:
    number: int               # catalog position 1..100
    name: str                 # PascalCase component name
    library: str              # owning library slug
    ports: str                # "(A, B) -> (O)" style signature
    description: str          # may contain `inline code`
    seed: bool                # ✦ — already exists in shdlc/examples
    published: bool = False   # has real .shdl source in packages/
    source: str | None = None # the component's .shdl source block
    tests: dict | None = None # the matching test case, if any


@dataclass
class Library:
    number: int
    name: str
    blurb: str                # one-line "what it provides"
    title: str                # heading subtitle from its section
    depends_on: list[str]
    declared_count: int       # circuit count claimed by the catalog table
    circuits: list[Circuit] = field(default_factory=list)
    version: str = DEFAULT_VERSION

    @property
    def published(self) -> bool:
        return any(c.published for c in self.circuits)

    @property
    def published_count(self) -> int:
        return sum(1 for c in self.circuits if c.published)


# --- markdown table parsing ----------------------------------------------
def _split_row(line: str) -> list[str]:
    """Split a markdown table row into trimmed cells."""
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _is_divider(line: str) -> bool:
    return bool(re.fullmatch(r"\|[\s:|-]+\|", line.strip()))


def _backtick_names(cell: str) -> list[str]:
    return re.findall(r"`([A-Za-z_][\w]*)`", cell)


def _strip_md(cell: str) -> str:
    """Remove backticks and the ✦ marker, collapse whitespace."""
    return re.sub(r"\s+", " ", cell.replace("`", "").replace("✦", "")).strip()


# --- SHDL source extraction ----------------------------------------------
_COMPONENT_RE = re.compile(r"(?:^|\n)([ \t]*)((?:top\s+)?component\s+(\w+))")


def extract_components(src: str) -> dict[str, str]:
    """Map component name -> its full ``component ... { ... }`` source block."""
    blocks: dict[str, str] = {}
    for m in _COMPONENT_RE.finditer(src):
        name = m.group(3)
        decl_start = m.start(2)
        brace = src.find("{", m.end())
        if brace == -1:
            continue
        depth = 0
        j = brace
        end = None
        while j < len(src):
            ch = src[j]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = j + 1
                    break
            j += 1
        if end is None:
            continue
        blocks[name] = src[decl_start:end].rstrip()
    return blocks


def _load_package(lib: str) -> tuple[dict, dict[str, str], dict[str, dict]]:
    """Return (manifest, component sources, component test cases) for a library.

    Reads ``packages/<lib>/package.json`` if present, otherwise falls back to
    the repo conventions (``<lib>.shdl`` module, ``tests/<lib>.tests.json``).
    The manifest is the authoritative contract: a circuit is only "published"
    if the manifest lists it as an export.
    """
    pkg = PKG_DIR / lib
    if not pkg.is_dir():
        return {}, {}, {}

    manifest = {}
    mpath = pkg / "package.json"
    if mpath.is_file():
        try:
            manifest = json.loads(mpath.read_text())
        except json.JSONDecodeError:
            manifest = {}

    module = manifest.get("module", f"{lib}.shdl")
    sources: dict[str, str] = {}
    mod_path = pkg / module
    if mod_path.is_file():
        sources = extract_components(mod_path.read_text())

    tests: dict[str, dict] = {}
    tfile = pkg / "tests" / f"{lib}.tests.json"
    if tfile.is_file():
        try:
            spec = json.loads(tfile.read_text())
            for case in spec.get("cases", []):
                comp = case.get("component")
                if comp:
                    tests[comp] = case
        except json.JSONDecodeError:
            pass

    return manifest, sources, tests


def _registry_deps() -> dict[str, list[str]]:
    """Per-package dependency lists from the registry index — a fallback for
    packages that have no manifest yet (so e.g. planned ``mem``/``cpu`` still
    show their real dependency graph rather than the prose catalog's)."""
    if not REGISTRY_JSON.is_file():
        return {}
    try:
        reg = json.loads(REGISTRY_JSON.read_text())
    except json.JSONDecodeError:
        return {}
    out: dict[str, list[str]] = {}
    for p in reg.get("packages", []):
        name = p.get("name")
        if name:
            out[name] = list((p.get("dependencies") or {}).keys())
    return out


# --- the catalog parser ---------------------------------------------------
def _parse_libraries_table(text: str) -> dict[str, Library]:
    """Parse the '## 3. The libraries' summary table into Library stubs."""
    libs: dict[str, Library] = {}
    # locate the table that has a "Library" header column
    lines = text.splitlines()
    for i, line in enumerate(lines):
        cells = _split_row(line) if line.strip().startswith("|") else []
        if len(cells) >= 5 and cells[1].lower() == "library":
            j = i + 1
            if j < len(lines) and _is_divider(lines[j]):
                j += 1
            while j < len(lines) and lines[j].strip().startswith("|"):
                row = _split_row(lines[j])
                j += 1
                if len(row) < 5 or not row[0].isdigit():
                    continue
                name = _strip_md(row[1])
                count = re.sub(r"\D", "", row[4])
                libs[name] = Library(
                    number=int(row[0]),
                    name=name,
                    blurb=_strip_md(row[2]),
                    title="",
                    depends_on=_backtick_names(row[3]),
                    declared_count=int(count) if count else 0,
                )
            break
    return libs


_SECTION_RE = re.compile(r"^###\s+(\d+)\s+·\s+`(\w+)`\s+—\s+(.*)$")


def _parse_circuit_sections(text: str, libs: dict[str, Library]) -> None:
    """Walk each '### N · `lib` — title' section and parse its circuit table."""
    lines = text.splitlines()
    current: Library | None = None
    in_table = False
    header_cols: list[str] = []

    for idx, line in enumerate(lines):
        m = _SECTION_RE.match(line)
        if m:
            current = libs.get(m.group(2))
            if current is not None:
                current.title = m.group(3).strip()
            in_table = False
            continue
        if current is None:
            continue

        stripped = line.strip()
        if stripped.startswith("|"):
            cells = _split_row(line)
            if not in_table:
                if cells and cells[0].lower() in ("#", "no", "num"):
                    header_cols = [c.lower() for c in cells]
                    in_table = True
                continue
            if _is_divider(line):
                continue
            if len(cells) < 4 or not cells[0].isdigit():
                continue
            name_cell = cells[1]
            current.circuits.append(
                Circuit(
                    number=int(cells[0]),
                    name=_strip_md(name_cell),
                    library=current.name,
                    ports=cells[2].replace("`", "").strip(),
                    description=cells[3].strip(),
                    seed="✦" in name_cell,
                )
            )
        elif stripped and not stripped.startswith("|"):
            # a non-table, non-blank line ends the current table
            in_table = False


def _build_catalog() -> dict[str, Library]:
    """Parse CATALOG.md and overlay authored source + tests from packages/."""
    text = CATALOG_MD.read_text() if CATALOG_MD.is_file() else ""
    libs = _parse_libraries_table(text)
    _parse_circuit_sections(text, libs)

    # overlay real authored source + tests from packages/, with the manifest
    # (and the registry as fallback) as the source of truth for what is real.
    reg_deps = _registry_deps()
    for lib in libs.values():
        manifest, sources, tests = _load_package(lib.name)
        lib.version = manifest.get("version", DEFAULT_VERSION)
        export_names = {e.get("name") for e in manifest.get("exports", [])}

        # Dependencies: the manifest is authoritative; fall back to the registry
        # index, and only then to the catalog table parsed above.
        if "dependencies" in manifest:
            lib.depends_on = list(manifest["dependencies"].keys())
        elif lib.name in reg_deps:
            lib.depends_on = reg_deps[lib.name]

        for circ in lib.circuits:
            if circ.name in sources:
                circ.source = sources[circ.name]
                circ.tests = tests.get(circ.name)
                # "published" means the manifest ships it as an export AND it
                # has real source — so a manifest-less or unexported circuit
                # never shows as live.
                circ.published = circ.name in export_names
    return libs


# The catalog is cached but invalidated whenever any source file's mtime
# changes, so newly authored packages appear without restarting the server.
_cache: dict[str, Library] | None = None
_cache_key: tuple | None = None


def _fingerprint() -> tuple:
    parts: list[tuple[str, int]] = []
    for p in (CATALOG_MD, INTRO_MD, REGISTRY_JSON):
        try:
            parts.append((str(p), p.stat().st_mtime_ns))
        except OSError:
            parts.append((str(p), 0))
    if PKG_DIR.is_dir():
        for p in sorted(PKG_DIR.rglob("*")):
            if p.is_file() and p.suffix in (".shdl", ".json"):
                try:
                    parts.append((str(p), p.stat().st_mtime_ns))
                except OSError:
                    pass
    return tuple(parts)


def load_catalog() -> dict[str, Library]:
    """The full {lib_name: Library} index, rebuilt only when files change."""
    global _cache, _cache_key
    key = _fingerprint()
    if _cache is None or _cache_key != key:
        _cache = _build_catalog()
        _cache_key = key
    return _cache


# --- convenience accessors used by the app & API -------------------------
def all_libraries() -> list[Library]:
    return sorted(load_catalog().values(), key=lambda l: l.number)


def get_library(name: str) -> Library | None:
    return load_catalog().get(name)


def get_circuit(lib: str, component: str) -> Circuit | None:
    library = get_library(lib)
    if library is None:
        return None
    for circ in library.circuits:
        if circ.name == component:
            return circ
    return None


def all_circuits() -> list[Circuit]:
    out: list[Circuit] = []
    for lib in all_libraries():
        out.extend(lib.circuits)
    return out


def search(query: str) -> list[Circuit]:
    q = query.strip().lower()
    if not q:
        return []
    hits: list[tuple[int, Circuit]] = []
    for circ in all_circuits():
        name = circ.name.lower()
        if q == name:
            score = 0
        elif name.startswith(q):
            score = 1
        elif q in name:
            score = 2
        elif q in circ.description.lower() or q in circ.ports.lower():
            score = 3
        elif q in circ.library.lower():
            score = 4
        else:
            continue
        hits.append((score, circ))
    hits.sort(key=lambda t: (t[0], t[1].number))
    return [c for _, c in hits]


def stats() -> dict:
    libs = all_libraries()
    circuits = all_circuits()
    return {
        "libraries": len(libs),
        "circuits": len(circuits),
        "published": sum(1 for c in circuits if c.published),
    }


def intro_text() -> str:
    """The lede paragraph from CircuitCircus.md, minus its heading."""
    if not INTRO_MD.is_file():
        return ""
    body = INTRO_MD.read_text()
    body = re.sub(r"^#.*$", "", body, count=1, flags=re.MULTILINE)
    return body.strip()
