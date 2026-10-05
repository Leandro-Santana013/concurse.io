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
  supabaseNativeOAuth,
  supabaseAuthConfigured,
  supabaseRedirectUrl,
  assertGoogleLoginAvailable,
} from './supabase';

const SUPABASE_URL = (import.meta.env.VITE_SUPABASE_URL || '').trim().replace(/\/+$/, '');
const SUPABASE_FUNCTIONS_URL = (import.meta.env.VITE_SUPABASE_FUNCTIONS_URL || `${SUPABASE_URL}/functions/v1`).replace(/\/+$/, '');
export const OFFLINE_DESKTOP = import.meta.env.VITE_OFFLINE_DESKTOP === '1';
export const DESKTOP_APP = import.meta.env.VITE_DESKTOP_APP === '1';
export const LOCAL_ENGINE = import.meta.env.VITE_LOCAL_ENGINE === '1';
export const TAURI_MOBILE_APP = import.meta.env.VITE_TAURI_MOBILE === '1';
export const MOBILE_OAUTH_RETURN = 'concurse://oauth/callback';
const SUPABASE_OAUTH_FLOW_KEY = 'concurse.supabase.oauth.flow.v1';

export type OAuthDeepLinkResult = {
  code?: string;
  flowId?: string;
  accessToken?: string;
  refreshToken?: string;
  error?: string;
  errorDescription?: string;
};

const DESKTOP_SESSION_KEY = 'concurse.desktop.session.v1';
const API_REQUEST_TIMEOUT_MS = 8000;
const LOCAL_API_BASE = (import.meta.env.VITE_LOCAL_API_BASE || 'http://127.0.0.1:45873/api/v1').replace(/\/+$/, '');
const localRemoteSourceObjects = new Map<number, string>();
const localPublicationPromises = new Map<number, Promise<ExamIngestResult>>();
const localPublishedExams = new Map<number, { ownerId: string; result: ExamIngestResult }>();
let engineSessionSubject = '';
let engineSessionPromise: Promise<void> | null = null;
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

