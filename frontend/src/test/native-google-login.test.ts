import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  openUrl: vi.fn(async (_url: string) => undefined),
  signInWithOAuth: vi.fn(async (_options: unknown) => ({
    data: { url: 'https://project.supabase.co/auth/v1/authorize?provider=google' },
    error: null,
  })),
}));

vi.mock('@supabase/supabase-js', () => ({
  createClient: vi.fn(() => ({ auth: { signInWithOAuth: mocks.signInWithOAuth } })),
}));
vi.mock('@tauri-apps/plugin-opener', () => ({ openUrl: mocks.openUrl }));

describe('login Google no aplicativo mobile', () => {
  beforeEach(() => {
    vi.resetModules();
    vi.stubEnv('VITE_SUPABASE_URL', 'https://project.supabase.co');
    vi.stubEnv('VITE_SUPABASE_PUBLISHABLE_KEY', 'public-test-key');
    vi.stubEnv('VITE_TAURI_MOBILE', '1');
    vi.stubEnv('VITE_DESKTOP_APP', '0');
    vi.stubEnv('VITE_OFFLINE_DESKTOP', '0');
    mocks.openUrl.mockClear();
    mocks.signInWithOAuth.mockClear();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('não abre o navegador quando o domínio do serviço não responde', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    const { api } = await import('../services/api');

    await expect(api.beginSupabaseLogin()).rejects.toThrow('Não foi possível conectar ao serviço de login');
    expect(mocks.signInWithOAuth).not.toHaveBeenCalled();
    expect(mocks.openUrl).not.toHaveBeenCalled();
  });

  it('mantém o retorno para o aplicativo depois de verificar o serviço', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ external: { google: true } })));
    vi.stubGlobal('fetch', fetchMock);
    const { api } = await import('../services/api');

    await api.beginSupabaseLogin('/biblioteca');
    expect(fetchMock).toHaveBeenCalledWith('https://project.supabase.co/auth/v1/settings', expect.objectContaining({ credentials: 'omit' }));
    expect(mocks.signInWithOAuth).toHaveBeenCalledWith(expect.objectContaining({
      provider: 'google',
      options: expect.objectContaining({ redirectTo: 'concurse://oauth/callback', skipBrowserRedirect: true }),
    }));
    expect(mocks.openUrl).toHaveBeenCalledWith('https://project.supabase.co/auth/v1/authorize?provider=google');
  });

  it('explica uma chave de acesso recusada sem abrir o navegador', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 401 })));
    const { api } = await import('../services/api');

    await expect(api.beginSupabaseLogin()).rejects.toThrow('A configuração de acesso deste aplicativo está indisponível');
    expect(mocks.openUrl).not.toHaveBeenCalled();
  });

  it('trata um projeto indisponível sem iniciar a autorização', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 503 })));
    const { api } = await import('../services/api');

    await expect(api.beginSupabaseLogin()).rejects.toThrow('O serviço de login está temporariamente indisponível');
    expect(mocks.signInWithOAuth).not.toHaveBeenCalled();
  });

  it('não oferece autorização quando o provedor Google está desabilitado', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ external: { google: false } }))));
    const { api } = await import('../services/api');

    await expect(api.beginSupabaseLogin()).rejects.toThrow('O login com Google está temporariamente indisponível');
    expect(mocks.openUrl).not.toHaveBeenCalled();
  });

  it('encerra a espera quando a verificação do serviço excede oito segundos', async () => {
    vi.useFakeTimers();
    vi.stubGlobal('fetch', vi.fn((_url: string, options: RequestInit) => new Promise((_resolve, reject) => {
      options.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
    })));
    const { api } = await import('../services/api');

    const result = expect(api.beginSupabaseLogin()).rejects.toThrow('Não foi possível conectar ao serviço de login');
    await vi.advanceTimersByTimeAsync(8000);
    await result;
    expect(mocks.openUrl).not.toHaveBeenCalled();
  });
});
