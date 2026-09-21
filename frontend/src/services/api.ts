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

const SUPABASE_URL = (import.meta.env.VITE_SUPABASE_URL || '').trim().replace(/\/+$/, '');
const SUPABASE_FUNCTIONS_URL = (import.meta.env.VITE_SUPABASE_FUNCTIONS_URL || `${SUPABASE_URL}/functions/v1`).replace(/\/+$/, '');
export const OFFLINE_DESKTOP = import.meta.env.VITE_OFFLINE_DESKTOP === '1';
export const DESKTOP_APP = import.meta.env.VITE_DESKTOP_APP === '1';
export const TAURI_MOBILE_APP = import.meta.env.VITE_TAURI_MOBILE === '1';
export const MOBILE_OAUTH_RETURN = 'concurse://oauth/callback';
const SUPABASE_OAUTH_FLOW_KEY = 'concurse.supabase.oauth.flow.v1';

export type OAuthDeepLinkResult = {
  code?: string;
  flowId?: string;
  error?: string;
  errorDescription?: string;
};

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

const getPendingSupabaseOAuthFlow = (): string => {
  try {
    return typeof window === 'undefined'
      ? ''
      : window.localStorage.getItem(SUPABASE_OAUTH_FLOW_KEY) || '';
  } catch {
    return '';
  }
};

const setPendingSupabaseOAuthFlow = (flowId: string | null | undefined) => {
  try {
    if (typeof window === 'undefined') return;
    if (flowId) window.localStorage.setItem(SUPABASE_OAUTH_FLOW_KEY, flowId);
    else window.localStorage.removeItem(SUPABASE_OAUTH_FLOW_KEY);
  } catch {
    // O retorno profundo ainda pode concluir o fluxo se o armazenamento local
    // estiver indisponível: o callback também carrega o flow id quando o
    // Supabase o acrescenta à URL.
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
  if (!path || /^[a-z][a-z\d+.-]*:\/\//i.test(path)) return path;
  const normalized = path.startsWith('/') ? path : `/${path}`;
  if (normalized.startsWith('/api/v1')) return `${SUPABASE_FUNCTIONS_URL}/app-gateway${normalized}`;
  return path;
};

const API_BASE = apiUrl('/api/v1');

const base64Bytes = (value: string): Uint8Array => {
  const binary = atob(value);
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
};

const utf8Base64 = (value: string): string => {
  const bytes = new TextEncoder().encode(value);
  let binary = '';
  const chunkSize = 0x8000;
  for (let index = 0; index < bytes.length; index += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize));
  }
  return btoa(binary);
};

const baseName = (value: string): string => {
  const normalized = value.replace(/\\/g, '/');
  const candidate = normalized.split('/').pop() || normalized;
  try {
    return decodeURIComponent(candidate).toLowerCase();
  } catch {
    return candidate.toLowerCase();
  }
};

