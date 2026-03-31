export interface ProjectConfig {
  id: string;
  name: string;
  githubOwner: string;
  githubRepo: string;
  branch: string;
  agentNeoUrl: string;
  agentNeoToken: string;
  deploymentHealthUrl: string;
  serviceBindings: Record<string, string>;
  deploymentTargets: Record<string, string>;
}

export type IntegrationAuthType = 'bearer' | 'x-api-key' | 'custom_header' | 'none';

export interface IntegrationCatalogEntry {
  provider: string;
  label: string;
  description: string;
  default_base_url?: string | null;
  default_auth_type: IntegrationAuthType;
  default_auth_header: string;
  default_auth_scheme?: string | null;
}

export interface IntegrationSummary {
  id: string;
  provider: string;
  label: string;
  base_url?: string | null;
  auth_type: IntegrationAuthType;
  auth_header: string;
  auth_scheme?: string | null;
  headers: Record<string, string>;
  metadata: Record<string, unknown>;
  description?: string | null;
  secret_configured: boolean;
  created_at: string;
  updated_at: string;
}

export interface IntegrationsListResponse {
  integrations: IntegrationSummary[];
}

export interface IntegrationUpsertPayload {
  provider: string;
  label: string;
  base_url?: string | null;
  auth_type: IntegrationAuthType;
  auth_header: string;
  auth_scheme?: string | null;
  secret?: string;
  clear_secret?: boolean;
  headers: Record<string, string>;
  metadata: Record<string, unknown>;
  description?: string | null;
}

export interface TreeNode {
  name: string;
  path: string;
  type: 'file' | 'dir';
  sha?: string;
  children?: TreeNode[];
}

export interface OpenFile {
  path: string;
  sha?: string;
  language: string;
  content: string;
  originalContent: string;
  dirty: boolean;
}

export interface DiffProposal {
  diff: string;
  files_changed: string[];
  additions: number;
  deletions: number;
  summary: string;
}

export interface ExecutionResultCard {
  status: string;
  mode: string;
  commit_sha?: string | null;
  files_changed: string[];
  lines_changed: number;
  pushed: boolean;
  verify_steps: string[];
  rollback_command?: string | null;
  pre_test_passed?: boolean | null;
  post_test_passed?: boolean | null;
  validation_passed?: boolean | null;
  error?: string | null;
}

export interface ChatResponse {
  session_id: string;
  message: string;
  action_type: string;
  proposed_diff?: DiffProposal | null;
  timestamp: string;
}

export interface ApprovalResponse {
  session_id: string;
  approved: boolean;
  message: string;
  execution_result?: ExecutionResultCard | null;
}

export interface RollbackResponse {
  session_id: string;
  success: boolean;
  message: string;
  commit_reverted?: string | null;
}

export interface ChatContextPayload {
  current_file?: string;
  current_file_content?: string;
  language?: string;
  diagnostics?: string[];
}

export interface ChatMessageItem {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  diffProposal?: DiffProposal | null;
  executionResult?: ExecutionResultCard | null;
}

export interface PhaseState {
  id: string;
  name: string;
  specialist?: string;
  status: 'pending' | 'running' | 'complete' | 'failed';
  summary?: string;
  checkpoint?: string;
  verifyOutput?: string;
  error?: string;
}

export interface ServiceStatus {
  state: 'idle' | 'loading' | 'ok' | 'error';
  message: string;
  details?: string;
}

export interface ActivityItem {
  id: string;
  tool: string;
  path?: string;
  command?: string;
  query?: string;
  linesRead?: number;
  linesAdded?: number;
  linesRemoved?: number;
  totalLines?: number;
  durationMs?: number;
  status: 'running' | 'done';
  timestamp: string;
}
