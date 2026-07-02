# Circuit Circus — Index Format

*The producer/consumer treaty for the hosted package index. Version 2.*

This document pins everything a client (`shdl add` / `shdl install`) and the
producer (`tools/cc.py gen-index`) must agree on: the JSON index schemas, the
archive layout and its byte-determinism recipe, the URL layout, the semver
grammar, and the admission rules. `MANIFEST_FORMAT.md` remains the spec for a
*package's own files* (`package.json`, tests); this document is the spec for
what the registry *publishes about* those packages.

Format lineage: `registry.json` moves from `registry_format: 1` (hand-written
digest) to `registry_format: 2` (generated, with archive pointers). Package
manifests stay at `manifest_format: 1` — nothing in them changes.

---

## 1. Site layout = repo layout

The published site is the repository tree, byte for byte. The same paths work
over raw git, `file://`, `python -m http.server`, and GitHub Pages:

```
registry.json                     # root index (generated — never hand-edit)
index/<name>.json                 # per-package version file (generated)
archives/<name>-<version>.tar.gz  # immutable archives, committed, append-only
packages/<name>/…                 # source of truth (manifests, .shdl, tests)
```

A client is configured with a single **index URL** (e.g.
`https://rafa-rrayes.github.io/CCircus`). It fetches
`<index-url>/registry.json`; **every URL inside the index is relative to the
index root** — the directory holding `registry.json` — regardless of which
JSON file contains it (equivalently: RFC 3986 `urljoin` against the
`registry.json` URL, never against a nested file like `index/<name>.json`).
No index file contains an absolute URL, so a mirror or a local checkout works
unchanged.

## 2. Root index — `registry.json`

One fetch answers "what exists, and what is the latest of each": the latest
version of every package is inlined, so `shdl add <pkg>` needs exactly two
fetches (root index + archive) in the common no-conflict case.

```jsonc
{
  "registry_format": 2,
  "name": "Circuit Circus",
  "homepage": "https://github.com/rafa-rrayes/CCircus",
  "packages": [
    {
      "name": "arith",                     // package id
      "version": "0.1.0",                  // the LATEST version
      "summary": "Adders, subtractors, comparators, multiply/divide, and an ALU.",
      "keywords": ["adder", "alu"],        // latest version's keywords ([] if none)
      "circuits": 16,                      // len(exports) of the latest version
      "dependencies": {"gates": "^0.1.0"}, // latest version's dependencies
      "index": "index/arith.json",         // per-package version file (relative URL)
      "archive": "archives/arith-0.1.0.tar.gz",  // latest archive (relative URL)
      "sha256": "…64 hex chars…"           // sha256 of that archive's bytes
    }
    // … one entry per package, sorted by name …
  ]
}
```

Rules:

- `packages` is sorted by `name`. Every field shown is required (`keywords`
  may be `[]`, `dependencies` may be `{}`).
- **No timestamps anywhere** — regeneration from the same tree must be
  byte-identical (this is what `gen-index --check` verifies in CI).
- JSON is emitted with `indent=2`, `sort_keys=False` (field order as shown),
  UTF-8, LF line endings, trailing newline.
- Consumers that only need the dependency graph (`registry_format: 1`
  readers of `packages[].name` / `.dependencies`) keep working unchanged.

## 3. Per-package version file — `index/<name>.json`

The full version history of one package. Clients consult this when the latest
does not satisfy a range, and for `shdl info`.

```jsonc
{
  "index_format": 2,
  "name": "arith",
  "latest": "0.1.0",
  "versions": {
    "0.1.0": {
      "summary": "Adders, subtractors, comparators, multiply/divide, and an ALU.",
      "description": "…longer prose…",     // "" if the manifest has none
      "license": "GPL-3.0-or-later",
      "authors": ["rafa-rrayes <rafa@rayes.com.br>"],
      "homepage": "https://github.com/rafa-rrayes/SHDL",  // "" if none
      "keywords": ["adder", "alu"],
      "shdl": ">=1.0.0",                   // toolchain range (manifest `shdl`)
      "module": "arith.shdl",
      "dependencies": {"gates": "^0.1.0"},
      "archive": "archives/arith-0.1.0.tar.gz",  // relative URL
      "sha256": "…64 hex chars…",
      "size": 12691,                       // archive size in bytes
      "exports": [ /* the manifest's exports array, verbatim */ ]
    }
  }
}
```

Rules:

- `versions` keys are exact `X.Y.Z` strings; `latest` is the
  highest version present under the ordering of §6.
