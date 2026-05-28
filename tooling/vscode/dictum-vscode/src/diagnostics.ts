import * as vscode from 'vscode';
import { exec } from 'child_process';
import { promisify } from 'util';
import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';

const execAsync = promisify(exec);

export class DictumDiagnostics {
    private collection: vscode.DiagnosticCollection;
    private timeout: NodeJS.Timeout | undefined;
    private pendingValidation: Map<string, string> = new Map();

    constructor() {
        this.collection = vscode.languages.createDiagnosticCollection('dictum');
    }

    subscribe(context: vscode.ExtensionContext): void {
        context.subscriptions.push(this.collection);

        // Validate on change (debounced)
        vscode.workspace.onDidChangeTextDocument(e => {
            if (e.document.languageId === 'dictum') {
                this.pendingValidation.set(e.document.uri.toString(), e.document.getText());
                clearTimeout(this.timeout);
                this.timeout = setTimeout(() => this._validateAllPending(), 500);
            }
        }, null, context.subscriptions);

        // Validate on save
        vscode.workspace.onDidSaveTextDocument(doc => {
            if (doc.languageId === 'dictum') {
                this.pendingValidation.delete(doc.uri.toString());
                this.validate(doc.uri, doc.getText());
            }
        }, null, context.subscriptions);

        // Validate open documents
        vscode.workspace.textDocuments.forEach(doc => {
            if (doc.languageId === 'dictum') {
                this.validate(doc.uri, doc.getText());
            }
        });
    }

    private async _validateAllPending(): Promise<void> {
        for (const [uri, text] of this.pendingValidation) {
            await this.validate(vscode.Uri.parse(uri), text);
        }
        this.pendingValidation.clear();
    }

    async validate(uri: vscode.Uri, text: string): Promise<void> {
        const config = vscode.workspace.getConfiguration('dictum');
        if (!config.get<boolean>('enableDiagnostics', true)) return;

        const dictumcPath = config.get<string>('dictumcPath', 'dictumc');

        try {
            const tmpFile = path.join(os.tmpdir(), `dictum_validate_${Date.now()}.dict`);
            fs.writeFileSync(tmpFile, text);

            const { stderr } = await execAsync(
                `python ${dictumcPath} "${tmpFile}" --backend c`,
                { timeout: 15000 }
            ).catch(e => ({ stdout: '', stderr: e.stderr || e.message }));

            fs.unlinkSync(tmpFile);

            const diagnostics = this._parseDiagnostics(stderr, uri);
            this.collection.set(uri, diagnostics);
        } catch (err) {
            console.error('Validation failed:', err);
        }
    }

    private _parseDiagnostics(stderr: string, uri: vscode.Uri): vscode.Diagnostic[] {
        const diagnostics: vscode.Diagnostic[] = [];

        // Parse validation errors: "[Line X] Error message"
        const errorRegex = /\[Line (\d+)\] (.+)/g;
        let match;
        while ((match = errorRegex.exec(stderr)) !== null) {
            const line = Math.max(0, parseInt(match[1]) - 1);
            const message = match[2];
            const range = new vscode.Range(line, 0, line, 999);
            diagnostics.push(new vscode.Diagnostic(
                range, message, vscode.DiagnosticSeverity.Error
            ));
        }

        // Parse warnings: "[Line X] Warning: message"
        const warnRegex = /\[Line (\d+)\] Warning: (.+)/g;
        while ((match = warnRegex.exec(stderr)) !== null) {
            const line = Math.max(0, parseInt(match[1]) - 1);
            const message = match[2];
            const range = new vscode.Range(line, 0, line, 999);
            diagnostics.push(new vscode.Diagnostic(
                range, message, vscode.DiagnosticSeverity.Warning
            ));
        }

        // Parse ownership violations
        const ownershipRegex = /Ownership violation: (.+)/g;
        while ((match = ownershipRegex.exec(stderr)) !== null) {
            // Try to find line number from context
            const line = 0; // Fallback
            const range = new vscode.Range(line, 0, line, 999);
            diagnostics.push(new vscode.Diagnostic(
                range, match[1], vscode.DiagnosticSeverity.Error
            ));
        }

        return diagnostics;
    }
}