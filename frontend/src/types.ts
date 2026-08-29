// API payload types mirroring src/web/

export interface VictimBlock {
  model: string;
  tier: string;
  gguf: string;
  gguf_size_mb: number;
  gguf_sha256: string;
  litellm_model: string;
}

export interface RunSummary {
  name: string;
  tier: string;
  victim_model: string;
  status: string;
  dataset_size: number | null;
  created_at: string;
  raw_count: number;
  scored_counts: Record<string, number>;
  summaries: { asr: boolean; refusal: boolean; crosstab: boolean };
  notes: string;
}

export interface RunMeta {
  tier: string;
  dataset_size: number | null;
  victim_model: string;
  victim: VictimBlock | Record<string, never>;
  strategies: string[];
  created_at: string;
  updated_at: string;
  status: string;
  notes: string;
}

export interface SummaryBlock {
  present: boolean;
  rows: Record<string, string>[];
}

export interface RunOverview {
  name: string;
  meta: RunMeta;
  status: string;
  raw_count: number;
  scorers: string[];
  summaries: { asr: SummaryBlock; refusal: SummaryBlock; crosstab: SummaryBlock };
  backups: string[];
}

export interface ScoreEntry {
  value: string;
  rationale: string;
}

export interface PromptRow {
  objective: string;
  last_response: string;
  strategy: string;
  conversation_id: string;
  executed_turns: string;
  execution_time_ms: string;
  pyrit_outcome: string;
  pyrit_outcome_reason: string;
  scores: Record<string, ScoreEntry | null>;
  quadrants: Record<string, string | null>;
}

export interface PromptsResponse {
  run: string;
  count: number;
  scorers: string[];
  rows: PromptRow[];
}

export interface JobRecord {
  id: string;
  kind: string;
  params: Record<string, unknown>;
  run_name: string | null;
  status: string;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  progress: Record<string, { done: number; total: number }>;
  recent_events?: JobEvent[];
}

export interface JobEvent {
  seq: number;
  ts: number;
  type: string;
  line?: string;
  scorer?: string;
  done?: number;
  total?: number;
  status?: string;
  phase?: string;
  event?: string;
  run_name?: string;
  error?: string;
}

export interface SystemStatus {
  servers: { victim_8080: boolean; bf16_8081: boolean; litellm_4000: boolean };
  tiers: { tier: string; gguf: string; available: boolean }[];
  scorers: string[];
  queue: { current: JobRecord | null; queued: number };
}

export interface CompareResponse {
  kind: string;
  columns: { run: string; tier: string }[];
  metrics: { metric: string; values: Record<string, string> }[];
}

export interface ComparePromptsResponse {
  runs: string[];
  tiers: Record<string, string>;
  objectives: {
    objective: string;
    runs: Record<string, { pyrit_outcome: string; scores: Record<string, string> }>;
  }[];
}
