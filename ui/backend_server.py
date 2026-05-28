#!/usr/bin/env python3
"""
Dictum VibeCoder Backend Server — v5.2
Bridges the VibeCoder HTML UI to the Dictum v5 transpiler.

v5.1 additions:
  • SQLite-backed workspace persistence: save/load/list named programs.
    Programs survive browser tab close and server restart.

v5.2 additions:
  • QEMU user-mode execution (Strategy 1).
    Set target: "arm64" | "riscv64" | "mips" | "mipsel" | "ppc64le"
    in any /run request to cross-compile and execute under qemu-user.
    "linux" (default) keeps the original host-native behaviour.
  • GET /targets — list available targets and their availability on
    this machine (cross-compiler + qemu binary presence checks).

Setup for QEMU targets (Ubuntu/Debian):
    sudo apt install qemu-user \
        gcc-aarch64-linux-gnu   g++-aarch64-linux-gnu   \
        gcc-riscv64-linux-gnu   g++-riscv64-linux-gnu   \
        gcc-mips-linux-gnu      g++-mips-linux-gnu      \
        gcc-mipsel-linux-gnu    g++-mipsel-linux-gnu    \
        gcc-powerpc64le-linux-gnu g++-powerpc64le-linux-gnu

Usage:
    pip install fastapi uvicorn pydantic
    python ui/backend_server.py
    # Open ui/dictum_vibecoder.html in browser
"""
import sys
import os
import shutil
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
# QEMU user-mode target table (v5.2)
# ---------------------------------------------------------------------------

# Each entry:
#   cc       — C cross-compiler binary name
#   cxx      — C++ cross-compiler binary name
#   qemu     — qemu-user binary name
#   sysroot  — default Debian/Ubuntu multiarch sysroot path for -L flag
#   label    — human-readable name shown in /targets

_QEMU_TARGETS: dict = {
    "linux": {
        "cc": "gcc", "cxx": "g++",
        "qemu": None, "sysroot": None,
        "label": "Linux x86-64 (host native)",
    },
    "arm64": {
        "cc": "aarch64-linux-gnu-gcc",  "cxx": "aarch64-linux-gnu-g++",
        "qemu": "qemu-aarch64",         "sysroot": "/usr/aarch64-linux-gnu",
        "label": "ARM64 / AArch64",
    },
    "riscv64": {
        "cc": "riscv64-linux-gnu-gcc",  "cxx": "riscv64-linux-gnu-g++",
        "qemu": "qemu-riscv64",         "sysroot": "/usr/riscv64-linux-gnu",
        "label": "RISC-V 64-bit",
    },
    "mips": {
        "cc": "mips-linux-gnu-gcc",     "cxx": "mips-linux-gnu-g++",
        "qemu": "qemu-mips",            "sysroot": "/usr/mips-linux-gnu",
        "label": "MIPS big-endian",
    },
    "mipsel": {
        "cc": "mipsel-linux-gnu-gcc",   "cxx": "mipsel-linux-gnu-g++",
        "qemu": "qemu-mipsel",          "sysroot": "/usr/mipsel-linux-gnu",
        "label": "MIPS little-endian",
    },
    "ppc64le": {
        "cc": "powerpc64le-linux-gnu-gcc",  "cxx": "powerpc64le-linux-gnu-g++",
        "qemu": "qemu-ppc64le",             "sysroot": "/usr/powerpc64le-linux-gnu",
        "label": "PowerPC 64-bit LE",
    },
}


def _target_available(name: str) -> dict:
    """Return availability info for a single target."""
    t = _QEMU_TARGETS.get(name)
    if t is None:
        return {"available": False, "reason": "unknown target"}
    if name == "linux":
        cc_ok = shutil.which("gcc") is not None
        return {"available": cc_ok, "reason": None if cc_ok else "gcc not found"}
    cc_ok   = shutil.which(t["cc"])   is not None
    qemu_ok = shutil.which(t["qemu"]) is not None
    if cc_ok and qemu_ok:
        return {"available": True, "reason": None}
    missing = []
    if not cc_ok:   missing.append(t["cc"])
    if not qemu_ok: missing.append(t["qemu"])
    return {"available": False, "reason": f"missing: {', '.join(missing)}"}


