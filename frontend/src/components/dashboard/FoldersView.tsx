import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowUpRight,
  BookOpen,
  CalendarDays,
  CheckCircle2,
  ClipboardList,
  FileQuestion,
  Folder as FolderIcon,
  Loader2,
  Play,
  Plus,
  RefreshCw,
  Search,
  Shuffle,
} from 'lucide-react';
import { api, AuthRequiredError } from '../../services/api';
import type {
  CustomSimulationRequest,
  CustomSimulationSummary,
  ExamSummary,
  Folder,
} from '../../types/exam';
import { useExam } from '../../context/ExamContext';
import { useUI } from '../../context/UIContext';
import { useExamStore } from '../../store/useExamStore';
import { SourceModal, SourceModalData } from '../ui/SourceModal';
import { CustomSimulationModal } from './CustomSimulationModal';

interface FoldersViewProps {
  onStartExam?: () => void;
}

type SortMode = 'title' | 'questions' | 'score' | 'attempts';
const IDCAP_PATTERN = /\b(?:id\s*cap|idecap)\b/i;

const isIdcapExam = (exam: ExamSummary) =>
  IDCAP_PATTERN.test(`${exam.title} ${exam.source_url || ''}`);

const formatCustomDate = (value: string) => {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return 'Data não disponível';
  return parsed.toLocaleDateString('pt-BR', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
};

const compareExamSummaries = (a: ExamSummary, b: ExamSummary, sortMode: SortMode) => {
  if (sortMode === 'questions') {
    return (b.question_count - a.question_count) || a.title.localeCompare(b.title, 'pt-BR');
  }
  if (sortMode === 'score') {
    return ((b.best_score ?? -1) - (a.best_score ?? -1)) || a.title.localeCompare(b.title, 'pt-BR');
  }
  if (sortMode === 'attempts') {
    return (b.attempt_count - a.attempt_count) || a.title.localeCompare(b.title, 'pt-BR');
  }
  return a.title.localeCompare(b.title, 'pt-BR');
};

const compareFolderSummaries = (a: Folder, b: Folder, sortMode: SortMode) => {
  if (sortMode === 'title') return a.name.localeCompare(b.name, 'pt-BR');
  const firstExamA = a.exams[0];
  const firstExamB = b.exams[0];
  if (!firstExamA || !firstExamB) return a.name.localeCompare(b.name, 'pt-BR');
  return compareExamSummaries(firstExamA, firstExamB, sortMode) || a.name.localeCompare(b.name, 'pt-BR');
};

export const FoldersView: React.FC<FoldersViewProps> = ({ onStartExam }) => {
  const navigate = useNavigate();
  const [folders, setFolders] = useState<Folder[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [sortMode, setSortMode] = useState<SortMode>('title');
  const [loadingExamId, setLoadingExamId] = useState<number | 'custom' | null>(null);
  const [customSimulations, setCustomSimulations] = useState<CustomSimulationSummary[]>([]);
  const [customError, setCustomError] = useState<string | null>(null);
  const [activeLibraryTab, setActiveLibraryTab] = useState<'exams' | 'custom'>('exams');
  const [isCustomModalOpen, setIsCustomModalOpen] = useState(false);
  const [sourceModalData, setSourceModalData] = useState<SourceModalData | null>(null);
  const [isSourceModalOpen, setIsSourceModalOpen] = useState(false);
  const { loadAndStartExam, generateCustomExam } = useExam();
  const { showToast, openDirectIngestModal } = useUI();

  const goToExam = (examId: number) => {
    if (onStartExam) onStartExam();
    else navigate(`/prova/${examId}`);
  };

  const loadFolders = async () => {
    setIsLoading(true);
    setError(null);
    setCustomError(null);
    try {
      setFolders(await api.getFolders());
      try {
        if (typeof api.getCustomSimulations === 'function') {
          setCustomSimulations(await api.getCustomSimulations());
        }
      } catch (customErr) {
        if (customErr instanceof AuthRequiredError) {
          navigate(`/login?next=${encodeURIComponent('/biblioteca')}`, { replace: true });
          return;
        }
        setCustomError(customErr instanceof Error ? customErr.message : 'Não foi possível carregar os testes personalizados.');
      }
    } catch (err) {
      if (err instanceof AuthRequiredError) {
        navigate(`/login?next=${encodeURIComponent('/biblioteca')}`, { replace: true });
        return;
      }
      const message = err instanceof Error ? err.message : 'Não foi possível carregar a biblioteca.';
      setError(message);
      showToast('error', 'Erro ao carregar a biblioteca', message);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void loadFolders();
  }, []);

  const visibleFolders = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase('pt-BR');
    return folders
      .map((folder) => ({
        ...folder,
        exams: [...folder.exams]
          .filter((exam) => !normalized || exam.title.toLocaleLowerCase('pt-BR').includes(normalized))
          .sort((a, b) => compareExamSummaries(a, b, sortMode)),
      }))
      .filter((folder) => folder.exams.length > 0)
      .sort((a, b) => compareFolderSummaries(a, b, sortMode));
  }, [folders, query, sortMode]);

  const handleLaunchExam = async (examId: number) => {
    setLoadingExamId(examId);
    try {
      await loadAndStartExam(examId);
      goToExam(examId);
    } catch (err) {
      showToast('error', 'Falha ao abrir o simulado', err instanceof Error ? err.message : undefined);
    } finally {
      setLoadingExamId(null);
    }
  };

  const handleGenerateCustom = async (request: CustomSimulationRequest) => {
    setLoadingExamId('custom');
    try {
      await generateCustomExam(request);
      const examId = useExamStore.getState().activeExam?.id;
      setIsCustomModalOpen(false);
      showToast('success', 'Simulado pronto', `${request.count} questões foram selecionadas para você.`);
      if (examId) goToExam(examId);
    } catch (err) {
      showToast('error', 'Erro ao gerar o simulado', err instanceof Error ? err.message : undefined);
    } finally {
      setLoadingExamId(null);
    }
  };

  const handleLaunchCustom = async (examId: number) => {
    setLoadingExamId(examId);
    try {
      await loadAndStartExam(examId);
      goToExam(examId);
    } catch (err) {
      showToast('error', 'Falha ao abrir o teste personalizado', err instanceof Error ? err.message : undefined);
    } finally {
      setLoadingExamId(null);
    }
  };

  const openCustomModal = useCallback(() => setIsCustomModalOpen(true), []);
  const closeCustomModal = useCallback(() => setIsCustomModalOpen(false), []);

  const totalExams = folders.reduce((total, folder) => total + folder.exams.length, 0);
  const answerKeyRelevantTotal = folders.reduce(
    (total, folder) => total + folder.exams.filter((exam) => !isIdcapExam(exam)).length,
    0,
  );
  const examsWithAnswerKey = folders.reduce(
    (total, folder) => total + folder.exams.filter((exam) => !isIdcapExam(exam) && exam.has_official_answers).length,
    0,
  );

  if (isLoading && folders.length === 0) {
    return (
      <div className="page-shell" aria-busy="true">
        <div className="space-y-3"><div className="skeleton h-7 w-56" /><div className="skeleton h-4 w-full max-w-xl" /></div>
        <div className="mt-8 space-y-3">{[1, 2, 3].map((item) => <div key={item} className="skeleton h-24 w-full" />)}</div>
      </div>
    );
  }

  return (
    <div className="page-shell space-y-8">
      <header className="flex flex-col gap-5 border-b border-[var(--border)] pb-7 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="eyebrow">Biblioteca</p>
          <h1 className="page-title">Suas provas</h1>
          <p className="page-description">Escolha um caderno salvo ou monte uma sessão rápida com questões da sua base.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button className="button-secondary" onClick={() => openDirectIngestModal()}><Plus aria-hidden="true" /> Importar prova</button>
          <button className="button-primary" onClick={openCustomModal} disabled={loadingExamId === 'custom'}>
            <Shuffle aria-hidden="true" />
            Montar simulado
          </button>
        </div>
      </header>

      <div className="flex w-fit max-w-full gap-1 overflow-x-auto rounded-xl border border-[var(--border)] bg-[var(--surface-subtle)] p-1" role="tablist" aria-label="Conteúdo da biblioteca">
        <button
          type="button"
          role="tab"
          aria-selected={activeLibraryTab === 'exams'}
          className={`min-h-11 whitespace-nowrap rounded-lg px-4 text-sm font-semibold transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus)] ${activeLibraryTab === 'exams' ? 'bg-[var(--surface)] text-[var(--text)] shadow-sm' : 'text-[var(--text-muted)] hover:text-[var(--text)]'}`}
          onClick={() => setActiveLibraryTab('exams')}
        >
          <BookOpen aria-hidden="true" className="mr-2 inline h-4 w-4" />
          Provas reais
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeLibraryTab === 'custom'}
          className={`min-h-11 whitespace-nowrap rounded-lg px-4 text-sm font-semibold transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus)] ${activeLibraryTab === 'custom' ? 'bg-[var(--surface)] text-[var(--text)] shadow-sm' : 'text-[var(--text-muted)] hover:text-[var(--text)]'}`}
          onClick={() => setActiveLibraryTab('custom')}
        >
          <ClipboardList aria-hidden="true" className="mr-2 inline h-4 w-4" />
          Testes personalizados{customSimulations.length > 0 ? ` · ${customSimulations.length}` : ''}
        </button>
      </div>

      {activeLibraryTab === 'exams' ? (
        <>
        <section aria-label="Resumo da biblioteca" className="grid gap-3 sm:grid-cols-3">
        <div className="metric-card"><span>Provas salvas</span><strong>{totalExams}</strong></div>
        <div className="metric-card"><span>Grupos</span><strong>{folders.length}</strong></div>
        <div className="metric-card">
          <span>{answerKeyRelevantTotal > 0 ? 'Com gabarito' : 'Provas prontas'}</span>
          <strong>{answerKeyRelevantTotal > 0 ? `${examsWithAnswerKey} de ${answerKeyRelevantTotal}` : totalExams}</strong>
        </div>
      </section>

      <div className="flex flex-col gap-3 sm:flex-row">
        <label className="relative flex-1">
          <span className="sr-only">Filtrar provas por título</span>
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-muted)]" aria-hidden="true" />
          <input className="input-control input-leading-icon" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Filtrar por título" />
        </label>
        <label className="flex items-center gap-2 text-sm text-[var(--text-muted)]">
          Ordenar por
          <select aria-label="Ordenar provas" className="input-control w-auto" value={sortMode} onChange={(event) => setSortMode(event.target.value as SortMode)}>
            <option value="title">Título</option><option value="questions">Mais questões</option><option value="score">Melhor nota</option><option value="attempts">Mais tentativas</option>
          </select>
        </label>
      </div>

      {error && (
        <section className="state-card" role="alert">
          <RefreshCw aria-hidden="true" /><div><h2>Não foi possível abrir a biblioteca</h2><p>{error}</p></div>
          <button className="button-secondary" onClick={loadFolders}>Tentar novamente</button>
        </section>
      )}

      {!error && folders.length === 0 && (
        <section className="state-card text-center">
          <FolderIcon className="mx-auto" aria-hidden="true" /><h2>Nenhuma prova salva</h2>
          <p>Busque uma prova pública ou importe um link para criar sua biblioteca.</p>
          <button className="button-primary mx-auto" onClick={() => navigate('/buscar')}>Buscar provas <ArrowUpRight aria-hidden="true" /></button>
        </section>
      )}

      {!error && folders.length > 0 && visibleFolders.length === 0 && (
        <section className="state-card text-center">
          <Search className="mx-auto" aria-hidden="true" /><h2>Nenhuma prova corresponde ao filtro</h2>
          <button className="button-secondary mx-auto" onClick={() => setQuery('')}>Limpar filtro</button>
        </section>
      )}

      <div className="space-y-8">
        {visibleFolders.map((folder) => (
          <section key={folder.id} aria-labelledby={`folder-${folder.id}`}>
            <div className="mb-3">
              <h2 id={`folder-${folder.id}`} className="section-title flex items-center gap-2"><FolderIcon aria-hidden="true" /> {folder.name}</h2>
              <p className="text-sm text-[var(--text-muted)]">{folder.exams.length} {folder.exams.length === 1 ? 'prova' : 'provas'}</p>
            </div>
            <div className="overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface)]">
              {folder.exams.map((exam) => (
                <article key={exam.id} className="flex flex-col gap-4 border-b border-[var(--border)] p-4 last:border-b-0 md:flex-row md:items-center md:justify-between">
                  <div className="min-w-0">
                    <h3 className="font-semibold text-[var(--text)]">{exam.title}</h3>
                    <div className="mt-2 flex flex-wrap gap-x-4 gap-y-2 text-sm text-[var(--text-muted)]">
                      <span className="inline-flex items-center gap-1"><FileQuestion aria-hidden="true" /> {exam.question_count} questões</span>
                      <span>{exam.attempt_count ? `${exam.attempt_count} tentativa(s)` : 'Ainda não realizada'}</span>
                      {exam.best_score !== null && <span>Melhor nota: <strong className="text-[var(--text)]">{exam.best_score}%</strong></span>}
                      {exam.last_score !== null && <span>Última: <strong className="text-[var(--text)]">{exam.last_score}%</strong></span>}
                    </div>
                    <div className="mt-2 flex flex-wrap gap-2 text-xs">
                      {isIdcapExam(exam) ? (
                        <span className="status-success">
                          <CheckCircle2 aria-hidden="true" /> Processada
                        </span>
                      ) : (
                        <span className={exam.has_official_answers ? 'status-success' : 'status-warning'}>
                          <CheckCircle2 aria-hidden="true" /> {exam.has_official_answers ? `Gabarito ${Math.round(exam.gabarito_coverage)}%` : 'Gabarito não confirmado'}
                        </span>
                      )}
                      <button
                        type="button"
                        className="status-neutral inline-flex items-center gap-1 cursor-pointer transition-colors hover:bg-[var(--surface-hover)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus)]"
                        onClick={() => {
                          setSourceModalData({
                            title: exam.title,
                            source_url: exam.source_url,
                            gabarito_url: exam.gabarito_url,
                          });
                          setIsSourceModalOpen(true);
                        }}
                      >
                        <BookOpen aria-hidden="true" className="h-3.5 w-3.5" /> Fonte
                      </button>
                    </div>
                  </div>
                  <button className="button-primary shrink-0" onClick={() => handleLaunchExam(exam.id)} disabled={loadingExamId === exam.id}>
                    {loadingExamId === exam.id ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Play aria-hidden="true" />} Iniciar prova
                  </button>
                </article>
              ))}
            </div>
          </section>
        ))}
      </div>
        </>
      ) : (
        <section className="space-y-5" role="tabpanel" aria-label="Testes personalizados">
          <div className="flex flex-col gap-4 rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5 sm:flex-row sm:items-end sm:justify-between sm:p-6">
            <div>
              <p className="eyebrow">Seu motor de questões</p>
              <h2 className="section-title mt-1 flex items-center gap-2"><ClipboardList aria-hidden="true" /> Testes personalizados</h2>
              <p className="mt-2 max-w-2xl text-sm text-[var(--text-muted)]">
                Aqui ficam as sessões montadas por você. Elas não se misturam com a numeração nem com os grupos das provas reais.
              </p>
            </div>
            <button type="button" className="button-primary shrink-0" onClick={openCustomModal}>
              <Shuffle aria-hidden="true" /> Montar novo teste
            </button>
          </div>

          {customError && (
            <section className="state-card" role="alert">
              <RefreshCw aria-hidden="true" />
              <div><h2>Não foi possível carregar seus testes</h2><p>{customError}</p></div>
              <button type="button" className="button-secondary" onClick={loadFolders}>Tentar novamente</button>
            </section>
          )}

          {!customError && customSimulations.length === 0 && (
            <section className="state-card text-center">
              <ClipboardList className="mx-auto" aria-hidden="true" />
              <h2>Nenhum teste personalizado ainda</h2>
              <p>Monte uma sessão por quantidade, disciplina ou prova de origem para começar.</p>
              <button type="button" className="button-primary mx-auto" onClick={openCustomModal}>
                <Shuffle aria-hidden="true" /> Montar primeiro teste
              </button>
            </section>
          )}

          {customSimulations.length > 0 && (
            <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface)]">
              {customSimulations.map((simulation) => (
                <article key={simulation.id} className="flex flex-col gap-4 border-b border-[var(--border)] p-4 last:border-b-0 sm:flex-row sm:items-center sm:justify-between sm:p-5">
                  <div className="min-w-0">
                    <h3 className="font-semibold text-[var(--text)]">{simulation.title}</h3>
                    <div className="mt-2 flex flex-wrap gap-x-4 gap-y-2 text-sm text-[var(--text-muted)]">
                      <span className="inline-flex items-center gap-1"><FileQuestion aria-hidden="true" /> {simulation.question_count} questões</span>
                      <span className="inline-flex items-center gap-1"><CalendarDays aria-hidden="true" /> {formatCustomDate(simulation.created_at)}</span>
                      <span>{simulation.attempt_count ? `${simulation.attempt_count} tentativa(s)` : 'Ainda não realizado'}</span>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-2 text-xs">
                      <span className="status-neutral">Sessão independente</span>
                      {simulation.best_score !== null && <span className="status-success">Melhor nota: {simulation.best_score}%</span>}
                      {simulation.last_score !== null && <span className="status-neutral">Última: {simulation.last_score}%</span>}
                    </div>
                  </div>
                  <button
                    type="button"
                    className="button-primary shrink-0"
                    onClick={() => void handleLaunchCustom(simulation.id)}
                    disabled={loadingExamId === simulation.id}
                  >
                    {loadingExamId === simulation.id ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Play aria-hidden="true" />}
                    {simulation.attempt_count ? 'Refazer teste' : 'Iniciar teste'}
                  </button>
                </article>
              ))}
            </div>
          )}
        </section>
      )}

      <CustomSimulationModal
        isOpen={isCustomModalOpen}
        onClose={closeCustomModal}
        onSubmit={handleGenerateCustom}
      />
      <SourceModal
        isOpen={isSourceModalOpen}
        onClose={() => setIsSourceModalOpen(false)}
        data={sourceModalData}
      />
    </div>
  );
};
