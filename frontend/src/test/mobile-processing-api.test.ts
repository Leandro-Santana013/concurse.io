import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  getSession: vi.fn(async () => ({ data: { session: { access_token: 'supabase-token', user: { id: 'account-one' } } }, error: null })),
}));
vi.mock('../services/supabase', () => ({
  supabase: { auth: { getSession: mocks.getSession, signOut: vi.fn() } },
  supabaseNativeOAuth: null, supabaseAuthConfigured: true, supabaseRedirectUrl: vi.fn(), assertGoogleLoginAvailable: vi.fn(),
}));

describe('processamento embarcado no mobile', () => {
  beforeEach(() => {
    vi.resetModules();
    localStorage.clear();
    vi.stubEnv('VITE_SUPABASE_URL', 'https://project.supabase.co');
    vi.stubEnv('VITE_SUPABASE_FUNCTIONS_URL', 'https://project.supabase.co/functions/v1');
    vi.stubEnv('VITE_LOCAL_ENGINE', '1');
    vi.stubEnv('VITE_TAURI_MOBILE', '1');
    vi.stubEnv('VITE_DESKTOP_APP', '0');
    vi.stubEnv('VITE_OFFLINE_DESKTOP', '0');
    mocks.getSession.mockResolvedValue({ data: { session: { access_token: 'supabase-token', user: { id: 'account-one' } } }, error: null });
  });
  afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); });

  it('mantém a identidade central mesmo quando a conta de processamento tem outro ID', async () => {
    const fetchMock = vi.fn(async (_url: string) => new Response(JSON.stringify({ id: 11, name: 'Leandro', is_authenticated: true })));
    vi.stubGlobal('fetch', fetchMock);
    const { api } = await import('../services/api');
    expect(await api.exchangeSupabaseSession()).toMatchObject({ id: 11 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0][0])).toContain('app-gateway/api/v1/auth/me');
  });

  it('reutiliza a prova central e evita uma segunda extração no aparelho', async () => {
    const fetchMock = vi.fn(async (url: string) => new Response(JSON.stringify(url.includes('reuse-lookup')
      ? { 'https://example.com/prova.pdf': { id: 77, title: 'Prova' } }
      : { exam_id: 77, status: 'Aprovada', progress: 100, reused: true })));
    vi.stubGlobal('fetch', fetchMock);
    const { api } = await import('../services/api');
    expect(await api.ingestExam('https://example.com/prova.pdf', 'Prova')).toMatchObject({ exam_id: 77, processing_location: 'cloud', reused: true });
    expect(fetchMock.mock.calls.map(([url]) => url).some(url => url.includes('127.0.0.1'))).toBe(false);
  });

  it('inicia a extração local e acompanha o progresso com a sessão do motor', async () => {
    const fetchMock = vi.fn(async (url: string, options?: RequestInit) => {
      if (url.includes('reuse-lookup')) return new Response('{}');
      if (url.endsWith('/health')) return new Response('{"status":"ok"}');
      if (url.endsWith('/auth/supabase/exchange')) return new Response('{"session_token":"engine-token","user":{"id":2}}');
      expect(new Headers(options?.headers).get('Authorization')).toBe('Bearer engine-token');
      if (url.endsWith('/exams/ingest')) {
        expect(JSON.parse(String(options?.body))).toMatchObject({ gabarito_url: 'https://example.com/gabarito.pdf' });
        return new Response('{"exam_id":42,"status":"Processando","progress":5}');
      }
      return new Response('{"status":"Processando","progress":25}');
    });
    vi.stubGlobal('fetch', fetchMock);
    const { api } = await import('../services/api');
    expect(await api.ingestExam('https://example.com/prova.pdf', 'Prova', 'https://example.com/gabarito.pdf')).toMatchObject({ exam_id: 42, processing_location: 'device' });
    expect(await api.getLocalExamProgress(42)).toMatchObject({ progress: 25 });
    expect(fetchMock.mock.calls.filter(([url]) => url.endsWith('/auth/supabase/exchange'))).toHaveLength(1);
  });

  it('permite repetir a busca após indisponibilidade do login sem tratar a conta como expirada', async () => {
    let exchangeAttempts = 0;
    const fetchMock = vi.fn(async (url: string) => {
      if (url.endsWith('/health')) return new Response('{}');
      if (url.endsWith('/auth/supabase/exchange')) {
        exchangeAttempts += 1;
        return exchangeAttempts === 1
          ? new Response('{"detail":"Serviço indisponível"}', { status: 503 })
          : new Response('{"session_token":"engine-token"}');
      }
      if (url.includes('/search?')) return new Response('{"items":[],"total":0}');
      return new Response('{}');
    });
    vi.stubGlobal('fetch', fetchMock);
    const { api, AuthRequiredError } = await import('../services/api');
    const failed = api.searchExams('Fiscal de Postura IDCAP');
    await expect(failed).rejects.toThrow('Confira sua conexão');
    await expect(failed).rejects.not.toBeInstanceOf(AuthRequiredError);
    await expect(api.searchExams('Fiscal de Postura IDCAP')).resolves.toBeDefined();
    expect(exchangeAttempts).toBe(2);
  });

  it('envia PDF, gabarito e imagens uma vez e conserva apenas IDs centrais na biblioteca', async () => {
    const fetchMock = vi.fn(async (url: string, options?: RequestInit) => {
      if (url.endsWith('/health')) return new Response('{}');
      if (url.endsWith('/auth/supabase/exchange')) return new Response('{"session_token":"engine-token"}');
      if (url.endsWith('/exams/42')) return new Response(JSON.stringify({ id: 42, title: 'Prova', source_url: 'https://example.com/prova.pdf', questions: Array.from({ length: 5 }, (_, index) => ({
        id: index + 1, numero_questao: String(index + 1), statement: 'Questão de prova', options: { A: 'Sim', B: 'Não' }, correct_answer: 'B', images: ['data:image/png;base64,AQID'],
      })) }));
      if (url.includes('/pdf/')) return new Response(new Uint8Array([37, 80, 68, 70]));
      if (url.includes('media-gateway')) return new Response('{}');
      if (url.endsWith('/exams/import-local')) {
        const payload = JSON.parse(String(options?.body));
        expect(payload.source_object).toMatch(/^exams\/uploads\/.+\.pdf$/);
        expect(payload.gabarito_object).toMatch(/^exams\/uploads\/.+\.pdf$/);
        expect(payload.source_url).toBe('https://example.com/prova.pdf');
        expect(payload.import_key).toMatch(/^[a-f0-9]{64}$/);
        const bytes = Uint8Array.from(atob(payload.data_base64), character => character.charCodeAt(0));
        const document = JSON.parse(new TextDecoder().decode(bytes));
        expect(document.questions).toHaveLength(5);
        expect(document.questions[0].id).toBeUndefined();
        expect(document.questions[0].images[0]).toMatch(/^questions\/import-assets-/);
        expect(new Headers(options?.headers).get('Authorization')).toBe('Bearer supabase-token');
        return new Response('{"exam_id":97,"status":"Aprovada","progress":100}');
      }
      if (url.endsWith('/published')) {
        expect(JSON.parse(String(options?.body))).toEqual({ remote_exam_id: 97 });
        return new Response('{}');
      }
      throw new Error(`Unexpected route: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);
    const { api } = await import('../services/api');
    const results = await Promise.all([api.syncLocalExam(42), api.syncLocalExam(42)]);
    expect(results[0].exam_id).toBe(97);
    expect(await api.syncLocalExam(42)).toMatchObject({ exam_id: 97, processing_location: 'cloud' });
    expect(fetchMock.mock.calls.filter(([url]) => url.endsWith('/exams/import-local'))).toHaveLength(1);
  });
});
