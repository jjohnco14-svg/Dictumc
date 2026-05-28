#!/usr/bin/env python3
"""
Dictum Web — Production server
Serves the landing page / editor frontend as static files
and mounts the full Dictum API at /api/*

Designed for fly.io free tier deployment.
PORT env var overrides default 8080.
"""
import sys
import os
import shutil
import sqlite3
import subprocess
import tempfile
import time

# ── Resolve project root ──────────────────────────────────────────────────
# When running from dictum-web/, the Dictumc repo is expected one level up.
# In Docker (Dockerfile), WORKDIR is /app which is the repo root.
_HERE        = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT   = os.environ.get("DICTUM_REPO", os.path.dirname(_HERE))
_STATIC_DIR  = os.path.join(_HERE, "static")
_DB_PATH     = os.path.join(_HERE, "workspace.db")

sys.path.insert(0, _REPO_ROOT)

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, HTMLResponse
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel
    from typing import Optional, List
    import uvicorn
except ImportError:
    print("pip install fastapi uvicorn[standard] pydantic aiofiles")
    sys.exit(1)

# ── Dictum imports ────────────────────────────────────────────────────────
try:
    from dictumc.transpiler import StdlibTranspiler, Transpiler
    from dictumc.grammar import DictumGrammar
    from dictumc.stdlib_registry import DICTUM_STDLIB_TYPES, STDLIB_ACTION_FAMILIES
    DICTUM_AVAILABLE = True
except ImportError as e:
    print(f"[warn] Dictum package not found ({e}). /transpile and /run will return stub responses.")
    DICTUM_AVAILABLE = False

STDLIB_ROOT = os.path.join(_REPO_ROOT, "stdlib")
NICHE_ROOT  = os.path.join(_REPO_ROOT, "niche")

# ────────────────────────────────────────────────────────────────────────────
# QEMU target table
# ────────────────────────────────────────────────────────────────────────────
_QEMU_TARGETS = {
    "linux": {
        "cc": "gcc", "cxx": "g++", "qemu": None, "sysroot": None,
        "label": "Linux x86-64 (host native)",
    },
    "arm64": {
        "cc": "aarch64-linux-gnu-gcc", "cxx": "aarch64-linux-gnu-g++",
        "qemu": "qemu-aarch64",        "sysroot": "/usr/aarch64-linux-gnu",
        "label": "ARM64 / AArch64",
    },
    "riscv64": {
        "cc": "riscv64-linux-gnu-gcc", "cxx": "riscv64-linux-gnu-g++",
        "qemu": "qemu-riscv64",        "sysroot": "/usr/riscv64-linux-gnu",
        "label": "RISC-V 64-bit",
    },
    "mips": {
        "cc": "mips-linux-gnu-gcc",    "cxx": "mips-linux-gnu-g++",
        "qemu": "qemu-mips",           "sysroot": "/usr/mips-linux-gnu",
        "label": "MIPS big-endian",
    },
    "mipsel": {
        "cc": "mipsel-linux-gnu-gcc",  "cxx": "mipsel-linux-gnu-g++",
        "qemu": "qemu-mipsel",         "sysroot": "/usr/mipsel-linux-gnu",
        "label": "MIPS little-endian",
    },
    "ppc64le": {
        "cc": "powerpc64le-linux-gnu-gcc", "cxx": "powerpc64le-linux-gnu-g++",
        "qemu": "qemu-ppc64le",            "sysroot": "/usr/powerpc64le-linux-gnu",
        "label": "PowerPC 64-bit LE",
    },
}


def _target_available(name: str) -> dict:
    t = _QEMU_TARGETS.get(name)
    if t is None:
        return {"available": False, "reason": "unknown target"}
    if name == "linux":
        ok = shutil.which("gcc") is not None
        return {"available": ok, "reason": None if ok else "gcc not found"}
    cc_ok   = shutil.which(t["cc"])   is not None
    qemu_ok = shutil.which(t["qemu"]) is not None
    if cc_ok and qemu_ok:
        return {"available": True, "reason": None}
    missing = []
    if not cc_ok:   missing.append(t["cc"])
    if not qemu_ok: missing.append(t["qemu"])
    return {"available": False, "reason": f"missing: {', '.join(missing)}"}


