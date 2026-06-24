# Agent NEO - VS Code Extension

Interactive coding partner powered by Agent NEO.

## Features

- **Sidebar chat** — Agent NEO lives in its own activity-bar view (left sidebar). `Agent NEO: Open Chat` focuses it; an editor panel is used as a fallback.
- **Live run cards** — AutoRun and phased runs stream progress into the chat: context packs, plan/phase progress, tool activity, verification + repair attempts, governance gate outcomes, commits, and a final run summary card with clickable file chips.
- **Workspace awareness** — a header strip shows the current folder, git branch, and pending change count (via VS Code's built-in git extension).
- **Terminal integration** — `run_command` results include a "Run in terminal" button that replays the command in a dedicated "Agent NEO" terminal (`Agent NEO: Open Agent NEO Terminal`).
- **In-chat settings** — the ⚙️ button opens a settings surface: integrations/health, rules & guidelines (`.neo`, `.neo.md`, `AGENT.md`), last context pack, terminal, workspace, and preferences.
- **Chat extras** — slash commands (`/run`, `/plan`, `/fix`, `/verify`, `/rollback`, `/clone`), diff proposals with approve/reject, image/PDF attachments, speech-to-text, prompt suggestions, inline completion.
- **Backend toggle (Neo ↔ Auggie)** — run prompts through the Neo backend or through a local [Auggie CLI](https://docs.augmentcode.com/cli/overview) subprocess. Auggie's output streams into the same run cards, and Neo's safety model still applies: changed files are surfaced for review in Source Control and **nothing is committed or pushed automatically**.

## Requirements

- VS Code 1.85.0 or higher
- Agent NEO backend running (see main README)

## Extension Settings

This extension contributes the following settings:

- `agentNeo.apiUrl`: Agent NEO API URL (default: `http://127.0.0.1:8000`)
- `agentNeo.apiToken`: Agent NEO API Bearer Token
- `agentNeo.enableInlineCompletion`: Enable inline code completion (default: `true`)
- `agentNeo.enableSuggestions`: Enable prompt suggestions (default: `true`)
- `agentNeo.agentBackend`: Which agent runs your prompts — `neo` (HTTP backend) or `auggie` (local CLI) (default: `neo`)
- `agentNeo.auggiePath`: Path/command used to launch the Auggie CLI (default: `auggie`)

## Using the Auggie backend

The Auggie backend runs the [Auggie CLI](https://docs.augmentcode.com/cli/overview)
locally as a subprocess instead of calling the Neo HTTP API — useful as a fallback
when the Neo backend is unavailable.

1. Install the CLI:

   ```bash
   npm install -g @augmentcode/auggie
   ```

2. Authenticate once:

   ```bash
   auggie login
   ```

3. Switch backends, either:
   - In chat, open ⚙️ settings → **Integrations** → **Switch to Auggie CLI**, or
   - Run `Agent NEO: Toggle Agent Backend (Neo / Auggie)` from the command palette, or
   - Set `agentNeo.agentBackend` to `auggie` in settings.

Prompts now run through Auggie. After a run, changed files are listed for manual
review in Source Control — commit and push yourself; the extension never does it for
you. Use `Agent NEO: Stop Auggie Session` to cancel an in-progress run.

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
code --install-extension agent-neo-vscode-2.3.0.vsix
```

## License

See main Agent NEO repository.

