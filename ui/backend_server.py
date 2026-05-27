#!/usr/bin/env python3
"""
Dictum VibeCoder Backend Server — v5.1
Bridges the VibeCoder HTML UI to the Dictum v5 transpiler.

v5.1 additions:
  • SQLite-backed workspace persistence: save/load/list named programs.
    Programs survive browser tab close and server restart.

Usage:
    pip install fastapi uvicorn pydantic
    python ui/backend_server.py
    # Open ui/dictum_vibecoder.html in browser
"""
import sys
import os
import sqlite3
import subprocess
import tempfile
import time

# Resolve package root (ui/ is one level below project root)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    from typing import Optional, List
    import uvicorn
except ImportError:
    print("Install dependencies: pip install fastapi uvicorn pydantic")
    sys.exit(1)

# v5 imports — from split dictumc package
from dictumc.transpiler import StdlibTranspiler, Transpiler
from dictumc.grammar import DictumGrammar
from dictumc.stdlib_registry import DICTUM_STDLIB_TYPES, STDLIB_ACTION_FAMILIES

app = FastAPI(title="Dictum VibeCoder API", version="5.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STDLIB_ROOT = os.path.join(_PROJECT_ROOT, "stdlib")
NICHE_ROOT  = os.path.join(_PROJECT_ROOT, "niche")

# ---------------------------------------------------------------------------
# SQLite workspace — P6.2: persist programs across sessions
# ---------------------------------------------------------------------------

_DB_PATH = os.path.join(_PROJECT_ROOT, "ui", "vibecoder_workspace.db")

def _db() -> sqlite3.Connection:
    """Return a thread-local SQLite connection with WAL mode for concurrency."""
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
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


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_transpiler(req: TranspileRequest):
    kwargs = dict(backend=req.backend, cpp_standard=req.cpp_standard)
    if req.stdlib:
        return StdlibTranspiler(req.source, **kwargs)
    return Transpiler(req.source, **kwargs)


# ---------------------------------------------------------------------------
# Core endpoints
# ---------------------------------------------------------------------------

@app.get("/")
def root():
    return {"status": "ok", "version": "5.1", "language": "Dictum",
            "features": ["workspace_persistence", "https_support",
                         "json_arrays", "grapheme_clusters", "multi_file_imports"]}


@app.post("/transpile")
def transpile(req: TranspileRequest):
    try:
        t = _make_transpiler(req)
        result = t.run(validate=req.validate_code)
        out = {
            "ok": True,
            "code": result.get("code", ""),
            "warnings": result.get("warnings", []),
            "summary": result.get("summary", ""),
            "stdlib_headers": result.get("stdlib_headers", []),
        }
        if result.get("dict_modules"):
            out["dict_modules"] = {
                name: {"c_code": m["c_code"], "h_code": m["h_code"]}
                for name, m in result["dict_modules"].items()
            }
        return out
    except Exception as e:
        return {"ok": False, "error": str(e), "code": "", "warnings": []}


@app.post("/run")
def run(req: RunRequest):
    transpile_result = transpile(req)
    if not transpile_result["ok"]:
        return transpile_result
    if not req.compile:
        return transpile_result

    code = transpile_result["code"]
    ext = ".cpp" if req.backend.lower() in ("cpp", "c++") else ".c"
    compiler = "g++" if ext == ".cpp" else "gcc"

    with tempfile.TemporaryDirectory() as tmpdir:
        src_path = os.path.join(tmpdir, f"program{ext}")
        bin_path = os.path.join(tmpdir, "program")
        with open(src_path, "w", encoding="utf-8") as f:
            f.write(code)

        compile_cmd = [
            compiler, src_path, "-o", bin_path,
            f"-I{STDLIB_ROOT}", f"-I{NICHE_ROOT}",
            f"-L{STDLIB_ROOT}",
            "-lpthread", "-lm",
        ]
        if ext == ".cpp":
            compile_cmd += [f"-std=c++{req.cpp_standard}"]
        else:
            compile_cmd += ["-std=c11"]

        compile_proc = subprocess.run(
            compile_cmd, capture_output=True, text=True, timeout=30
        )
        if compile_proc.returncode != 0:
            return {"ok": False, "error": compile_proc.stderr, "code": code,
                    "warnings": transpile_result["warnings"]}

        run_proc = subprocess.run(
            [bin_path], capture_output=True, text=True, timeout=10
        )
        return {
            "ok": True, "code": code,
            "output": run_proc.stdout,
            "stderr": run_proc.stderr,
            "exit_code": run_proc.returncode,
            "warnings": transpile_result["warnings"],
        }


# ---------------------------------------------------------------------------
# Workspace persistence endpoints (P6.2)
# ---------------------------------------------------------------------------

@app.post("/workspace/{name}")
def workspace_save(name: str, req: WorkspaceSaveRequest):
    """Save or overwrite a named program in the workspace."""
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
        """, (name, req.source, req.backend, req.cpp_standard,
              int(time.time()), req.notes))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "name": name}


@app.get("/workspace/{name}", response_model=WorkspaceProgram)
def workspace_load(name: str):
    """Load a named program."""
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


@app.get("/workspace", response_model=List[WorkspaceProgram])
def workspace_list():
    """List all saved programs (source omitted for brevity — use GET /workspace/{name} to load)."""
    conn = _db()
    try:
        rows = conn.execute(
            "SELECT name,source,backend,cpp_std,saved_at,notes FROM programs ORDER BY saved_at DESC"
        ).fetchall()
    finally:
        conn.close()
    return [
        WorkspaceProgram(name=r[0], source=r[1], backend=r[2],
                         cpp_standard=r[3], saved_at=r[4], notes=r[5])
        for r in rows
    ]


@app.delete("/workspace/{name}")
def workspace_delete(name: str):
    """Delete a named program."""
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


@app.post("/workspace/{name}/rename")
def workspace_rename(name: str, new_name: str):
    """Rename a saved program."""
    if not new_name or len(new_name) > 128:
        raise HTTPException(400, "new_name must be 1–128 characters")
    conn = _db()
    try:
        cur = conn.execute(
            "UPDATE programs SET name=? WHERE name=?", (new_name, name)
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(404, f"Program '{name}' not found")
    finally:
        conn.close()
    return {"ok": True, "name": new_name}


# ---------------------------------------------------------------------------
# Info endpoints
# ---------------------------------------------------------------------------

@app.get("/skills")
def list_skills():
    return {
        "families": list(STDLIB_ACTION_FAMILIES.keys()),
        "types": list(DICTUM_STDLIB_TYPES),
    }


@app.get("/grammar/tokens")
def grammar_tokens():
    g = DictumGrammar(cpp_mode=False)
    tokens = g.get_valid_tokens() if hasattr(g, "get_valid_tokens") else []
    return {"tokens": tokens}


if __name__ == "__main__":
    # Ensure DB directory exists
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    uvicorn.run(app, host="0.0.0.0", port=8765, reload=True)
Bridges the VibeCoder HTML UI to the Dictum v5 transpiler.

Updated for v5: uses split dictumc package (v4 architecture).
Previously imported from monolith transpiler.py; now imports from
dictumc package modules.

Usage:
    pip install fastapi uvicorn pydantic
    python ui/backend_server.py
    # Open ui/dictum_vibecoder.html in browser
"""
import sys
import os
import subprocess
import tempfile

# Resolve package root (ui/ is one level below project root)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

try:
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    import uvicorn
except ImportError:
    print("Install dependencies: pip install fastapi uvicorn pydantic")
    sys.exit(1)

# v5 imports — from split dictumc package
from dictumc.transpiler import StdlibTranspiler, Transpiler
from dictumc.grammar import DictumGrammar
from dictumc.stdlib_registry import DICTUM_STDLIB_TYPES, STDLIB_ACTION_FAMILIES

app = FastAPI(title="Dictum VibeCoder API", version="5.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STDLIB_ROOT = os.path.join(_PROJECT_ROOT, "stdlib")
NICHE_ROOT  = os.path.join(_PROJECT_ROOT, "niche")


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class TranspileRequest(BaseModel):
    source: str
    backend: str = "c"
    target: str = "linux"
    cpp_standard: int = 17
    stdlib: bool = True
    validate_code: bool = True   # renamed from `validate` to avoid Pydantic clash


class RunRequest(TranspileRequest):
    compile: bool = True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_transpiler(req: TranspileRequest):
    """Return a StdlibTranspiler (if stdlib=True) or plain Transpiler."""
    kwargs = dict(
        backend=req.backend,
        cpp_standard=req.cpp_standard,
    )
    if req.stdlib:
        return StdlibTranspiler(req.source, **kwargs)
    return Transpiler(req.source, **kwargs)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/")
def root():
    return {"status": "ok", "version": "5.0", "language": "Dictum"}


@app.post("/transpile")
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


@app.post("/run")
def run(req: RunRequest):
    transpile_result = transpile(req)
    if not transpile_result["ok"]:
        return transpile_result
    if not req.compile:
        return transpile_result

    code = transpile_result["code"]
    ext = ".cpp" if req.backend.lower() in ("cpp", "c++") else ".c"
    compiler = "g++" if ext == ".cpp" else "gcc"

    with tempfile.TemporaryDirectory() as tmpdir:
        src_path = os.path.join(tmpdir, f"program{ext}")
        bin_path = os.path.join(tmpdir, "program")
        with open(src_path, "w", encoding="utf-8") as f:
            f.write(code)

        compile_cmd = [
            compiler, src_path, "-o", bin_path,
            f"-I{STDLIB_ROOT}", f"-I{NICHE_ROOT}",
            f"-L{STDLIB_ROOT}",
            "-lpthread", "-lm",
        ]
        if ext == ".cpp":
            compile_cmd += [f"-std=c++{req.cpp_standard}"]
        else:
            compile_cmd += ["-std=c11"]

        compile_proc = subprocess.run(
            compile_cmd, capture_output=True, text=True, timeout=30
        )
        if compile_proc.returncode != 0:
            return {
                "ok": False,
                "error": compile_proc.stderr,
                "code": code,
                "warnings": transpile_result["warnings"],
            }

        run_proc = subprocess.run(
            [bin_path], capture_output=True, text=True, timeout=10
        )
        return {
            "ok": True,
            "code": code,
            "output": run_proc.stdout,
            "stderr": run_proc.stderr,
            "exit_code": run_proc.returncode,
            "warnings": transpile_result["warnings"],
        }


@app.get("/skills")
def list_skills():
    """List available stdlib module families."""
    return {
        "families": list(STDLIB_ACTION_FAMILIES.keys()),
        "types": list(DICTUM_STDLIB_TYPES),
    }


@app.get("/grammar/tokens")
def grammar_tokens():
    """Return valid first tokens for grammar-constrained generation."""
    g = DictumGrammar(cpp_mode=False)
    tokens = g.get_valid_tokens() if hasattr(g, "get_valid_tokens") else []
    return {"tokens": tokens}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8765, reload=True)
