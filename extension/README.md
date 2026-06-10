# Agent NEO - VS Code Extension

Interactive coding partner powered by Agent NEO.

## Features

- **Sidebar chat** — Agent NEO lives in its own activity-bar view (left sidebar). `Agent NEO: Open Chat` focuses it; an editor panel is used as a fallback.
- **Live run cards** — AutoRun and phased runs stream progress into the chat: context packs, plan/phase progress, tool activity, verification + repair attempts, governance gate outcomes, commits, and a final run summary card with clickable file chips.
- **Workspace awareness** — a header strip shows the current folder, git branch, and pending change count (via VS Code's built-in git extension).
- **Terminal integration** — `run_command` results include a "Run in terminal" button that replays the command in a dedicated "Agent NEO" terminal (`Agent NEO: Open Agent NEO Terminal`).
- **In-chat settings** — the ⚙️ button opens a settings surface: integrations/health, rules & guidelines (`.neo`, `.neo.md`, `AGENT.md`), last context pack, terminal, workspace, and preferences.
- **Chat extras** — slash commands (`/run`, `/plan`, `/fix`, `/verify`, `/rollback`, `/clone`), diff proposals with approve/reject, image/PDF attachments, speech-to-text, prompt suggestions, inline completion.

## Requirements

- VS Code 1.85.0 or higher
- Agent NEO backend running (see main README)

## Extension Settings

This extension contributes the following settings:

- `agentNeo.apiUrl`: Agent NEO API URL (default: `http://127.0.0.1:8000`)
- `agentNeo.apiToken`: Agent NEO API Bearer Token
- `agentNeo.enableInlineCompletion`: Enable inline code completion (default: `true`)
- `agentNeo.enableSuggestions`: Enable prompt suggestions (default: `true`)

## Development

```bash
cd extension
npm install
npm run compile
```

Press F5 in VS Code to launch the extension in debug mode.

## Building

```bash
npm run vscode:prepublish
```

## Installation

For personal use, install the VSIX file:

```bash
code --install-extension agent-neo-vscode-2.1.0.vsix
```

## License

See main Agent NEO repository.

