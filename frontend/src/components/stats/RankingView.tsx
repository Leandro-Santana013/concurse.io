import React, { useEffect, useState } from 'react';
import { Medal, RefreshCw, Trophy, UserRound } from 'lucide-react';
import { api } from '../../services/api';
import { RankingEntry } from '../../types/exam';

const UserAvatar: React.FC<{ name?: string | null; picture?: string | null }> = ({ name, picture }) => {
  const [hasError, setHasError] = useState(false);
  const initial = (name || 'C').trim().charAt(0).toUpperCase();

  if (picture && !hasError) {
    return (
      <img
        src={picture}
        alt=""
        className="h-9 w-9 shrink-0 rounded-full object-cover border border-[var(--border)]"
        referrerPolicy="no-referrer"
        onError={() => setHasError(true)}
      />
    );
  }

  return (
    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[var(--surface-subtle)] font-bold text-[var(--text)] text-xs border border-[var(--border)]">
      {initial}
    </span>
  );
};

export const RankingView: React.FC = () => {
  const [ranking, setRanking] = useState<RankingEntry[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setIsLoading(true); setError(null);
    try { setRanking(await api.getRanking()); }
    catch (err) { setError(err instanceof Error ? err.message : 'Não foi possível carregar o ranking.'); }
    finally { setIsLoading(false); }
  };
  useEffect(() => { void load(); }, []);

  if (isLoading) return <div className="space-y-3" aria-busy="true">{[1,2,3,4].map((item) => <div key={item} className="skeleton h-16" />)}</div>;
  if (error) return <div className="state-card" role="alert"><RefreshCw aria-hidden="true" /><div><h2>Não foi possível carregar o ranking</h2><p>{error}</p></div><button className="button-secondary" onClick={load}>Tentar novamente</button></div>;
  if (ranking.length === 0) return <div className="state-card text-center"><Trophy className="mx-auto" aria-hidden="true" /><h2>Ranking ainda vazio</h2><p>As posições aparecerão depois que houver tentativas concluídas.</p></div>;

  return (
    <div className="space-y-4">
      <div className="hidden overflow-x-auto rounded-xl border border-[var(--border)] bg-[var(--surface)] md:block">
        <table className="data-table">
          <caption className="sr-only">Ranking por questões resolvidas e taxa de acerto</caption>
          <thead>
            <tr>
              <th className="w-20">Posição</th>
              <th>Participante</th>
              <th className="text-right">Questões Resolvidas</th>
              <th className="text-right">Precisão</th>
            </tr>
          </thead>
          <tbody>
            {ranking.map((entry, index) => (
              <tr key={`${entry.name}-${index}`}>
                <td className="font-mono font-bold">
                  <span className="inline-flex items-center gap-1.5">
                    {index === 0 ? <Medal className="h-5 w-5 text-amber-500" aria-hidden="true" /> :
                     index === 1 ? <Medal className="h-5 w-5 text-slate-400" aria-hidden="true" /> :
                     index === 2 ? <Medal className="h-5 w-5 text-amber-700" aria-hidden="true" /> : null}
                    {index + 1}º
                  </span>
                </td>
                <td>
                  <div className="inline-flex items-center gap-3">
                    <UserAvatar name={entry.name} picture={entry.picture} />
                    <span className="font-semibold text-[var(--text)]">{entry.name || 'Concurseiro'}</span>
                  </div>
                </td>
                <td className="text-right font-mono">{entry.total_questions}</td>
                <td className="text-right font-mono font-bold text-[var(--primary)]">{entry.accuracy}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ol className="space-y-2 md:hidden">
        {ranking.map((entry, index) => (
          <li key={`${entry.name}-${index}`} className="flex items-center justify-between gap-4 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4">
            <div className="flex min-w-0 items-center gap-3">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--surface-subtle)] font-mono text-xs font-bold text-[var(--text-muted)]">
                {index + 1}
              </span>
              <UserAvatar name={entry.name} picture={entry.picture} />
              <div className="min-w-0">
                <p className="truncate font-semibold text-[var(--text)]">{entry.name || 'Concurseiro'}</p>
                <p className="text-xs text-[var(--text-muted)]">{entry.total_questions} questões</p>
              </div>
            </div>
            <strong className="font-mono text-base font-bold text-[var(--primary)]">{entry.accuracy}%</strong>
          </li>
        ))}
      </ol>
    </div>
  );
};
