import React, { Suspense, useEffect, useRef, useState } from 'react';
import {
  Navigate,
  Outlet,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
} from 'react-router-dom';
import { DirectIngestModal } from './components/dashboard/DirectIngestModal';
import { LoginPage } from './components/auth/LoginPage';
import { Navbar } from './components/layout/Navbar';
import { ProgressLayout } from './components/layout/ProgressLayout';
import { Sidebar } from './components/layout/Sidebar';
import { ToastViewport } from './components/ui/ToastViewport';
import { useExam } from './context/ExamContext';
import { useAuth } from './context/AuthContext';
import { useUI } from './context/UIContext';
import { api } from './services/api';
import { useExamStore } from './store/useExamStore';

const HomeView = React.lazy(() => import('./components/dashboard/HomeView').then((module) => ({ default: module.HomeView })));
const FoldersView = React.lazy(() => import('./components/dashboard/FoldersView').then((module) => ({ default: module.FoldersView })));
const SearchHub = React.lazy(() => import('./components/dashboard/SearchHub').then((module) => ({ default: module.SearchHub })));
const ExamSimulator = React.lazy(() => import('./components/exam/ExamSimulator').then((module) => ({ default: module.ExamSimulator })));
const AnalyticsView = React.lazy(() => import('./components/stats/AnalyticsView').then((module) => ({ default: module.AnalyticsView })));
const ErrorNotebookView = React.lazy(() => import('./components/stats/ErrorNotebookView').then((module) => ({ default: module.ErrorNotebookView })));
const RankingView = React.lazy(() => import('./components/stats/RankingView').then((module) => ({ default: module.RankingView })));
const ProfileView = React.lazy(() => import('./components/profile/ProfileView').then((module) => ({ default: module.ProfileView })));


const PageFallback: React.FC = () => (
  <div className="exam-load-state" role="status" aria-live="polite">
    <span className="ui-loader" aria-hidden="true" />
    <p>Carregando…</p>
  </div>
);

const LazyPage: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <Suspense fallback={<PageFallback />}>{children}</Suspense>
);

const PageScrollReset: React.FC = () => {
  const { pathname } = useLocation();

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
  }, [pathname]);

  return null;
};

const AppShell: React.FC = () => (
  <div className="app-shell">
    <a href="#main-content" className="skip-link">Pular para o conteúdo</a>
    <Sidebar />
    <div className="app-content">
      <Navbar />
      <main id="main-content" className="app-main" tabIndex={-1}>
        <Outlet />
      </main>
    </div>
  </div>
);

const ProtectedRoute: React.FC = () => {
  const location = useLocation();
  const { status } = useAuth();

  if (status === 'loading') {
    return (
      <main className="auth-load-state" aria-busy="true">
        <span className="brand-symbol" aria-hidden="true">C</span>
        <span className="ui-loader" aria-hidden="true" />
        <p>Preparando seu espaço de estudo…</p>
      </main>
    );
  }

  if (status === 'unauthenticated') {
    const returnPath = `${location.pathname}${location.search}${location.hash}`;
    return <Navigate to={`/login?next=${encodeURIComponent(returnPath)}`} replace />;
  }

  return <Outlet />;
};

