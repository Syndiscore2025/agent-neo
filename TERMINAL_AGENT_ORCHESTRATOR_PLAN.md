# Terminal Agent Orchestrator — Implementation Plan

> **Status:** Proposal (pre-coding). No feature code written yet.
> **Goal:** Make Neo the permanent *workflow brain* while terminal-based AI
> coding agents act as swappable *execution engines*. Augment CLI ships as the
> first provider; the system stays provider-agnostic.

---

## 1. Inspection findings (what we build on, not duplicate)

| Concern | Existing asset | Reuse |
|---|---|---|
| Local CLI subprocess | `extension/src/auggieRunner.ts` — spawns `auggie --print`, streams `{type: text/error/finish}`, Windows shell-quoting, `stop()` | Generalize into `processRunner` + `AugmentCLIProvider` |
| Settings | `extension/package.json` → `contributes.configuration` (`agentNeo.*`); already has `agentBackend` enum + `auggiePath` | Add `agentNeo.terminalAgent.*` |
| Settings reader | `vscode.workspace.getConfiguration('agentNeo')` | Same pattern |
| Chat UI | `chatPanel.ts` — `WebviewViewProvider`, `post()` helper, message router, card renderers, settings overlay, `runAuggie()`, `_getGitRepo()` | Add panels + message handlers |
| Commands | `commands.ts` (+ `toggleBackend`, `stopAuggie`) | Add orchestrator commands |
| Local state / secrets | `storage.ts` — globalState + SecretStorage | Store non-secret session history |
| Run history (server) | `managed_repos.py` `record_run`/`list_runs`, `RunRecorder` | Pattern reference only |
| Git/context (server) | `git_history.py`, `service_graph.py`, `repo_context.py` | Pattern reference only |
| Tests | `pytest` (backend, `tests/`); extension has no JS test harness yet | Add lightweight TS tests (see §7) |

---

## 2. Architecture decision (needs confirmation)

The CLI agents (Augment, Claude Code, etc.) run **on the user's machine**, and so
does the VS Code extension — but the **Python backend is remote**
(DigitalOcean). A remote server **cannot** observe a local terminal, tail a local
log file, or watch the local git working tree in real time.

**Decision: build the Terminal Agent Orchestrator as an extension-primary
(TypeScript) subsystem**, mirroring the existing client-side `auggieRunner.ts`
pattern.

- Observer Mode, the repo watcher, and direct stdout/stderr capture only work
  client-side — this is the only functional placement.
- Prompt building is template-variable substitution → works offline, no LLM
  required for any acceptance criterion.
- The Python backend stays **optional**: it can later expose an LLM
  "prompt-structuring" endpoint via the existing model router, but it is **not**
  a dependency of this module.

> If you prefer logic in the remote Python backend instead, Observer + Watcher
> become severely limited. Recommend extension-primary.

---

## 3. Proposed module/file plan

New folder: `extension/src/terminalAgent/`. Provider-agnostic core; Augment is
the first adapter and **no Augment-specific logic leaks outside the adapter**.

```
extension/src/terminalAgent/
  providers/
    types.ts          # TerminalAgentProvider interface
    registry.ts       # register/lookup providers (future: Claude Code, Codex, Gemini, Roo)
    augmentCli.ts     # AugmentCLIProvider (reuses auggieRunner spawn logic)
  promptBuilder.ts    # template + {{var}} substitution; missing vars omitted cleanly
  processRunner.ts    # spawn / stream / timeout / cancel (generalized auggieRunner)
  terminalObserver.ts # rolling buffer; Neo-launched / log-file tail / manual paste
  repoWatcher.ts      # branch/status/staged/unstaged/untracked/commits/diff
  outputParser.ts     # milestones/errors/tests/commits (delegates provider bits)
  suggestionEngine.ts # 8 actionable suggestions + suggested prompts
  safetyDetector.ts   # dangerous-command flags + secret redaction
  session.ts          # TerminalAgentSession model
  history.ts          # non-secret session history (globalState)
  orchestratorPanel.ts# webview surfaces, wired into chatPanel
```

Touched existing files: `package.json` (settings + commands), `chatPanel.ts`
(message handlers + panel mount), `commands.ts` (new commands), `extension.ts`
(registration), `storage.ts` (history keys). `README.md` updated at the end.

### Provider interface (shape)

