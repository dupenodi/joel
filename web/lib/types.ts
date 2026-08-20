/** Shared product types — mirrors §12 API shapes. */

export type ConnectorStatus =
  | "pending_auth"
  | "pending_setup"
  | "backfilling"
  | "distilling"
  | "linking"
  | "ready"
  | "syncing"
  | "needs_reauth"
  | "error"
  | "coming_soon";

export type AuthMode = "composio" | "oauth" | "token";

export type AnswerStatus = "answered" | "partial" | "conflicted" | "absent";

export interface Org {
  domain: string;
  name: string;
  logo_url: string;
  created_at: string;
}

export type MemberRole = "admin" | "member";

export interface Workspace {
  id: string;
  domain: string;
  name: string;
  logo_url: string;
  created_at: string;
  created_by: string;
}

export interface WorkspaceMember {
  id: string;
  email: string;
  display_name: string;
  role: MemberRole;
  created_at: string;
}

export interface WorkspaceInvite {
  id: string;
  email: string;
  role: MemberRole;
  created_at: string;
  expires_at: string;
  accepted_at: string | null;
}

export interface Me {
  id: string;
  email: string;
  display_name: string;
  role: MemberRole;
}

export interface ApiKey {
  id: string;
  label: string;
  last4: string;
  created_at: string;
  last_used_at: string | null;
}

export interface AuthStatus {
  state: "setup" | "login" | "ok";
  me: Me | null;
  workspace: Workspace | null;
}

export interface InvitePeek {
  email: string;
  role: MemberRole;
  workspace_name: string;
  workspace_domain: string;
}

export interface ReadinessChecklist {
  fetched: boolean;
  distilled: boolean;
  people_resolved: boolean;
  graph_linked: boolean;
  indexes_consistent: boolean;
  ready: boolean;
}

export interface ConnectorCard {
  id: string | null;
  provider: string;
  label: string;
  status: ConnectorStatus;
  mode: AuthMode | null;
  doc_count: number;
  last_sync_at: string | null;
  next_sync_at: string | null;
  backfill_done: boolean;
  backfill_progress: number | null;
  backfill_cursor?: string | null;
  error: string | null;
  interval_min: number;
  lookback_days?: number;
  channel_ids?: string[];
  coming_soon: boolean;
  ingest?: boolean;
  checklist?: ReadinessChecklist;
  sync_started_at?: string | null;
}

export interface JobRow {
  id: string;
  started_at: string;
  finished_at: string | null;
  status: "running" | "ok" | "error" | "cancelled";
  new_count: number;
  changed_count: number;
  unchanged_count: number;
  duration_ms: number | null;
  error: string | null;
}

export interface Profile {
  display_name: string;
  org: Org;
  corpus: {
    docs: number;
    artifacts: number;
    entities: number;
    oldest_doc: string | null;
    index: {
      sqlite: number;
      vectors: number;
      graph: number;
      consistent: boolean;
    };
  };
  spend_30d: Record<string, number>;
}

export interface Settings {
  llm_base_url: string;
  llm_api_key_set: boolean;
  llm_model_distill: string;
  llm_model_extract: string;
  llm_model_answer: string;
  llm_model_resolve: string;
  llm_model_rerank: string;
  sync_enabled: boolean;
  sync_default_interval_min?: number;
  history_floor?: string | null;
  composio_api_key_set?: boolean;
  embed_model: string;
  slack_signing_secret_set?: boolean;
  raw?: Record<string, string>;
}

export interface ComposioAccount {
  id: string;
  toolkit: string;
  status: string;
  label: string | null;
}

export interface ComposioStatus {
  configured: boolean;
  key_source: "settings" | "env" | "none";
  masked_key: string | null;
  accounts: ComposioAccount[];
  error?: string;
}

export interface Health {
  hydra: "ok" | "down";
  schema_version: number;
  sync_enabled: boolean;
  queue_depth: number;
  llm_error: string | null;
  index: {
    sqlite: number;
    vectors: number;
    graph: number;
    consistent: boolean;
  };
  connectors: Array<{
    provider: string;
    status: ConnectorStatus;
    last_success: string | null;
    next_run: string | null;
  }>;
}

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
}

export interface Citation {
  doc_id: string;
  title: string;
  url: string | null;
  live: boolean;
  provider?: string | null;
  source_type?: string | null;
}

export interface ToolCall {
  id: string;
  name: string;
  provider?: string | null;
  status: "running" | "done" | "skipped" | "error";
  detail?: string | null;
}

export interface ConflictPosition {
  claim: string;
  date?: string | null;
  source?: string | null;
  url?: string | null;
}

export interface Message {
  id?: string;
  role: "user" | "assistant";
  content: string;
  status?: AnswerStatus;
  not_found?: string[];
  citations?: Citation[];
  lanes?: string[];
  reasoning_path?: string[];
  tool_calls?: ToolCall[];
  conflicts?: Array<{
    assessment?: string;
    positions: ConflictPosition[];
  }>;
  created_at?: string;
}
