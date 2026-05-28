# Language Server Protocol (LSP)

Dictum ships a lightweight LSP server that powers the VS Code extension and any LSP-capable editor (Neovim, Emacs, Helix).

## Starting the server

```bash
dictumc --lsp
```

The server speaks JSON-RPC over stdio (standard LSP transport).

## Supported capabilities

| Capability                  | Status       |
|----------------------------|--------------|
| `textDocument/diagnostics`  | ✅ Supported  |
| `textDocument/hover`        | ✅ Supported  |
| `textDocument/completion`   | ✅ Supported  |
| `textDocument/formatting`   | ⚠️ Partial    |
| `textDocument/definition`   | 🔜 Planned   |
| `textDocument/references`   | 🔜 Planned   |

## Neovim (nvim-lspconfig)

```lua
require('lspconfig').configs.dictum = {
  default_config = {
    cmd = { 'dictumc', '--lsp' },
    filetypes = { 'dictum' },
    root_dir = require('lspconfig').util.root_pattern('pyproject.toml', '.git'),
  },
}
require('lspconfig').dictum.setup {}
```

## Helix

Add to `~/.config/helix/languages.toml`:

```toml
[[language]]
name = "dictum"
scope = "source.dictum"
file-types = ["dict"]
language-server = { command = "dictumc", args = ["--lsp"] }
```
