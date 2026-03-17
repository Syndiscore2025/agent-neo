# Agent NEO - VS Code Extension

Interactive coding partner powered by Agent NEO.

## Features (In Development)

This extension is being built in slices. Current status:

- **SLICE 1 (Current)**: Scaffolding complete
- **SLICE 2**: Chat MVP (TODO)
- **SLICE 3**: Context-aware repo understanding (TODO)
- **SLICE 4**: Action planner + diff proposal (TODO)
- **SLICE 5**: Agent NEO execution integration (TODO)
- **SLICE 6**: Image + PDF attachments (TODO)
- **SLICE 7**: Inline autocomplete (TODO)
- **SLICE 8**: Predictive prompt suggestions (TODO)
- **SLICE 9**: Hardening + UX polish (TODO)

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

