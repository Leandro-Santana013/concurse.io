import React, { useEffect, useState } from 'react';
import { api } from '../../services/api';
import { Trophy, Medal, Award, User, Loader2, Crown } from 'lucide-react';

export const RankingView: React.FC = () => {
  const [ranking, setRanking] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const loadRanking = async () => {
      setIsLoading(true);
      try {
        const data = await api.getRanking();
        setRanking(data);
      } catch (e) {
        console.error('Erro ao carregar ranking:', e);
      } finally {
        setIsLoading(false);
      }
    };
    loadRanking();
  }, []);

  if (isLoading) {
    return (
      <div className="flex h-96 flex-col items-center justify-center text-slate-400">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-400" />
        <p className="mt-3 font-heading font-medium text-sm text-slate-300">Carregando ranking global de concurseiros...</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl animate-fadeIn p-4 sm:p-6 lg:p-8 space-y-8">
      <header className="text-center sm:text-left">
        <span className="inline-flex items-center gap-1.5 rounded-full glass-pill-amber px-3.5 py-1 text-xs font-bold">
          <Trophy className="h-3.5 w-3.5 text-yellow-400" /> Comunidade Competitiva
        </span>
        <h1 className="mt-3 font-heading text-2xl sm:text-3xl font-black text-white">Ranking Global de Concurseiros</h1>
        <p className="mt-1 text-sm text-slate-300 font-reading">
          Compare sua quantidade de questões resolvidas e taxa de precisão global.
        </p>
      </header>

      <div className="glass-card overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-white/10 bg-slate-900/60 text-[11px] font-bold uppercase tracking-wider text-slate-400 backdrop-blur-md">
            <tr>
              <th className="py-4 pl-6 pr-3">Posição</th>
              <th className="px-4 py-4">Concurseiro</th>
              <th className="px-4 py-4 text-center">Questões Resolvidas</th>
              <th className="py-4 pl-3 pr-6 text-right">Taxa de Acerto</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5 text-slate-200">
            {ranking.map((user, idx) => {
              let posBadge = <span className="font-mono font-bold text-slate-400">#{idx + 1}</span>;
              if (idx === 0)
                posBadge = (
                  <span className="inline-flex items-center gap-1 rounded-xl glass-pill-amber px-2.5 py-1 font-mono font-black text-amber-300 shadow-sm">
                    <Trophy className="h-3.5 w-3.5 text-amber-400" /> 1º Lugar
                  </span>
                );
              if (idx === 1)
                posBadge = (
                  <span className="inline-flex items-center gap-1 rounded-xl glass-pill px-2.5 py-1 font-mono font-black text-slate-200 border-slate-400/40 shadow-sm">
                    <Medal className="h-3.5 w-3.5 text-slate-300" /> 2º Lugar
                  </span>
                );
              if (idx === 2)
                posBadge = (
                  <span className="inline-flex items-center gap-1 rounded-xl glass-pill px-2.5 py-1 font-mono font-black text-amber-500 border-amber-600/40 shadow-sm">
                    <Award className="h-3.5 w-3.5 text-amber-500" /> 3º Lugar
                  </span>
                );

              return (
                <tr key={idx} className="transition hover:bg-white/[0.04]">
                  <td className="py-4 pl-6 pr-3">{posBadge}</td>
                  <td className="px-4 py-4">
                    <div className="flex items-center gap-3">
                      {user.picture ? (
                        <img
                          src={user.picture}
                          alt={user.name}
                          className="h-9 w-9 rounded-2xl object-cover border border-indigo-500/30"
                        />
                      ) : (
                        <div className="flex h-9 w-9 items-center justify-center rounded-2xl bg-gradient-to-tr from-slate-800 to-indigo-950 font-bold text-xs text-indigo-300 border border-white/10">
                          {user.name ? user.name[0].toUpperCase() : 'C'}
                        </div>
                      )}
                      <div>
                        <p className="font-heading font-bold text-white leading-none">{user.name || 'Concurseiro'}</p>
                        <span className="text-[10px] font-semibold text-slate-400">Membro Pro</span>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-4 text-center font-mono font-bold text-slate-300">
                    {user.total_questions}
                  </td>
                  <td className="py-4 pl-3 pr-6 text-right font-mono font-black text-emerald-400 text-base">
                    {user.accuracy}%
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