def _resolve_target(target: str):
    if target not in _QEMU_TARGETS:
        return _QEMU_TARGETS["linux"], f"Unknown target '{target}', falling back to linux"
    return _QEMU_TARGETS[target], None


# ────────────────────────────────────────────────────────────────────────────
# SQLite workspace
# ────────────────────────────────────────────────────────────────────────────
def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS programs (
            name        TEXT PRIMARY KEY,
            source      TEXT NOT NULL,
            backend     TEXT NOT NULL DEFAULT 'c',
            cpp_std     INTEGER NOT NULL DEFAULT 17,
            saved_at    INTEGER NOT NULL,
            notes       TEXT NOT NULL DEFAULT ''
        )
    """)
    conn.commit()
    return conn


# ────────────────────────────────────────────────────────────────────────────
# Request models
# ────────────────────────────────────────────────────────────────────────────
class TranspileRequest(BaseModel):
    source: str
    backend: str = "c"
    target: str = "linux"
    cpp_standard: int = 17
    stdlib: bool = True
    validate_code: bool = True


class RunRequest(TranspileRequest):
    compile: bool = True


class WorkspaceSaveRequest(BaseModel):
    name: str
    source: str
    backend: str = "c"
    cpp_standard: int = 17
    notes: str = ""


class WorkspaceProgram(BaseModel):
    name: str
    source: str
    backend: str
    cpp_standard: int
    saved_at: int
    notes: str


class GenerateRequest(BaseModel):
    prompt: str
    backend: str = "c"
    cpp_standard: int = 17
    skills: List[str] = []
    api_key: str = ""
    model: str = "claude-sonnet-4-6"
    auto_transpile: bool = True


# ────────────────────────────────────────────────────────────────────────────
# App
# ────────────────────────────────────────────────────────────────────────────
app = FastAPI(title="Dictum", version="5.2", docs_url="/api/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helpers ──────────────────────────────────────────────────────────────────
def _make_transpiler(req: TranspileRequest):
    if not DICTUM_AVAILABLE:
        raise RuntimeError("Dictum package not installed in this environment.")
    kwargs = dict(backend=req.backend, cpp_standard=req.cpp_standard)
    if req.stdlib:
        return StdlibTranspiler(req.source, **kwargs)
    return Transpiler(req.source, **kwargs)


# ── API routes ────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {
        "ok": True,
        "dictum_available": DICTUM_AVAILABLE,
        "version": "5.2",
        "targets_available": [
            k for k, v in _QEMU_TARGETS.items()
            if _target_available(k)["available"]
        ],
    }


@app.get("/api/targets")
def list_targets():
    result = []
    for name, t in _QEMU_TARGETS.items():
        avail = _target_available(name)
        result.append({
            "id":        name,
            "label":     t["label"],
            "cc":        t["cc"],
            "qemu":      t["qemu"],
            "available": avail["available"],
            "reason":    avail["reason"],
        })
    return {"targets": result}


@app.post("/api/transpile")
def transpile(req: TranspileRequest):
    try:
        t = _make_transpiler(req)
        result = t.run(validate=req.validate_code)
        return {
            "ok": True,
            "code": result.get("code", ""),
            "warnings": result.get("warnings", []),
            "summary": result.get("summary", ""),
            "stdlib_headers": result.get("stdlib_headers", []),
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "code": "", "warnings": []}


@app.post("/api/run")
def run(req: RunRequest):
    transpile_result = transpile(req)
    if not transpile_result["ok"]:
        return transpile_result
    if not req.compile:
        return transpile_result

    tgt, tgt_warning = _resolve_target(req.target)
    warnings = list(transpile_result.get("warnings", []))
    if tgt_warning:
        warnings.append(tgt_warning)

    avail = _target_available(req.target if req.target in _QEMU_TARGETS else "linux")
    if not avail["available"]:
        return {
            "ok": False,
            "error": (
                f"Target '{req.target}' unavailable on this server.\n"
                f"Reason: {avail['reason']}\n\n"
                "Free tier supports Linux x86-64. "
                "Upgrade to Pro for all QEMU cross-compilation targets."
            ),
            "code": transpile_result["code"],
            "warnings": warnings,
        }

    code = transpile_result["code"]
    ext  = ".cpp" if req.backend.lower() in ("cpp", "c++") else ".c"
    compiler = tgt["cxx"] if ext == ".cpp" else tgt["cc"]

    with tempfile.TemporaryDirectory() as tmpdir:
        src_path = os.path.join(tmpdir, f"program{ext}")
        bin_path = os.path.join(tmpdir, "program")
        with open(src_path, "w", encoding="utf-8") as f:
            f.write(code)

        compile_cmd = [
            compiler, src_path, "-o", bin_path,
            f"-I{STDLIB_ROOT}", f"-I{NICHE_ROOT}",
            f"-L{STDLIB_ROOT}", "-lpthread", "-lm",
        ]
        if ext == ".cpp":
            compile_cmd += [f"-std=c++{req.cpp_standard}"]
        else:
            compile_cmd += ["-std=c11"]

        if tgt["qemu"] is not None:
            compile_cmd += ["-static"]

        try:
            cp = subprocess.run(compile_cmd, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "Compilation timed out (30s)", "code": code, "warnings": warnings}

        if cp.returncode != 0:
            return {"ok": False, "error": cp.stderr, "code": code, "warnings": warnings}

        run_cmd = [bin_path] if tgt["qemu"] is None else (
            [tgt["qemu"]] +
            (["-L", tgt["sysroot"]] if tgt["sysroot"] and os.path.isdir(tgt["sysroot"]) else []) +
            [bin_path]
        )

        try:
            rp = subprocess.run(run_cmd, capture_output=True, text=True, timeout=10)
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "Execution timed out (10s)", "code": code, "warnings": warnings}

        return {
            "ok": True,
            "code": code,
            "output": rp.stdout,
            "stderr": rp.stderr,
            "exit_code": rp.returncode,
            "warnings": warnings,
            "target": req.target,
            "target_label": tgt["label"],
        }


# ── Workspace ────────────────────────────────────────────────────────────────

@app.post("/api/workspace/{name}")
def workspace_save(name: str, req: WorkspaceSaveRequest):
    if not name or len(name) > 128:
        raise HTTPException(400, "name must be 1–128 characters")
    if not req.source.strip():
        raise HTTPException(400, "source cannot be empty")
    conn = _db()
    try:
        conn.execute("""
            INSERT INTO programs (name, source, backend, cpp_std, saved_at, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                source   = excluded.source,
                backend  = excluded.backend,
                cpp_std  = excluded.cpp_std,
                saved_at = excluded.saved_at,
                notes    = excluded.notes
        """, (name, req.source, req.backend, req.cpp_standard, int(time.time()), req.notes))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "name": name}


@app.get("/api/workspace/{name}")
def workspace_load(name: str):
    conn = _db()
    try:
        row = conn.execute(
            "SELECT name,source,backend,cpp_std,saved_at,notes FROM programs WHERE name=?",
            (name,)
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(404, f"Program '{name}' not found")
    return WorkspaceProgram(
        name=row[0], source=row[1], backend=row[2],
        cpp_standard=row[3], saved_at=row[4], notes=row[5]
    )


@app.get("/api/workspace")
def workspace_list():
    conn = _db()
    try:
        rows = conn.execute(
            "SELECT name,source,backend,cpp_std,saved_at,notes FROM programs ORDER BY saved_at DESC"
        ).fetchall()
    finally:
        conn.close()
    return [
        WorkspaceProgram(
            name=r[0], source=r[1], backend=r[2],
            cpp_standard=r[3], saved_at=r[4], notes=r[5]
        )
        for r in rows
    ]


@app.delete("/api/workspace/{name}")
def workspace_delete(name: str):
    conn = _db()
    try:
        cur = conn.execute("DELETE FROM programs WHERE name=?", (name,))
        conn.commit()
        deleted = cur.rowcount > 0
    finally:
        conn.close()
    if not deleted:
        raise HTTPException(404, f"Program '{name}' not found")
    return {"ok": True, "deleted": name}


# ── Generate (BYOK) ──────────────────────────────────────────────────────────

_SKILLS_ROOT = os.path.join(_REPO_ROOT, "industry_skills")
_SKILL_FILES = {
    "general":    "SKILL_GENERAL.md",
    "syntax":     "DICTUM_SYNTAX.md",
    "medical":    "SKILL_MEDICAL.md",
    "embedded":   "SKILL_EMBEDDED.md",
    "automotive": "SKILL_AUTOMOTIVE.md",
    "aerospace":  "SKILL_AEROSPACE.md",
    "edgeai":     "SKILL_EDGEAI.md",
}


def _load_skill(sid: str) -> str:
    fname = _SKILL_FILES.get(sid.lower(), "")
    if not fname:
        return ""
    path = os.path.join(_SKILLS_ROOT, fname)
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def _build_system_prompt(skills: List[str]) -> str:
    import re
    parts = ["""You are a Dictum code generation assistant.
Dictum is an AI-native systems programming language that compiles to C11 or C++17/20/23.

Follow this four-step pipeline:
1. PLAN    — list shapes, modules, actions, control flow, error paths
2. VERIFY  — run syntax checklist mentally
3. CODE    — emit valid Dictum in a ```dictum block
4. COMPILE — show the dictumc CLI command to validate and build

Never emit raw C. Always use Dictum syntax. Never hardcode credentials.
"""]
    for sid in (["syntax", "general"] + skills):
        content = _load_skill(sid)
        if content:
            parts.append(f"---\n# SKILL: {sid.upper()}\n\n{content[:6000]}")
    return "\n\n".join(parts)


def _extract_dictum(text: str) -> str:
    import re
    m = re.search(r"```(?:dictum|dict)\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    m = re.search(r"(program\s+\w+:.*?end\s+program)", text, re.DOTALL)
    return m.group(1).strip() if m else ""


@app.post("/api/generate")
def generate(req: GenerateRequest):
    import urllib.request, json

    api_key = req.api_key.strip() or os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {
            "ok": False,
            "error": "No API key. Enter your Anthropic key in Settings → API Key.",
        }

    payload = json.dumps({
        "model": req.model,
        "max_tokens": 4096,
        "system": _build_system_prompt(req.skills),
        "messages": [{"role": "user", "content": req.prompt}],
    }).encode()

    api_req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(api_req, timeout=60) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"API error {e.code}: {e.read().decode()[:300]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

    full_text = "".join(
        b["text"] for b in body.get("content", []) if b.get("type") == "text"
    )
    dictum_code = _extract_dictum(full_text)

    result = {"ok": True, "message": full_text, "dictum": dictum_code, "c": "", "warnings": []}

    if req.auto_transpile and dictum_code:
        tr = transpile(TranspileRequest(
            source=dictum_code, backend=req.backend,
            cpp_standard=req.cpp_standard, stdlib=True, validate_code=True,
        ))
        result["transpile_ok"] = tr.get("ok", False)
        result["c"] = tr.get("code", "")
        result["warnings"] = tr.get("warnings", [])
        if not tr.get("ok"):
            result["transpile_error"] = tr.get("error", "")

    return result


# ── Static files (index.html) ──────────────────────────────────────────────

if os.path.isdir(_STATIC_DIR):
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

@app.get("/", response_class=HTMLResponse)
@app.get("/{full_path:path}", response_class=HTMLResponse)
def serve_spa(full_path: str = ""):
    index = os.path.join(_STATIC_DIR, "index.html")
    if not os.path.exists(index):
        return HTMLResponse(
            "<h1>Dictum Web</h1>"
            "<p>index.html not found in /static. "
            "Copy dictum-web/index.html to /app/static/index.html</p>",
            status_code=503
        )
    with open(index, encoding="utf-8") as f:
        # Inject the correct API base URL so the frontend hits /api/*
        html = f.read().replace(
            "window.DICTUM_API || 'http://localhost:8765'",
            "window.DICTUM_API || ''"     # same-origin, prefix /api in JS
        )
    return HTMLResponse(html)


# ────────────────────────────────────────────────────────────────────────────
# Entry
# ────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"Dictum Web starting on port {port}")
    print(f"Dictum package: {'available' if DICTUM_AVAILABLE else 'NOT FOUND — transpile/run will fail'}")
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