- **History accumulates by merge.** `gen-index` reads the existing
  `index/<name>.json` (if any), keeps every prior version entry untouched,
  and upserts the entry for the version currently in `packages/<name>/`.
  It never deletes or rewrites a published version entry.
- If the on-disk package has the same `version` as a published entry but the
  freshly-built archive's sha256 differs, `gen-index` **hard-errors**:
  *"package <name> 0.1.0 changed but the version was not bumped"*. Bump the
  version; published archives are immutable forever.

## 4. Archives — `archives/<name>-<version>.tar.gz`

One archive per published version. Committed to the repo; **append-only**
(CI rejects any PR that modifies or deletes an existing archive).

**Members.** Every member path is prefixed `<name>-<version>/`. The member
whitelist, relative to the package directory:

1. `package.json` (required)
2. the manifest's `module` file (required, e.g. `arith.shdl`)
3. `README.md` (if present)
4. `tests/**` — every file under `tests/`, recursively (if present)

Nothing else — no dotfiles, no `__pycache__`, nothing outside the whitelist.

**Determinism recipe.** The producer builds the archive in memory exactly
like this, so the same tree always yields the same bytes:

- outer stream: `gzip.GzipFile(fileobj=buf, mode="wb", filename="", mtime=0)`
  (empty embedded filename, fixed mtime, default compresslevel 9);
- inner tar: `tarfile.open(mode="w", fileobj=gz, format=tarfile.USTAR_FORMAT)`;
- members added in **sorted order of their full member name** (plain string
  sort of `<name>-<version>/<relpath>` with `/` separators);
- **files only** — no directory entries, no symlinks (symlinks in the
  package dir are an admission error);
- every `TarInfo` normalized: `uid = gid = 0`, `uname = gname = ""`,
  `mtime = 0`, `mode = 0o644`, type regular file;
- member paths always use `/` separators.

`sha256` (in both index levels) is over the **final `.tar.gz` bytes** as
committed. The gzip envelope is written **once**, when the version is first
published, and never regenerated; from then on the committed `.tar.gz` bytes
are canonical. Because compressed output can vary between zlib builds,
producer-side equality checks (immutability, `--check`) always compare the
**decompressed tar bytes** — the tar layer above is deterministic on every
platform — never the gzip bytes. The repo's `.gitattributes` forces LF for
text files so checkouts on any OS reproduce identical tar bytes.

**Extraction contract for clients:** verify the sha256 of the downloaded
bytes *before* extracting; extract with `tarfile`'s `filter="data"`; reject
any member whose path does not start with `<name>-<version>/`.

## 5. URL layout

| Resource | URL (relative to the index URL) |
|---|---|
| root index | `registry.json` |
| package versions | `index/<name>.json` |
| archive | `archives/<name>-<version>.tar.gz` |
| package source (browse) | `packages/<name>/…` |

Relative URLs inside index JSON — wherever they appear, including inside
`index/<name>.json` — are resolved against the **index root** (the
`registry.json` URL): `archive: "archives/arith-0.1.0.tar.gz"` under index
URL `https://host/CCircus` resolves to
`https://host/CCircus/archives/arith-0.1.0.tar.gz`. The same works for
`file:///…/CCircus`.

## 6. Semver: versions and ranges

**Version grammar.** Exactly `X.Y.Z` — three dot-separated non-negative
decimal integers, no leading `+`/`-`, no leading zeros (except `0` itself),
no prerelease/build suffix. Anything else is rejected loudly.

**Ordering.** Lexicographic on the integer triple `(X, Y, Z)`.

**Range grammar** (cargo semantics; whitespace around tokens is ignored):

| Range | Meaning |
|---|---|
| `1.2.3` | exactly `=1.2.3` |
| `^1.2.3` | `>=1.2.3, <2.0.0` |
| `^0.2.3` | `>=0.2.3, <0.3.0` |
| `^0.0.3` | `>=0.0.3, <0.0.4` |
| `^0.0.0` | `>=0.0.0, <0.0.1` (i.e. exactly `0.0.0`) |
| `>=1.2.3` / `>1.2.3` / `<=1.2.3` / `<1.2.3` | the obvious comparator |
| `>=1.0.0, <2.0.0` | comma = AND of the parts |

Caret rule stated generally: `^X.Y.Z` allows changes that do not modify the
leftmost **non-zero** component (for `^0.0.Z` only `=0.0.Z` matches).

**Rejected loudly** (parse error, not empty-match): tilde (`~1.2`),
wildcards (`1.*`, `x`), bare `1` / `1.2` partial versions, prerelease tags,
hyphen ranges, `||` alternatives.