def _resolve_target(target: str):
    """Return (target_dict, warning_str|None). Falls back to linux if unknown."""
    if target not in _QEMU_TARGETS:
        return _QEMU_TARGETS["linux"], f"Unknown target '{target}', falling back to linux"
    return _QEMU_TARGETS[target], None


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

    # ── v5.2: resolve QEMU target ──────────────────────────────────────────
    tgt, tgt_warning = _resolve_target(req.target)
    warnings = list(transpile_result.get("warnings", []))
    if tgt_warning:
        warnings.append(tgt_warning)

    # Check that required tools are present before wasting time compiling
    avail = _target_available(req.target if req.target in _QEMU_TARGETS else "linux")
    if not avail["available"]:
        return {
            "ok": False,
            "error": (
                f"Target '{req.target}' is not available on this machine.\n"
                f"Reason: {avail['reason']}\n\n"
                "Install guide (Ubuntu/Debian):\n"
                f"  sudo apt install qemu-user {tgt['cc'].replace('-gcc','')}* {tgt['cxx'].replace('-g++','')}-*"
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
            f"-L{STDLIB_ROOT}",
            "-lpthread", "-lm",
        ]
        if ext == ".cpp":
            compile_cmd += [f"-std=c++{req.cpp_standard}"]
        else:
            compile_cmd += ["-std=c11"]

        # Cross-targets need static linking so the binary is self-contained
        # inside the QEMU sandbox (avoids dynamic linker path issues).
        if tgt["qemu"] is not None:
            compile_cmd += ["-static"]

        compile_proc = subprocess.run(
            compile_cmd, capture_output=True, text=True, timeout=30
        )
        if compile_proc.returncode != 0:
            return {"ok": False, "error": compile_proc.stderr, "code": code,
                    "warnings": warnings}

        # ── Build the execution command ────────────────────────────────────
        if tgt["qemu"] is None:
            # Native host execution
            run_cmd = [bin_path]
        else:
            # qemu-user: qemu-<arch> [sysroot] <binary>
            run_cmd = [tgt["qemu"]]
            if tgt["sysroot"] and os.path.isdir(tgt["sysroot"]):
                run_cmd += ["-L", tgt["sysroot"]]
            run_cmd.append(bin_path)

        run_proc = subprocess.run(
            run_cmd, capture_output=True, text=True, timeout=10
        )
        return {
            "ok": True, "code": code,
            "output": run_proc.stdout,
            "stderr": run_proc.stderr,
            "exit_code": run_proc.returncode,
            "warnings": warnings,
            "target": req.target,
            "target_label": tgt["label"],
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
# /generate endpoint — Ask → Plan → Verify → Output pipeline (v5.2, BYOK)
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    prompt:       str
    backend:      str = "c"
    cpp_standard: int = 17
    project:      str = ""
    currentFile:  str = ""
    skills:       List[str] = []          # e.g. ["general","embedded","medical"]
    api_key:      str = ""                # BYOK — Claude API key from the UI
    model:        str = "claude-opus-4-5" # override if needed
    auto_transpile: bool = True           # run transpiler on generated code


# Skill file registry — maps skill id → filename under industry_skills/
_SKILL_FILES: dict = {
    "general":   "SKILL_GENERAL.md",
    "syntax":    "DICTUM_SYNTAX.md",
    "medical":   "SKILL_MEDICAL.md",
    "robotics":  "SKILL_ROBOTICS.md",
    "automotive":"SKILL_AUTOMOTIVE.md",
    "industrial":"SKILL_INDUSTRIAL.md",
    "aerospace": "SKILL_AEROSPACE.md",
    "telecom":   "SKILL_TELECOM_ENERGY.md",
    "embedded":  "SKILL_EMBEDDED.md",
    "edgeai":    "SKILL_EDGEAI.md",
    "security":  "SKILL_SECURITY.md",
}

_SKILLS_ROOT = os.path.join(_PROJECT_ROOT, "industry_skills")


def _load_skill(skill_id: str) -> str:
    """Load a skill file and return its content, or empty string if not found."""
    fname = _SKILL_FILES.get(skill_id.lower())
    if not fname:
        return ""
    path = os.path.join(_SKILLS_ROOT, fname)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return f"# Skill file '{fname}' not found\n"


def _build_system_prompt(skills: List[str]) -> str:
    """
    Assemble the system prompt for the code generation pipeline.
    Always loads: syntax + general.
    Then appends any domain skills requested.
    """
    # Always-on base skills
    base_skills = ["syntax", "general"]
    domain_skills = [s for s in skills if s not in base_skills]

    parts = []

    parts.append("""You are a Dictum code generation assistant. Dictum is a natural-language programming language that compiles to C or C++.

You follow a strict four-step pipeline for every request:
  1. CLARIFY — identify what is needed; ask at most one question if critical info is missing
  2. PLAN    — write a numbered plan (shapes, modules, actions, control flow, error paths)
  3. VERIFY  — run the syntax checklist mentally before emitting any code
  4. OUTPUT  — emit valid Dictum code followed by compile commands

You NEVER emit raw C or C++ directly. You write Dictum and let the compiler handle C.
You NEVER hardcode API keys, tokens, or credentials — always BYOK via env var or config file.
""")

    # Append syntax reference
    syntax = _load_skill("syntax")
    if syntax:
        parts.append("---\n# DICTUM SYNTAX REFERENCE\n\n" + syntax)

    # Append general skill
    general = _load_skill("general")
    if general:
        parts.append("---\n# GENERAL SKILL — PIPELINE & PATTERNS\n\n" + general)

    # Append domain skills
    for sid in domain_skills:
        content = _load_skill(sid)
        if content:
            parts.append(f"---\n# DOMAIN SKILL: {sid.upper()}\n\n" + content)

    parts.append("""---
## Output format

Always structure your response as:

CLARIFY (if needed):
<one question if the request is ambiguous — otherwise skip this section>

PLAN:
1. Shapes: ...
2. Modules: ...
3. Actions: ...
4. Control flow: ...
5. Error paths: ...

VERIFY:
[ ] (checklist — mark all as checked before proceeding)

DICTUM CODE:
```dictum
<full valid Dictum program>
```

COMPILE:
```bash
<validate and compile commands>
```
""")

    return "\n\n".join(parts)


def _extract_dictum_code(text: str) -> str:
    """Pull the Dictum code block out of the LLM response."""
    import re
    # Try ```dictum ... ``` first
    m = re.search(r"```(?:dictum|dict)\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    # Fallback: find program ... end program
    m = re.search(r"(program\s+\w+:.*?end\s+program)", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    # Fallback: find module ... end module
    m = re.search(r"(module\s+\w+:.*?end\s+module)", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return ""


@app.post("/generate")
def generate(req: GenerateRequest):
    """
    Ask → Plan → Verify → Output pipeline.

    Calls the Anthropic Claude API (BYOK) with the assembled system prompt,
    extracts the generated Dictum code, optionally auto-transpiles it,
    and returns the full structured response.
    """
    import urllib.request
    import json as _json

    api_key = req.api_key.strip()
    if not api_key:
        # Try env fallback
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {
            "ok": False,
            "error": (
                "No API key provided. "
                "Pass your Anthropic API key in the request as \'api_key\' "
                "or set the ANTHROPIC_API_KEY environment variable."
            ),
            "message": "API key required — enter your key in Settings → LLM Provider.",
        }

    system_prompt = _build_system_prompt(req.skills)

    payload = _json.dumps({
        "model": req.model,
        "max_tokens": 4096,
        "system": system_prompt,
        "messages": [
            {"role": "user", "content": req.prompt}
        ],
    }).encode("utf-8")

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
            body = _json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        return {"ok": False, "error": f"Anthropic API error {e.code}: {err_body}", "message": "API call failed."}
    except Exception as e:
        return {"ok": False, "error": str(e), "message": "API call failed."}

    # Extract text content from response
    full_text = ""
    for block in body.get("content", []):
        if block.get("type") == "text":
            full_text += block["text"]

    if not full_text:
        return {"ok": False, "error": "Empty response from API", "message": "No content returned."}

    # Extract Dictum code block
    dictum_code = _extract_dictum_code(full_text)

    result = {
        "ok": True,
        "message": full_text,
        "dictum": dictum_code,
        "c": "",
        "warnings": [],
    }

    # Auto-transpile if code was extracted and compile=True
    if req.auto_transpile and dictum_code:
        transpile_req = TranspileRequest(
            source=dictum_code,
            backend=req.backend,
            cpp_standard=req.cpp_standard,
            stdlib=True,
            validate_code=True,
        )
        transpile_result = transpile(transpile_req)
        result["transpile_ok"] = transpile_result.get("ok", False)
        result["c"] = transpile_result.get("code", "")
        result["warnings"] = transpile_result.get("warnings", [])
        if not transpile_result.get("ok"):
            result["transpile_error"] = transpile_result.get("error", "")

    return result


# ---------------------------------------------------------------------------
# Info endpoints
# ---------------------------------------------------------------------------

@app.get("/targets")
def list_targets():
    """List all supported QEMU execution targets and their availability."""
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


# (Legacy v5.0 duplicate /run removed in v5.2 — QEMU-aware /run lives above)


@app.get("/grammar/tokens")
def grammar_tokens():
    """Return valid first tokens for grammar-constrained generation."""
    g = DictumGrammar(cpp_mode=False)
    tokens = g.get_valid_tokens() if hasattr(g, "get_valid_tokens") else []
    return {"tokens": tokens}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8765, reload=True)
