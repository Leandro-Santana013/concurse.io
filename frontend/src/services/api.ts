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
} from '../types/exam';
import { AuthConfig, AuthUser } from '../types/auth';
import {
  supabase,
  supabaseAuthConfigured,
  supabaseRedirectUrl,
} from './supabase';

export const API_ORIGIN = (import.meta.env.VITE_API_ORIGIN || '').trim().replace(/\/+$/, '');
export const OFFLINE_DESKTOP = import.meta.env.VITE_OFFLINE_DESKTOP === '1';
export const DESKTOP_APP = import.meta.env.VITE_DESKTOP_APP === '1';
export const TAURI_MOBILE_APP = import.meta.env.VITE_TAURI_MOBILE === '1';
export const MOBILE_OAUTH_RETURN = 'concurse://oauth/callback';

const DESKTOP_SESSION_KEY = 'concurse.desktop.session.v1';
const API_REQUEST_TIMEOUT_MS = 8000;
let desktopSessionToken = (() => {
  try {
    return typeof window === 'undefined' ? '' : window.localStorage.getItem(DESKTOP_SESSION_KEY) || '';
  } catch {
    return '';
  }
})();

const setDesktopSessionToken = (token: string) => {
  desktopSessionToken = token;
  try {
    if (typeof window === 'undefined') return;
    if (token) window.localStorage.setItem(DESKTOP_SESSION_KEY, token);
    else window.localStorage.removeItem(DESKTOP_SESSION_KEY);
  } catch {
    // A sessão em memória ainda permite o uso desta execução do aplicativo.
  }
};

const invokeDesktop = async <T>(command: string, args: Record<string, unknown> = {}): Promise<T> => {
  if (!DESKTOP_APP) {
    throw new Error('O comando local só está disponível no aplicativo desktop.');
  }
  const { invoke } = await import('@tauri-apps/api/core');
  return invoke<T>(command, args);
};

const invokeOffline = async <T>(command: string, args: Record<string, unknown> = {}): Promise<T> => {
  if (!OFFLINE_DESKTOP) throw new Error('O armazenamento offline não está habilitado neste build.');
  return invokeDesktop<T>(command, args);
};

const isTransportFailure = (error: unknown): boolean => {
  if (error instanceof TypeError) return true;
  const message = error instanceof Error ? error.message : String(error || '');
  return /failed to fetch|load failed|network|timed out|timeout|aborted|canceled|cancelled/i.test(message);
};

const invokeLocalFallback = async <T>(command: string, args: Record<string, unknown> = {}): Promise<T> => {
  if (!DESKTOP_APP) throw new Error('O cache local só está disponível no aplicativo desktop.');
  return invokeDesktop<T>(command, args);
};

