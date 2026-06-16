export type ChangeStatus = "unchanged" | "changed" | "added" | "removed";

export interface EvidenceItem {
  tag: string;
  before: string;
  after: string;
}

export interface ComparisonItem {
  article_number: string;
  dieu_number: string | null;
  khoan_number: string | null;
  article_title: string;
  status: ChangeStatus;
  match_score: number;
  matched_article_v2: string | null;
  conclusion: string;
  grounded: boolean;
  llm_used: boolean;
  evidence: EvidenceItem[];
  /** True when this item only exists in V2 (added). dieu_number/khoan_number are V2 coordinates. */
  v2_only?: boolean;
}

export interface ReportConfig {
  file_v1: string;
  file_v2: string;
  llm_model: string;
  embed_model: string;
  total_khoans: number;
  status_counts: Record<string, number>;
  grounded_count: number;
  llm_used_count: number;
}

export interface CompareResponse {
  session_id: string;
  config: ReportConfig;
  results: ComparisonItem[];
  has_docx_v1: boolean;
  has_docx_v2: boolean;
}

export interface HealthStatus {
  embedder: "ready" | "loading";
  ollama: "ready" | "error";
}
