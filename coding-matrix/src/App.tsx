import { useCallback, useEffect, useMemo, useState } from 'react';
import Editor from '@monaco-editor/react';
import {
  approveDiff,
  buildChatContext,
  fetchHealth,
  rollbackLastChange,
  sendChatMessage,
  streamPhasedRun,
} from './lib/agentNeo';
import { fetchFile, fetchRepoTree, saveFile } from './lib/github';
import {
  createIntegration,
  deleteIntegration,
  listIntegrationCatalog,
  listIntegrations,
  updateIntegration,
} from './lib/integrations';
import { fetchDigitalOceanStatus, fetchRenderStatus, fetchVercelStatus } from './lib/services';
import type {
  ChatMessageItem,
  IntegrationAuthType,
  IntegrationCatalogEntry,
  IntegrationSummary,
  OpenFile,
  PhaseState,
  ProjectConfig,
  ServiceStatus,
  TreeNode,
} from './types';

const PROJECTS_KEY = 'coding-matrix.projects.v1';
const ACTIVE_PROJECT_KEY = 'coding-matrix.active-project.v1';

const PROVIDER_ORDER = [
  'github',
  'digitalocean',
  'render',
  'supabase',
  'vercel',
  'openai',
  'anthropic',
  'stripe',
  'linear',
  'notion',
  'slack',
  'custom_api',
] as const;

const PROVIDER_LABELS: Record<string, string> = {
  github: 'GitHub',
  digitalocean: 'DigitalOcean',
  render: 'Render',
  supabase: 'Supabase',
  vercel: 'Vercel',
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  stripe: 'Stripe',
  linear: 'Linear',
  notion: 'Notion',
  slack: 'Slack',
  custom_api: 'Custom API',
};

type SidebarView = 'explorer' | 'services';

interface ServiceFormState {
  provider: string;
  label: string;
  baseUrl: string;
  authType: IntegrationAuthType;
  authHeader: string;
  authScheme: string;
  secret: string;
  clearSecret: boolean;
  headersJson: string;
  description: string;
}

const DEPLOYMENT_TARGET_FIELDS = [
  {
    provider: 'digitalocean',
    label: 'DigitalOcean App ID',
    placeholder: 'e.g. 12345678-aaaa-bbbb-cccc-1234567890ab',
  },
  {
    provider: 'render',
    label: 'Render Service ID',
    placeholder: 'e.g. srv-xxxxxxxxxxxx',
  },
  {
    provider: 'vercel',
    label: 'Vercel Project ID / Name',
    placeholder: 'e.g. coding-matrix or prj_xxxxx',
  },
] as const;

function createProject(overrides: Partial<ProjectConfig> = {}): ProjectConfig {
  return {
    id: crypto.randomUUID(),
    name: 'Agent NEO MVP',
    githubOwner: 'Syndiscore2025',
    githubRepo: 'agent-neo',
    branch: 'main',
    agentNeoUrl: '/api/backend',
    agentNeoToken: '',
    deploymentHealthUrl: '',
    serviceBindings: {},
    deploymentTargets: {},
    ...overrides,
  };
}

function normalizeProjectConfig(input: Partial<ProjectConfig> & { githubToken?: string }): ProjectConfig {
  const rawBindings = input.serviceBindings;
  const serviceBindings =
    rawBindings && typeof rawBindings === 'object'
      ? Object.fromEntries(
          Object.entries(rawBindings).filter(
            ([provider, integrationId]) => Boolean(provider) && typeof integrationId === 'string' && integrationId.trim(),
          ),
        )
      : {};

  const rawDeploymentTargets = input.deploymentTargets;
  const deploymentTargets =
    rawDeploymentTargets && typeof rawDeploymentTargets === 'object'
      ? Object.fromEntries(
          Object.entries(rawDeploymentTargets).filter(
            ([provider, target]) => Boolean(provider) && typeof target === 'string' && target.trim(),
          ),
        )
      : {};

  return createProject({
    id: typeof input.id === 'string' && input.id.trim() ? input.id : crypto.randomUUID(),
    name: typeof input.name === 'string' && input.name.trim() ? input.name : 'Agent NEO MVP',
    githubOwner: typeof input.githubOwner === 'string' ? input.githubOwner : 'Syndiscore2025',
    githubRepo: typeof input.githubRepo === 'string' ? input.githubRepo : 'agent-neo',
    branch: typeof input.branch === 'string' ? input.branch : 'main',
    agentNeoUrl: typeof input.agentNeoUrl === 'string' && input.agentNeoUrl.trim() ? input.agentNeoUrl : '/api/backend',
    agentNeoToken: typeof input.agentNeoToken === 'string' ? input.agentNeoToken : '',
    deploymentHealthUrl: typeof input.deploymentHealthUrl === 'string' ? input.deploymentHealthUrl : '',
    serviceBindings,
    deploymentTargets,
  });
}

function loadProjects(): ProjectConfig[] {
  const raw = localStorage.getItem(PROJECTS_KEY);
  if (!raw) {
    return [createProject()];
  }

  try {
    const parsed = JSON.parse(raw) as Array<Partial<ProjectConfig> & { githubToken?: string }>;
    const normalized = Array.isArray(parsed) ? parsed.map(normalizeProjectConfig) : [];
    return normalized.length > 0 ? normalized : [createProject()];
  } catch {
    return [createProject()];
  }
}

function providerLabel(provider: string, catalog: IntegrationCatalogEntry[] = []): string {
  return catalog.find((entry) => entry.provider === provider)?.label ?? PROVIDER_LABELS[provider] ?? provider;
}

function createServiceForm(catalog: IntegrationCatalogEntry[], provider = 'github'): ServiceFormState {
  const preset = catalog.find((entry) => entry.provider === provider) ?? catalog[0];
  const nextProvider = preset?.provider ?? provider;
  return {
    provider: nextProvider,
    label: providerLabel(nextProvider, catalog),
    baseUrl: preset?.default_base_url ?? '',
    authType: preset?.default_auth_type ?? 'bearer',
    authHeader: preset?.default_auth_header ?? 'Authorization',
    authScheme: preset?.default_auth_scheme ?? 'Bearer',
    secret: '',
    clearSecret: false,
    headersJson: '{}',
    description: preset?.description ?? '',
  };
}

