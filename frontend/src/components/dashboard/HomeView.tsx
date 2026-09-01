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
} from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { useExam } from '../../context/ExamContext';
import { useUI } from '../../context/UIContext';
import { api } from '../../services/api';
import { useExamStore } from '../../store/useExamStore';
import type { ExamSummary, Folder, NotebookSubjectStat } from '../../types/exam';

type LoadState = 'loading' | 'ready' | 'error';

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
    isLoadingExam,
    loadAndStartExam,
    progressPercentage,
  } = useExam();
  const [folders, setFolders] = useState<Folder[]>([]);
  const [notebook, setNotebook] = useState<NotebookSubjectStat[]>([]);
  const [loadState, setLoadState] = useState<LoadState>('loading');
  const [launchingExamId, setLaunchingExamId] = useState<number | null>(null);

  const loadOverview = useCallback(async () => {
    setLoadState('loading');
    const [foldersResult, notebookResult] = await Promise.allSettled([
      api.getFolders(),
      api.getNotebookStats(),
    ]);

    if (foldersResult.status === 'fulfilled') setFolders(foldersResult.value);
    if (notebookResult.status === 'fulfilled') setNotebook(notebookResult.value);
    setLoadState(
      foldersResult.status === 'rejected' && notebookResult.status === 'rejected'
        ? 'error'
        : 'ready',
    );
  }, []);

  useEffect(() => {
    void loadOverview();
  }, [loadOverview]);

  const recentExams = useMemo<LibraryExam[]>(() => folders
    .flatMap((folder) => folder.exams.map((exam) => ({ ...exam, folderName: folder.name })))
    .slice(0, 3), [folders]);

  const totalErrors = notebook.reduce((total, item) => total + item.count, 0);
  const answeredCount = Object.values(answers).filter(Boolean).length;
  const totalQuestions = activeExam?.questions.length ?? 0;

  const continuePath = activeExam
    ? `/prova/${activeExam.id}${isFinished ? '/resultado' : ''}`
    : '/biblioteca';

  const handleGenerate = async () => {
    try {
      await generateCustomExam(20);
      const generatedExam = useExamStore.getState().activeExam;
      if (!generatedExam) throw new Error('O simulado não pôde ser aberto.');
      showToast('success', 'Simulado pronto', 'Selecionamos 20 questões da sua biblioteca.');
      navigate(`/prova/${generatedExam.id}`);
    } catch (error) {
      showToast(
        'error',
        'Não foi possível gerar o simulado',
        error instanceof Error ? error.message : undefined,
      );
    }
  };

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
            onClick={handleGenerate}
            disabled={isLoadingExam}
          >
            <RotateCcw aria-hidden="true" />
            <span>
              <strong>{isLoadingExam ? 'Preparando…' : 'Simulado de 20 questões'}</strong>
              <small>Seleção mista da biblioteca</small>
            </span>
            <ArrowRight aria-hidden="true" />
          </button>
        </div>
      </section>

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
    </div>
  );
};
