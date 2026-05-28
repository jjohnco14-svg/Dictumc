# Dictum VibeCoder UI

Browser-based IDE for the Dictum language. Two components:

- **`dictum_vibecoder.html`** — standalone single-file editor with syntax highlighting, transpile, and run buttons
- **`backend_server.py`** — FastAPI backend that connects the UI to the transpiler

## Setup

```bash
pip install fastapi uvicorn
python backend_server.py        # starts on http://localhost:8765
# Then open dictum_vibecoder.html in browser
```

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/transpile` | POST | Dictum source → C/C++ code |
| `/run` | POST | Transpile, compile with gcc/g++, execute |
| `/skills` | GET | List available stdlib families and types |
| `/grammar/tokens` | GET | Valid next tokens (grammar-constrained generation) |