function integrationToServiceForm(integration: IntegrationSummary): ServiceFormState {
  return {
    provider: integration.provider,
    label: integration.label,
    baseUrl: integration.base_url ?? '',
    authType: integration.auth_type,
    authHeader: integration.auth_header,
    authScheme: integration.auth_scheme ?? '',
    secret: '',
    clearSecret: false,
    headersJson: JSON.stringify(integration.headers ?? {}, null, 2),
    description: integration.description ?? '',
  };
}

function sortProviders(providers: Iterable<string>): string[] {
  return [...providers].sort((left, right) => {
    const leftIndex = PROVIDER_ORDER.indexOf(left as (typeof PROVIDER_ORDER)[number]);
    const rightIndex = PROVIDER_ORDER.indexOf(right as (typeof PROVIDER_ORDER)[number]);
    const normalizedLeft = leftIndex === -1 ? Number.MAX_SAFE_INTEGER : leftIndex;
    const normalizedRight = rightIndex === -1 ? Number.MAX_SAFE_INTEGER : rightIndex;
    return normalizedLeft - normalizedRight || left.localeCompare(right);
  });
}

function timestamp(): string {
  return new Date().toLocaleTimeString();
}

function introMessage(projectName: string): ChatMessageItem {
  return {
    id: crypto.randomUUID(),
    role: 'assistant',
    content:
      `Coding Matrix is ready for ${projectName}. Bind your GitHub integration in Services, open a file, ` +
      'then chat with Agent NEO or run `/run <task>` for a phased autonomous workflow.',
    timestamp: new Date().toISOString(),
  };
}

