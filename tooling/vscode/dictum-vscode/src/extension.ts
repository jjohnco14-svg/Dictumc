import * as vscode from 'vscode';
import { exec } from 'child_process';
import { promisify } from 'util';
import { DictumDiagnostics } from './diagnostics';
import { startLSP } from './lspClient';

const execAsync = promisify(exec);

let lspClient: any = null;

export function activate(context: vscode.ExtensionContext): void {
    console.log('Dictum extension activated');

    // ── Register Commands ──────────────────────────────────────────────

    // Transpile current file
    context.subscriptions.push(
        vscode.commands.registerCommand('dictum.transpile', async () => {
            const editor = vscode.window.activeTextEditor;
            if (!editor) {
                vscode.window.showWarningMessage('No active editor');
                return;
            }

            const doc = editor.document;
            if (doc.languageId !== 'dictum') {
                vscode.window.showWarningMessage('Not a Dictum file');
                return;
            }

            await _transpile(doc, false);
        })
    );

    // Transpile + Compile
    context.subscriptions.push(
        vscode.commands.registerCommand('dictum.transpileCompile', async () => {
            const editor = vscode.window.activeTextEditor;
            if (!editor) return;
            const doc = editor.document;
            if (doc.languageId !== 'dictum') return;

            await _transpile(doc, true);
        })
    );

    // Insert stdlib snippet
    context.subscriptions.push(
        vscode.commands.registerCommand('dictum.insertSnippet', async () => {
            const snippets = [
                { label: 'llm', description: 'LLM chatbot scaffold' },
                { label: 'speech', description: 'Speech recognition' },
                { label: 'robot', description: 'Robot servo/motor' },
                { label: 'pin', description: 'GPIO blink' },
                { label: 'wifi', description: 'WiFi connection' },
                { label: 'sensor', description: 'I2C sensor read' },
                { label: 'program', description: 'Program scaffold' },
                { label: 'action', description: 'Action definition' },
                { label: 'attempt', description: 'Error handling block' }
            ];

            const choice = await vscode.window.showQuickPick(snippets, {
                placeHolder: 'Select stdlib module or template'
            });
            if (!choice) return;

            const editor = vscode.window.activeTextEditor;
            if (!editor) return;

            try {
                const config = vscode.workspace.getConfiguration('dictum');
                const dictumcPath = config.get<string>('dictumcPath', 'dictumc');
                const { stdout } = await execAsync(`${dictumcPath} --snippet ${choice.label}`);

                await editor.edit(edit => {
                    edit.insert(editor.selection.active, stdout);
                });
            } catch (err: any) {
                vscode.window.showErrorMessage(`Failed to fetch snippet: ${err.message}`);
            }
        })
    );

    // Start REPL
    context.subscriptions.push(
        vscode.commands.registerCommand('dictum.runRepl', async () => {
            const terminal = vscode.window.createTerminal('Dictum REPL');
            const config = vscode.workspace.getConfiguration('dictum');
            const dictumcPath = config.get<string>('dictumcPath', 'dictumc');
            const backend = config.get<string>('backend', 'c');

            terminal.sendText(`${dictumcPath} --repl --backend ${backend}`);
            terminal.show();
        })
    );

    // ── Diagnostics ────────────────────────────────────────────────────
    const diagnostics = new DictumDiagnostics();
    diagnostics.subscribe(context);

    // ── LSP Client ─────────────────────────────────────────────────────
    const config = vscode.workspace.getConfiguration('dictum');
    if (config.get<boolean>('lsp.enabled', true)) {
        try {
            lspClient = startLSP(context);
        } catch (err) {
            console.error('Failed to start LSP client:', err);
        }
    }

    // ── Status Bar ─────────────────────────────────────────────────────
    const statusBar = vscode.window.createStatusBarItem(
        vscode.StatusBarAlignment.Right,
        100
    );
    statusBar.text = "$(file-code) Dictum";
    statusBar.tooltip = "Dictum language mode";
    statusBar.command = 'dictum.transpile';
    context.subscriptions.push(statusBar);

    vscode.window.onDidChangeActiveTextEditor(e => {
        if (e && e.document.languageId === 'dictum') {
            statusBar.show();
        } else {
            statusBar.hide();
        }
    });
}

export function deactivate(): void {
    if (lspClient) {
        lspClient.stop();
    }
}

// ── Helper: Transpile Document ─────────────────────────────────────────

async function _transpile(doc: vscode.TextDocument, compile: boolean): Promise<void> {
    const config = vscode.workspace.getConfiguration('dictum');
    const dictumcPath = config.get<string>('dictumcPath', 'dictumc');
    const backend = config.get<string>('backend', 'c');
    const cppStandard = config.get<number>('cppStandard', 17);

    const filePath = doc.fileName;
    const outExt = backend === 'cpp' ? '.cpp' : '.c';
    const outPath = filePath.replace(/\.(dict|dictum)$/, outExt);

    let cmd = `${dictumcPath} "${filePath}" --backend ${backend}`;
    if (backend === 'cpp') {
        cmd += ` --cpp-standard ${cppStandard}`;
    }

    try {
        vscode.window.withProgress({
            location: vscode.ProgressLocation.Notification,
            title: `Transpiling ${path.basename(filePath)}...`,
            cancellable: false
        }, async () => {
            const { stdout, stderr } = await execAsync(cmd, { timeout: 30000 });

            if (stderr && stderr.includes('VALIDATION FAILED')) {
                vscode.window.showErrorMessage('Transpile failed — check Problems panel');
                return;
            }

            // Write output file
            const fs = await import('fs');
            fs.writeFileSync(outPath, stdout);

            // Open generated file
            const uri = vscode.Uri.file(outPath);
            const generated = await vscode.workspace.openTextDocument(uri);
            await vscode.window.showTextDocument(generated, { 
                viewColumn: vscode.ViewColumn.Beside,
                preview: false 
            });

            vscode.window.showInformationMessage(
                `Transpiled to ${path.basename(outPath)}`,
                compile ? 'Compile' : undefined
            ).then(selection => {
                if (selection === 'Compile') {
                    _compile(outPath, backend, cppStandard);
                }
            });
        });
    } catch (err: any) {
        vscode.window.showErrorMessage(`Transpile failed: ${err.message}`);
    }
}

async function _compile(srcPath: string, backend: string, cppStandard: number): Promise<void> {
    const compiler = backend === 'cpp' ? 'g++' : 'gcc';
    const stdFlag = backend === 'cpp' 
        ? `-std=c++${cppStandard}` 
        : '-std=c11';
    const exePath = srcPath.replace(/\.(c|cpp)$/, '');

    const cmd = [compiler, stdFlag, '-O2', '-Wall', '-Wextra', srcPath, '-o', exePath];
    if (backend === 'c') cmd.push('-lm');

    try {
        const { stderr } = await execAsync(cmd.join(' '), { timeout: 30000 });
        if (stderr) {
            vscode.window.showWarningMessage(`Compile warnings: ${stderr}`);
        } else {
            vscode.window.showInformationMessage(`Compiled: ${path.basename(exePath)}`);
        }
    } catch (err: any) {
        vscode.window.showErrorMessage(`Compile failed: ${err.stderr || err.message}`);
    }
}

import * as path from 'path';