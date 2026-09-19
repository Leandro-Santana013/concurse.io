import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ArrowRight,
  BookOpen,
  CircleAlert,
  Clock3,
  FileSearch,
  Import,
  Play,
  RefreshCw,
  RotateCcw,
  Wifi,
} from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { useExam } from '../../context/ExamContext';
import { useUI } from '../../context/UIContext';
import { api, AuthRequiredError } from '../../services/api';
import { useExamStore } from '../../store/useExamStore';
import type {
  CustomSimulationRequest,
  ExamSummary,
  Folder,
  NotebookSubjectStat,
} from '../../types/exam';
import { CustomSimulationModal } from './CustomSimulationModal';

type LoadState = 'loading' | 'ready' | 'error';
const OFFLINE_DESKTOP = import.meta.env.VITE_OFFLINE_DESKTOP === '1';

interface LibraryExam extends ExamSummary {
  folderName: string;
}

export const HomeView: React.FC = () => {
  const navigate = useNavigate();
  const { openDirectIngestModal, showToast } = useUI();
  const {
    activeExam,
    answers,
    elapsedSeconds,
    formatTime,
    generateCustomExam,
    isFinished,
    loadAndStartExam,
    progressPercentage,
  } = useExam();
  const [folders, setFolders] = useState<Folder[]>([]);
  const [notebook, setNotebook] = useState<NotebookSubjectStat[]>([]);
  const [loadState, setLoadState] = useState<LoadState>('loading');
  const [launchingExamId, setLaunchingExamId] = useState<number | null>(null);
  const [isCustomModalOpen, setIsCustomModalOpen] = useState(false);
  const [meshPeers, setMeshPeers] = useState<Array<{ node_id: string; profile_name: string; assets: Array<{ asset_id: string; title: string }> }>>([]);
  const [meshBusy, setMeshBusy] = useState(false);

  const refreshMesh = useCallback(async () => {
    if (!OFFLINE_DESKTOP) return;
    try {
      const state = await api.getMeshPeers();
      setMeshPeers(state.peers);
    } catch {
      setMeshPeers([]);
    }
  }, []);

  const loadOverview = useCallback(async () => {
    setLoadState('loading');
    const [foldersResult, notebookResult] = await Promise.allSettled([
      api.getFolders(),
      api.getNotebookStats(),
    ]);

    if (foldersResult.status === 'fulfilled') setFolders(foldersResult.value);
    if (notebookResult.status === 'fulfilled') setNotebook(notebookResult.value);
    const sessionExpired = [foldersResult, notebookResult].some(
      (result) => result.status === 'rejected' && result.reason instanceof AuthRequiredError,
    );
    if (sessionExpired) {
      navigate(`/login?next=${encodeURIComponent('/')}`, { replace: true });
      return;
    }
    setLoadState(
      foldersResult.status === 'rejected' && notebookResult.status === 'rejected'
        ? 'error'
        : 'ready',
    );
  }, []);

  useEffect(() => {
    void loadOverview();
  }, [loadOverview]);

  useEffect(() => {
    if (!OFFLINE_DESKTOP) return;
    void refreshMesh();
    const interval = window.setInterval(() => void refreshMesh(), 5000);
    return () => window.clearInterval(interval);
  }, [refreshMesh]);

  const syncMesh = async () => {
    setMeshBusy(true);
    let downloaded = 0;
    try {
      for (const peer of meshPeers) {
        for (const asset of peer.assets) {
          const result = await api.downloadMeshAsset(asset.asset_id);
          if (result.status === 'downloaded') downloaded += 1;
        }
      }
      if (downloaded > 0) {
        showToast('success', 'Provas recebidas', `${downloaded} prova(s) foram reconstruídas pelos pares.`);
        await loadOverview();
      } else {
        showToast('info', 'Malha sincronizada', 'Nenhum arquivo novo foi encontrado nos pares online.');
      }
    } catch (error) {
      showToast('error', 'Falha na malha', error instanceof Error ? error.message : 'Não foi possível buscar os blocos.');
    } finally {
      setMeshBusy(false);
    }
  };

  const recentExams = useMemo<LibraryExam[]>(() => folders
    .flatMap((folder) => folder.exams.map((exam) => ({ ...exam, folderName: folder.name })))
    .slice(0, 3), [folders]);

  const totalErrors = notebook.reduce((total, item) => total + item.count, 0);
  const answeredCount = Object.values(answers).filter(Boolean).length;
  const totalQuestions = activeExam?.questions.length ?? 0;

  const continuePath = activeExam
    ? `/prova/${activeExam.id}${isFinished ? '/resultado' : ''}`
    : '/biblioteca';

  const handleGenerate = async (request: CustomSimulationRequest) => {
    try {
      await generateCustomExam(request);
      const generatedExam = useExamStore.getState().activeExam;
      if (!generatedExam) throw new Error('O simulado não pôde ser aberto.');
      setIsCustomModalOpen(false);
      showToast('success', 'Simulado pronto', `${request.count} questões foram selecionadas para você.`);
      navigate(`/prova/${generatedExam.id}`);
    } catch (error) {
      showToast(
        'error',
        'Não foi possível gerar o simulado',
        error instanceof Error ? error.message : undefined,
      );
    }
  };

  const openCustomModal = useCallback(() => setIsCustomModalOpen(true), []);
  const closeCustomModal = useCallback(() => setIsCustomModalOpen(false), []);

  const handleOpenExam = async (examId: number) => {
    setLaunchingExamId(examId);
    try {
      await loadAndStartExam(examId);
      navigate(`/prova/${examId}`);
    } catch (error) {
      showToast(
        'error',
        'Não foi possível abrir a prova',
        error instanceof Error ? error.message : undefined,
      );
    } finally {
      setLaunchingExamId(null);
    }
  };

  return (
    <div className="page-container home-page">
      <header className="page-heading">
        <p className="page-kicker">Seu espaço de estudo</p>
        <h1>Continue de onde parou.</h1>
        <p>Provas, revisões e desempenho reunidos em uma experiência feita para leitura.</p>
      </header>

      {activeExam ? (
        <section className="ui-card resume-card" aria-labelledby="resume-title">
          <div className="resume-copy">
            <span className="status-label">
              {isFinished ? 'Resultado disponível' : 'Prova em andamento'}
            </span>
            <h2 id="resume-title">{activeExam.title}</h2>
            <div className="resume-meta" aria-label="Progresso da prova">
              <span><BookOpen aria-hidden="true" /> {answeredCount} de {totalQuestions} respondidas</span>
              <span><Clock3 aria-hidden="true" /> {formatTime(elapsedSeconds)}</span>
            </div>
            <div
              className="ui-progress"
              role="progressbar"
              aria-label="Questões respondidas"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(progressPercentage)}
            >
              <span style={{ width: `${progressPercentage}%` }} />
            </div>
          </div>
          <Link to={continuePath} className="ui-button ui-button-primary resume-action">
            {isFinished ? 'Ver resultado' : 'Continuar'}
            <ArrowRight aria-hidden="true" />
          </Link>
        </section>
      ) : (
        <section className="ui-card resume-card resume-card-empty" aria-labelledby="resume-title">
          <div className="resume-copy">
            <span className="status-label">Pronto para começar</span>
            <h2 id="resume-title">Escolha uma prova da sua biblioteca.</h2>
            <p>Seu progresso será salvo para você retomar depois.</p>
          </div>
          <Link to="/biblioteca" className="ui-button ui-button-primary resume-action">
            Abrir biblioteca
            <ArrowRight aria-hidden="true" />
          </Link>
        </section>
      )}

      <section aria-labelledby="quick-actions-title">
        <div className="section-heading-row">
          <div>
            <p className="page-kicker">Atalhos</p>
            <h2 id="quick-actions-title">O que você quer estudar?</h2>
          </div>
        </div>

        <div className="quick-action-grid">
          <Link to="/buscar" className="quick-action-card">
            <FileSearch aria-hidden="true" />
            <span>
              <strong>Buscar provas</strong>
              <small>Encontre por banca ou concurso</small>
            </span>
            <ArrowRight aria-hidden="true" />
          </Link>
          <button type="button" className="quick-action-card" onClick={() => openDirectIngestModal()}>
            <Import aria-hidden="true" />
            <span>
              <strong>Importar por link</strong>
              <small>Adicione prova e gabarito</small>
            </span>
            <ArrowRight aria-hidden="true" />
          </button>
          <button
            type="button"
            className="quick-action-card"
            onClick={openCustomModal}
          >
            <RotateCcw aria-hidden="true" />
            <span>
              <strong>Montar simulado personalizado</strong>
              <small>Escolha quantidade e disciplinas</small>
            </span>
            <ArrowRight aria-hidden="true" />
          </button>
        </div>
      </section>

      {OFFLINE_DESKTOP && (
        <section className="ui-card" aria-labelledby="mesh-title">
          <div className="section-heading-row">
            <div>
              <p className="page-kicker">Rede local entre pares</p>
              <h2 id="mesh-title" className="flex items-center gap-2"><Wifi aria-hidden="true" /> Malha de provas</h2>
            </div>
            <button type="button" className="ui-button ui-button-secondary" onClick={() => void syncMesh()} disabled={meshBusy || meshPeers.length === 0}>
              <RefreshCw aria-hidden="true" className={meshBusy ? 'animate-spin' : undefined} /> {meshBusy ? 'Sincronizando…' : 'Buscar dos pares'}
            </button>
          </div>
          <p className="mt-2 text-sm text-[var(--text-muted)]">Seu computador compartilha blocos verificados por SHA-256 somente com outros aplicativos na mesma rede. Nenhum servidor central é usado.</p>
          {meshPeers.length === 0 ? (
            <p className="mt-4 text-sm text-[var(--text-muted)]">Nenhum par online anunciado ainda. Deixe outro aplicativo aberto na mesma rede Wi-Fi.</p>
          ) : (
            <ul className="mt-4 grid gap-3 sm:grid-cols-2">
              {meshPeers.map((peer) => (
                <li key={peer.node_id} className="rounded-lg border border-[var(--border)] bg-[var(--surface-subtle)] p-3 text-sm">
                  <strong className="flex items-center gap-2"><Wifi aria-hidden="true" className="h-4 w-4 text-[var(--success)]" /> {peer.profile_name || 'Par local'}</strong>
                  <span className="mt-1 block text-xs text-[var(--text-muted)]">{peer.assets.length} prova(s) anunciada(s)</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {loadState === 'error' ? (
        <section className="ui-error-state" role="alert">
          <CircleAlert aria-hidden="true" />
          <div>
            <h2>Não foi possível carregar seu resumo.</h2>
            <p>Confira se o servidor está disponível e tente novamente.</p>
          </div>
          <button type="button" className="ui-button ui-button-secondary" onClick={() => void loadOverview()}>
            <RefreshCw aria-hidden="true" /> Tentar novamente
          </button>
        </section>
      ) : (
        <div className="home-overview-grid">
          <section className="ui-card overview-card" aria-labelledby="library-preview-title">
            <div className="section-heading-row">
              <div>
                <p className="page-kicker">Biblioteca</p>
                <h2 id="library-preview-title">Provas salvas</h2>
              </div>
              <Link to="/biblioteca" className="text-link">Ver todas <ArrowRight aria-hidden="true" /></Link>
            </div>

            {loadState === 'loading' ? (
              <div className="skeleton-list" aria-label="Carregando provas">
                <span className="ui-skeleton" /><span className="ui-skeleton" /><span className="ui-skeleton" />
              </div>
            ) : recentExams.length > 0 ? (
              <ul className="preview-list">
                {recentExams.map((exam) => (
                  <li key={exam.id}>
                    <div>
                      <span>{exam.folderName}</span>
                      <h3>{exam.title}</h3>
                      <p>
                        {exam.question_count} questões
                        {exam.last_score !== null ? ` · Última nota: ${exam.last_score}%` : ''}
                      </p>
                    </div>
                    <button
                      type="button"
                      className="ui-icon-button"
                      onClick={() => void handleOpenExam(exam.id)}
                      disabled={launchingExamId !== null}
                      aria-label={`Iniciar ${exam.title}`}
                    >
                      {launchingExamId === exam.id
                        ? <RefreshCw aria-hidden="true" />
                        : <Play aria-hidden="true" />}
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="compact-empty-state">
                <BookOpen aria-hidden="true" />
                <p>Sua biblioteca ainda está vazia.</p>
                <Link to="/buscar" className="text-link">Buscar a primeira prova</Link>
              </div>
            )}
          </section>

          <section className="ui-card overview-card review-summary" aria-labelledby="review-summary-title">
            <div>
              <p className="page-kicker">Revisão</p>
              <h2 id="review-summary-title">Caderno de erros</h2>
            </div>
            {loadState === 'loading' ? (
              <div className="review-skeleton" aria-label="Carregando revisão">
                <span className="ui-skeleton ui-skeleton-number" />
                <span className="ui-skeleton" />
              </div>
            ) : (
              <>
                <p className="review-count"><strong>{totalErrors}</strong> questões para revisar</p>
                <p className="review-detail">
                  {notebook.length > 0
                    ? `${notebook.length} ${notebook.length === 1 ? 'disciplina precisa' : 'disciplinas precisam'} de atenção.`
                    : 'Quando você errar uma questão, ela aparecerá aqui.'}
                </p>
              </>
            )}
            <Link to="/progresso/erros" className="ui-button ui-button-secondary">
              Abrir caderno <ArrowRight aria-hidden="true" />
            </Link>
          </section>
        </div>
      )}

      <CustomSimulationModal
        isOpen={isCustomModalOpen}
        onClose={closeCustomModal}
        onSubmit={handleGenerate}
      />
    </div>
  );
};