```ts
interface TerminalAgentProvider {
  id: string; displayName: string; executableName: string;
  buildCommand(config, prompt, context): { cmd: string; args: string[]; useShell: boolean };
  parseOutput(raw: string): ParsedOutput;
  detectMilestones(output: string): Milestone[];
  detectErrors(output: string): DetectedError[];
  detectCompletion(output: string): boolean;
  supportsStreaming: boolean;
  supportsInteractiveInput: boolean;
  supportsTerminalObservation: boolean;
}
```

---

## 4. Settings to add (`agentNeo.terminalAgent.*`)

1. `enabled` (bool, default **false**) — master toggle; off ⇒ behavior unchanged
2. `defaultProvider` (enum, seeded `augment-cli`; registry-extensible)
3. `cliPath` (string, e.g. `augment`)
4. `defaultWorkingDir` (string / folder)
5. `promptTemplate` (multiline string; ships with the default template)
6. `maxTimeoutSeconds` (number; `0` disables)
7. `captureOutput` (bool, default **true**)
8. `autoSaveSummaries` (bool, default **true**)
9. `observer.enabled` (bool, default **false**; only active when module enabled)
10. `observer.mode` (enum: neo-process / vscode-terminal / log-file / manual)
11. `observer.logFilePath` (string, optional)
12. `confirmBeforeSendingInput` (bool, default **true**)

---

## 5. Default prompt template + variables

Template (verbatim from spec) with variables: `{{repo_path}}`,
`{{current_branch}}`, `{{user_request}}`, `{{project_memory}}`,
`{{open_files}}`, `{{git_status}}`, `{{changed_files}}`, `{{recent_commits}}`,
`{{provider_name}}`, `{{date_time}}`. Unavailable variables are **omitted
cleanly** (no `null`/`undefined`).

---

## 6. Phased delivery (each phase tested; no commit/push/merge/deploy without approval)

1. **Foundation** — settings + provider interface + registry + `AugmentCLIProvider` + prompt builder (+ tests)
2. **Execution** — process runner (timeout/cancel) + session model + history (+ tests)
3. **Prompt Orchestrator UI** — "Send to Terminal Agent" → review/edit → run → stream (+ tests)
4. **Observer + repo watcher** — buffer, log-tail, manual paste, git diffing (+ tests)
5. **Intelligence + safety** — output parser, suggestion engine, safety/redaction (+ tests)
6. **Polish** — history UI, observer controls, README, full test run + report

---

## 7. Safety & secrets

- **Redaction** before any display/persist: API keys, bearer/OAuth tokens,
  passwords, connection strings, private keys, `.env` contents, GitHub/OpenAI/
  Anthropic/Azure keys, database URLs.
- Secrets are **never** written to history, session objects, or logs.
- **Confirmation gates**: sending input to a terminal requires explicit Send +
  confirm; destructive commands (`rm -rf`, `git reset --hard`, `git clean`,
  `git push --force`, merge/rebase, deploy, prod DB, file deletion, `.env`
  edits) require a **second** confirmation.
- The module never auto-runs, auto-commits, auto-pushes, or auto-types.

---

## 8. Testing approach

- **Provider/prompt/parser/suggestion/safety** logic is pure → unit-tested in
  isolation (no real CLI). Mocked process for the runner (streamed stdout/stderr,
  timeout, cancel).
- The extension currently has **no JS test harness**; Phase 1 adds a minimal one
  (e.g. `mocha`/`vitest` via `npm`, dev-only) — flagged for your approval before
  install, since adding deps is gated.
- Coverage maps 1:1 to the spec's nine test areas.

---

## 9. Open questions (need answers before Phase 1)

1. **Confirm extension-primary (TypeScript) architecture** (§2)?
2. **Test harness**: OK to add a dev-only JS test runner (`vitest`) via `npm`?
   (Adding deps is normally gated.)
3. **Start point**: begin **Phase 1** now, or plan-only first?
4. **VS Code integrated-terminal observation**: the API cannot reliably read
   arbitrary terminal scrollback. Acceptable to implement this mode as
   *best-effort* and rely on **log-file** + **manual paste** as the robust paths?

> On your go-ahead (Q1–Q3, and Q4 acknowledgement), I start Phase 1 with tests.
> Nothing will be committed, pushed, merged, or deployed.
