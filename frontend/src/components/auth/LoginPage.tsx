import React, { useEffect, useMemo, useRef, useState } from 'react';
import { BookOpen, Bookmark, Check, ShieldCheck } from 'lucide-react';
import { Navigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { api, OAuthDeepLinkResult } from '../../services/api';
import { supabaseAuthConfigured } from '../../services/supabase';

const DESKTOP_APP = import.meta.env.VITE_DESKTOP_APP === '1';
const OFFLINE_DESKTOP = import.meta.env.VITE_OFFLINE_DESKTOP === '1';
const TAURI_MOBILE_APP = import.meta.env.VITE_TAURI_MOBILE === '1';

const errorMessages: Record<string, string> = {
  access_denied: 'O acesso pelo Google foi cancelado. Você pode tentar novamente quando quiser.',
  google_not_configured: 'O login com Google ainda não está configurado neste ambiente.',
  google_validation_failed: 'Não foi possível validar sua conta Google. Tente novamente.',
  invalid_state: 'A tentativa de login expirou por segurança. Inicie o acesso novamente.',
  missing_code: 'O Google não concluiu a autorização. Tente novamente.',
  invalid_desktop_callback: 'O retorno local do aplicativo não é válido. Tente abrir o login novamente.',
};

const safeNextPath = (value: string | null) => {
  if (!value || !value.startsWith('/') || value.startsWith('//')) return '/';
  return value;
};

const GoogleMark: React.FC = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true" className="google-mark">
    <path fill="#4285F4" d="M21.6 12.23c0-.71-.06-1.4-.18-2.06H12v3.9h5.38a4.6 4.6 0 0 1-2 3.02v2.53h3.24c1.9-1.75 2.98-4.33 2.98-7.39Z" />
    <path fill="#34A853" d="M12 22c2.7 0 4.98-.9 6.63-2.38l-3.24-2.53c-.9.6-2.05.96-3.39.96-2.61 0-4.82-1.76-5.61-4.13H3.04v2.61A10 10 0 0 0 12 22Z" />
    <path fill="#FBBC05" d="M6.39 13.92A6.02 6.02 0 0 1 6.07 12c0-.67.12-1.32.32-1.92V7.47H3.04A10 10 0 0 0 2 12c0 1.62.39 3.15 1.04 4.53l3.35-2.61Z" />
    <path fill="#EA4335" d="M12 5.95c1.47 0 2.79.5 3.83 1.5l2.87-2.88A9.63 9.63 0 0 0 12 2a10 10 0 0 0-8.96 5.47l3.35 2.61C7.18 7.71 9.39 5.95 12 5.95Z" />
  </svg>
);