const ExamRoute: React.FC<{ result?: boolean }> = ({ result = false }) => {
  const { examId = '' } = useParams();
  const navigate = useNavigate();
  const {
    activeExam,
    isFinished,
  } = useExam();
  const [loadError, setLoadError] = useState<string | null>(null);
  const [validatedExamId, setValidatedExamId] = useState<number | null>(null);
  const validationRunRef = useRef(0);

  const numericExamId = Number(examId);
  const isActiveAlias = examId === 'ativa';
  const isValidExamId = Number.isInteger(numericExamId) && numericExamId > 0;

  useEffect(() => {
    if (isActiveAlias || !isValidExamId) return;
    const validationRun = ++validationRunRef.current;
    setLoadError(null);
    setValidatedExamId(null);

    void api.getExam(numericExamId)
      .then((exam) => {
        if (validationRunRef.current !== validationRun) return;
        const state = useExamStore.getState();
        if (state.activeExam?.id === numericExamId) {
          state.refreshExam(exam);
        } else {
          state.startExam(exam);
        }
        setValidatedExamId(numericExamId);
      })
      .catch((error) => {
        if (validationRunRef.current !== validationRun) return;
        useExamStore.getState().resetExam();
        setLoadError(error instanceof Error ? error.message : 'Não foi possível carregar esta prova.');
      });

    return () => {
      if (validationRunRef.current === validationRun) validationRunRef.current += 1;
    };
  }, [isActiveAlias, isValidExamId, numericExamId]);

  useEffect(() => {
    if (!result && activeExam && activeExam.id === numericExamId && isFinished) {
      navigate(`/prova/${numericExamId}/resultado`, { replace: true });
    }
  }, [activeExam, isFinished, navigate, numericExamId, result]);

  if (isActiveAlias) {
    if (!activeExam) return <Navigate to="/biblioteca" replace />;
    return (
      <Navigate
        to={`/prova/${activeExam.id}${isFinished ? '/resultado' : ''}`}
        replace
      />
    );
  }

  if (!isValidExamId) return <Navigate to="/biblioteca" replace />;

  if (loadError) {
    return (
      <main className="exam-load-state" id="main-content">
        <h1>Não foi possível abrir a prova.</h1>
        <p>{loadError}</p>
        <button type="button" className="ui-button ui-button-primary" onClick={() => navigate('/biblioteca')}>
          Voltar à biblioteca
        </button>
      </main>
    );
  }

  if (validatedExamId !== numericExamId || activeExam?.id !== numericExamId) {
    return (
      <main className="exam-load-state" id="main-content" aria-busy="true">
        <span className="ui-loader" aria-hidden="true" />
        <p>Preparando sua prova…</p>
      </main>
    );
  }

  if (result && !isFinished) {
    return <Navigate to={`/prova/${numericExamId}`} replace />;
  }

  return (
    <LazyPage>
      <ExamSimulator
        onBackToDashboard={() => navigate('/biblioteca')}
        onOpenNotebook={() => navigate('/progresso/erros')}
      />
    </LazyPage>
  );
};

export const App: React.FC = () => {
  const navigate = useNavigate();
  const {
    closeDirectIngestModal,
    directIngestData,
    isDirectIngestModalOpen,
    showToast,
  } = useUI();
  const { loadAndStartExam } = useExam();

  const openCurrentExam = () => {
    const current = useExamStore.getState();
    if (!current.activeExam) {
      navigate('/biblioteca');
      return;
    }
    navigate(`/prova/${current.activeExam.id}${current.isFinished ? '/resultado' : ''}`);
  };

  const handleExamReady = async (examId: number) => {
    try {
      await loadAndStartExam(examId);
      navigate(`/prova/${examId}`);
    } catch (error) {
      showToast(
        'error',
        'A prova foi adicionada, mas não abriu',
        error instanceof Error ? error.message : 'Abra a prova pela biblioteca.',
      );
    }
  };

  return (
    <>
      <PageScrollReset />
      <Routes>
        <Route path="login" element={<LoginPage />} />
        <Route element={<ProtectedRoute />}>
          <Route element={<AppShell />}>
            <Route index element={<LazyPage><HomeView /></LazyPage>} />
            <Route path="biblioteca" element={<LazyPage><FoldersView onStartExam={openCurrentExam} /></LazyPage>} />
            <Route path="buscar" element={<LazyPage><SearchHub onExamReady={handleExamReady} /></LazyPage>} />
            <Route path="perfil" element={<LazyPage><ProfileView /></LazyPage>} />
            <Route path="progresso" element={<ProgressLayout />}>

              <Route index element={<LazyPage><AnalyticsView /></LazyPage>} />
              <Route path="erros" element={<LazyPage><ErrorNotebookView onStartExam={openCurrentExam} /></LazyPage>} />
              <Route path="ranking" element={<LazyPage><RankingView /></LazyPage>} />
            </Route>
          </Route>
          <Route path="prova/:examId" element={<ExamRoute />} />
          <Route path="prova/:examId/resultado" element={<ExamRoute result />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>

      <DirectIngestModal
        isOpen={isDirectIngestModalOpen}
        onClose={closeDirectIngestModal}
        onExamReady={handleExamReady}
        initialExamUrl={directIngestData.examUrl}
        initialGabaritoUrl={directIngestData.gabaritoUrl}
        initialTitle={directIngestData.title}
      />
      <ToastViewport />
    </>
  );
};
