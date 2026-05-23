// VSCode extension entry — launches the Python LSP server and pipes
// JSON-RPC over stdio via vscode-languageclient.

import * as vscode from "vscode";
import {
    LanguageClient,
    LanguageClientOptions,
    ServerOptions,
    TransportKind,
} from "vscode-languageclient/node";

let client: LanguageClient | undefined;

export function activate(context: vscode.ExtensionContext): void {
    const config = vscode.workspace.getConfiguration("autocontrolLsp");
    const pythonPath = config.get<string>("python.path", "python");
    const serverModule = config.get<string>(
        "server.module", "autocontrol_lsp.server",
    );

    const serverOptions: ServerOptions = {
        command: pythonPath,
        args: ["-m", serverModule],
        transport: TransportKind.stdio,
    };

    // Activate for any JSON document, but the server filters at the
    // request level so we don't churn on unrelated package.json files.
    const clientOptions: LanguageClientOptions = {
        documentSelector: [
            { scheme: "file", language: "json" },
            { scheme: "file", language: "jsonc" },
        ],
        synchronize: {
            fileEvents: vscode.workspace.createFileSystemWatcher(
                "**/*.{json,jsonc}",
            ),
        },
    };

    client = new LanguageClient(
        "autocontrolLsp",
        "AutoControl LSP",
        serverOptions,
        clientOptions,
    );
    client.start();
    context.subscriptions.push({ dispose: () => client?.stop() });
}

export function deactivate(): Thenable<void> | undefined {
    return client?.stop();
}
