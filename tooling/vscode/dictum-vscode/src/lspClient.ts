import * as vscode from 'vscode';
import { 
    LanguageClient, 
    LanguageClientOptions, 
    ServerOptions, 
    TransportKind 
} from 'vscode-languageclient/node';

export function startLSP(context: vscode.ExtensionContext): LanguageClient {
    const config = vscode.workspace.getConfiguration('dictum');
    const serverPath = config.get<string>('lsp.serverPath', 'dictum-lsp');

    const serverOptions: ServerOptions = {
        command: serverPath,
        args: [],
        transport: TransportKind.stdio
    };

    const clientOptions: LanguageClientOptions = {
        documentSelector: [
            { scheme: 'file', language: 'dictum' },
            { scheme: 'untitled', language: 'dictum' }
        ],
        synchronize: {
            fileEvents: vscode.workspace.createFileSystemWatcher('**/*.dict')
        },
        outputChannelName: 'Dictum LSP'
    };

    const client = new LanguageClient(
        'dictum-lsp',
        'Dictum Language Server',
        serverOptions,
        clientOptions
    );

    client.start();
    return client;
}