export const localApiUrl = (path: string): string => {
  if (!path || /^[a-z][a-z\d+.-]*:\/\//i.test(path)) return path;
  const normalized = path.startsWith('/') ? path : `/${path}`;
  if (normalized.startsWith('/api/v1')) return `${LOCAL_API_BASE}${normalized.slice('/api/v1'.length)}`;
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

const localApiFetch = async (input: RequestInfo | URL, init: RequestInit = {}, timeoutMs = API_REQUEST_TIMEOUT_MS) => {
  if (LOCAL_ENGINE) await ensureLocalEngineSession();
  const headers = new Headers(init.headers);
  if (!headers.has('Authorization') && desktopSessionToken) {
    headers.set('Authorization', `Bearer ${desktopSessionToken}`);
  }
  return apiFetch(input, { ...init, headers }, timeoutMs);
};

const ensureLocalEngineSession = async (): Promise<void> => {
  const session = supabase ? (await supabase.auth.getSession()).data.session : null;
  if (!session?.access_token || !session.user?.id) throw new AuthRequiredError();
  if (desktopSessionToken && engineSessionSubject === session.user.id) return;
  if (engineSessionPromise) return engineSessionPromise;
  engineSessionPromise = (async () => {
    setDesktopSessionToken('');
    engineSessionSubject = '';
    // The native engine starts on its own thread while the welcome screen is
    // usable. Wait for readiness here, before a processing action needs it.
    const deadline = Date.now() + 45000;
    let ready = false;
    while (Date.now() < deadline) {
      try {
        const response = await apiFetch(`${LOCAL_API_BASE.replace(/\/api\/v1$/, '')}/health`, {}, 1200);
        if (response.ok) { ready = true; break; }
      } catch { /* The engine may still be loading the first time. */ }
      await new Promise(resolve => globalThis.setTimeout(resolve, 300));
    }
    if (!ready) throw new Error('O processamento no dispositivo ainda não iniciou. Feche e abra o aplicativo para tentar novamente.');
    const response = await apiFetch(localApiUrl('/api/v1/auth/supabase/exchange'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${session.access_token}` },
      body: JSON.stringify({ access_token: session.access_token }),
    }, 30000);
    if (response.status === 401) throw new AuthRequiredError();
    if (response.status === 503) {
      throw new Error('Não foi possível conectar ao serviço de login. Confira sua conexão e tente a busca novamente.');
    }
    if (!response.ok) throw new Error('Não foi possível preparar o processamento para sua conta.');
    const payload = await response.json() as { session_token?: string };
    if (!payload.session_token) throw new Error('O processamento retornou uma sessão inválida.');
    const currentSession = supabase ? (await supabase.auth.getSession()).data.session : null;
    if (currentSession?.user?.id !== session.user.id) throw new AuthRequiredError();
    setDesktopSessionToken(payload.session_token);
    engineSessionSubject = session.user.id;
  })().finally(() => { engineSessionPromise = null; });
  return engineSessionPromise;
};

const binaryToDataUrl = (bytes: Uint8Array, contentType: string): string => {
  let binary = '';
  const chunkSize = 0x8000;
  for (let index = 0; index < bytes.length; index += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize));
  }
  return `data:${contentType || 'application/octet-stream'};base64,${btoa(binary)}`;
};

const fileToDataUrl = async (file: File): Promise<string> => binaryToDataUrl(
  new Uint8Array(await file.arrayBuffer()),
  file.type || 'application/octet-stream',
);

const localMediaUrl = (examId: number, value: string): string => {
  if (/^\/api\/v1\//i.test(value)) return localApiUrl(value);
  if (/^\/static\/images\/questions\//i.test(value)) {
    const filename = value.split('/').pop() || '';
    return localApiUrl(`/api/v1/exams/${examId}/media/${encodeURIComponent(filename)}`);
  }
  return value;
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
    if (LOCAL_ENGINE) return { google_enabled: supabaseAuthConfigured, supabase_enabled: supabaseAuthConfigured };
    return { google_enabled: supabaseAuthConfigured, supabase_enabled: supabaseAuthConfigured };
  },

  async exchangeSupabaseSession(): Promise<AuthUser | null> {
    if (!supabaseAuthConfigured || !supabase) return null;
    const { data, error } = await supabase.auth.getSession();
    if (error) throw new Error('Falha ao ler a sessão do Supabase.');
    const accessToken = data.session?.access_token;
    if (!accessToken) return null;

    // The central user ID owns the library and attempts. A processing database
    // ID is private to the engine and must never become the displayed identity.
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
    const oauthClient = nativeApp ? supabaseNativeOAuth : supabase;
    if (!oauthClient) throw new Error('O login Supabase não está configurado neste build.');
    // signInWithOAuth constructs its URL locally. Check the service before
    // handing it to the system browser so DNS failures remain recoverable here.
    await assertGoogleLoginAvailable();
    const { data, error } = await oauthClient.auth.signInWithOAuth({
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
    // O desktop usa o fluxo implícito no navegador externo, portanto não há
    // verifier PKCE para transportar entre o navegador e a WebView.
    if (nativeApp) setPendingSupabaseOAuthFlow(null);
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

  async exchangeSupabaseOAuthTokens(accessToken: string, refreshToken: string): Promise<AuthUser | null> {
    if (!supabase) throw new Error('O login Supabase não está configurado neste build.');
    const { error } = await supabase.auth.setSession({
      access_token: accessToken,
      refresh_token: refreshToken,
    });
    if (error) throw new Error(`Não foi possível concluir o login Google no aplicativo: ${error.message}`);
    return this.exchangeSupabaseSession();
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
           const fragment = new URLSearchParams(parsed.hash.replace(/^#/, ''));
           const getParam = (name: string) => parsed.searchParams.get(name) || fragment.get(name);
           const error = getParam('error');
           const errorDescription = getParam('error_description') || undefined;
           const code = parsed.searchParams.get('code');
           const flowId = parsed.searchParams.get('sb_flow_id') || undefined;
           const accessToken = getParam('access_token') || undefined;
           const refreshToken = getParam('refresh_token') || undefined;
           if (error) onResult({ error, errorDescription });
           else if (accessToken && refreshToken) onResult({ accessToken, refreshToken });
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
    engineSessionSubject = '';
    localRemoteSourceObjects.clear();
    localPublishedExams.clear();
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
      if (DESKTOP_APP && OFFLINE_DESKTOP && isTransportFailure(error)) {
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
      if (DESKTOP_APP && OFFLINE_DESKTOP && isTransportFailure(error)) {
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
      if (DESKTOP_APP && OFFLINE_DESKTOP && isTransportFailure(error)) {
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
    const res = LOCAL_ENGINE
      ? await localApiFetch(`${LOCAL_API_BASE}/search?${params.toString()}`, {}, 120000)
      : await apiFetch(`${API_BASE}/search?${params.toString()}`);
    if (!res.ok) throw new Error('Falha ao realizar busca de provas');
    const data: unknown = await res.json();
    const result: SearchResultsPage = Array.isArray(data)
      ? {
        items: data as SearchResultItem[],
        page,
        page_size: pageSize,
        total: data.length,
        total_pages: data.length > 0 ? Math.ceil(data.length / pageSize) : 0,
        has_previous: page > 1,
        has_next: data.length === pageSize,
      } : data as SearchResultsPage;
    if (LOCAL_ENGINE && result.items.length) {
      const catalog = await apiFetch(`${API_BASE}/search/catalog`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, items: result.items.slice(0, 50) }),
      }, 30000);
      if (!catalog.ok) throw new Error('A busca terminou, mas os resultados não puderam ser sincronizados. Tente novamente.');
      const reusable = await this.lookupProcessedExams(result.items.map(item => item.url));
      result.items = result.items.map(item => {
        const existing = reusable[item.url];
        return { ...item, id: existing?.id || null, status: existing ? 'Aprovada' : 'Pendente', reuse_available: Boolean(existing) };
      });
    }
    return result;
  },

  async lookupProcessedExams(urls: string[]): Promise<Record<string, { id: number; title: string }>> {
    const response = await apiFetch(`${API_BASE}/exams/reuse-lookup`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ urls }),
    }, 30000);
    if (!response.ok) throw new Error('Não foi possível verificar as provas já processadas na biblioteca central.');
    return response.json();
  },

  async ingestExam(url: string, title: string, gabaritoUrl?: string): Promise<ExamIngestResult> {
    if (OFFLINE_DESKTOP) {
      throw new Error('No modo offline escolha um arquivo local em vez de um link.');
    }
    if (LOCAL_ENGINE) {
      const existing = (await this.lookupProcessedExams([url]))[url];
      if (existing) return { ...(await this.claimProcessedExam(existing.id)), processing_location: 'cloud' };
    }
    const fetcher = LOCAL_ENGINE ? localApiFetch : apiFetch;
    const res = await fetcher(`${LOCAL_ENGINE ? LOCAL_API_BASE : API_BASE}/exams/ingest`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, title, gabarito_url: gabaritoUrl }),
    });
    if (!res.ok) throw new Error('Falha ao iniciar processamento da prova');
    const result = await res.json() as ExamIngestResult;
    return { ...result, processing_location: LOCAL_ENGINE ? 'device' : 'cloud' };
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
      if (DESKTOP_APP && OFFLINE_DESKTOP && isTransportFailure(error)) {
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
    if (TAURI_MOBILE_APP && LOCAL_ENGINE) {
      const response = await localApiFetch(`${LOCAL_API_BASE}/processing/jobs`);
      if (!response.ok) throw new Error('Não foi possível acompanhar as importações neste dispositivo.');
      const jobs = await response.json() as ActiveDownload[];
      const pending: ActiveDownload[] = [];
      for (const job of jobs) {
        if (job.status === 'Aprovada' && job.progress >= 100) {
          try { await this.syncLocalExam(job.id); }
          catch { pending.push({ ...job, status: 'Aguardando envio à biblioteca' }); }
        } else pending.push(job);
      }
      return pending;
    }
    const res = LOCAL_ENGINE
      ? await localApiFetch(`${LOCAL_API_BASE}/downloads/active`)
      : await apiFetch(`${API_BASE}/downloads/active`);
    if (!res.ok) return [];
    return res.json();
  },

  async getExamProgress(examId: number): Promise<ExamProgress> {
    if (OFFLINE_DESKTOP) return { status: 'Aprovada', progress: 100 };
    const res = await apiFetch(`${API_BASE}/exams/${examId}/progress`);
    if (!res.ok) throw new Error('Falha ao consultar o processamento da prova');
    return res.json();
  },

  async uploadMedia(objectPath: string, bytes: Uint8Array, contentType: string, token?: string): Promise<void> {
    if (OFFLINE_DESKTOP) throw new Error('O envio para o Oracle exige uma sessão Supabase online.');
    const res = await apiFetch(`${SUPABASE_FUNCTIONS_URL}/media-gateway?path=${encodeURIComponent(objectPath)}`, {
      method: 'PUT',
      headers: { 'Content-Type': contentType, ...(token ? { Authorization: `Bearer ${token}` } : {}) },
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
    if (LOCAL_ENGINE) {
      const bytes = base64Bytes(dataBase64);
      let localPayload: Record<string, unknown> = { filename, title, data_base64: dataBase64 };

      if (/\.json$/i.test(filename)) {
        try {
          const parsed = JSON.parse(new TextDecoder().decode(bytes)) as Record<string, unknown>;
          const mediaByName = new Map<string, string>();
          for (const imageFile of imageFiles) {
            mediaByName.set(imageFile.name.toLowerCase(), await fileToDataUrl(imageFile));
          }
          rewriteQuestionMedia(parsed, mediaByName);
          localPayload = { filename, title, data_base64: utf8Base64(JSON.stringify(parsed)) };
        } catch {
          // O endpoint local retorna a mensagem precisa para JSON invÃ¡lido.
        }
      }
      const localImportPath = /\.json$/i.test(filename) ? '/exams/import-local' : '/exams/import-file';
      const res = await localApiFetch(localApiUrl(`/api/v1${localImportPath}`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(localPayload),
      });
      if (!res.ok) {
        let detail = '';
        try {
          const payload = await res.json() as { detail?: string; error?: string };
          detail = payload.detail || payload.error || '';
        } catch {
          // Mantém a mensagem segura abaixo quando a resposta não é JSON.
        }
        throw new Error(detail || 'Não foi possível iniciar a extração local da prova.');
      }
      const result = await res.json() as ExamIngestResult;
      return { ...result, processing_location: 'device' };
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

  async getLocalExamProgress(examId: number): Promise<ExamProgress> {
    const res = await localApiFetch(localApiUrl(`/api/v1/exams/${examId}/progress`));
    if (!res.ok) throw new Error('Falha ao consultar a extração da prova no dispositivo.');
    return res.json();
  },

  async syncLocalExam(examId: number): Promise<ExamIngestResult> {
    const owner = supabase ? (await supabase.auth.getSession()).data.session?.user?.id : null;
    const published = localPublishedExams.get(examId);
    if (owner && published?.ownerId === owner) {
      await this.confirmLocalPublication(examId, published.result.exam_id);
      return published.result;
    }
    const existing = localPublicationPromises.get(examId);
    if (existing) return existing;
    const publication = this.publishLocalExam(examId).then(result => {
      if (owner) localPublishedExams.set(examId, { ownerId: owner, result });
      return result;
    })
      .finally(() => localPublicationPromises.delete(examId));
    localPublicationPromises.set(examId, publication);
    return publication;
  },

  async confirmLocalPublication(examId: number, remoteExamId: number): Promise<void> {
    if (!TAURI_MOBILE_APP) return;
    // The server import key also prevents duplicates after an app restart.
    // A lost local receipt is retried when the processing queue is refreshed.
    await localApiFetch(`${LOCAL_API_BASE}/processing/jobs/${examId}/published`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ remote_exam_id: remoteExamId }),
    }).catch(() => undefined);
  },

  async publishLocalExam(examId: number): Promise<ExamIngestResult> {
    if (!LOCAL_ENGINE) throw new Error('O processamento no dispositivo não está habilitado nesta versão.');
    const ownerSession = supabase ? (await supabase.auth.getSession()).data.session : null;
    if (!ownerSession?.access_token || !ownerSession.user?.id) throw new AuthRequiredError();
    const requireSameOwner = async () => {
      const current = supabase ? (await supabase.auth.getSession()).data.session : null;
      if (current?.user?.id !== ownerSession.user.id) throw new AuthRequiredError();
    };
    const storeMedia = async (objectPath: string, bytes: Uint8Array, contentType: string) => {
      await requireSameOwner();
      await this.uploadMedia(objectPath, bytes, contentType, ownerSession.access_token);
    };
    const localResponse = await localApiFetch(localApiUrl(`/api/v1/exams/${examId}`), {}, 30000);
    if (!localResponse.ok) throw new Error('Não foi possível ler a prova extraída neste dispositivo.');
    const localExam = await localResponse.json() as ExamDetail;

    const toRemoteMedia = async (value: string): Promise<string> => {
      if (!value || (/^https?:\/\//i.test(value) && !value.startsWith(LOCAL_API_BASE))) return value;
      let bytes: Uint8Array;
      let contentType: string;
      const embedded = value.match(/^data:([^;,]+)?;base64,(.*)$/s);
      if (embedded) {
        bytes = base64Bytes(embedded[2]);
        contentType = embedded[1] || 'application/octet-stream';
      } else {
        const response = await localApiFetch(localMediaUrl(examId, value), {}, 30000);
        if (!response.ok) throw new Error('Não foi possível ler uma imagem extraída.');
        bytes = new Uint8Array(await response.arrayBuffer());
        contentType = response.headers.get('content-type') || 'application/octet-stream';
      }
      const extension = contentType.split('/')[1]?.replace(/[^a-z0-9]/gi, '') || 'bin';
      const objectPath = `questions/import-assets-${await hexDigest(bytes)}.${extension}`;
      await storeMedia(objectPath, bytes, contentType);
      return objectPath;
    };
    // Upload one question at a time to keep large scanned exams within a
    // phone's memory budget and avoid putting all images into one JSON body.
    const questions = [];
    for (const question of localExam.questions || []) {
      const { id: _workingQuestionId, ...content } = question;
      questions.push({
      ...content,
      images: question.images ? await Promise.all(question.images.map(toRemoteMedia)) : question.images,
      option_images: question.option_images
        ? Object.fromEntries(await Promise.all(Object.entries(question.option_images).map(async ([key, values]) => [
            key,
            await Promise.all(values.map(toRemoteMedia)),
          ])))
        : question.option_images,
      });
    }
    const storePdf = async (kind: 'prova' | 'gabarito'): Promise<string | undefined> => {
      const response = await localApiFetch(`${LOCAL_API_BASE}/exams/${examId}/pdf/${kind}`, {}, 30000);
      if (response.status === 404) return undefined;
      if (!response.ok) throw new Error('Não foi possível ler o PDF processado.');
      const bytes = new Uint8Array(await response.arrayBuffer());
      const objectPath = `exams/uploads/${await hexDigest(bytes)}.pdf`;
      await storeMedia(objectPath, bytes, 'application/pdf');
      return objectPath;
    };
    const sourceObject = localRemoteSourceObjects.get(examId) || await storePdf('prova');
    const answerKeyObject = await storePdf('gabarito');
    const document = { title: localExam.title, questions };

    const payload = {
      filename: `processed-${examId}.json`,
      title: localExam.title,
      source_object: sourceObject,
      source_url: /^https?:\/\//i.test(localExam.source_url || '') ? localExam.source_url : undefined,
      gabarito_object: answerKeyObject,
      gabarito_url: localExam.gabarito_url || null,
      data_base64: utf8Base64(JSON.stringify(document)),
      import_key: await hexDigest(new TextEncoder().encode(JSON.stringify(document))),
    };
    await requireSameOwner();
    const remoteResponse = await apiFetch(`${API_BASE}/exams/import-local`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${ownerSession.access_token}` },
      body: JSON.stringify(payload),
    }, 120000);
    if (!remoteResponse.ok) {
      const detail = await remoteResponse.text().catch(() => '');
      throw new Error(detail || 'Não foi possível enviar a prova extraída para o Supabase.');
    }
    localRemoteSourceObjects.delete(examId);
    const result = await remoteResponse.json() as ExamIngestResult;
    await requireSameOwner();
    await this.confirmLocalPublication(examId, result.exam_id);
    if (typeof window !== 'undefined') window.dispatchEvent(new Event('concurse:library-updated'));
    return { ...result, processing_location: 'cloud' };
  },

};