function TreeView({
  nodes,
  activePath,
  expanded,
  onToggle,
  onOpen,
}: {
  nodes: TreeNode[];
  activePath?: string;
  expanded: Record<string, boolean>;
  onToggle: (path: string) => void;
  onOpen: (path: string) => void;
}) {
  return (
    <ul className="tree-list">
      {nodes.map((node) => {
        if (node.type === 'dir') {
          const isOpen = expanded[node.path] ?? false;
          return (
            <li key={node.path}>
              <button className="tree-node tree-dir" onClick={() => onToggle(node.path)}>
                <span>{isOpen ? '▾' : '▸'}</span>
                <span>{node.name}</span>
              </button>
              {isOpen && node.children && (
                <TreeView
                  nodes={node.children}
                  activePath={activePath}
                  expanded={expanded}
                  onToggle={onToggle}
                  onOpen={onOpen}
                />
              )}
            </li>
          );
        }

        return (
          <li key={node.path}>
            <button
              className={`tree-node tree-file ${activePath === node.path ? 'active' : ''}`}
              onClick={() => onOpen(node.path)}
            >
              <span>•</span>
              <span>{node.name}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function App() {
  const [projects, setProjects] = useState<ProjectConfig[]>(loadProjects);
  const [activeProjectId, setActiveProjectId] = useState<string>(() => {
    return localStorage.getItem(ACTIVE_PROJECT_KEY) ?? loadProjects()[0].id;
  });
  const [sidebarView, setSidebarView] = useState<SidebarView>('explorer');
  const [tree, setTree] = useState<TreeNode[]>([]);
  const [treeLoading, setTreeLoading] = useState(false);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [openFiles, setOpenFiles] = useState<OpenFile[]>([]);
  const [activeFilePath, setActiveFilePath] = useState<string>();
  const [chatInput, setChatInput] = useState('');
  const [messages, setMessages] = useState<ChatMessageItem[]>([]);
  const [sessionId, setSessionId] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  const [phases, setPhases] = useState<PhaseState[]>([]);
  const [bottomTab, setBottomTab] = useState<'terminal' | 'deploy'>('terminal');
  const [agentStatus, setAgentStatus] = useState<ServiceStatus>({ state: 'idle', message: 'Not checked yet' });
  const [deployStatus, setDeployStatus] = useState<ServiceStatus>({ state: 'idle', message: 'No deployment URL configured' });
  const [providerStatuses, setProviderStatuses] = useState<Record<string, ServiceStatus>>({});
  const [integrationCatalog, setIntegrationCatalog] = useState<IntegrationCatalogEntry[]>([]);
  const [integrations, setIntegrations] = useState<IntegrationSummary[]>([]);
  const [servicesLoading, setServicesLoading] = useState(false);
  const [serviceBusy, setServiceBusy] = useState(false);
  const [servicesError, setServicesError] = useState<string>();
  const [selectedIntegrationId, setSelectedIntegrationId] = useState<string>('new');
  const [serviceForm, setServiceForm] = useState<ServiceFormState>(() => createServiceForm([]));

  const activeProject = useMemo(
    () => projects.find((project) => project.id === activeProjectId) ?? projects[0],
    [projects, activeProjectId],
  );

  const activeFile = useMemo(
    () => openFiles.find((file) => file.path === activeFilePath),
    [openFiles, activeFilePath],
  );

  const canManageBackend = Boolean(activeProject.agentNeoUrl.trim() && activeProject.agentNeoToken.trim());

  const bindingProviders = useMemo(() => {
    const providers = new Set<string>(PROVIDER_ORDER.filter((provider) => provider !== 'custom_api'));
    integrationCatalog.forEach((entry) => {
      if (entry.provider !== 'custom_api') {
        providers.add(entry.provider);
      }
    });
    Object.keys(activeProject.serviceBindings).forEach((provider) => providers.add(provider));
    return sortProviders(providers);
  }, [integrationCatalog, activeProject.serviceBindings]);

  const integrationOptionsByProvider = useMemo(() => {
    const grouped = new Map<string, IntegrationSummary[]>();
    integrations.forEach((integration) => {
      const current = grouped.get(integration.provider) ?? [];
      current.push(integration);
      grouped.set(integration.provider, current);
    });
    return grouped;
  }, [integrations]);

  const availableServiceProviders = useMemo(
    () => sortProviders(new Set([...PROVIDER_ORDER, ...integrationCatalog.map((entry) => entry.provider)])),
    [integrationCatalog],
  );

  const boundServiceCount = useMemo(
    () => Object.values(activeProject.serviceBindings).filter((value) => Boolean(value?.trim())).length,
    [activeProject.serviceBindings],
  );

  const deployProviderCards = useMemo(
    () => [
      {
        provider: 'digitalocean',
        title: 'DigitalOcean',
        target: activeProject.deploymentTargets.digitalocean?.trim() ?? '',
      },
      {
        provider: 'render',
        title: 'Render',
        target: activeProject.deploymentTargets.render?.trim() ?? '',
      },
      {
        provider: 'vercel',
        title: 'Vercel',
        target: activeProject.deploymentTargets.vercel?.trim() ?? '',
      },
    ],
    [activeProject.deploymentTargets],
  );

  const appendLog = useCallback((message: string) => {
    setLogs((current) => [...current.slice(-199), `[${timestamp()}] ${message}`]);
  }, []);

  useEffect(() => {
    localStorage.setItem(PROJECTS_KEY, JSON.stringify(projects));
    localStorage.setItem(ACTIVE_PROJECT_KEY, activeProjectId);
  }, [projects, activeProjectId]);

  useEffect(() => {
    setTree([]);
    setExpanded({});
    setOpenFiles([]);
    setActiveFilePath(undefined);
    setMessages([introMessage(activeProject.name)]);
    setSessionId(undefined);
    setLogs([`[${timestamp()}] Switched to ${activeProject.name}`]);
    setPhases([]);
    setProviderStatuses({});
  }, [activeProject.id, activeProject.name]);

  const loadServices = useCallback(
    async (preferredIntegrationId?: string) => {
      if (!canManageBackend) {
        setIntegrationCatalog([]);
        setIntegrations([]);
        setSelectedIntegrationId('new');
        setServiceForm(createServiceForm([]));
        setServicesError('Add Agent NEO URL and token to unlock backend-backed services.');
        return;
      }

      try {
        setServicesLoading(true);
        setServicesError(undefined);
        const [catalog, storedIntegrations] = await Promise.all([
          listIntegrationCatalog(activeProject),
          listIntegrations(activeProject),
        ]);
        setIntegrationCatalog(catalog);
        setIntegrations(storedIntegrations);

        const nextId = preferredIntegrationId ?? selectedIntegrationId;
        if (nextId !== 'new') {
          const selected = storedIntegrations.find((integration) => integration.id === nextId);
          if (selected) {
            setSelectedIntegrationId(selected.id);
            setServiceForm(integrationToServiceForm(selected));
            return;
          }
        }

        setSelectedIntegrationId('new');
        setServiceForm(createServiceForm(catalog));
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Failed to load services.';
        setServicesError(message);
        appendLog(message);
      } finally {
        setServicesLoading(false);
      }
    },
    [activeProject, appendLog, canManageBackend, selectedIntegrationId],
  );

  useEffect(() => {
    void loadServices();
  }, [loadServices]);

  const updateActiveProject = useCallback(
    (patch: Partial<ProjectConfig>) => {
      setProjects((current) =>
        current.map((project) => (project.id === activeProject.id ? { ...project, ...patch } : project)),
      );
    },
    [activeProject.id],
  );

  const updateDeploymentTarget = (provider: string, target: string) => {
    updateActiveProject({
      deploymentTargets: {
        ...activeProject.deploymentTargets,
        [provider]: target,
      },
    });
  };

  const handleAddProject = () => {
    const project = createProject({ name: `MVP ${projects.length + 1}` });
    setProjects((current) => [...current, project]);
    setActiveProjectId(project.id);
  };

  const handleRemoveProject = () => {
    if (projects.length === 1 || !window.confirm(`Remove ${activeProject.name}?`)) {
      return;
    }

    const remaining = projects.filter((project) => project.id !== activeProject.id);
    setProjects(remaining);
    setActiveProjectId(remaining[0].id);
  };

  const handleLoadTree = async () => {
    if (!activeProject.githubOwner.trim() || !activeProject.githubRepo.trim()) {
      appendLog('GitHub owner and repo are required before loading the file tree.');
      return;
    }

    if (!activeProject.serviceBindings.github?.trim()) {
      setSidebarView('services');
      appendLog('Bind a GitHub integration in Services before loading the file tree.');
      return;
    }

    try {
      setTreeLoading(true);
      appendLog(`Loading ${activeProject.githubOwner}/${activeProject.githubRepo}…`);
      const response = await fetchRepoTree(activeProject);
      setTree(response.tree);
      setExpanded({ 'src': true, 'app': true });
      if (response.branch !== activeProject.branch) {
        updateActiveProject({ branch: response.branch });
      }
      appendLog(`Loaded ${response.tree.length} top-level nodes from GitHub.`);
    } catch (error) {
      appendLog(error instanceof Error ? error.message : 'Failed to load repository tree.');
    } finally {
      setTreeLoading(false);
    }
  };

  const handleOpenFile = async (path: string) => {
    const existing = openFiles.find((file) => file.path === path);
    if (existing) {
      setActiveFilePath(path);
      return;
    }

    try {
      appendLog(`Opening ${path}…`);
      const file = await fetchFile(activeProject, path);
      setOpenFiles((current) => [...current, file]);
      setActiveFilePath(path);
      appendLog(`Opened ${path}.`);
    } catch (error) {
      appendLog(error instanceof Error ? error.message : `Failed to open ${path}.`);
    }
  };

  const handleEditorChange = (value?: string) => {
    if (!activeFilePath) {
      return;
    }

    const next = value ?? '';
    setOpenFiles((current) =>
      current.map((file) =>
        file.path === activeFilePath
          ? { ...file, content: next, dirty: next !== file.originalContent }
          : file,
      ),
    );
  };

  const handleSaveActiveFile = async () => {
    if (!activeFile) {
      return;
    }

    try {
      appendLog(`Saving ${activeFile.path} back to GitHub…`);
      const { sha } = await saveFile(activeProject, activeFile);
      setOpenFiles((current) =>
        current.map((file) =>
          file.path === activeFile.path
            ? { ...file, sha, originalContent: file.content, dirty: false }
            : file,
        ),
      );
      appendLog(`Saved ${activeFile.path}.`);
    } catch (error) {
      appendLog(error instanceof Error ? error.message : 'Save failed.');
    }
  };

  const pushMessage = useCallback((message: Omit<ChatMessageItem, 'id' | 'timestamp'>) => {
    setMessages((current) => [
      ...current,
      { id: crypto.randomUUID(), timestamp: new Date().toISOString(), ...message },
    ]);
  }, []);

  const refreshStatus = useCallback(async () => {
    if (canManageBackend) {
      setAgentStatus({ state: 'loading', message: 'Checking Agent NEO…' });
      try {
        const health = await fetchHealth(activeProject);
        setAgentStatus({ state: 'ok', message: 'Agent NEO reachable', details: JSON.stringify(health, null, 2) });
      } catch (error) {
        setAgentStatus({
          state: 'error',
          message: error instanceof Error ? error.message : 'Agent NEO health check failed.',
        });
      }
    } else {
      setAgentStatus({ state: 'idle', message: 'Configure Agent NEO URL + token' });
    }

    if (!activeProject.deploymentHealthUrl.trim()) {
      setDeployStatus({ state: 'idle', message: 'No deployment health URL configured' });
    } else {
      setDeployStatus({ state: 'loading', message: 'Checking deployment…' });
      try {
        const response = await fetch(activeProject.deploymentHealthUrl.trim());
        const text = await response.text();
        if (!response.ok) {
          throw new Error(`Deployment ${response.status}: ${text || response.statusText}`);
        }
        setDeployStatus({ state: 'ok', message: 'Deployment reachable', details: text });
      } catch (error) {
        setDeployStatus({
          state: 'error',
          message: error instanceof Error ? error.message : 'Deployment check failed.',
        });
      }
    }

    const checks = deployProviderCards.map(({ provider, target }) => {
      if (!canManageBackend) {
        return Promise.resolve<[string, ServiceStatus]>([
          provider,
          { state: 'idle', message: 'Configure Agent NEO URL + token' },
        ]);
      }

      if (!activeProject.serviceBindings[provider]?.trim()) {
        return Promise.resolve<[string, ServiceStatus]>([
          provider,
          { state: 'idle', message: 'Not bound in Services' },
        ]);
      }

      if (!target) {
        return Promise.resolve<[string, ServiceStatus]>([
          provider,
          { state: 'idle', message: 'Add target ID in project settings' },
        ]);
      }

      const fetcher =
        provider === 'digitalocean'
          ? fetchDigitalOceanStatus
          : provider === 'render'
            ? fetchRenderStatus
            : fetchVercelStatus;

      return fetcher(activeProject, target)
        .then((status) => [provider, status] as [string, ServiceStatus])
        .catch((error) => [
          provider,
          {
            state: 'error',
            message: error instanceof Error ? error.message : `${provider} status check failed.`,
          },
        ] as [string, ServiceStatus]);
    });

    const resolvedStatuses = await Promise.all(checks);
    setProviderStatuses(Object.fromEntries(resolvedStatuses));
  }, [activeProject, canManageBackend, deployProviderCards]);

  useEffect(() => {
    void refreshStatus();
    const intervalId = window.setInterval(() => {
      void refreshStatus();
    }, 60000);
    return () => window.clearInterval(intervalId);
  }, [refreshStatus]);

  const handleApprove = async (approved: boolean, push: boolean) => {
    if (!sessionId) {
      appendLog('No active Agent NEO session to approve.');
      return;
    }

    try {
      setBusy(true);
      const response = await approveDiff(activeProject, sessionId, approved, push);
      pushMessage({ role: 'assistant', content: response.message, executionResult: response.execution_result ?? null });
      appendLog(approved ? `Diff ${push ? 'approved and pushed' : 'approved'}.` : 'Diff rejected.');
    } catch (error) {
      pushMessage({ role: 'system', content: error instanceof Error ? error.message : 'Approval failed.' });
    } finally {
      setBusy(false);
    }
  };

  const handleRollback = async () => {
    if (!sessionId) {
      appendLog('No active session to roll back.');
      return;
    }

    try {
      setBusy(true);
      const response = await rollbackLastChange(activeProject, sessionId);
      pushMessage({ role: 'assistant', content: response.message });
      appendLog(`Rollback: ${response.message}`);
    } catch (error) {
      pushMessage({ role: 'system', content: error instanceof Error ? error.message : 'Rollback failed.' });
    } finally {
      setBusy(false);
    }
  };

  const handleRunTask = async (task: string) => {
    setBottomTab('terminal');
    setPhases([]);
    pushMessage({ role: 'user', content: `/run ${task}` });
    appendLog(`Starting phased run: ${task}`);

    try {
      setBusy(true);
      await streamPhasedRun(activeProject, task, sessionId, buildChatContext(activeProject, activeFile), (event) => {
        const type = event.type;
        if (type === 'planning') {
          appendLog(`Planner: ${String(event.task ?? task)}`);
        }
        if (type === 'phase_plan') {
          const next = ((event.phases as Array<{ id: string; name: string; specialist?: string }>) ?? []).map((phase) => ({
            id: phase.id,
            name: phase.name,
            specialist: phase.specialist,
            status: 'pending' as const,
          }));
          setPhases(next);
          appendLog(`Planner created ${next.length} phases.`);
        }
        if (type === 'phase_start') {
          setPhases((current) =>
            current.map((phase) =>
              phase.id === event.phase_id ? { ...phase, status: 'running' } : phase,
            ),
          );
          appendLog(`Phase start: ${String(event.phase_name ?? event.phase_id)}`);
        }
        if (type === 'tool_start') {
          appendLog(`Tool start: ${String(event.tool ?? 'unknown')}`);
        }
        if (type === 'tool_end') {
          appendLog(`Tool end: ${String(event.tool ?? 'unknown')}`);
        }
        if (type === 'phase_checkpoint') {
          setPhases((current) =>
            current.map((phase) =>
              phase.id === event.phase_id ? { ...phase, checkpoint: String(event.commit_sha ?? '') } : phase,
            ),
          );
          appendLog(`Checkpoint: ${String(event.commit_sha ?? '')}`);
        }
        if (type === 'phase_verify') {
          setPhases((current) =>
            current.map((phase) =>
              phase.id === event.phase_id
                ? { ...phase, verifyOutput: String(event.output ?? '') }
                : phase,
            ),
          );
          appendLog(`Verify: ${String(event.command ?? 'phase command')}`);
        }
        if (type === 'phase_end') {
          setPhases((current) =>
            current.map((phase) =>
              phase.id === event.phase_id
                ? { ...phase, status: 'complete', summary: String(event.summary ?? '') }
                : phase,
            ),
          );
          appendLog(`Phase complete: ${String(event.phase_name ?? event.phase_id)}`);
        }
        if (type === 'error') {
          const phaseId = typeof event.phase_id === 'string' ? event.phase_id : undefined;
          if (phaseId) {
            setPhases((current) =>
              current.map((phase) =>
                phase.id === phaseId
                  ? { ...phase, status: 'failed', error: String(event.error ?? 'Unknown error') }
                  : phase,
              ),
            );
          }
          appendLog(`Error: ${String(event.error ?? 'Unknown streaming error')}`);
        }
        if (type === 'phased_done') {
          pushMessage({ role: 'assistant', content: `Phased run complete for: ${task}` });
          appendLog(`Run complete. Files touched: ${String((event.files_written as string[] | undefined)?.join(', ') ?? 'n/a')}`);
        }
      });
    } catch (error) {
      pushMessage({ role: 'system', content: error instanceof Error ? error.message : 'Run failed.' });
      appendLog(error instanceof Error ? error.message : 'Run failed.');
    } finally {
      setBusy(false);
    }
  };

  const handleSend = async () => {
    const message = chatInput.trim();
    if (!message || busy) {
      return;
    }

    setChatInput('');

    if (message === '/help') {
      pushMessage({
        role: 'assistant',
        content: 'Commands: /run <task>, /rollback, /new, /help. Normal messages go to /chat.',
      });
      return;
    }

    if (message === '/new') {
      setSessionId(undefined);
      setMessages([introMessage(activeProject.name)]);
      appendLog('Started a fresh local chat thread.');
      return;
    }

    if (message === '/rollback') {
      await handleRollback();
      return;
    }

    if (message.startsWith('/run ')) {
      await handleRunTask(message.slice(5).trim());
      return;
    }

    pushMessage({ role: 'user', content: message });

    try {
      setBusy(true);
      const response = await sendChatMessage(
        activeProject,
        message,
        sessionId,
        buildChatContext(activeProject, activeFile),
      );
      setSessionId(response.session_id);
      pushMessage({
        role: 'assistant',
        content: response.message,
        diffProposal: response.proposed_diff ?? null,
      });
      appendLog(`Agent NEO replied with ${response.action_type}.`);
    } catch (error) {
      pushMessage({ role: 'system', content: error instanceof Error ? error.message : 'Chat request failed.' });
      appendLog(error instanceof Error ? error.message : 'Chat request failed.');
    } finally {
      setBusy(false);
    }
  };

  const handleSelectIntegration = (integrationId: string) => {
    setSelectedIntegrationId(integrationId);
    if (integrationId === 'new') {
      setServiceForm(createServiceForm(integrationCatalog));
      return;
    }

    const selected = integrations.find((integration) => integration.id === integrationId);
    if (selected) {
      setServiceForm(integrationToServiceForm(selected));
    }
  };

  const handleServiceProviderChange = (provider: string) => {
    setServiceForm(createServiceForm(integrationCatalog, provider));
    setSelectedIntegrationId('new');
  };

  const handleBindingChange = (provider: string, integrationId: string) => {
    const nextBindings = { ...activeProject.serviceBindings };
    if (integrationId.trim()) {
      nextBindings[provider] = integrationId;
    } else {
      delete nextBindings[provider];
    }
    updateActiveProject({ serviceBindings: nextBindings });
    appendLog(`${providerLabel(provider, integrationCatalog)} binding ${integrationId ? 'updated' : 'cleared'} for ${activeProject.name}.`);
  };

  const handleSaveIntegration = async () => {
    try {
      const parsedHeaders = serviceForm.headersJson.trim() ? JSON.parse(serviceForm.headersJson) : {};
      if (!parsedHeaders || typeof parsedHeaders !== 'object' || Array.isArray(parsedHeaders)) {
        throw new Error('Headers JSON must be an object like {"X-Header":"value"}.');
      }

      const payload = {
        provider: serviceForm.provider,
        label: serviceForm.label.trim(),
        base_url: serviceForm.baseUrl.trim() || null,
        auth_type: serviceForm.authType,
        auth_header: serviceForm.authHeader.trim(),
        auth_scheme: serviceForm.authScheme.trim() || null,
        secret: serviceForm.secret.trim() || undefined,
        clear_secret: serviceForm.clearSecret,
        headers: Object.fromEntries(
          Object.entries(parsedHeaders as Record<string, unknown>).map(([key, value]) => [key, String(value)]),
        ),
        metadata: {},
        description: serviceForm.description.trim() || null,
      };

      if (!payload.label) {
        throw new Error('Integration label is required.');
      }

      setServiceBusy(true);
      if (selectedIntegrationId === 'new') {
        const created = await createIntegration(activeProject, payload);
        appendLog(`Created ${created.label} integration.`);
        await loadServices(created.id);
      } else {
        const updated = await updateIntegration(activeProject, selectedIntegrationId, payload);
        appendLog(`Updated ${updated.label} integration.`);
        await loadServices(updated.id);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to save integration.';
      setServicesError(message);
      appendLog(message);
    } finally {
      setServiceBusy(false);
    }
  };

  const handleDeleteIntegration = async () => {
    if (selectedIntegrationId === 'new') {
      return;
    }

    const selected = integrations.find((integration) => integration.id === selectedIntegrationId);
    if (!selected || !window.confirm(`Delete ${selected.label}?`)) {
      return;
    }

    try {
      setServiceBusy(true);
      await deleteIntegration(activeProject, selectedIntegrationId);
      const nextBindings = Object.fromEntries(
        Object.entries(activeProject.serviceBindings).filter(([, integrationId]) => integrationId !== selectedIntegrationId),
      );
      updateActiveProject({ serviceBindings: nextBindings });
      appendLog(`Deleted ${selected.label} integration.`);
      await loadServices('new');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to delete integration.';
      setServicesError(message);
      appendLog(message);
    } finally {
      setServiceBusy(false);
    }
  };

  return (
    <div className="matrix-shell">
      <aside className="activity-bar">
        <div className="activity-logo">CM</div>
        <button
          className={`activity-btn ${sidebarView === 'explorer' ? 'active' : ''}`}
          onClick={() => setSidebarView('explorer')}
          title="Explorer"
        >
          ≡
        </button>
        <button
          className={`activity-btn ${sidebarView === 'services' ? 'active' : ''}`}
          onClick={() => setSidebarView('services')}
          title="Services"
        >
          ⛭
        </button>
        <button
          className={`activity-btn ${bottomTab === 'deploy' ? 'active' : ''}`}
          onClick={() => setBottomTab('deploy')}
          title="Deploy / Health"
        >
          ☁
        </button>
      </aside>

      <header className="title-bar">
        <div>
          <strong>Coding Matrix</strong>
          <span className="title-subtle"> VS Code-style workspace for Agent NEO</span>
        </div>
        <div className="title-actions">
          <button onClick={handleLoadTree} disabled={treeLoading || !activeProject.serviceBindings.github?.trim()}>
            {treeLoading ? 'Loading…' : 'Reload Repo'}
          </button>
          <button onClick={handleSaveActiveFile} disabled={!activeFile?.dirty}>
            Save File
          </button>
          <button onClick={() => void refreshStatus()}>Refresh Status</button>
        </div>
      </header>

      <section className="sidebar explorer-panel">
        {sidebarView === 'explorer' ? (
          <>
            <div className="panel-header">
              <span>Projects / MVPs</span>
              <div className="inline-actions">
                <button onClick={handleAddProject}>+</button>
                <button onClick={handleRemoveProject}>−</button>
              </div>
            </div>

            <select value={activeProject.id} onChange={(event) => setActiveProjectId(event.target.value)}>
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>

            <div className="sidebar-scroll">
              <div className="form-grid compact-form section-card">
                <label>
                  Project Name
                  <input value={activeProject.name} onChange={(event) => updateActiveProject({ name: event.target.value })} />
                </label>
                <label>
                  GitHub Owner
                  <input
                    value={activeProject.githubOwner}
                    onChange={(event) => updateActiveProject({ githubOwner: event.target.value })}
                  />
                </label>
                <label>
                  GitHub Repo
                  <input
                    value={activeProject.githubRepo}
                    onChange={(event) => updateActiveProject({ githubRepo: event.target.value })}
                  />
                </label>
                <label>
                  Branch
                  <input value={activeProject.branch} onChange={(event) => updateActiveProject({ branch: event.target.value })} />
                </label>
                <label>
                  Agent NEO URL
                  <input
                    value={activeProject.agentNeoUrl}
                    onChange={(event) => updateActiveProject({ agentNeoUrl: event.target.value })}
                  />
                </label>
                <label>
                  Agent NEO Token
                  <input
                    type="password"
                    value={activeProject.agentNeoToken}
                    onChange={(event) => updateActiveProject({ agentNeoToken: event.target.value })}
                  />
                </label>
                <label>
                  Deployment Health URL
                  <input
                    value={activeProject.deploymentHealthUrl}
                    onChange={(event) => updateActiveProject({ deploymentHealthUrl: event.target.value })}
                  />
                </label>
              </div>

              <div className="section-card compact-form">
                <div className="panel-header secondary no-margin">
                  <span>Deployment Targets</span>
                  <span className="title-subtle">per-provider IDs</span>
                </div>
                {DEPLOYMENT_TARGET_FIELDS.map((field) => (
                  <label key={field.provider}>
                    {field.label}
                    <input
                      value={activeProject.deploymentTargets[field.provider] ?? ''}
                      placeholder={field.placeholder}
                      onChange={(event) => updateDeploymentTarget(field.provider, event.target.value)}
                    />
                  </label>
                ))}
              </div>

              <div className="section-card binding-card">
                <div className="panel-header secondary no-margin">
                  <span>Bound Services</span>
                  <span className="title-subtle">{boundServiceCount} linked</span>
                </div>

                <div className="binding-list compact-form">
                  {bindingProviders.map((provider) => {
                    const options = integrationOptionsByProvider.get(provider) ?? [];
                    return (
                      <label key={provider}>
                        {providerLabel(provider, integrationCatalog)}
                        <select
                          value={activeProject.serviceBindings[provider] ?? ''}
                          onChange={(event) => handleBindingChange(provider, event.target.value)}
                        >
                          <option value="">Not bound</option>
                          {options.map((integration) => (
                            <option key={integration.id} value={integration.id}>
                              {integration.label}
                            </option>
                          ))}
                        </select>
                      </label>
                    );
                  })}
                </div>

                {!activeProject.serviceBindings.github?.trim() && (
                  <div className="inline-note warning">
                    Bind GitHub in Services to browse, open, and save repo files.
                  </div>
                )}

                <button className="secondary-action" onClick={() => setSidebarView('services')}>
                  Open Services Registry
                </button>
              </div>

              <div className="panel-header secondary">
                <span>Explorer</span>
                <span className="title-subtle">{activeProject.githubOwner}/{activeProject.githubRepo}</span>
              </div>

              <div className="tree-container">
                {tree.length > 0 ? (
                  <TreeView
                    nodes={tree}
                    activePath={activeFilePath}
                    expanded={expanded}
                    onToggle={(path) => setExpanded((current) => ({ ...current, [path]: !(current[path] ?? false) }))}
                    onOpen={(path) => void handleOpenFile(path)}
                  />
                ) : (
                  <div className="empty-state small">Bind GitHub, then load the repo to browse files.</div>
                )}
              </div>
            </div>
          </>
        ) : (
          <>
            <div className="panel-header">
              <span>Services Registry</span>
              <div className="inline-actions">
                <button onClick={() => handleSelectIntegration('new')}>New</button>
                <button onClick={() => void loadServices(selectedIntegrationId)}>↻</button>
              </div>
            </div>

            <div className="title-subtle">
              Store service secrets on the backend, then bind them per MVP from Explorer.
            </div>

            <div className="sidebar-scroll">
              {servicesError && <div className="inline-note error">{servicesError}</div>}

              <div className="section-card compact-form">
                <label>
                  Saved Integrations
                  <select value={selectedIntegrationId} onChange={(event) => handleSelectIntegration(event.target.value)}>
                    <option value="new">Create new integration</option>
                    {integrations.map((integration) => (
                      <option key={integration.id} value={integration.id}>
                        {integration.label} · {providerLabel(integration.provider, integrationCatalog)}
                      </option>
                    ))}
                  </select>
                </label>

                <div className="integration-list">
                  {integrations.length > 0 ? (
                    integrations.map((integration) => (
                      <button
                        key={integration.id}
                        className={`integration-item ${selectedIntegrationId === integration.id ? 'active' : ''}`}
                        onClick={() => handleSelectIntegration(integration.id)}
                      >
                        <span>{integration.label}</span>
                        <span className="integration-meta">
                          {providerLabel(integration.provider, integrationCatalog)} · {integration.secret_configured ? 'secret set' : 'no secret'}
                        </span>
                      </button>
                    ))
                  ) : (
                    <div className="empty-state small">No integrations saved yet.</div>
                  )}
                </div>
              </div>

              <div className="section-card compact-form">
                <label>
                  Provider
                  <select value={serviceForm.provider} onChange={(event) => handleServiceProviderChange(event.target.value)}>
                    {availableServiceProviders.map((provider) => (
                      <option key={provider} value={provider}>
                        {providerLabel(provider, integrationCatalog)}
                      </option>
                    ))}
                  </select>
                </label>

                <label>
                  Label
                  <input
                    value={serviceForm.label}
                    onChange={(event) => setServiceForm((current) => ({ ...current, label: event.target.value }))}
                  />
                </label>

                <label>
                  Base URL
                  <input
                    value={serviceForm.baseUrl}
                    onChange={(event) => setServiceForm((current) => ({ ...current, baseUrl: event.target.value }))}
                  />
                </label>

                <label>
                  Auth Type
                  <select
                    value={serviceForm.authType}
                    onChange={(event) =>
                      setServiceForm((current) => ({ ...current, authType: event.target.value as IntegrationAuthType }))
                    }
                  >
                    <option value="bearer">Bearer</option>
                    <option value="x-api-key">X-API-Key</option>
                    <option value="custom_header">Custom Header</option>
                    <option value="none">None</option>
                  </select>
                </label>

                <label>
                  Auth Header
                  <input
                    value={serviceForm.authHeader}
                    onChange={(event) => setServiceForm((current) => ({ ...current, authHeader: event.target.value }))}
                  />
                </label>

                <label>
                  Auth Scheme
                  <input
                    value={serviceForm.authScheme}
                    onChange={(event) => setServiceForm((current) => ({ ...current, authScheme: event.target.value }))}
                  />
                </label>

                <label>
                  Secret
                  <input
                    type="password"
                    value={serviceForm.secret}
                    onChange={(event) => setServiceForm((current) => ({ ...current, secret: event.target.value }))}
                    placeholder={selectedIntegrationId === 'new' ? 'Paste token / API key' : 'Leave blank to keep current secret'}
                  />
                </label>

                {selectedIntegrationId !== 'new' && (
                  <label className="checkbox-row">
                    <input
                      type="checkbox"
                      checked={serviceForm.clearSecret}
                      onChange={(event) =>
                        setServiceForm((current) => ({ ...current, clearSecret: event.target.checked, secret: '' }))
                      }
                    />
                    <span>Clear stored secret on save</span>
                  </label>
                )}

                <label>
                  Extra Headers JSON
                  <textarea
                    rows={4}
                    value={serviceForm.headersJson}
                    onChange={(event) => setServiceForm((current) => ({ ...current, headersJson: event.target.value }))}
                  />
                </label>

                <label>
                  Description
                  <textarea
                    rows={3}
                    value={serviceForm.description}
                    onChange={(event) => setServiceForm((current) => ({ ...current, description: event.target.value }))}
                  />
                </label>

                <div className="diff-actions">
                  <button onClick={() => void handleSaveIntegration()} disabled={serviceBusy || servicesLoading || !canManageBackend}>
                    {serviceBusy ? 'Saving…' : selectedIntegrationId === 'new' ? 'Create Integration' : 'Save Changes'}
                  </button>
                  <button className="secondary" onClick={() => handleSelectIntegration('new')} disabled={serviceBusy}>
                    Reset
                  </button>
                  <button
                    className="secondary"
                    onClick={() => void handleDeleteIntegration()}
                    disabled={serviceBusy || selectedIntegrationId === 'new'}
                  >
                    Delete
                  </button>
                </div>
              </div>
            </div>
          </>
        )}
      </section>

      <main className="editor-panel">
        <div className="tabs-bar">
          {openFiles.length === 0 ? (
            <div className="tab inactive">No file open</div>
          ) : (
            openFiles.map((file) => (
              <button
                key={file.path}
                className={`tab ${file.path === activeFilePath ? 'active' : ''}`}
                onClick={() => setActiveFilePath(file.path)}
              >
                {file.path.split('/').pop()}
                {file.dirty ? ' •' : ''}
              </button>
            ))
          )}
        </div>

        <div className="editor-surface">
          {activeFile ? (
            <Editor
              height="100%"
              path={activeFile.path}
              language={activeFile.language}
              theme="vs-dark"
              value={activeFile.content}
              onChange={handleEditorChange}
              options={{ minimap: { enabled: false }, fontSize: 13, wordWrap: 'on' }}
            />
          ) : (
            <div className="empty-state">
              <h2>Welcome to Coding Matrix</h2>
              <p>Pick an MVP, load a GitHub repo, and open a file to start editing.</p>
              <p>Use the right chat panel to ask Agent NEO for diffs or phased `/run` tasks.</p>
            </div>
          )}
        </div>
      </main>

      <section className="chat-panel">
        <div className="panel-header">
          <span>Agent NEO</span>
          <span className="title-subtle">{sessionId ? `Session ${sessionId.slice(0, 8)}` : 'New session'}</span>
        </div>

        {phases.length > 0 && (
          <div className="phase-board">
            {phases.map((phase) => (
              <div key={phase.id} className={`phase-card ${phase.status}`}>
                <div className="phase-title">{phase.name}</div>
                <div className="phase-meta">{phase.specialist ?? 'specialist'} • {phase.status}</div>
                {phase.checkpoint && <div className="phase-detail">checkpoint {phase.checkpoint}</div>}
                {phase.summary && <div className="phase-detail">{phase.summary}</div>}
                {phase.error && <div className="phase-detail error">{phase.error}</div>}
              </div>
            ))}
          </div>
        )}

        <div className="chat-stream">
          {messages.map((message) => (
            <div key={message.id} className={`chat-message ${message.role}`}>
              <div className="chat-role">{message.role === 'user' ? 'You' : message.role === 'assistant' ? 'Agent NEO' : 'System'}</div>
              <div className="chat-content">{message.content}</div>

              {message.diffProposal && (
                <div className="diff-card">
                  <div className="diff-title">Proposed Changes</div>
                  <div className="diff-summary">{message.diffProposal.summary}</div>
                  <div className="diff-stats">
                    {message.diffProposal.files_changed.length} files • +{message.diffProposal.additions} / -{message.diffProposal.deletions}
                  </div>
                  <pre>{message.diffProposal.diff.slice(0, 1800)}</pre>
                  <div className="diff-actions">
                    <button onClick={() => void handleApprove(true, false)} disabled={busy}>Apply</button>
                    <button onClick={() => void handleApprove(true, true)} disabled={busy}>Commit & Push</button>
                    <button className="secondary" onClick={() => void handleApprove(false, false)} disabled={busy}>Reject</button>
                  </div>
                </div>
              )}

              {message.executionResult && (
                <div className="exec-card">
                  <div>{message.executionResult.status} • {message.executionResult.mode}</div>
                  {message.executionResult.commit_sha && <div>commit {message.executionResult.commit_sha}</div>}
                  {message.executionResult.files_changed.length > 0 && (
                    <div>{message.executionResult.files_changed.join(', ')}</div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>

        <div className="chat-input-panel">
          <div className="title-subtle">Commands: /run &lt;task&gt;, /rollback, /new, /help</div>
          <textarea
            value={chatInput}
            onChange={(event) => setChatInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                void handleSend();
              }
            }}
            placeholder="Ask Agent NEO anything…"
          />
          <button onClick={() => void handleSend()} disabled={busy}>
            {busy ? 'Working…' : 'Send'}
          </button>
        </div>
      </section>

      <section className="bottom-panel">
        <div className="panel-header">
          <div className="inline-actions tabs-inline">
            <button className={bottomTab === 'terminal' ? 'active' : ''} onClick={() => setBottomTab('terminal')}>
              Terminal
            </button>
            <button className={bottomTab === 'deploy' ? 'active' : ''} onClick={() => setBottomTab('deploy')}>
              Deploy / Health
            </button>
          </div>
        </div>

        {bottomTab === 'terminal' ? (
          <div className="terminal-log">
            {logs.map((entry, index) => (
              <div key={`${entry}-${index}`}>{entry}</div>
            ))}
          </div>
        ) : (
          <div className="deploy-grid">
            <div className={`status-card ${agentStatus.state}`}>
              <div className="status-title">Agent NEO</div>
              <div>{agentStatus.message}</div>
              {agentStatus.details && <pre>{agentStatus.details}</pre>}
            </div>
            <div className={`status-card ${deployStatus.state}`}>
              <div className="status-title">Deployment</div>
              <div>{deployStatus.message}</div>
              {deployStatus.details && <pre>{deployStatus.details}</pre>}
            </div>
            <div className="status-card idle">
              <div className="status-title">Proxy Note</div>
              <div>
                Use <code>/api/backend</code> + <code>VITE_DEV_PROXY_TARGET</code> for local dev, or serve the app behind the same origin as Agent NEO in production.
              </div>
            </div>
            {deployProviderCards.map(({ provider, title, target }) => {
              const status = providerStatuses[provider] ?? { state: 'idle', message: 'Waiting for refresh…' };
              return (
                <div key={provider} className={`status-card ${status.state}`}>
                  <div className="status-title">{title}</div>
                  <div>{status.message}</div>
                  <div className="status-meta">{target || 'No target configured'}</div>
                  {status.details && <pre>{status.details}</pre>}
                </div>
              );
            })}
          </div>
        )}
      </section>

      <footer className="status-bar">
        <span>{activeProject.githubOwner}/{activeProject.githubRepo}</span>
        <span>{activeProject.branch || 'default branch'}</span>
        <span>GitHub {activeProject.serviceBindings.github ? 'bound' : 'unbound'}</span>
        <span>{boundServiceCount} services linked</span>
        <span>{activeFile?.path ?? 'No file selected'}</span>
        <span>{openFiles.filter((file) => file.dirty).length} dirty</span>
      </footer>
    </div>
  );
}

export default App;