const rewriteQuestionMedia = (document: Record<string, unknown>, mediaByName: Map<string, string>) => {
  const rewrite = (value: unknown): unknown => {
    if (typeof value !== 'string' || /^data:/i.test(value) || /^https?:\/\//i.test(value)) return value;
    return mediaByName.get(baseName(value)) || value;
  };
  const questions = Array.isArray(document.questions) ? document.questions : [];
  for (const rawQuestion of questions) {
    if (!rawQuestion || typeof rawQuestion !== 'object') continue;
    const question = rawQuestion as Record<string, unknown>;
    if (Array.isArray(question.images)) question.images = question.images.map(rewrite);
    if (question.option_images && typeof question.option_images === 'object') {
      const optionImages = question.option_images as Record<string, unknown>;
      for (const [key, values] of Object.entries(optionImages)) {
        if (Array.isArray(values)) optionImages[key] = values.map(rewrite);
      }
    }
  }
  return document;
};

const hexDigest = async (bytes: Uint8Array): Promise<string> => {
  const stableBytes = new Uint8Array(bytes.byteLength);
  stableBytes.set(bytes);
  const digest = await crypto.subtle.digest('SHA-256', stableBytes.buffer);
  return [...new Uint8Array(digest)].map((value) => value.toString(16).padStart(2, '0')).join('');
};

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

const apiFetch = async (input: RequestInfo | URL, init: RequestInit = {}, timeoutMs = API_REQUEST_TIMEOUT_MS) => {
  const headers = new Headers(init.headers);
  if (!headers.has('Authorization')) {
    const session = supabase ? (await supabase.auth.getSession()).data.session : null;
    if (session?.access_token) headers.set('Authorization', `Bearer ${session.access_token}`);
    else if (desktopSessionToken) headers.set('Authorization', `Bearer ${desktopSessionToken}`);
  }
  // Supabase Edge Functions use the bearer token above and intentionally return
  // a wildcard CORS origin. Sending cookies with a wildcard origin makes the
  // WebView reject the response as a generic "Failed to fetch" error after the
  // Google callback. Keep credentials only for same-origin legacy development
  // requests; the hosted Supabase gateway must be token-only.
  let credentials = init.credentials;
  try {
    const requestUrl = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
    const pageOrigin = typeof window !== 'undefined' ? window.location.origin : '';
    const requestOrigin = new URL(requestUrl, pageOrigin || undefined).origin;
    credentials = pageOrigin && requestOrigin !== pageOrigin ? 'omit' : (credentials || 'include');
  } catch {
    credentials = credentials || 'include';
  }
  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);
  return fetch(input, {
    ...init,
    headers,
    credentials,
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
    return { google_enabled: supabaseAuthConfigured, supabase_enabled: supabaseAuthConfigured };
  },

  async exchangeSupabaseSession(): Promise<AuthUser | null> {
    if (!supabaseAuthConfigured || !supabase) return null;
    const { data, error } = await supabase.auth.getSession();
    if (error) throw new Error('Falha ao ler a sessão do Supabase.');
    const accessToken = data.session?.access_token;
    if (!accessToken) return null;

    const res = await apiFetch(`${API_BASE}/auth/me`);
    if (res.status === 401) {
      await supabase.auth.signOut();
      return null;
    }
    if (!res.ok) throw new Error('Não foi possível sincronizar a conta Supabase.');
    return res.json();
  },

  async getCurrentUser(): Promise<AuthUser | null> {
    if (OFFLINE_DESKTOP) return invokeOffline<AuthUser>('offline_current_user');
    try {
      const res = await apiFetch(`${API_BASE}/auth/me`);
      if (res.status === 401) return null;
      if (!res.ok) throw new Error('Falha ao verificar sua sessão');
      return res.json();
    } catch (error) {
      // O modo remoto nunca cria uma sessão anônima quando a API fica
      // indisponível. A identidade local só existe no perfil offline explícito.
      if (DESKTOP_APP && OFFLINE_DESKTOP && isTransportFailure(error)) {
        return invokeLocalFallback<AuthUser>('offline_current_user');
      }
      throw error;
    }
  },

  getGoogleLoginUrl(_nextPath: string = '/'): string {
    // O login remoto passa sempre pelo Supabase Auth; não há mais rota Google
    // legada no aplicativo.
    return '#';
  },

  async beginGoogleLogin(nextPath: string = '/'): Promise<void> {
    return this.beginSupabaseLogin(nextPath);
  },

  async beginSupabaseLogin(nextPath: string = '/'): Promise<void> {
    if (!supabaseAuthConfigured || !supabase) {
      throw new Error('O login Supabase não está configurado neste build.');
    }
    const nativeApp = DESKTOP_APP || TAURI_MOBILE_APP;
    const redirectTo = nativeApp
      ? MOBILE_OAUTH_RETURN
      : supabaseRedirectUrl(nextPath);
    const { data, error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo,
        // Keep the Tauri window on the login screen while Google runs in the
        // system browser. The callback returns through concurse://oauth/callback.
        skipBrowserRedirect: nativeApp,
        queryParams: { access_type: 'offline', prompt: 'select_account' },
      },
    });
    if (error) throw new Error('Não foi possível abrir o login Google pelo Supabase.');
    // O navegador do sistema não compartilha a sessão da WebView. Mantemos o
    // flow id retornado pelo Supabase para selecionar o verifier PKCE correto
    // quando o deep link voltar ao aplicativo.
    if (nativeApp) setPendingSupabaseOAuthFlow(data?.flowId);
    if (nativeApp && data?.url) {
      const { openUrl } = await import('@tauri-apps/plugin-opener');
      try {
        await openUrl(data.url);
      } catch (error) {
        setPendingSupabaseOAuthFlow(null);
        throw error;
      }
    }
  },

  async exchangeSupabaseOAuthCode(code: string, flowId?: string): Promise<AuthUser | null> {
    if (!supabase) throw new Error('O login Supabase não está configurado neste build.');
    const pendingFlowId = flowId || getPendingSupabaseOAuthFlow();
    try {
      const { error } = await supabase.auth.exchangeCodeForSession(
        code,
        pendingFlowId ? { flowId: pendingFlowId } : undefined,
      );
      if (error) {
        throw new Error(`Não foi possível concluir o login Google no aplicativo: ${error.message}`);
      }
      return this.exchangeSupabaseSession();
    } finally {
      setPendingSupabaseOAuthFlow(null);
    }
  },

  clearPendingSupabaseOAuth(): void {
    setPendingSupabaseOAuthFlow(null);
  },

  async listenMobileOAuth(onResult: (result: OAuthDeepLinkResult) => void): Promise<() => void> {
    if (!DESKTOP_APP && !TAURI_MOBILE_APP) return () => undefined;
    const { getCurrent, onOpenUrl } = await import('@tauri-apps/plugin-deep-link');
    let lastUrl = '';
    const consume = (urls: string[] | null | undefined) => {
      for (const value of urls || []) {
        if (value === lastUrl) continue;
        lastUrl = value;
        try {
          const parsed = new URL(value);
          if (
            parsed.protocol !== 'concurse:'
            || parsed.hostname !== 'oauth'
            || parsed.pathname !== '/callback'
          ) continue;
          const error = parsed.searchParams.get('error');
          const errorDescription = parsed.searchParams.get('error_description') || undefined;
          const code = parsed.searchParams.get('code');
          const flowId = parsed.searchParams.get('sb_flow_id') || undefined;
          if (error) onResult({ error, errorDescription });
          else if (code) onResult({ code, flowId });
        } catch {
          // A deep link from another source is ignored.
        }
      }
    };
    // Register first so a callback that arrives while the app is already open
    // cannot race with the initial getCurrent() check on mobile.
    const stop = await onOpenUrl(consume);
    try {
      consume(await getCurrent());
    } catch (error) {
      stop();
      throw error;
    }
    return stop;
  },

  async logout(): Promise<void> {
    if (OFFLINE_DESKTOP) return;
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

  async uploadMedia(objectPath: string, bytes: Uint8Array, contentType: string): Promise<void> {
    if (OFFLINE_DESKTOP) throw new Error('O envio para o Oracle exige uma sessão Supabase online.');
    const res = await apiFetch(`${SUPABASE_FUNCTIONS_URL}/media-gateway?path=${encodeURIComponent(objectPath)}`, {
      method: 'PUT',
      headers: { 'Content-Type': contentType },
      body: bytes as BodyInit,
    }, 120000);
    if (!res.ok) {
      const detail = await res.text().catch(() => '');
      throw new Error(detail || 'Não foi possível armazenar o arquivo no Oracle.');
    }
  },

  async ingestLocalFile(filename: string, dataBase64: string, title: string, imageFiles: File[] = []): Promise<ExamIngestResult> {
    if (OFFLINE_DESKTOP) {
      return invokeOffline<ExamIngestResult>('offline_import_file', {
        filename,
        dataBase64,
        title,
      });
    }
    const bytes = base64Bytes(dataBase64);
    let payload: Record<string, unknown> = { filename, title, data_base64: dataBase64 };
    if (/\.pdf$/i.test(filename)) {
      const objectPath = `exams/uploads/${await hexDigest(bytes)}.pdf`;
      await this.uploadMedia(objectPath, bytes, 'application/pdf');
      payload = { filename, title, source_object: objectPath };
    } else if (/\.json$/i.test(filename)) {
      try {
        const parsed = JSON.parse(new TextDecoder().decode(bytes)) as Record<string, unknown>;
        const mediaByName = new Map<string, string>();
        for (const imageFile of imageFiles) {
          const imageBytes = new Uint8Array(await imageFile.arrayBuffer());
          const digest = await hexDigest(imageBytes);
          const extension = imageFile.name.split('.').pop()?.replace(/[^a-z0-9]+/gi, '').toLowerCase() || 'bin';
          const objectPath = `questions/import-assets-${digest}.${extension}`;
          await this.uploadMedia(objectPath, imageBytes, imageFile.type || 'application/octet-stream');
          mediaByName.set(imageFile.name.toLowerCase(), objectPath);
        }
        rewriteQuestionMedia(parsed, mediaByName);
        payload = { filename, title, data_base64: utf8Base64(JSON.stringify(parsed)) };
      } catch {
        // The gateway returns the precise invalid-JSON error for a malformed file.
      }
    }
    const res = await apiFetch(`${API_BASE}/exams/import-local`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error('Não foi possível sincronizar a prova e seus arquivos no Oracle.');
    return res.json();
  },

};
