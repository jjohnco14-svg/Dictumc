# VS Code Extension

The Dictum VS Code extension provides syntax highlighting, snippets, and inline diagnostics.

## Installation

From the VS Code Marketplace (once published):
1. Open VS Code → Extensions (`Ctrl+Shift+X`).
2. Search for "Dictum Language".
3. Click Install.

Or install from VSIX:
```bash
cd tooling/vscode/dictum-vscode
npm install
npm run compile
vsce package
code --install-extension dictum-*.vsix
```

## Features

- **Syntax highlighting** — keywords, types, operators, comments, string literals.
- **Snippets** — type `prog` + Tab for a program scaffold; `act` for an action; `shp` for a shape.
- **Diagnostics** — error squiggles via the Dictum Language Server (requires `dictumc` on PATH).
- **Hover information** — type information for variables and actions.

## Requirements

- VS Code 1.80+
- Node.js 18+
- `dictumc` installed and on your system `PATH`

## Configuration

| Setting                        | Default  | Description                         |
|-------------------------------|----------|-------------------------------------|
| `dictum.dictumcPath`          | `dictumc`| Path to the dictumc binary          |
| `dictum.lintOnSave`           | `true`   | Run diagnostics on file save        |
| `dictum.backend`              | `c`      | Default compile target (`c`/`cpp`)  |
