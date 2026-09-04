import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowUpRight,
  BookOpen,
  CheckCircle2,
  FileQuestion,
  Folder as FolderIcon,
  Loader2,
  Play,
  Plus,
  RefreshCw,
  Search,
  Shuffle,
} from 'lucide-react';
import { api } from '../../services/api';
import { Folder } from '../../types/exam';
import { useExam } from '../../context/ExamContext';
import { useUI } from '../../context/UIContext';
import { useExamStore } from '../../store/useExamStore';
import { SourceModal, SourceModalData } from '../ui/SourceModal';

interface FoldersViewProps {
  onStartExam?: () => void;
}

type SortMode = 'title' | 'questions' | 'score' | 'attempts';

export const FoldersView: React.FC<FoldersViewProps> = ({ onStartExam }) => {
  const navigate = useNavigate();
  const [folders, setFolders] = useState<Folder[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [sortMode, setSortMode] = useState<SortMode>('title');
  const [loadingExamId, setLoadingExamId] = useState<number | 'custom' | null>(null);
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
    try {
      setFolders(await api.getFolders());
    } catch (err) {
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
        exams: folder.exams
          .filter((exam) => !normalized || exam.title.toLocaleLowerCase('pt-BR').includes(normalized))
          .sort((a, b) => {
            if (sortMode === 'questions') return b.question_count - a.question_count;
            if (sortMode === 'score') return (b.best_score ?? -1) - (a.best_score ?? -1);
            if (sortMode === 'attempts') return b.attempt_count - a.attempt_count;
            return a.title.localeCompare(b.title, 'pt-BR');
          }),
      }))
      .filter((folder) => folder.exams.length > 0);
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

  const handleGenerateCustom = async () => {
    setLoadingExamId('custom');
    try {
      await generateCustomExam(20);
      const examId = useExamStore.getState().activeExam?.id;
      showToast('success', 'Simulado pronto', '20 questões foram selecionadas para você.');
      if (examId) goToExam(examId);
    } catch (err) {
      showToast('error', 'Erro ao gerar o simulado', err instanceof Error ? err.message : undefined);
    } finally {
      setLoadingExamId(null);
    }
  };

  const totalExams = folders.reduce((total, folder) => total + folder.exams.length, 0);
  const examsWithAnswerKey = folders.reduce(
    (total, folder) => total + folder.exams.filter((exam) => exam.has_official_answers).length,
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
          <button className="button-primary" onClick={handleGenerateCustom} disabled={loadingExamId === 'custom'}>
            {loadingExamId === 'custom' ? <Loader2 aria-hidden="true" /> : <Shuffle aria-hidden="true" />}
            Simulado de 20 questões
          </button>
        </div>
      </header>

      <section aria-label="Resumo da biblioteca" className="grid gap-3 sm:grid-cols-3">
        <div className="metric-card"><span>Provas salvas</span><strong>{totalExams}</strong></div>
        <div className="metric-card"><span>Grupos</span><strong>{folders.length}</strong></div>
        <div className="metric-card"><span>Com gabarito</span><strong>{examsWithAnswerKey} de {totalExams}</strong></div>
      </section>

      <div className="flex flex-col gap-3 sm:flex-row">
        <label className="relative flex-1">
          <span className="sr-only">Filtrar provas por título</span>
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-muted)]" aria-hidden="true" />
          <input className="input-control pl-10" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Filtrar por título" />
        </label>
        <label className="flex items-center gap-2 text-sm text-[var(--text-muted)]">
          Ordenar por
          <select className="input-control w-auto" value={sortMode} onChange={(event) => setSortMode(event.target.value as SortMode)}>
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
                      <span className={exam.has_official_answers ? 'status-success' : 'status-warning'}>
                        <CheckCircle2 aria-hidden="true" /> {exam.has_official_answers ? `Gabarito ${Math.round(exam.gabarito_coverage)}%` : 'Gabarito não confirmado'}
                      </span>
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

      <SourceModal
        isOpen={isSourceModalOpen}
        onClose={() => setIsSourceModalOpen(false)}
        data={sourceModalData}
      />
    </div>
  );
};
