export type SignalType = 'finance_hiring' | 'funding' | 'expansion'
export type Lead = {
  id: string; company: string; domain: string; contact: string; email: string;
  country: string; employees: number | null; industry: string; owner: string;
  status: string; score: number; summary: string; angle: string; destination: string;
  is_demo: boolean; created_at: string; updated_at: string;
  signals: { id: string; type: SignalType; evidence: string; points: number; source_id: string }[];
  draft: {subject: string; body: string; revision: number; edited: boolean} | null;
  sources?: {id: string; kind: string; title: string; content: string; created_at: string}[];
  delivery?: {id: string; status: string; sequence: string; created_at: string} | null;
}
export type Metrics = {
  total: number; high_intent: number; ready: number; approved: number; rejected: number;
  pending: number; failed: number; discarded: number; edited: number; avg_approval_seconds: number | null;
  demo_leads: number; trend: {day: string; leads: number; high: number}[];
  budget: {reserved_usd: number; actual_usd: number; limit_usd: number}; llm_configured: boolean; model: string;
}
export type Rules = {finance_hiring: number; funding: number; expansion: number; corporate_domain: number; dm_threshold: number; template: string}
export type Job = {id: string; lead_id: string; company: string; status: string; attempts: number; error: string; created_at: string; available_at: string; trace: {model?: string; latency_ms?: number; prompt_tokens?: number; completion_tokens?: number; cost_usd?: number; demo?: boolean}}
export type Audit = {id: string; lead_id: string | null; company: string; action: string; actor: string; detail: Record<string, unknown>; created_at: string}
export type IngestionResult = {accepted: {id: string; company: string}[]; duplicates: {row: number; company: string; reason: string}[]; rejected: {row: number; company: string; reason: string}[]}

