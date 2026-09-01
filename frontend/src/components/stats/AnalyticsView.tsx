import React, { useEffect, useState } from 'react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { BookOpen, CheckCircle2, Clock, Flame, RefreshCw, Target, Trophy } from 'lucide-react';
import { api } from '../../services/api';
import { GlobalStats, NotebookSubjectStat } from '../../types/exam';

export const AnalyticsView: React.FC = () => {
  const [stats, setStats] = useState<GlobalStats | null>(null);
  const [subjects, setSubjects] = useState<NotebookSubjectStat[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadStats = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [overview, notebook] = await Promise.all([api.getGlobalStats(), api.getNotebookStats()]);
      setStats(overview);
      setSubjects(notebook);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Não foi possível carregar o seu progresso.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => { void loadStats(); }, []);

  if (isLoading) {
    return <div className="space-y-5" aria-busy="true"><div className="grid grid-cols-2 gap-3 lg:grid-cols-6">{[1,2,3,4,5,6].map((item) => <div key={item} className="skeleton h-28" />)}</div><div className="skeleton h-80" /></div>;
  }

  if (error || !stats) {
    return <div className="state-card" role="alert"><RefreshCw aria-hidden="true" /><div><h2>Não foi possível carregar seu progresso</h2><p>{error}</p></div><button className="button-secondary" onClick={loadStats}>Tentar novamente</button></div>;
  }

  const cards = [
    { label: 'Provas feitas', value: stats.total_exams, icon: BookOpen },
    { label: 'Questões', value: stats.total_questions, icon: Target },
    { label: 'Precisão', value: `${stats.global_accuracy}%`, icon: CheckCircle2 },
    { label: 'Sequência', value: `${stats.streak} dias`, icon: Flame },
    { label: 'Tempo de estudo', value: stats.study_time, icon: Clock },
    { label: 'Posição', value: stats.rank, icon: Trophy },
  ];

  return (
    <div className="space-y-8">
      <section aria-label="Resumo de desempenho" className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        {cards.map(({ label, value, icon: Icon }) => (
          <article key={label} className="metric-card">
            <Icon aria-hidden="true" /><span>{label}</span><strong>{value}</strong>
          </article>
        ))}
      </section>

      <section className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4 sm:p-6" aria-labelledby="attention-title">
        <div className="border-b border-[var(--border)] pb-4">
          <h2 id="attention-title" className="section-title">Pontos de atenção</h2>
          <p className="mt-1 text-sm text-[var(--text-muted)]">Disciplinas com mais erros registrados nas tentativas concluídas.</p>
        </div>

        {subjects.length === 0 ? (
          <div className="state-card mt-5 text-center"><CheckCircle2 className="mx-auto" aria-hidden="true" /><h3>Ainda não há erros registrados</h3><p>Finalize uma prova para começar a acompanhar seus pontos de atenção.</p></div>
        ) : (
          <>
            <div className="mt-5 h-72" aria-hidden="true">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={subjects.slice(0, 8)} margin={{ top: 8, right: 8, left: -20, bottom: 36 }}>
                  <CartesianGrid stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="subject" stroke="var(--text-muted)" fontSize={11} tickLine={false} interval={0} angle={-18} textAnchor="end" />
                  <YAxis stroke="var(--text-muted)" fontSize={11} tickLine={false} allowDecimals={false} />
                  <Tooltip contentStyle={{ background: 'var(--surface)', color: 'var(--text)', border: '1px solid var(--border)', borderRadius: 8 }} cursor={{ fill: 'var(--surface-subtle)' }} />
                  <Bar dataKey="count" name="Erros" fill="var(--primary)" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-5 overflow-x-auto">
              <table className="data-table">
                <caption className="sr-only">Erros registrados por disciplina</caption>
                <thead><tr><th>Disciplina</th><th className="text-right">Erros</th></tr></thead>
                <tbody>{subjects.slice(0, 8).map((item) => <tr key={item.subject}><td>{item.subject}</td><td className="text-right font-mono">{item.count}</td></tr>)}</tbody>
              </table>
            </div>
          </>
        )}
      </section>
    </div>
  );
};
