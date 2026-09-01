import {
  Folder,
  ExamDetail,
  SearchResultItem,
  AttemptSubmission,
  AttemptResult,
  GlobalStats,
  NotebookSubjectStat,
  RankingEntry,
  ExamProgress,
  ExamIngestResult,
  ActiveDownload,
} from '../types/exam';

const API_BASE = '/api/v1';

export const api = {
  async getFolders(): Promise<Folder[]> {
    const res = await fetch(`${API_BASE}/folders`);
    if (!res.ok) throw new Error('Falha ao carregar pastas de provas');
    return res.json();
  },

  async getExam(examId: number): Promise<ExamDetail> {
    const res = await fetch(`${API_BASE}/exams/${examId}`);
    if (!res.ok) throw new Error('Falha ao carregar exame');
    return res.json();
  },

  async generateCustomExam(count: number = 20): Promise<ExamDetail> {
    const res = await fetch(`${API_BASE}/exams/generate_custom?count=${count}`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error('Falha ao gerar simulado personalizado');
    return res.json();
  },

  async submitAttempt(submission: AttemptSubmission): Promise<AttemptResult> {
    const res = await fetch(`${API_BASE}/exams/attempt`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(submission),
    });
    if (!res.ok) throw new Error('Falha ao enviar respostas do simulado');
    return res.json();
  },

  async searchExams(query: string, sources?: string, refresh: boolean = false): Promise<SearchResultItem[]> {
    const params = new URLSearchParams({ q: query });
    if (sources) params.append('sources', sources);
    if (refresh) params.append('refresh', 'true');
    const res = await fetch(`${API_BASE}/search?${params.toString()}`);
    if (!res.ok) throw new Error('Falha ao realizar busca de provas');
    return res.json();
  },

  async ingestExam(url: string, title: string, gabaritoUrl?: string): Promise<ExamIngestResult> {
    const res = await fetch(`${API_BASE}/exams/ingest`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, title, gabarito_url: gabaritoUrl }),
    });
    if (!res.ok) throw new Error('Falha ao iniciar processamento da prova');
    return res.json();
  },

  async claimProcessedExam(examId: number): Promise<ExamIngestResult> {
    const res = await fetch(`${API_BASE}/exams/${examId}/claim`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error('Falha ao adicionar a prova processada à biblioteca');
    return res.json();
  },

  async getGlobalStats(): Promise<GlobalStats> {
    const res = await fetch(`${API_BASE}/stats/overview`);
    if (!res.ok) throw new Error('Falha ao obter estatísticas de desempenho');
    return res.json();
  },

  async getNotebookStats(): Promise<NotebookSubjectStat[]> {
    const res = await fetch(`${API_BASE}/notebook/stats`);
    if (!res.ok) throw new Error('Falha ao carregar dados do caderno de erros');
    return res.json();
  },

  async getErrorNotebookExam(subject?: string): Promise<ExamDetail> {
    const url = subject ? `${API_BASE}/notebook?subject=${encodeURIComponent(subject)}` : `${API_BASE}/notebook`;
    const res = await fetch(url);
    if (!res.ok) throw new Error('Falha ao gerar caderno de erros');
    return res.json();
  },

  async getRanking(): Promise<RankingEntry[]> {
    const res = await fetch(`${API_BASE}/ranking`);
    if (!res.ok) throw new Error('Falha ao carregar ranking global');
    return res.json();
  },

  async getActiveDownloads(): Promise<ActiveDownload[]> {
    const res = await fetch(`${API_BASE}/downloads/active`);
    if (!res.ok) return [];
    return res.json();
  },

  async getExamProgress(examId: number): Promise<ExamProgress> {
    const res = await fetch(`${API_BASE}/exams/${examId}/progress`);
    if (!res.ok) throw new Error('Falha ao consultar o processamento da prova');
    return res.json();
  },
};
