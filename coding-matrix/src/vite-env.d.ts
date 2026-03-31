/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Pre-filled Agent NEO bearer token (mirrors AGENT_NEO_TOKEN in root .env) */
  readonly VITE_AGENT_NEO_TOKEN?: string;
  /** Backend URL for the Vite dev proxy target */
  readonly VITE_DEV_PROXY_TARGET?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
