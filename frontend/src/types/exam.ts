export interface Option {
  key: string;
  text: string;
}

export interface Question {
  id?: number;
  numero_questao: string;
  statement: string;
  options: Record<string, string>;
  correct_answer: string;
  subject: string;
  images?: string[] | null;
  has_official_answer: boolean;
  latex_support: boolean;
  context_text?: string | null;
}

export interface ExamSummary {
  id: number;
  title: string;
  status: string;
  question_count: number;
  best_score: number | null;
  last_score: number | null;
  attempt_count: number;
  has_official_answers: boolean;
  answer_key_source: string;
  gabarito_coverage: number;
  gabarito_summary?: string | null;
  source_url?: string | null;
}

export interface Folder {
  id: number | string;
  name: string;
  exams: ExamSummary[];
}

export interface ExamDetail {
  id: number;
  title: string;
  status: string;
  folder_id?: number | null;
  source_url?: string | null;
  gabarito_url?: string | null;
  has_official_answers: boolean;
  gabarito_coverage: number;
  gabarito_text?: string | null;
  questions: Question[];
}

export interface SearchResultItem {
  id?: number | null;
  title: string;
  url: string;
  gabarito_url?: string | null;
  has_gabarito_link: boolean;
  match_score: number;
  source: string;
  status?: string;
  reuse_available?: boolean;
}

export interface ExamIngestResult {
  exam_id: number;
  title: string;
  status: string;
  progress: number;
  message: string;
  reused: boolean;
  already_in_library: boolean;
}

export interface ActiveDownload {
  id: number;
  title: string;
  url: string;
  status: string;
  progress: number;
  error_type?: string | null;
}

export interface AttemptSubmission {
  exam_id: number;
  elapsed_seconds: number;
  answers: Record<string, string>;
}

export interface AttemptResult {
  attempt_id: number;
  exam_id: number;
  score: number;
  total: number;
  percentage: number;
  elapsed_seconds: number;
  detailed_answers: Record<string, {
    question_id: number;
    user_answer: string;
    correct_answer: string;
    is_correct: boolean;
    subject: string;
  }>;
  feedback_per_subject: Record<string, {
    total: number;
    correct: number;
    percentage: number;
  }>;
}

export interface GlobalStats {
  total_exams: number;
  total_questions: number;
  total_correct: number;
  global_accuracy: number;
  streak: number;
  study_time: string;
  rank: string;
}

export interface NotebookSubjectStat {
  subject: string;
  count: number;
}

export interface RankingEntry {
  name?: string | null;
  picture?: string | null;
  total_questions: number;
  accuracy: number;
}

export interface ExamProgress {
  status: string;
  progress: number;
  error_type?: string | null;
}

export type AsyncStatus = 'idle' | 'loading' | 'success' | 'empty' | 'error';
export type ImportStage = 'form' | 'submitting' | 'processing' | 'ready' | 'error';