## 7. Admission rules (what `gen-index` / CI enforce)

A tree is admissible when all of the following hold; `gen-index` refuses to
emit an index otherwise, and CI runs `gen-index --check` plus the full
build+test sweep on every PR:

1. Every `packages/<dir>/package.json` parses and has the required
   `manifest_format: 1` fields (`name`, `version`, `summary`, `license`,
   `authors`, `shdl`, `module`, `dependencies`, `exports`).
2. `name == <dir> == module basename` (so `use <name>::{…}` resolves), and
   the module file exists.
3. `version` parses per §6; every dependency range parses per §6.
4. Every dependency names a package present in `packages/`, and its range is
   satisfied by that package's on-disk version.
5. The dependency graph is acyclic.
6. **Registry-wide uniqueness:** no two packages export the same component
   name, and no two packages have the same module basename. (The SHDL module
   namespace is flat and program-global; a collision would silently shadow.)
7. Same-version republish with different bytes is an error (§3); existing
   archives are never modified or deleted (append-only, CI-guarded).
8. Every package's test file exists (`tests` in the manifest, default
   `tests/<name>.tests.json`) — a missing or mistyped path is an error, never
   a skip — and every export builds at its default params and every test
   vector passes (`cc.py all` — the toolchain-dependent half of admission).

## 8. Golden example (minimal two-package registry)

`registry.json`:

```json
{
  "registry_format": 2,
  "name": "Example Registry",
  "homepage": "https://example.invalid/registry",
  "packages": [
    {
      "name": "adders",
      "version": "0.1.0",
      "summary": "One adder.",
      "keywords": [],
      "circuits": 1,
      "dependencies": {"nands": "^0.1.0"},
      "index": "index/adders.json",
      "archive": "archives/adders-0.1.0.tar.gz",
      "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    },
    {
      "name": "nands",
      "version": "0.2.0",
      "summary": "One gate.",
      "keywords": ["nand"],
      "circuits": 1,
      "dependencies": {},
      "index": "index/nands.json",
      "archive": "archives/nands-0.2.0.tar.gz",
      "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    }
  ]
}
```

`index/nands.json` (two published versions):

```json
{
  "index_format": 2,
  "name": "nands",
  "latest": "0.2.0",
  "versions": {
    "0.1.0": {
      "summary": "One gate.",
      "description": "",
      "license": "GPL-3.0-or-later",
      "authors": ["someone <s@example.invalid>"],
      "homepage": "",
      "keywords": ["nand"],
      "shdl": ">=1.0.0",
      "module": "nands.shdl",
      "dependencies": {},
      "archive": "archives/nands-0.1.0.tar.gz",
      "sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
      "size": 512,
      "exports": [
        {"name": "Nand2", "summary": "NAND.", "params": [],
         "inputs": [{"name": "A", "width": 1}, {"name": "B", "width": 1}],
         "outputs": [{"name": "O", "width": 1}]}
      ]
    },
    "0.2.0": {
      "summary": "One gate.",
      "description": "",
      "license": "GPL-3.0-or-later",
      "authors": ["someone <s@example.invalid>"],
      "homepage": "",
      "keywords": ["nand"],
      "shdl": ">=1.0.0",
      "module": "nands.shdl",
      "dependencies": {},
      "archive": "archives/nands-0.2.0.tar.gz",
      "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "size": 640,
      "exports": [
        {"name": "Nand2", "summary": "NAND.", "params": [],
         "inputs": [{"name": "A", "width": 1}, {"name": "B", "width": 1}],
         "outputs": [{"name": "O", "width": 1}]}
      ]
    }
  }
}
```

Archive `archives/nands-0.2.0.tar.gz` member list (in this exact order):

```
nands-0.2.0/README.md
nands-0.2.0/nands.shdl
nands-0.2.0/package.json
nands-0.2.0/tests/nands.tests.json
```

## 9. Version-bump semantics (policy, enforced at review)

- **patch** (`0.1.0 → 0.1.1`): docs, README, test additions, internal
  restructuring with identical exports and ports.
- **minor** (`0.1.0 → 0.2.0`): new exported components; new optional params
  with defaults preserving old instantiations.
- **major** (`0.x → 1.0.0`, `1.x → 2.0.0`): removed/renamed exports, changed
  ports or param defaults — anything that can break a `use` site. (While a
  package is `0.y.z`, the minor position carries breaking changes, matching
  the caret rule.)
