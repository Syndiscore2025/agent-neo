# Augment Code Migration Guide

**Purpose:** Where to go when Augment sunsets. Ranked options that replicate the Augment flow —
a real **context engine** you can talk to, **agentic** multi-file edits, **testing**, and **git**
(commit / branch / PR / push).

**Date:** 2026-07-01 · **Verify pricing/terms before switching — this space moves weekly.**

---

## What you're actually replacing (the Augment "flow")

1. **Context engine** — high-recall retrieval over your whole codebase (local + GitHub, multi-repo).
2. **Conversational** — ask questions, get answers grounded in your code.
3. **Agentic execution** — plans and makes multi-file edits with your approval.
4. **Testing** — runs tests, reads failures, repairs.
5. **Git-native** — stages, commits, branches, opens PRs, pushes.

A tool is a good replacement only if it does **all five**. Below they're graded on that basis.

---

## Part 1 — VS Code EXTENSIONS (stay in VS Code, closest form factor)

Ranked by how close they are to Augment overall.

### 1. Sourcegraph Cody — closest on the *context engine* axis
- **Context:** Best-in-class. Built for indexing whole GitHub orgs + multi-repo, plus local. This is
  the most "Augment-shaped" product still shipping as an extension.
- **Conversational:** Yes — strong codebase Q&A.
- **Agent / edits:** Yes — agentic edits and fixes.
- **Testing:** Via agent + terminal commands.
- **Git:** Works through the agent + VS Code SCM; PR workflows on enterprise.
- **Pick if:** multi-repo context recall is your #1 need (your `agent-neo` + `myhealth` setup).

### 2. Cline — best *open-source* agent, strongest git/terminal transparency
- **Context:** On-demand file reads + MCP context servers (add a context engine like Vexp/engram).
- **Conversational:** Yes.
- **Agent / edits:** Excellent — top-tier free agent, multi-file with per-action approval.
- **Testing:** Yes — runs commands, reads output, auto-repairs.
- **Git:** Strong — stages/commits/branches via terminal, you approve each step. BYOK (pay API only).
- **Pick if:** you want open-source, model-agnostic (point it at your own Neo backend), full control.

### 3. GitHub Copilot (agent mode) — native GitHub, easiest if you live in GitHub
- **Context:** Remote semantic index of GitHub repos + local workspace index.
- **Conversational:** Yes (`@workspace`).
- **Agent / edits:** Yes — agent mode does multi-file edits.
- **Testing:** Yes via agent.
- **Git / PR:** Best-in-class — native commits, branches, and **PR authoring/review** on GitHub.
- **Pick if:** your work is GitHub-centric and you want the smoothest PR loop.

### 4. Continue — open-source, model-agnostic, most customizable
- **Context:** Local embeddings index + `@codebase`; add MCP context servers.
- **Conversational / Agent / Testing / Git:** Yes across the board via agent + terminal.
- **Pick if:** you want to wire it to your **own Neo/Auggie backend** (BYO model + BYO context).

> **Add-on (works with ALL of the above):** a dedicated **context-engine MCP server** to get
> Augment-grade recall regardless of the front-end:
> - **Vexp**, **engram**, **HugeContext**, **Xanther**, **Contexly** — pre-index your repo into a
>   graph and feed *any* MCP agent. Install once, every agent (Cline, Continue, Copilot, Cursor,
>   Claude Code) starts "informed." This is the fastest way to recreate Augment's recall.

---

## Part 2 — STANDALONE platforms (no VS Code needed)

These replace the whole editor/terminal, not just an extension.

### 1. Claude Code — closest overall to Augment on capability (terminal-first)
- **Context:** 1M-token window ingests a mid-size repo; finds related files across the tree.
  Add an MCP context engine for true large-repo recall.
- **Conversational:** Yes — talk to it in the terminal (this matches your Auggie habit).
- **Agent / edits:** Highest SWE-bench score; multi-file, long-running tasks, Agent Teams.
- **Testing:** Strongest autonomous test-run + repair loop.
- **Git:** Deep native git — commits, branches, **PRs**, CI triage. MCP, hooks, skills, routines.
- **Pick if:** you're comfortable in a terminal and want the most powerful agent. **Top pick.**

### 2. Cursor — best all-in-one IDE experience (VS Code fork)
- **Context:** Mature `@codebase` indexing + `@` mentions for files/folders/docs/URLs.
- **Conversational / Agent (Composer) / Testing / Git:** Yes — Composer plans multi-file changes,
  runs terminal commands with approval, integrated diff review before accept.
- **Pick if:** you want the best UX + autocomplete in one editor and don't mind switching editors.

### 3. Windsurf (now part of OpenAI) — best *automatic* context ("Fast Context")
- **Context:** Cascade auto-indexes the whole codebase + **persistent memory across sessions** —
  the feature users stay for; nearest to Augment's "it just knows your repo."
- **Conversational / Agent / Testing / Git:** Yes — flow-based, asks for confirmation often (safe).
- **Pick if:** you want deep automatic codebase awareness with minimal manual `@`-tagging.

### 4. Aider — lightweight terminal agent, git-first
- **Context:** Repo map; pair with an MCP context engine for scale. BYOK.
- **Agent / Testing / Git:** Auto-commits each change with sensible messages — git-native by design.
- **Pick if:** you want a minimal, scriptable, open-source terminal agent.

---

## Quick recommendation for YOU

Given your setup (local-first, multi-repo `agent-neo` + `myhealth`, you already like talking to
**Auggie in the terminal**, and you push your own git):

- **Primary (standalone):** **Claude Code** — terminal-native like Auggie, best agent + git/PR flow.
- **Primary (stay in VS Code):** **Cline** + a **Vexp/engram** context-engine MCP — open, BYOK,
  full git control, Augment-grade recall.
- **If context recall is everything:** **Sourcegraph Cody** (extension) or **Windsurf** (standalone).
- **If GitHub PRs are everything:** **GitHub Copilot agent mode**.

**Fastest safety net:** install a context-engine MCP (Vexp or engram) *today*. It's front-end
agnostic, so whichever agent you land on, your codebase recall carries over.

---

## At-a-glance matrix

| Tool | Form | Context engine | Chat | Agent edits | Testing | Git/PR | Model |
|---|---|---|---|---|---|---|---|
| Cody | Extension | ★★★★★ | ✅ | ✅ | ✅ | ✅ | Hosted |
| Cline | Extension | ★★★☆ (+MCP) | ✅ | ★★★★★ | ✅ | ✅ | BYOK |
| Copilot | Extension | ★★★★ | ✅ | ✅ | ✅ | ★★★★★ | Hosted |
| Continue | Extension | ★★★ (+MCP) | ✅ | ✅ | ✅ | ✅ | BYO |
| Claude Code | Standalone (CLI) | ★★★★ (+MCP) | ✅ | ★★★★★ | ★★★★★ | ★★★★★ | Hosted |
| Cursor | Standalone (fork) | ★★★★ | ✅ | ✅ | ✅ | ✅ | Hosted |
| Windsurf | Standalone (fork) | ★★★★★ (auto) | ✅ | ✅ | ✅ | ✅ | Hosted |
| Aider | Standalone (CLI) | ★★★ (+MCP) | ✅ | ✅ | ✅ | ★★★★ | BYOK |
