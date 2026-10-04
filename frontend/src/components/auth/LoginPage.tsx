import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, BookOpen, Check, Library, ListChecks, NotebookPen, ShieldCheck } from 'lucide-react';
import { Navigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { api, OAuthDeepLinkResult } from '../../services/api';
import { supabaseAuthConfigured } from '../../services/supabase';

const DESKTOP_APP = import.meta.env.VITE_DESKTOP_APP === '1';
const OFFLINE_DESKTOP = import.meta.env.VITE_OFFLINE_DESKTOP === '1';
const TAURI_MOBILE_APP = import.meta.env.VITE_TAURI_MOBILE === '1';

const introduction = [
  {
    label: 'Sua biblioteca',
    title: 'Suas provas. Seu espaço.',
    description: 'Reúna as provas que você quer estudar e encontre tudo em uma biblioteca organizada.',
    detail: 'Mais tempo para estudar, menos tempo procurando.',
    icon: Library,
    illustration: 'library',
  },
  {
    label: 'Sua prática',
    title: 'Uma questão de cada vez.',
    description: 'Resolva questões e faça simulados no seu ritmo. Retome seu estudo de onde parou.',
    detail: 'Uma rotina que acompanha você.',
    icon: ListChecks,
    illustration: 'practice',
  },
  {
    label: 'Sua revisão',
    title: 'Cada erro, um novo passo.',
    description: 'Encontre as questões que precisam de atenção no caderno de erros e volte a praticar.',
    detail: 'Transforme a revisão em parte do seu caminho.',
    icon: NotebookPen,
    illustration: 'review',
  },
] as const;

const LOGIN_SLIDE = introduction.length;
const slideLabels = [...introduction.map((slide) => slide.label), 'Entrar na sua conta'];

const StudyIllustration: React.FC<{ variant: string }> = ({ variant }) => (
  <div className={`login-illustration is-${variant}`} aria-hidden="true">
    <div className="login-paper is-back" />
    <div className="login-paper is-front">
      {variant === 'library' ? <BookOpen /> : variant === 'practice' ? <ListChecks /> : variant === 'review' ? <NotebookPen /> : <ShieldCheck />}
      <span className="login-paper-line is-title" />
      <span className="login-paper-line" />
      <span className="login-paper-line is-short" />
      <div className="login-paper-check"><Check /><span /></div>
    </div>
    <span className="login-illustration-caption">Leitura. Prática. Revisão.</span>
  </div>
);

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
  const [activeSlide, setActiveSlide] = useState(() =>
    searchParams.has('error') || searchParams.has('code') ? LOGIN_SLIDE : 0,
  );
  const slidesRef = useRef<HTMLDivElement>(null);
  const activeSlideRef = useRef(activeSlide);
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

  const selectSlide = useCallback((index: number) => {
    const nextSlide = Math.max(0, Math.min(LOGIN_SLIDE, index));
    activeSlideRef.current = nextSlide;
    setActiveSlide(nextSlide);
    const viewport = slidesRef.current;
    viewport?.scrollTo({ left: viewport.clientWidth * nextSlide, behavior: 'auto' });
    requestAnimationFrame(() => {
      viewport?.children.item(nextSlide)?.querySelector<HTMLHeadingElement>('h1')?.focus({ preventScroll: true });
    });
  }, []);

  useEffect(() => {
    const viewport = slidesRef.current;
    if (!viewport) return;
    viewport.scrollTo({ left: viewport.clientWidth * activeSlideRef.current, behavior: 'auto' });
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(() => {
      viewport.scrollTo({ left: viewport.clientWidth * activeSlideRef.current, behavior: 'auto' });
    });
    observer.observe(viewport);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (visibleError) selectSlide(LOGIN_SLIDE);
  }, [selectSlide, visibleError]);

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
      selectSlide(LOGIN_SLIDE);
      setHasLoginAttempt(true);
      setIsRedirecting(true);
      try {
        let currentUser = null;
        if (accessToken && refreshToken) {
          currentUser = await api.exchangeSupabaseOAuthTokens(accessToken, refreshToken);
        } else if (code) {
          currentUser = await api.exchangeSupabaseOAuthCode(code, flowId);
        }
        if (!currentUser) throw new Error('Sua sessão não foi concluída. Tente entrar novamente.');
        await refreshSession();
        if (active) setIsRedirecting(false);
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
  }, [refreshSession, selectSlide]);

  if (status === 'authenticated') {
    return <Navigate to={nextPath} replace />;
  }

  const useSupabaseLogin = supabaseEnabled === true
    && supabaseAuthConfigured
    && !OFFLINE_DESKTOP;
  const loginDisabled = (!useSupabaseLogin && googleEnabled !== true) || isRedirecting;

  const beginLogin = async () => {
    if (loginDisabled) return;
    loginAttemptRef.current = true;
    setHasLoginAttempt(false);
    setDesktopLoginError(null);
    setIsRedirecting(true);
    try {
      if (useSupabaseLogin) await api.beginSupabaseLogin(nextPath);
      else await api.beginGoogleLogin(nextPath);
      // Opening the browser completes this action. The callback has its own
      // loading state; returning after cancellation must allow another attempt.
      if (DESKTOP_APP || TAURI_MOBILE_APP) setIsRedirecting(false);
    } catch (error) {
      setIsRedirecting(false);
      setDesktopLoginError(error instanceof Error ? error.message : 'Não foi possível abrir o login Google.');
    }
  };

  return (
    <main className="login-page" id="main-content">
      <a href="#login-title" className="skip-link" onClick={() => selectSlide(LOGIN_SLIDE)}>Ir para o acesso</a>

      <section className="login-carousel" aria-roledescription="carrossel" aria-label="Bem-vindo ao concurse.io">
        <header className="login-carousel-header">
          <div className="login-brand">
            <img className="brand-symbol brand-logo-image" src="/concurse-icon-64.png" alt="" width={32} height={32} />
            <span>concurse.io</span>
          </div>
          <button type="button" className="login-shortcut" onClick={() => selectSlide(activeSlide === LOGIN_SLIDE ? 0 : LOGIN_SLIDE)}>
            {activeSlide === LOGIN_SLIDE ? 'Ver apresentação' : 'Entrar'}
          </button>
        </header>

        <div
          className="login-slides"
          id="login-slides"
          ref={slidesRef}
          tabIndex={0}
          onScroll={(event) => {
            const viewport = event.currentTarget;
            if (!viewport.clientWidth) return;
            const index = Math.max(0, Math.min(LOGIN_SLIDE, Math.round(viewport.scrollLeft / viewport.clientWidth)));
            activeSlideRef.current = index;
            setActiveSlide(index);
          }}
          onKeyDown={(event) => {
            if (event.altKey || event.ctrlKey || event.metaKey) return;
            if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
              event.preventDefault();
              selectSlide(activeSlide + (event.key === 'ArrowRight' ? 1 : -1));
            }
          }}
        >
          {introduction.map((slide, index) => (
            <div className="login-slide" key={slide.label} role="group" aria-roledescription="página" aria-label={`${index + 1} de ${slideLabels.length}`} aria-hidden={activeSlide !== index} inert={activeSlide !== index}>
              <StudyIllustration variant={slide.illustration} />
              <div className="login-slide-copy">
                <p className="login-kicker"><slide.icon aria-hidden="true" />{slide.label}</p>
                <h1 tabIndex={-1}>{slide.title}</h1>
                <p className="login-description">{slide.description}</p>
                <p className="login-slide-detail">{slide.detail}</p>
              </div>
            </div>
          ))}

          <div className="login-slide" role="group" aria-roledescription="página" aria-label={`4 de ${slideLabels.length}`} aria-hidden={activeSlide !== LOGIN_SLIDE} inert={activeSlide !== LOGIN_SLIDE}>
            <StudyIllustration variant="account" />
            <div className="login-slide-copy login-card">
              <p className="login-kicker"><ShieldCheck aria-hidden="true" />Seu espaço de estudo</p>
              <h1 id="login-title" tabIndex={-1}>Seu estudo continua daqui.</h1>
              <p className="login-description">Entre para acessar sua biblioteca, acompanhar seu progresso e continuar de onde parou.</p>

              {visibleError && (
                <div className="login-alert" role="alert">
                  <strong>Não foi possível entrar.</strong>
                  <span>{visibleError}</span>
                </div>
              )}

              <button type="button" className="google-login-button" disabled={loginDisabled} aria-busy={isRedirecting} onClick={() => { void beginLogin(); }}>
                {isRedirecting ? <span className="ui-loader" aria-hidden="true" /> : <GoogleMark />}
                <span>{googleEnabled === null ? 'Verificando acesso…' : useSupabaseLogin || googleEnabled ? isRedirecting ? 'Conectando ao Google…' : 'Continuar com Google' : 'Google indisponível'}</span>
              </button>

              <div className="login-security-note">
                <ShieldCheck aria-hidden="true" />
                <p>Usamos o Google somente para identificar sua conta. Sua senha não passa pelo concurse.io.</p>
              </div>
            </div>
          </div>
        </div>

        <footer className="login-carousel-footer">
          <div className="login-pagination" aria-label="Páginas da apresentação">
            {slideLabels.map((label, index) => (
              <button type="button" key={label} aria-label={`Ir para a página ${index + 1}: ${label}`} aria-current={activeSlide === index ? 'step' : undefined} aria-controls="login-slides" onClick={() => selectSlide(index)}><span /></button>
            ))}
          </div>
          <p className="login-page-count" aria-live="polite" aria-atomic="true">Página {activeSlide + 1} de {slideLabels.length}</p>
          <div className="login-navigation">
            <button type="button" className="login-back" disabled={activeSlide === 0} onClick={() => selectSlide(activeSlide - 1)}><ArrowLeft aria-hidden="true" />Voltar</button>
            {activeSlide < LOGIN_SLIDE && (
              <button type="button" className="login-next" onClick={() => selectSlide(activeSlide + 1)}>{activeSlide === LOGIN_SLIDE - 1 ? 'Vamos começar' : 'Próximo'}<ArrowRight aria-hidden="true" /></button>
            )}
          </div>
        </footer>
      </section>
    </main>
  );
};
