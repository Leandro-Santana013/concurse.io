import React, { useEffect, useState } from 'react';
import { api } from '../../services/api';
import { GlobalStats } from '../../types/exam';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import {
  Trophy,
  Flame,
  Clock,
  Target,
  CheckCircle2,
  BookOpen,
  Sparkles,
  Loader2,
  BarChart3,
  TrendingUp,
} from 'lucide-react';

export const AnalyticsView: React.FC = () => {
  const [stats, setStats] = useState<GlobalStats | null>(null);
  const [subjectStats, setSubjectStats] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const loadStats = async () => {
      setIsLoading(true);
      try {
        const [global, subjects] = await Promise.all([
          api.getGlobalStats(),
          api.getNotebookStats(),
        ]);
        setStats(global);
        setSubjectStats(subjects);
      } catch (e) {
        console.error('Erro ao carregar estatísticas:', e);
      } finally {
        setIsLoading(false);
      }
    };
    loadStats();
  }, []);

  if (isLoading || !stats) {
    return (
      <div className="flex h-96 flex-col items-center justify-center text-slate-400">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-400" />
        <p className="mt-3 font-heading font-medium text-sm text-slate-300">Carregando seus dados de telemetria...</p>
      </div>
    );
  }

  const statCards = [
    { label: 'Provas Feitas', value: stats.total_exams, icon: BookOpen, color: 'text-indigo-400', pillClass: 'glass-pill-indigo' },
    { label: 'Questões Feitas', value: stats.total_questions, icon: Target, color: 'text-purple-400', pillClass: 'glass-pill' },
    { label: 'Precisão Geral', value: `${stats.global_accuracy}%`, icon: CheckCircle2, color: 'text-emerald-400', pillClass: 'glass-pill-emerald' },
    { label: 'Ofensiva (Dias)', value: stats.streak, icon: Flame, color: 'text-amber-400', pillClass: 'glass-pill-amber' },
    { label: 'Tempo de Estudo', value: stats.study_time, icon: Clock, color: 'text-cyan-400', pillClass: 'glass-pill-cyan' },
    { label: 'Posição Ranking', value: stats.rank, icon: Trophy, color: 'text-yellow-400', pillClass: 'glass-pill-amber' },
  ];

  return (
    <div className="mx-auto max-w-6xl animate-fadeIn p-4 sm:p-6 lg:p-8 space-y-8">
      {/* Header */}
      <div>
        <span className="inline-flex items-center gap-1.5 rounded-full glass-pill-indigo px-3.5 py-1 text-xs font-bold">
          <BarChart3 className="h-3.5 w-3.5" /> Telemetria de Estudos
        </span>
        <h1 className="mt-3 font-heading text-2xl sm:text-3xl font-black text-white">Meu Desempenho Global</h1>
        <p className="mt-1 text-sm text-slate-300 font-reading">
          Acompanhe sua taxa de retenção, tempo médio de resolução e pontos de melhoria contínua.
        </p>
      </div>

      {/* Bento 6-KPI Grid with Glassmorphism */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        {statCards.map((card, idx) => {
          const Icon = card.icon;
          return (
            <div
              key={idx}
              className="glass-card-interactive p-5 flex flex-col justify-between"
            >
              <div className={`inline-flex h-10 w-10 items-center justify-center rounded-2xl ${card.pillClass} ${card.color}`}>
                <Icon className="h-5 w-5" />
              </div>
              <div className="mt-4">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">{card.label}</span>
                <p className="mt-1 font-mono text-2xl font-black text-white">{card.value}</p>
              </div>
            </div>
          );
        })}
      </div>

      {/* Chart: Weak Points / Errors by Subject in Bento Card */}
      {subjectStats.length > 0 && (
        <div className="glass-card p-6 sm:p-8 space-y-6">
          <div className="flex items-center justify-between border-b border-white/10 pb-4">
            <div>
              <h2 className="font-heading text-lg font-bold text-white">Pontos de Atenção por Disciplina</h2>
              <p className="text-xs text-slate-400 mt-0.5">Matérias com maior volume de erros registrados no seu histórico</p>
            </div>
            <div className="flex items-center gap-2 text-xs font-bold glass-pill-rose px-3.5 py-1.5 rounded-xl">
              <TrendingUp className="h-3.5 w-3.5" /> Maior Foco Necessário
            </div>
          </div>

          <div className="h-80 w-full pt-2">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={subjectStats.slice(0, 8)} margin={{ top: 10, right: 10, left: -20, bottom: 20 }}>
                <XAxis
                  dataKey="subject"
                  stroke="#94a3b8"
                  fontSize={11}
                  tickLine={false}
                  interval={0}
                  angle={-15}
                  textAnchor="end"
                />
                <YAxis stroke="#94a3b8" fontSize={11} tickLine={false} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: 'rgba(15, 23, 42, 0.90)',
                    backdropFilter: 'blur(16px)',
                    border: '1px solid rgba(255, 255, 255, 0.15)',
                    borderRadius: '16px',
                    boxShadow: '0 15px 35px -5px rgba(0, 0, 0, 0.6)',
                  }}
                  itemStyle={{ color: '#F8FAFC', fontWeight: 'bold' }}
                />
                <Bar dataKey="count" fill="#6366f1" radius={[8, 8, 0, 0]}>
                  {subjectStats.map((_, index) => (
                    <Cell key={`cell-${index}`} fill={index === 0 ? '#f43f5e' : '#6366f1'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
};
