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
- **Terminal Agent Orchestrator** — Neo acts as a *workflow brain* that drives a terminal-based coding agent (Augment CLI first) as a swappable *execution engine*. It gathers repo context, builds a structured prompt for your review/edit, streams output into a run card, then analyses the result: detects tests/errors/milestones, **verifies the agent's claimed file/commit edits against the real working tree**, flags risky commands, and offers prioritised next-step suggestions. Secrets are redacted before output is buffered, displayed, or saved, and **suggestions only prefill the chat input — Neo never auto-sends or auto-commits**.

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

### Terminal Agent Orchestrator (`agentNeo.terminalAgent.*`)

The orchestrator is **off by default**; when disabled, Neo behaves exactly as before.

- `agentNeo.terminalAgent.enabled`: Master toggle for the orchestrator (default: `false`)
- `agentNeo.terminalAgent.defaultProvider`: Provider id to drive (default: `augment-cli`)
- `agentNeo.terminalAgent.cliPath`: Path/command for the selected CLI agent (default: `auggie`)
- `agentNeo.terminalAgent.defaultWorkingDir`: Repo path for runs; empty uses the first workspace folder (default: `""`)
- `agentNeo.terminalAgent.promptTemplate`: Prompt template with `{{variables}}` (`repo_path`, `current_branch`, `user_request`, …); empty uses the built-in default (default: `""`)
- `agentNeo.terminalAgent.maxTimeoutSeconds`: Hard per-run timeout in seconds; `0` disables it (default: `1800`)
- `agentNeo.terminalAgent.captureOutput`: Capture stdout/stderr into the rolling buffer (default: `true`)
- `agentNeo.terminalAgent.autoSaveSummaries`: Save a secret-redacted run summary to history when a run ends (default: `true`)
- `agentNeo.terminalAgent.observer.enabled`: Enable the Terminal Observer; only active when the orchestrator is on (default: `false`)
- `agentNeo.terminalAgent.observer.mode`: Observation source — `neo-process`, `vscode-terminal`, `log-file`, or `manual` (default: `neo-process`)
- `agentNeo.terminalAgent.observer.logFilePath`: Log file to tail when `observer.mode` is `log-file` (default: `""`)
- `agentNeo.terminalAgent.confirmBeforeSendingInput`: Require explicit confirmation before Neo sends any input to a terminal session (default: `true`)

## Using the Terminal Agent Orchestrator

1. Enable it: set `agentNeo.terminalAgent.enabled` to `true` (and pick a `cliPath` if your
   CLI isn't `auggie`).
2. Run a task, either:
   - In chat, open ⚙️ settings → **Terminal Agent** → **Send to Terminal Agent…**, or
   - Run `Agent NEO: Send to Terminal Agent` from the command palette.
3. Neo gathers repo context and shows the **generated prompt in an editor for review/edit**.
   Choose **Send** to launch the agent, **Copy**, or cancel — nothing runs until you Send.
4. Output streams into a run card. When it finishes, Neo shows post-run cards:
   - **Safety flags** for any risky commands it saw (never auto-run).
   - **Claim verification** — claimed vs. actual file/commit changes in the working tree.
   - **Suggested next steps** — click one to **prefill** the chat input (review before sending).
5. **Import / analyse pasted output** (⚙️ → **Terminal Agent**) runs the same analysis on
   output you paste from any agent, without git claim verification.
6. Finished runs are listed under ⚙️ → **Terminal Agent → Run history** (secret-redacted);
   use **Clear run history** to remove them. Stop an in-progress run with **Stop current run**
   or `Agent NEO: Stop Terminal Agent Run`.

Neo's safety model always applies: changed files are surfaced for manual review in Source
Control and **nothing is committed or pushed automatically**.

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

