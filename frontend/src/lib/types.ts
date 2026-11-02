export type Sport = "football" | "basketball" | "tennis";
export interface Team { id: number; name: string; country: string; logo_url: string | null; sport: Sport; extra: Record<string, unknown> }
export interface Competition { id: number; name: string; country: string; season: string; sport: Sport; logo_url: string | null }
export interface Match {
  id: number; sport: Sport; start_time: string; status: "scheduled" | "live" | "finished" | "postponed" | "cancelled" | "unknown";
  status_detail: string; elapsed: number | null; home: Team; away: Team; home_score: number | null; away_score: number | null;
  periods: Record<string, any>; competition: Competition | null; surface: string | null; last_synced_at: string | null;
  source: string; venue?: string; stats?: Record<string, any>;
}
export interface Factor { text: string; value: number }
export interface Prediction {
  id: number; match_id: number; sport: Sport; market: string; market_label: string; engine: string; engine_version: string;
  probabilities: Record<string, number>; predicted_outcome: string; confidence: number;
  explanation: { summary?: string; factors_for?: Factor[]; factors_against?: Factor[]; trends?: string[];
    stats_used?: Record<string, any>; confidence_label?: string; limited?: boolean };
  data_quality: { level?: string; warnings?: string[]; data_until?: string; days_since_last_match?: number | null; [k: string]: any };
  created_at: string; kickoff_at: string; content_hash: string; is_backtest: boolean;
  result: null | { actual_outcome: string; is_correct: boolean | null; brier: number | null; log_loss: number | null; resolved_at: string };
  match?: Match;
}
export interface Plan { code: string; name: string; description: string; prediction_views_per_day: number | null; max_follows: number;
  full_explanations: boolean; push_notifications: boolean; history_days: number | null; features: string[] }
export interface User { id: number; email: string; full_name: string; role: "user" | "admin"; plan: Plan; timezone: string; created_at: string }
export interface Notification { id: number; kind: string; title: string; body: string; data: Record<string, any>; match_id: number | null; created_at: string; read_at: string | null }
export interface Block { n: number; hits?: number; accuracy: number | null; accuracy_ci95: [number, number] | null; brier: number | null;
  brier_uniform_baseline?: number; log_loss: number | null; avg_confidence?: number; conclusive: boolean }
export interface Evaluation {
  target_accuracy: number; target_note: string; min_sample_for_conclusions: number; overall: Block & { gap_to_target: number | null };
  pending_predictions: number; by_mode: Record<string, Block>; by_sport: Record<string, Block>; by_market: Record<string, Block>;
  by_competition: Record<string, Block>; by_confidence: Record<string, Block>;
  calibration: Record<string, { bins: { range: [number, number]; n: number; mean_predicted: number; observed_frequency: number }[]; ece: number | null; n_points: number }>;
}
