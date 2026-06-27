/**
 * AGENT NEO - Terminal Agent Orchestrator: Safety detector
 *
 * Two responsibilities, both pure (no `vscode`):
 *  1. Flag dangerous shell commands seen in agent output (rm -rf, force push,
 *     piped installers, destructive SQL, ...).
 *  2. Redact secrets (API keys, tokens, passwords, private keys) from any text
 *     before it is displayed or persisted. Secret VALUES are never emitted.
 */

import { SafetyFlag } from './session';

interface DangerRule {
    rule: string;
    re: RegExp;
    severity: 'warn' | 'danger';
    detail: string;
}

const DANGER_RULES: DangerRule[] = [
    { rule: 'rm-rf', re: /\brm\s+-[a-z]*r[a-z]*f|\brm\s+-[a-z]*f[a-z]*r\b/i, severity: 'danger', detail: 'Recursive force delete (rm -rf).' },
    { rule: 'sudo-rm', re: /\bsudo\s+rm\b/i, severity: 'danger', detail: 'Privileged file deletion (sudo rm).' },
    { rule: 'git-force-push', re: /\bgit\s+push\b[^\n]*--force(?!-with-lease)|\bgit\s+push\b[^\n]*\s-f\b/i, severity: 'danger', detail: 'Force push can overwrite remote history.' },
    { rule: 'git-push', re: /\bgit\s+push\b/i, severity: 'warn', detail: 'Pushes to a remote — confirm before allowing.' },
    { rule: 'git-reset-hard', re: /\bgit\s+reset\s+--hard\b/i, severity: 'warn', detail: 'Discards uncommitted work (git reset --hard).' },
    { rule: 'git-clean', re: /\bgit\s+clean\s+-[a-z]*f/i, severity: 'warn', detail: 'Deletes untracked files (git clean -f).' },
    { rule: 'pipe-to-shell', re: /\b(?:curl|wget)\b[^\n]*\|\s*(?:sudo\s+)?(?:bash|sh|zsh)\b/i, severity: 'danger', detail: 'Piping a download straight into a shell.' },
    { rule: 'disk-write', re: /\bdd\s+if=|\bmkfs\b|>\s*\/dev\/sd[a-z]/i, severity: 'danger', detail: 'Raw disk / filesystem write.' },
    { rule: 'chmod-777', re: /\bchmod\s+(?:-[a-zA-Z]+\s+)?777\b/i, severity: 'warn', detail: 'World-writable permissions (chmod 777).' },
    { rule: 'fork-bomb', re: /:\(\)\s*\{\s*:\s*\|\s*:/i, severity: 'danger', detail: 'Fork bomb pattern.' },
    { rule: 'sql-drop', re: /\bDROP\s+(?:TABLE|DATABASE|SCHEMA)\b|\bTRUNCATE\s+TABLE\b/i, severity: 'danger', detail: 'Destructive SQL (DROP/TRUNCATE).' },
    { rule: 'sql-delete-all', re: /\bDELETE\s+FROM\s+[^\n;]+(?:;|$)(?![^\n]*\bWHERE\b)/i, severity: 'warn', detail: 'DELETE without a WHERE clause.' },
];

/** Scan text for dangerous commands; one flag per matched rule. */
export function detectDangerousCommands(text: string): SafetyFlag[] {
    if (!text) { return []; }
    const flags: SafetyFlag[] = [];
    for (const r of DANGER_RULES) {
        if (r.re.test(text)) {
            flags.push({ rule: r.rule, detail: r.detail, severity: r.severity });
        }
    }
    return flags;
}

const REDACTED = '[REDACTED]';

type Redactor = (s: string) => string;

const REDACTORS: Redactor[] = [
    s => s.replace(/-----BEGIN[^-]*PRIVATE KEY-----[\s\S]*?-----END[^-]*PRIVATE KEY-----/g, '[REDACTED PRIVATE KEY]'),
    s => s.replace(/\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}/g, REDACTED), // JWT
    s => s.replace(/\bsk-[A-Za-z0-9_-]{12,}/g, REDACTED),                 // OpenAI-style
    s => s.replace(/\bAKIA[0-9A-Z]{16}\b/g, REDACTED),                    // AWS access key id
    s => s.replace(/\bgh[pousr]_[A-Za-z0-9]{20,}\b/g, REDACTED),          // GitHub token
    s => s.replace(/\bgithub_pat_[A-Za-z0-9_]{20,}\b/g, REDACTED),        // GitHub fine-grained PAT
    s => s.replace(/\bxox[baprs]-[A-Za-z0-9-]{10,}\b/g, REDACTED),        // Slack token
    s => s.replace(/\bAIza[0-9A-Za-z_-]{20,}\b/g, REDACTED),             // Google API key
    s => s.replace(/\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{10,}/gi, (_m, p1) => `${p1} ${REDACTED}`),
    // KEY=value / TOKEN: "value" / PASSWORD=... — keep the name, redact the value.
    s => s.replace(
        /([A-Za-z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|PWD)[A-Za-z0-9_]*)(\s*[:=]\s*)(["']?)([^\s"']+)(["']?)/gi,
        (_m, name, sep, q1) => `${name}${sep}${q1}${REDACTED}${q1}`,
    ),
];

/** Replace any detected secret VALUE with a redaction marker. Idempotent. */
export function redactSecrets(text: string): string {
    if (!text) { return text; }
    let out = text;
    for (const r of REDACTORS) { out = r(out); }
    return out;
}

/** Redact each safety flag's detail (defensive — details are static, but cheap). */
export function redactSafetyFlags(flags: SafetyFlag[]): SafetyFlag[] {
    return flags.map(f => ({ ...f, detail: redactSecrets(f.detail) }));
}
