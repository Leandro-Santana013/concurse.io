import { createClient, type SupabaseClient } from '@supabase/supabase-js';

const SUPABASE_URL = (import.meta.env.VITE_SUPABASE_URL || '').trim().replace(/\/+$/, '');
const SUPABASE_PUBLISHABLE_KEY = (import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY || '').trim();

export const supabaseAuthConfigured = Boolean(SUPABASE_URL && SUPABASE_PUBLISHABLE_KEY);

export const supabase: SupabaseClient | null = supabaseAuthConfigured
  ? createClient(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, {
      auth: {
        flowType: 'pkce',
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
      },
    })
  : null;

// O desktop abre o provedor no navegador do sistema e recebe o retorno por
// deep link. Nesse cenário não existe garantia de que o storage da WebView
// preserve o verifier PKCE criado antes de abrir o navegador externo. O fluxo
// implícito nativo transporta os tokens no retorno e evita essa dependência.
export const supabaseNativeOAuth: SupabaseClient | null = supabaseAuthConfigured
  ? createClient(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, {
      auth: {
        flowType: 'implicit',
        persistSession: false,
        autoRefreshToken: false,
        detectSessionInUrl: false,
        storageKey: 'concurse.desktop.oauth.native',
      },
    })
  : null;

export const supabaseRedirectUrl = (nextPath = '/'): string => {
  if (typeof window === 'undefined') return '';
  const safePath = nextPath.startsWith('/') && !nextPath.startsWith('//') ? nextPath : '/';
  const redirect = new URL('/login', window.location.origin);
  if (safePath !== '/') redirect.searchParams.set('next', safePath);
  return redirect.toString();
};
