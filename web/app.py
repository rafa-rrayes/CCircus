"""app.py — the Circuit Circus website.

A small FastAPI app: server-side rendered HTML pages for browsing the SHDL
circuit index, plus a PyPI-simple-style JSON API the ``shdl add`` client can
read. Run it with:

    uv run uvicorn web.app:app --reload

All data comes from :mod:`web.catalog` (CATALOG.md + the packages/ tree).
"""

from __future__ import annotations

import html
import re
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from . import catalog

BASE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE / "templates"))

app = FastAPI(title="Circuit Circus", description="The official SHDL circuit index")
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")


# --- template helpers -----------------------------------------------------
def md_inline(text: str | None) -> Markup:
    """Render `inline code` spans to <code>, escaping everything else."""
    if not text:
        return Markup("")
    parts = re.split(r"`([^`]*)`", text)
    out: list[str] = []
    for i, part in enumerate(parts):
        if i % 2 == 0:
            out.append(html.escape(part))
        else:
            out.append(f"<code>{html.escape(part)}</code>")
    return Markup("".join(out))


_KEYWORDS = (
    "top", "component", "connect", "when", "else", "use", "const", "init",
)
_PRIMS = ("AND", "OR", "NOT", "XOR", "__VCC__", "__GND__")


def highlight_shdl(src: str | None) -> Markup:
    """Tiny SHDL syntax highlighter: comments, keywords, primitives."""
    if not src:
        return Markup("")
    lines_out: list[str] = []
    for line in src.splitlines():
        code, _, comment = line.partition("#")
        esc = html.escape(code)
        esc = re.sub(
            r"\b(" + "|".join(_KEYWORDS) + r")\b",
            r'<span class="kw">\1</span>',
            esc,
        )
        esc = re.sub(
            r"\b(" + "|".join(map(re.escape, _PRIMS)) + r")\b",
            r'<span class="prim">\1</span>',
            esc,
        )
        if comment:
            esc += f'<span class="cmt">#{html.escape(comment)}</span>'
        lines_out.append(esc)
    return Markup("\n".join(lines_out))


templates.env.filters["md_inline"] = md_inline
templates.env.filters["highlight_shdl"] = highlight_shdl


def _ctx(request: Request, **kw) -> dict:
    base = {"request": request, "stats": catalog.stats()}
    base.update(kw)
    return base


# --- HTML pages -----------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        _ctx(
            request,
            libraries=catalog.all_libraries(),
            intro=catalog.intro_text(),
        ),
    )


@app.get("/library/{name}", response_class=HTMLResponse)
def library_page(request: Request, name: str):
    lib = catalog.get_library(name)
    if lib is None:
        return templates.TemplateResponse(
            request, "not_found.html",
            _ctx(request, what=f"library “{name}”"), status_code=404,
        )
    deps = [catalog.get_library(d) for d in lib.depends_on]
    return templates.TemplateResponse(
        request, "library.html",
        _ctx(request, lib=lib, deps=[d for d in deps if d], dep_names=lib.depends_on),
    )


@app.get("/circuit/{lib}/{component}", response_class=HTMLResponse)
def circuit_page(request: Request, lib: str, component: str):
    library = catalog.get_library(lib)
    circ = catalog.get_circuit(lib, component)
    if library is None or circ is None:
        return templates.TemplateResponse(
            request, "not_found.html",
            _ctx(request, what=f"circuit “{lib}::{component}”"),
            status_code=404,
        )
    return templates.TemplateResponse(
        request, "circuit.html", _ctx(request, lib=library, circ=circ)
    )


@app.get("/search", response_class=HTMLResponse)
def search_page(request: Request, q: str = ""):
    results = catalog.search(q)
    return templates.TemplateResponse(
        request, "search.html", _ctx(request, q=q, results=results)
    )


# --- JSON API (PyPI-simple flavour) --------------------------------------
def _circuit_json(c: catalog.Circuit, *, full: bool = False) -> dict:
    d = {
        "name": c.name,
        "library": c.library,
        "ports": c.ports,
        "description": c.description,
        "seed": c.seed,
        "published": c.published,
    }
    if full:
        d["source"] = c.source
        d["tests"] = c.tests
    return d


def _library_json(lib: catalog.Library, *, with_circuits: bool = True) -> dict:
    d = {
        "name": lib.name,
        "version": lib.version,
        "summary": lib.blurb,
        "title": lib.title,
        "dependencies": lib.depends_on,
        "circuit_count": len(lib.circuits),
        "published_count": lib.published_count,
        "published": lib.published,
        "install": f"shdl add {lib.name}",
    }
    if with_circuits:
        d["circuits"] = [_circuit_json(c) for c in lib.circuits]
    return d


@app.get("/api/packages")
def api_packages():
    return {
        "stats": catalog.stats(),
        "packages": [
            _library_json(lib, with_circuits=False) for lib in catalog.all_libraries()
        ],
    }


@app.get("/api/packages/{name}")
def api_package(name: str):
    lib = catalog.get_library(name)
    if lib is None:
        return HTMLResponse('{"error": "no such package"}', status_code=404,
                            media_type="application/json")
    return _library_json(lib)


@app.get("/api/circuits/{lib}/{component}")
def api_circuit(lib: str, component: str):
    circ = catalog.get_circuit(lib, component)
    if circ is None:
        return HTMLResponse('{"error": "no such circuit"}', status_code=404,
                            media_type="application/json")
    return _circuit_json(circ, full=True)
