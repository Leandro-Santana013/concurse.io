import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertTriangle, CheckCircle2, Loader2, Play, RefreshCw, RotateCcw } from 'lucide-react';
import { api } from '../../services/api';
import { NotebookSubjectStat } from '../../types/exam';
import { useExam } from '../../context/ExamContext';
import { useUI } from '../../context/UIContext';
import { useExamStore } from '../../store/useExamStore';

interface ErrorNotebookViewProps { onStartExam?: () => void; }

export const ErrorNotebookView: React.FC<ErrorNotebookViewProps> = ({ onStartExam }) => {
  const navigate = useNavigate();
  const [subjects, setSubjects] = useState<NotebookSubjectStat[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [launching, setLaunching] = useState<string | null>(null);
  const { loadErrorNotebookExam } = useExam();
  const { showToast } = useUI();

  const load = async () => {
    setIsLoading(true); setError(null);
    try { setSubjects(await api.getNotebookStats()); }
    catch (err) { setError(err instanceof Error ? err.message : 'Não foi possível carregar o caderno.'); }
    finally { setIsLoading(false); }
  };
  useEffect(() => { void load(); }, []);

  const launch = async (subject?: string) => {
    setLaunching(subject || 'all');
    try {
      await loadErrorNotebookExam(subject);
      const id = useExamStore.getState().activeExam?.id;
      showToast('info', 'Revisão iniciada', subject ? `Foco em ${subject}.` : 'Todas as disciplinas com erros.');
      if (onStartExam) onStartExam(); else if (id) navigate(`/prova/${id}`);
    } catch (err) {
      showToast('warning', 'Não foi possível iniciar a revisão', err instanceof Error ? err.message : undefined);
    } finally { setLaunching(null); }
  };

  const total = subjects.reduce((sum, item) => sum + item.count, 0);
  if (isLoading) return <div className="space-y-3" aria-busy="true">{[1,2,3].map((item) => <div key={item} className="skeleton h-24" />)}</div>;
  if (error) return <div className="state-card" role="alert"><RefreshCw aria-hidden="true" /><div><h2>Não foi possível abrir o Caderno de Erros</h2><p>{error}</p></div><button className="button-secondary" onClick={load}>Tentar novamente</button></div>;

  return (
    <div className="space-y-6">
      <section className="flex flex-col gap-5 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5 md:flex-row md:items-center md:justify-between">
        <div className="max-w-2xl"><p className="eyebrow">Revisão direcionada</p><h2 className="section-title mt-1">Caderno de Erros</h2><p className="mt-2 text-sm leading-relaxed text-[var(--text-muted)]">Retome as questões que você errou e transforme cada dificuldade em uma sessão objetiva.</p></div>
        <button className="button-primary shrink-0" disabled={total === 0 || Boolean(launching)} onClick={() => void launch()}>
          {launching === 'all' ? <Loader2 className="animate-spin" aria-hidden="true" /> : <RotateCcw aria-hidden="true" />} Revisar todos ({total})
        </button>
      </section>

      {total === 0 ? (
        <div className="state-card text-center"><CheckCircle2 className="mx-auto text-[var(--success)]" aria-hidden="true" /><h3>Nenhum erro pendente</h3><p>Finalize simulados com gabarito para alimentar esta área.</p></div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface)]">
          {subjects.map((item) => (
            <article key={item.subject} className="flex flex-col gap-4 border-b border-[var(--border)] p-4 last:border-b-0 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-start gap-3"><AlertTriangle className="mt-0.5 text-[var(--warning)]" aria-hidden="true" /><div><h3 className="font-semibold">{item.subject}</h3><p className="mt-1 text-sm text-[var(--text-muted)]">{item.count} {item.count === 1 ? 'erro registrado' : 'erros registrados'}</p></div></div>
              <button className="button-secondary shrink-0" disabled={Boolean(launching)} onClick={() => void launch(item.subject)}>
                {launching === item.subject ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Play aria-hidden="true" />} Revisar disciplina
              </button>
            </article>
          ))}
        </div>
      )}
    </div>
  );
};