export const LoginPage: React.FC = () => {
  const { error: sessionError, refreshSession, status } = useAuth();
  const [searchParams] = useSearchParams();
  const [googleEnabled, setGoogleEnabled] = useState<boolean | null>(null);
  const [supabaseEnabled, setSupabaseEnabled] = useState<boolean | null>(null);
  const [isRedirecting, setIsRedirecting] = useState(false);
  const [desktopLoginError, setDesktopLoginError] = useState<string | null>(null);
  const [hasLoginAttempt, setHasLoginAttempt] = useState(false);
  const loginAttemptRef = useRef(false);
  const nextPath = safeNextPath(searchParams.get('next'));
  const errorCode = searchParams.get('error') || '';
  const visibleError = useMemo(
    () => errorMessages[errorCode] || desktopLoginError || (hasLoginAttempt ? sessionError : null),
    [desktopLoginError, errorCode, hasLoginAttempt, sessionError],
  );

  useEffect(() => {
    let active = true;
    void api.getAuthConfig()
      .then((config) => {
        if (active) {
          setGoogleEnabled(config.google_enabled);
          setSupabaseEnabled(config.supabase_enabled === true);
        }
      })
      .catch(() => {
        if (active) {
          setGoogleEnabled(false);
          setSupabaseEnabled(false);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if ((!DESKTOP_APP && !TAURI_MOBILE_APP) || OFFLINE_DESKTOP) return;
    let active = true;
    let stopMobileListener: (() => void) | undefined;
    const completeLogin = async ({ code, error, errorDescription, flowId, accessToken, refreshToken }: OAuthDeepLinkResult) => {
      if (!active) return;
      if (error) {
        api.clearPendingSupabaseOAuth();
        setIsRedirecting(false);
        setDesktopLoginError(
          errorMessages[error]
            || errorDescription
            || 'O login Google não foi concluído.',
        );
        return;
      }
      if (!code && !(accessToken && refreshToken)) return;
      try {
        if (accessToken && refreshToken) {
          await api.exchangeSupabaseOAuthTokens(accessToken, refreshToken);
        } else if (code) {
          await api.exchangeSupabaseOAuthCode(code, flowId);
        }
        await refreshSession();
      } catch (error) {
        if (active) {
          setIsRedirecting(false);
          setDesktopLoginError(error instanceof Error ? error.message : 'Não foi possível concluir o login Google.');
        }
      }
    };
    void api.listenMobileOAuth((result) => { void completeLogin(result); })
      .then((stop) => {
        if (!active) {
          stop();
          return;
        }
        stopMobileListener = stop;
      })
      .catch((error) => {
        if (active && loginAttemptRef.current) {
          setIsRedirecting(false);
          setDesktopLoginError(error instanceof Error ? error.message : 'Não foi possível receber o retorno do Google.');
        }
      });
    return () => {
      active = false;
      stopMobileListener?.();
    };
  }, [refreshSession]);

  if (status === 'authenticated') {
    return <Navigate to={nextPath} replace />;
  }

  const useSupabaseLogin = supabaseEnabled === true
    && supabaseAuthConfigured
    && !OFFLINE_DESKTOP;
  const loginDisabled = (!useSupabaseLogin && googleEnabled !== true) || isRedirecting;

  return (
    <main className="login-page" id="main-content">
      <a href="#login-title" className="skip-link">Ir para o acesso</a>

      <div className="login-layout">
        <section className="login-entry" aria-labelledby="login-title">
          <div className="login-card">
            <div className="login-mobile-brand" aria-hidden="true">
              <img className="brand-symbol brand-logo-image" src="/concurse-icon-64.png" alt="" width={28} height={28} />
              <span>concurse.io</span>
            </div>

            <p className="login-kicker">Seu espaço de estudo</p>
            <h1 id="login-title">Seu estudo continua daqui.</h1>
            <p className="login-description">
              Entre para acessar sua biblioteca, acompanhar seu progresso e continuar exatamente de onde parou.
            </p>

            {visibleError && (
              <div className="login-alert" role="alert">
                <strong>Não foi possível entrar.</strong>
                <span>{visibleError}</span>
              </div>
            )}

            <a
              href={useSupabaseLogin ? '#' : api.getGoogleLoginUrl(nextPath)}
              className={`google-login-button${loginDisabled ? ' is-disabled' : ''}`}
              aria-disabled={loginDisabled}
              aria-busy={isRedirecting}
              onClick={(event) => {
                if (loginDisabled) {
                  event.preventDefault();
                  return;
                }
                loginAttemptRef.current = true;
                setHasLoginAttempt(true);
                setDesktopLoginError(null);
                setIsRedirecting(true);
                if (useSupabaseLogin) {
                  event.preventDefault();
                  void api.beginSupabaseLogin(nextPath).catch((error) => {
                    setIsRedirecting(false);
                    setDesktopLoginError(error instanceof Error ? error.message : 'Não foi possível abrir o login Supabase.');
                  });
                } else if (DESKTOP_APP || TAURI_MOBILE_APP) {
                  event.preventDefault();
                  void api.beginGoogleLogin(nextPath).catch((error) => {
                    setIsRedirecting(false);
                    setDesktopLoginError(error instanceof Error ? error.message : 'Não foi possível abrir o login Google.');
                  });
                }
              }}
            >
              {isRedirecting ? (
                <span className="ui-loader" aria-hidden="true" />
              ) : (
                <GoogleMark />
              )}
              <span>
                {googleEnabled === null
                  ? 'Verificando acesso…'
                  : useSupabaseLogin || googleEnabled
                    ? isRedirecting ? 'Abrindo o Google…' : 'Continuar com Google'
                    : 'Google indisponível'}
              </span>
            </a>

            <div className="login-security-note">
              <ShieldCheck aria-hidden="true" />
              <p>Usamos o Google somente para identificar sua conta. Sua senha não passa pelo concurse.io.</p>
            </div>
          </div>

          <p className="login-footnote">Leitura, prática e revisão em um só lugar.</p>
        </section>

        <aside className="login-story" aria-label="Benefícios da sua conta">
          <div className="login-brand">
            <img className="login-brand-symbol brand-logo-image" src="/concurse-icon-64.png" alt="" width={30} height={30} />
            <span>concurse.io</span>
          </div>

          <div className="login-story-copy">
            <BookOpen aria-hidden="true" />
            <p className="login-story-eyebrow">Feito para estudar com calma</p>
            <p className="login-story-title">Menos distração.<br />Mais constância.</p>
            <ul>
              <li><Check aria-hidden="true" /> Provas organizadas na sua biblioteca</li>
              <li><Check aria-hidden="true" /> Progresso salvo entre sessões</li>
              <li><Check aria-hidden="true" /> Erros reunidos para revisar depois</li>
            </ul>
          </div>

          <div className="login-reading-preview" aria-hidden="true">
            <div className="login-preview-topline">
              <span>Última leitura</span>
              <Bookmark />
            </div>
            <div className="login-preview-title" />
            <div className="login-preview-line is-long" />
            <div className="login-preview-line" />
            <div className="login-preview-line is-short" />
            <div className="login-preview-progress">
              <span style={{ width: '64%' }} />
            </div>
            <small>64% concluído</small>
          </div>
        </aside>
      </div>
    </main>
  );
};
