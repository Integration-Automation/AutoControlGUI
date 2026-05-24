// VSCode extension entry — launches the Python LSP server, registers
// Run / Screenshot / Preview commands that hit the AutoControl REST API,
// and exposes a tree view of the current script's steps.

import * as vscode from "vscode";
import * as http from "http";
import * as https from "https";
import { URL } from "url";
import {
    LanguageClient,
    LanguageClientOptions,
    ServerOptions,
    TransportKind,
} from "vscode-languageclient/node";

let client: LanguageClient | undefined;
let stepProvider: ScriptStepProvider | undefined;

export function activate(context: vscode.ExtensionContext): void {
    client = startLanguageClient();
    context.subscriptions.push({ dispose: () => client?.stop() });

    stepProvider = new ScriptStepProvider();
    context.subscriptions.push(
        vscode.window.registerTreeDataProvider(
            "autocontrolScriptSteps", stepProvider,
        ),
    );
    context.subscriptions.push(
        vscode.window.onDidChangeActiveTextEditor(() => stepProvider?.refresh()),
        vscode.workspace.onDidChangeTextDocument(() => stepProvider?.refresh()),
    );

    context.subscriptions.push(
        vscode.commands.registerCommand(
            "autocontrol.runScript", runCurrentScript,
        ),
        vscode.commands.registerCommand(
            "autocontrol.takeScreenshot", takeScreenshot,
        ),
        vscode.commands.registerCommand(
            "autocontrol.previewScript", () => stepProvider?.refresh(),
        ),
    );
}

export function deactivate(): Thenable<void> | undefined {
    return client?.stop();
}

// --- LSP client --------------------------------------------------

function startLanguageClient(): LanguageClient {
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
    const lc = new LanguageClient(
        "autocontrolLsp", "AutoControl LSP",
        serverOptions, clientOptions,
    );
    lc.start();
    return lc;
}

// --- REST helpers -------------------------------------------------

function restConfig(): { url: string; token: string } {
    const config = vscode.workspace.getConfiguration("autocontrolLsp");
    return {
        url: config.get<string>("rest.url", "http://127.0.0.1:9939"),
        token: config.get<string>("rest.token", "")
            || process.env.AC_TOKEN || "",
    };
}

interface RestReply {
    statusCode: number;
    body: string;
}

function postJson(path: string, payload: unknown): Promise<RestReply> {
    return new Promise((resolve, reject) => {
        const { url, token } = restConfig();
        let parsed: URL;
        try {
            parsed = new URL(path, url);
        } catch (error) {
            reject(error);
            return;
        }
        const isHttps = parsed.protocol === "https:";
        const body = Buffer.from(JSON.stringify(payload), "utf-8");
        const requestOptions: http.RequestOptions = {
            hostname: parsed.hostname,
            port: parsed.port || (isHttps ? 443 : 80),
            path: parsed.pathname + parsed.search,
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Content-Length": body.length,
                "Authorization": token ? `Bearer ${token}` : "",
            },
        };
        const httpModule = isHttps ? https : http;
        const request = httpModule.request(requestOptions, (response) => {
            const chunks: Buffer[] = [];
            response.on("data", (chunk: Buffer) => chunks.push(chunk));
            response.on("end", () => resolve({
                statusCode: response.statusCode || 0,
                body: Buffer.concat(chunks).toString("utf-8"),
            }));
        });
        request.on("error", reject);
        request.write(body);
        request.end();
    });
}

// --- Commands -----------------------------------------------------

async function runCurrentScript(): Promise<void> {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
        vscode.window.showWarningMessage(
            "AutoControl: open a JSON action file first.",
        );
        return;
    }
    let actions: unknown;
    try {
        actions = JSON.parse(editor.document.getText());
    } catch (error) {
        vscode.window.showErrorMessage(
            `AutoControl: cannot run — invalid JSON (${(error as Error).message})`,
        );
        return;
    }
    try {
        const reply = await postJson("/execute", { actions });
        if (reply.statusCode >= 200 && reply.statusCode < 300) {
            vscode.window.showInformationMessage(
                `AutoControl: ran ${editor.document.fileName}`,
            );
            return;
        }
        vscode.window.showErrorMessage(
            `AutoControl: REST ${reply.statusCode}: ${reply.body.slice(0, 240)}`,
        );
    } catch (error) {
        vscode.window.showErrorMessage(
            `AutoControl: REST call failed (${(error as Error).message})`,
        );
    }
}

async function takeScreenshot(): Promise<void> {
    try {
        const reply = await postJson("/screenshot", {});
        if (reply.statusCode >= 200 && reply.statusCode < 300) {
            vscode.window.showInformationMessage(
                "AutoControl: screenshot captured.",
            );
            return;
        }
        vscode.window.showErrorMessage(
            `AutoControl: REST ${reply.statusCode}`,
        );
    } catch (error) {
        vscode.window.showErrorMessage(
            `AutoControl: REST call failed (${(error as Error).message})`,
        );
    }
}

// --- Tree view ----------------------------------------------------

class ScriptStepProvider implements vscode.TreeDataProvider<StepItem> {
    private emitter = new vscode.EventEmitter<StepItem | undefined>();
    readonly onDidChangeTreeData = this.emitter.event;

    refresh(): void { this.emitter.fire(undefined); }

    getTreeItem(element: StepItem): vscode.TreeItem { return element; }

    getChildren(): vscode.ProviderResult<StepItem[]> {
        const editor = vscode.window.activeTextEditor;
        if (!editor || editor.document.languageId !== "json") {
            return [];
        }
        let parsed: unknown;
        try {
            parsed = JSON.parse(editor.document.getText());
        } catch {
            return [];
        }
        if (!Array.isArray(parsed)) { return []; }
        return parsed.map((entry, index) => {
            if (Array.isArray(entry) && typeof entry[0] === "string") {
                return new StepItem(`${index + 1}. ${entry[0]}`,
                    entry.length > 1 ? JSON.stringify(entry[1]) : "");
            }
            return new StepItem(`${index + 1}. (malformed)`,
                JSON.stringify(entry));
        });
    }
}

class StepItem extends vscode.TreeItem {
    constructor(label: string, description: string) {
        super(label, vscode.TreeItemCollapsibleState.None);
        this.description = description;
        this.tooltip = description;
    }
}
