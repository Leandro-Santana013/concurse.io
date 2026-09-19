import {
  Folder,
  LibrarySnapshot,
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
  SearchResultsPage,
  CustomSimulationOptions,
  CustomSimulationRequest,
  CustomSimulationSummary,
  MeshTicket,
} from '../types/exam';
import { AuthConfig, AuthUser } from '../types/auth';

export const API_ORIGIN = (import.meta.env.VITE_API_ORIGIN || '').trim().replace(/\/+$/, '');
export const OFFLINE_DESKTOP = import.meta.env.VITE_OFFLINE_DESKTOP === '1';

const invokeOffline = async <T>(command: string, args: Record<string, unknown> = {}): Promise<T> => {
  if (!OFFLINE_DESKTOP) {
    throw new Error('O comando local só está disponível no aplicativo desktop.');
  }
  const { invoke } = await import('@tauri-apps/api/core');
  return invoke<T>(command, args);
};

export const apiUrl = (path: string): string => {
  if (!path || /^[a-z][a-z\d+.-]*:\/\//i.test(path) || !API_ORIGIN) return path;
  return `${API_ORIGIN}${path.startsWith('/') ? path : `/${path}`}`;
};

const API_BASE = apiUrl('/api/v1');

const resolveApiUrl = (value: string): string => {
  return apiUrl(value);
};

const normalizeExam = (exam: ExamDetail): ExamDetail => ({
  ...exam,
  questions: (exam.questions || []).map((question) => ({
    ...question,
    images: question.images?.map(resolveApiUrl) || question.images,
    option_images: question.option_images
      ? Object.fromEntries(
          Object.entries(question.option_images).map(([key, images]) => [
            key,
            images.map(resolveApiUrl),
          ]),
        )
      : question.option_images,
  })),
});

const apiFetch = (input: RequestInfo | URL, init: RequestInit = {}) =>
  fetch(input, { ...init, credentials: 'include' });

export class AuthRequiredError extends Error {
  constructor(message = 'Sua sessão expirou. Faça login novamente para ver sua biblioteca.') {
    super(message);
    this.name = 'AuthRequiredError';
  }
}

export const api = {
  async getAuthConfig(): Promise<AuthConfig> {
    if (OFFLINE_DESKTOP) return invokeOffline<AuthConfig>('offline_auth_config');
    const res = await apiFetch(`${API_BASE}/auth/config`);
    if (!res.ok) throw new Error('Falha ao consultar a configuração de acesso');
    return res.json();
  },

  async getCurrentUser(): Promise<AuthUser | null> {
    if (OFFLINE_DESKTOP) return invokeOffline<AuthUser>('offline_current_user');
    const res = await apiFetch(`${API_BASE}/auth/me`);
    if (res.status === 401) return null;
    if (!res.ok) throw new Error('Falha ao verificar sua sessão');
    return res.json();
  },

  getGoogleLoginUrl(nextPath: string = '/'): string {
    const safePath = nextPath.startsWith('/') && !nextPath.startsWith('//') ? nextPath : '/';
    return `${API_BASE}/auth/google/login?next=${encodeURIComponent(safePath)}`;
  },

  async logout(): Promise<void> {
    if (OFFLINE_DESKTOP) return;
    const res = await apiFetch(`${API_BASE}/auth/logout`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error('Não foi possível encerrar a sessão');
  },

  async deleteAccount(): Promise<void> {
    if (OFFLINE_DESKTOP) return;
    const res = await apiFetch(`${API_BASE}/auth/me`, {
      method: 'DELETE',
    });
    if (!res.ok) throw new Error('Não foi possível excluir a sua conta');
  },

  async getFolders(): Promise<Folder[]> {
    if (OFFLINE_DESKTOP) return invokeOffline<Folder[]>('offline_folders');
    const res = await apiFetch(`${API_BASE}/folders`);
    if (res.status === 401) throw new AuthRequiredError();
    if (!res.ok) throw new Error('Falha ao carregar pastas de provas');
    return res.json();
  },

  async getLibrarySnapshot(): Promise<LibrarySnapshot> {
    if (OFFLINE_DESKTOP) return invokeOffline<LibrarySnapshot>('offline_library_snapshot');
    const res = await apiFetch(`${API_BASE}/library/snapshot`);
    if (res.status === 401) throw new AuthRequiredError();
    if (!res.ok) throw new Error('Falha ao sincronizar a biblioteca');
    const snapshot: LibrarySnapshot = await res.json();
    for (const manifest of Object.values(snapshot.asset_manifests || {})) {
      for (const asset of manifest.assets || []) {
        asset.media_url = resolveApiUrl(asset.media_url);
      }
    }
    return snapshot;
  },

  async getMeshTicket(assetId: string): Promise<MeshTicket> {
    if (OFFLINE_DESKTOP) {
      throw new Error('A prova local é lida diretamente do armazenamento deste computador.');
    }
    const res = await apiFetch(`${API_BASE}/mesh/ticket/${encodeURIComponent(assetId)}`);
    if (res.status === 401) throw new AuthRequiredError();
    if (!res.ok) throw new Error('Falha ao preparar a transferência entre dispositivos');
    return res.json();
  },

  async getExam(examId: number): Promise<ExamDetail> {
    if (OFFLINE_DESKTOP) return normalizeExam(await invokeOffline<ExamDetail>('offline_get_exam', { examId }));
    const res = await apiFetch(`${API_BASE}/exams/${examId}`);
    if (!res.ok) throw new Error('Falha ao carregar exame');
    return normalizeExam(await res.json());
  },

  async getCustomSimulationOptions(): Promise<CustomSimulationOptions> {
    if (OFFLINE_DESKTOP) return invokeOffline<CustomSimulationOptions>('offline_custom_options');
    const res = await apiFetch(`${API_BASE}/custom-simulations/options`);
    if (res.status === 401) throw new AuthRequiredError();
    if (!res.ok) throw new Error('Falha ao carregar filtros do simulado personalizado');
    return res.json();
  },

  async getCustomSimulations(): Promise<CustomSimulationSummary[]> {
    if (OFFLINE_DESKTOP) return [];
    const res = await apiFetch(`${API_BASE}/custom-simulations`);
    if (res.status === 401) throw new AuthRequiredError();
    if (!res.ok) throw new Error('Falha ao carregar testes personalizados');
    return res.json();
  },

  async generateCustomExam(
    request: number | CustomSimulationRequest = 20,
  ): Promise<ExamDetail> {
    const config: CustomSimulationRequest = typeof request === 'number'
      ? { count: request }
      : request;
    if (OFFLINE_DESKTOP) {
      return normalizeExam(await invokeOffline<ExamDetail>('offline_custom_exam', { count: config.count ?? 20 }));
    }
    const params = new URLSearchParams({ count: String(config.count ?? 20) });
    for (const subject of config.subjects || []) {
      params.append('subjects', subject);
    }
    if (config.sourceExamId) params.set('source_exam_id', String(config.sourceExamId));
    params.set('strict', 'true');

    const res = await apiFetch(`${API_BASE}/exams/generate_custom?${params.toString()}`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error('Falha ao gerar simulado personalizado');
    return normalizeExam(await res.json());
  },

  async submitAttempt(submission: AttemptSubmission): Promise<AttemptResult> {
    if (OFFLINE_DESKTOP) {
      return invokeOffline<AttemptResult>('offline_submit_attempt', {
        examId: submission.exam_id,
        elapsedSeconds: submission.elapsed_seconds,
        answers: submission.answers,
      });
    }
    const res = await apiFetch(`${API_BASE}/exams/attempt`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(submission),
    });
    if (!res.ok) throw new Error('Falha ao enviar respostas do simulado');
    return res.json();
  },

  async searchExams(
    query: string,
    sources?: string,
    refresh: boolean = false,
    page: number = 1,
    pageSize: number = 25,
  ): Promise<SearchResultsPage> {
    if (OFFLINE_DESKTOP) {
      return invokeOffline<SearchResultsPage>('offline_search', { query });
    }
    const params = new URLSearchParams({
      q: query,
      page: String(page),
      page_size: String(pageSize),
    });
    if (sources) params.append('sources', sources);
    if (refresh) params.append('refresh', 'true');
    const res = await apiFetch(`${API_BASE}/search?${params.toString()}`);
    if (!res.ok) throw new Error('Falha ao realizar busca de provas');
    const data: unknown = await res.json();
    if (Array.isArray(data)) {
      const items = data as SearchResultItem[];
      return {
        items,
        page,
        page_size: pageSize,
        total: items.length,
        total_pages: items.length > 0 ? Math.ceil(items.length / pageSize) : 0,
        has_previous: page > 1,
        has_next: items.length === pageSize,
      };
    }
    return data as SearchResultsPage;
  },

  async ingestExam(url: string, title: string, gabaritoUrl?: string): Promise<ExamIngestResult> {
    if (OFFLINE_DESKTOP) {
      throw new Error('No modo offline escolha um arquivo local em vez de um link.');
    }
    const res = await apiFetch(`${API_BASE}/exams/ingest`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, title, gabarito_url: gabaritoUrl }),
    });
    if (!res.ok) throw new Error('Falha ao iniciar processamento da prova');
    return res.json();
  },

  async claimProcessedExam(examId: number): Promise<ExamIngestResult> {
    if (OFFLINE_DESKTOP) throw new Error('A prova já pertence a este computador.');
    const res = await apiFetch(`${API_BASE}/exams/${examId}/claim`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error('Falha ao adicionar a prova processada à biblioteca');
    return res.json();
  },

  async getGlobalStats(): Promise<GlobalStats> {
    if (OFFLINE_DESKTOP) return invokeOffline<GlobalStats>('offline_stats');
    const res = await apiFetch(`${API_BASE}/stats/overview`);
    if (!res.ok) throw new Error('Falha ao obter estatísticas de desempenho');
    return res.json();
  },

  async getNotebookStats(): Promise<NotebookSubjectStat[]> {
    if (OFFLINE_DESKTOP) return invokeOffline<NotebookSubjectStat[]>('offline_notebook_stats');
    const res = await apiFetch(`${API_BASE}/notebook/stats`);
    if (res.status === 401) throw new AuthRequiredError();
    if (!res.ok) throw new Error('Falha ao carregar dados do caderno de erros');
    return res.json();
  },

  async getErrorNotebookExam(subject?: string): Promise<ExamDetail> {
    if (OFFLINE_DESKTOP) throw new Error('O caderno de erros local ainda não possui questões respondidas.');
    const url = subject ? `${API_BASE}/notebook?subject=${encodeURIComponent(subject)}` : `${API_BASE}/notebook`;
    const res = await apiFetch(url);
    if (!res.ok) throw new Error('Falha ao gerar caderno de erros');
    return normalizeExam(await res.json());
  },

  async getRanking(): Promise<RankingEntry[]> {
    if (OFFLINE_DESKTOP) return invokeOffline<RankingEntry[]>('offline_ranking');
    const res = await apiFetch(`${API_BASE}/ranking`);
    if (!res.ok) throw new Error('Falha ao carregar ranking global');
    return res.json();
  },

  async getActiveDownloads(): Promise<ActiveDownload[]> {
    if (OFFLINE_DESKTOP) return invokeOffline<ActiveDownload[]>('offline_active_downloads');
    const res = await apiFetch(`${API_BASE}/downloads/active`);
    if (!res.ok) return [];
    return res.json();
  },

  async getExamProgress(examId: number): Promise<ExamProgress> {
    if (OFFLINE_DESKTOP) return { status: 'Aprovada', progress: 100 };
    const res = await apiFetch(`${API_BASE}/exams/${examId}/progress`);
    if (!res.ok) throw new Error('Falha ao consultar o processamento da prova');
    return res.json();
  },

  async ingestLocalFile(filename: string, dataBase64: string, title: string): Promise<ExamIngestResult> {
    if (!OFFLINE_DESKTOP) throw new Error('Importação local disponível apenas no desktop.');
    return invokeOffline<ExamIngestResult>('offline_import_file', {
      filename,
      dataBase64,
      title,
    });
  },

  async getMeshPeers(): Promise<{ node_id: string; tcp_port: number; peers: Array<{ node_id: string; address: string; tcp_port: number; profile_name: string; assets: Array<{ asset_id: string; size: number; title: string }>; last_seen: number }> }> {
    if (!OFFLINE_DESKTOP) return { node_id: '', tcp_port: 0, peers: [] };
    return invokeOffline('offline_mesh_peers');
  },

  async downloadMeshAsset(assetId: string): Promise<{ ok: boolean; status: string; exam_id?: number; title?: string }> {
    if (!OFFLINE_DESKTOP) throw new Error('A malha local só está disponível no desktop.');
    return invokeOffline('offline_download_asset', { assetId });
  },
};