export const apiUrl = (path: string): string => {
  if (!path || /^[a-z][a-z\d+.-]*:\/\//i.test(path) || !API_ORIGIN) return path;
  return `${API_ORIGIN}${path.startsWith('/') ? path : `/${path}`}`;
};

const API_BASE = apiUrl('/api/v1');

const resolveApiUrl = (value: string): string => {
  // A desktop proof must remain self-contained.  Remote media references from
  // a web export are ignored rather than letting the WebView make a hidden
  // request; embedded data URLs and local asset paths remain available.
  if (OFFLINE_DESKTOP && /^https?:\/\//i.test(value)) return '';
  return apiUrl(value);
};

const normalizeExam = (exam: ExamDetail): ExamDetail => ({
  ...exam,
  questions: (exam.questions || []).map((question) => ({
    ...question,
    images: question.images?.map(resolveApiUrl).filter(Boolean) || question.images,
    option_images: question.option_images
      ? Object.fromEntries(
          Object.entries(question.option_images).map(([key, images]) => [
            key,
            images.map(resolveApiUrl).filter(Boolean),
          ]),
        )
      : question.option_images,
  })),
});

const apiFetch = (input: RequestInfo | URL, init: RequestInit = {}) => {
  const headers = new Headers(init.headers);
  if (desktopSessionToken && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${desktopSessionToken}`);
  }
  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => controller.abort(), API_REQUEST_TIMEOUT_MS);
  return fetch(input, {
    ...init,
    headers,
    credentials: 'include',
    signal: controller.signal,
  }).finally(() => globalThis.clearTimeout(timeout));
};

export class AuthRequiredError extends Error {
  constructor(message = 'Sua sessão expirou. Faça login novamente para ver sua biblioteca.') {
    super(message);
    this.name = 'AuthRequiredError';
  }
}

export const api = {
  async getAuthConfig(): Promise<AuthConfig> {
    if (OFFLINE_DESKTOP) return invokeOffline<AuthConfig>('offline_auth_config');
    try {
      const res = await apiFetch(`${API_BASE}/auth/config`);
      if (!res.ok) throw new Error('Falha ao consultar a configuração de acesso');
      return res.json();
    } catch (error) {
      if (DESKTOP_APP && isTransportFailure(error)) return { google_enabled: false };
      throw error;
    }
  },

  async exchangeSupabaseSession(): Promise<AuthUser | null> {
    if (!supabaseAuthConfigured || !supabase) return null;
    const { data, error } = await supabase.auth.getSession();
    if (error) throw new Error('Falha ao ler a sessão do Supabase.');
    const accessToken = data.session?.access_token;
    if (!accessToken) return null;

    const res = await apiFetch(`${API_BASE}/auth/supabase/exchange`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ access_token: accessToken }),
    });
    if (res.status === 401) {
      await supabase.auth.signOut();
      return null;
    }
    if (!res.ok) throw new Error('Não foi possível sincronizar a conta Supabase.');
    const payload: { user?: AuthUser; session_token?: string } = await res.json();
    if (!payload.user) throw new Error('O servidor não retornou um usuário válido.');
    if (DESKTOP_APP && payload.session_token) setDesktopSessionToken(payload.session_token);
    return payload.user;
  },

  async getCurrentUser(): Promise<AuthUser | null> {
    if (OFFLINE_DESKTOP) return invokeOffline<AuthUser>('offline_current_user');
    try {
      const res = await apiFetch(`${API_BASE}/auth/me`);
      if (res.status === 401) return null;
      if (!res.ok) throw new Error('Falha ao verificar sua sessão');
      return res.json();
    } catch (error) {
      // A conta remota pode ficar temporariamente indisponível; o desktop
      // continua abrindo a biblioteca já armazenada nesta máquina.
      if (DESKTOP_APP && isTransportFailure(error)) {
        return invokeLocalFallback<AuthUser>('offline_current_user');
      }
      throw error;
    }
  },

  getGoogleLoginUrl(nextPath: string = '/'): string {
    const safePath = nextPath.startsWith('/') && !nextPath.startsWith('//') ? nextPath : '/';
    const mobileReturn = TAURI_MOBILE_APP
      ? `&client=desktop&desktop_return=${encodeURIComponent(MOBILE_OAUTH_RETURN)}`
      : '';
    return `${API_BASE}/auth/google/login?next=${encodeURIComponent(safePath)}${mobileReturn}`;
  },

  async beginGoogleLogin(nextPath: string = '/'): Promise<void> {
    if (DESKTOP_APP) {
      await invokeDesktop('desktop_begin_google_login', {
        apiOrigin: API_ORIGIN,
        nextPath,
      });
      return;
    }
    if (TAURI_MOBILE_APP) {
      const { openUrl } = await import('@tauri-apps/plugin-opener');
      await openUrl(this.getGoogleLoginUrl(nextPath));
      return;
    }
    window.location.assign(this.getGoogleLoginUrl(nextPath));
  },

  async beginSupabaseLogin(nextPath: string = '/'): Promise<void> {
    if (!supabaseAuthConfigured || !supabase) {
      throw new Error('O login Supabase não está configurado neste build.');
    }
    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: supabaseRedirectUrl(nextPath),
        queryParams: { access_type: 'offline', prompt: 'select_account' },
      },
    });
    if (error) throw new Error('Não foi possível abrir o login Google pelo Supabase.');
  },

  async takeDesktopOAuthCode(): Promise<string | null> {
    if (!DESKTOP_APP) return null;
    return invokeDesktop<string | null>('desktop_take_oauth_result');
  },

  async exchangeDesktopOAuthCode(code: string): Promise<AuthUser> {
    const res = await fetch(`${API_BASE}/auth/google/desktop/exchange`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code }),
    });
    if (!res.ok) throw new Error('Não foi possível concluir o login Google no aplicativo.');
    const payload: { session_token?: string; user?: AuthUser } = await res.json();
    if (!payload.session_token || !payload.user) throw new Error('O servidor não retornou uma sessão válida.');
    setDesktopSessionToken(payload.session_token);
    return payload.user;
  },

  async listenMobileOAuth(onCode: (code: string) => void): Promise<() => void> {
    if (!TAURI_MOBILE_APP) return () => undefined;
    const { getCurrent, onOpenUrl } = await import('@tauri-apps/plugin-deep-link');
    const consume = (urls: string[] | null | undefined) => {
      for (const value of urls || []) {
        try {
          const parsed = new URL(value);
          if (
            parsed.protocol !== 'concurse:'
            || parsed.hostname !== 'oauth'
            || parsed.pathname !== '/callback'
          ) continue;
          const error = parsed.searchParams.get('error');
          const code = parsed.searchParams.get('code');
          if (error) onCode(`__oauth_error__:${error}`);
          else if (code) onCode(code);
        } catch {
          // A deep link from another source is ignored.
        }
      }
    };
    consume(await getCurrent());
    return onOpenUrl(consume);
  },

  async logout(): Promise<void> {
    if (OFFLINE_DESKTOP) return;
    const res = await apiFetch(`${API_BASE}/auth/logout`, { method: 'POST' });
    if (!res.ok) throw new Error('Não foi possível encerrar a sessão');
    if (supabase) await supabase.auth.signOut();
    setDesktopSessionToken('');
  },

  async deleteAccount(): Promise<void> {
    if (OFFLINE_DESKTOP) return;
    const res = await apiFetch(`${API_BASE}/auth/me`, {
      method: 'DELETE',
    });
    if (!res.ok) throw new Error('Não foi possível excluir a sua conta');
    if (supabase) await supabase.auth.signOut();
    setDesktopSessionToken('');
  },

  async getFolders(): Promise<Folder[]> {
    if (OFFLINE_DESKTOP) return invokeOffline<Folder[]>('offline_folders');
    try {
      const res = await apiFetch(`${API_BASE}/folders`);
      if (res.status === 401) throw new AuthRequiredError();
      if (!res.ok) throw new Error('Falha ao carregar pastas de provas');
      return res.json();
    } catch (error) {
      if (DESKTOP_APP && isTransportFailure(error)) {
        return invokeLocalFallback<Folder[]>('offline_folders');
      }
      throw error;
    }
  },

  async getLibrarySnapshot(): Promise<LibrarySnapshot> {
    if (OFFLINE_DESKTOP) return invokeOffline<LibrarySnapshot>('offline_library_snapshot');
    try {
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
    } catch (error) {
      if (DESKTOP_APP && isTransportFailure(error)) {
        return invokeLocalFallback<LibrarySnapshot>('offline_library_snapshot');
      }
      throw error;
    }
  },

  async getExam(examId: number): Promise<ExamDetail> {
    if (OFFLINE_DESKTOP) return normalizeExam(await invokeOffline<ExamDetail>('offline_get_exam', { examId }));
    try {
      const res = await apiFetch(`${API_BASE}/exams/${examId}`);
      if (!res.ok) throw new Error('Falha ao carregar exame');
      return normalizeExam(await res.json());
    } catch (error) {
      if (DESKTOP_APP && isTransportFailure(error)) {
        return normalizeExam(await invokeLocalFallback<ExamDetail>('offline_get_exam', { examId }));
      }
      throw error;
    }
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
    try {
      const res = await apiFetch(`${API_BASE}/notebook/stats`);
      if (res.status === 401) throw new AuthRequiredError();
      if (!res.ok) throw new Error('Falha ao carregar dados do caderno de erros');
      return res.json();
    } catch (error) {
      if (DESKTOP_APP && isTransportFailure(error)) {
        return invokeLocalFallback<NotebookSubjectStat[]>('offline_notebook_stats');
      }
      throw error;
    }
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

};
