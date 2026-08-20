import React, { useEffect, useState } from 'react';
import { api } from '../../services/api';
import { NotebookSubjectStat } from '../../types/exam';
import { useExam } from '../../context/ExamContext';
import { useUI } from '../../context/UIContext';
import {
  Bookmark,
  Play,
  RotateCcw,
  Sparkles,
  Loader2,
  AlertTriangle,
  Flame,
  CheckCircle2,
} from 'lucide-react';

interface ErrorNotebookViewProps {
  onStartExam?: () => void;
}

export const ErrorNotebookView: React.FC<ErrorNotebookViewProps> = ({ onStartExam }) => {
  const [subjectStats, setSubjectStats] = useState<NotebookSubjectStat[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [launchingSubject, setLaunchingSubject] = useState<string | null>(null);
  const { loadErrorNotebookExam } = useExam();
  const { showToast, navigateTo } = useUI();

  const handleStart = onStartExam || (() => navigateTo('exam'));

  const loadStats = async () => {
    setIsLoading(true);
    try {
      const data = await api.getNotebookStats();
      setSubjectStats(data);
    } catch (e: any) {
      console.error('Erro ao carregar caderno de erros:', e);
      showToast('error', 'Erro ao carregar caderno de erros', e.message);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadStats();
  }, []);

  const handleLaunchErrorExam = async (subject?: string) => {
    setLaunchingSubject(subject || 'all');
    try {
      await loadErrorNotebookExam(subject);
      showToast('info', 'Revisão Iniciada', `Caderno de erros montado com foco em ${subject || 'todas as disciplinas'}.`);
      handleStart();
    } catch (e: any) {
      showToast('warning', 'Aviso', e.message || 'Nenhuma questão com erro encontrada.');
    } finally {
      setLaunchingSubject(null);
    }
  };

  const totalErrors = subjectStats.reduce((acc, curr) => acc + curr.count, 0);

  return (
    <div className="mx-auto max-w-6xl animate-fadeIn p-4 sm:p-6 lg:p-8 space-y-8">
      {/* Top Bento Hero with Glassmorphic Rose Gradient */}
      <div className="glass-card relative overflow-hidden p-6 sm:p-10 flex flex-col md:flex-row items-start md:items-center justify-between gap-6 border-rose-500/25 bg-gradient-to-r from-rose-950/30 via-[#0E1626]/80 to-[#080C14]/90">
        <div className="absolute -left-12 -top-12 h-48 w-48 rounded-full bg-rose-500/15 blur-2xl pointer-events-none" />
        <div className="max-w-2xl relative z-10">
          <span className="inline-flex items-center gap-1.5 rounded-full glass-pill-rose px-3.5 py-1 text-xs font-bold">
            <AlertTriangle className="h-3.5 w-3.5 text-rose-400" /> Repetição Espaçada & Retenção
          </span>
          <h1 className="mt-3 font-heading text-2xl sm:text-3xl font-black text-white">
            Caderno de Erros Inteligente
          </h1>
          <p className="mt-2 text-sm text-slate-300 font-reading leading-relaxed">
            Revisar seus erros é a forma cientificamente mais rápida de subir sua nota de corte. Treine novamente cada questão errada até dominar o conteúdo.
          </p>
        </div>

        <button
          onClick={() => handleLaunchErrorExam()}
          disabled={totalErrors === 0 || Boolean(launchingSubject)}
          className="flex shrink-0 items-center gap-2 rounded-2xl bg-gradient-to-r from-rose-600 to-rose-700 px-6 py-4 font-heading font-bold text-sm text-white shadow-lg shadow-rose-600/30 hover:from-rose-500 hover:to-rose-600 border border-white/20 transition disabled:opacity-50 relative z-10"
        >
          {launchingSubject === 'all' ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <RotateCcw className="h-4 w-4" />
          )}
          <span>Resolver Todos os Erros ({totalErrors})</span>
        </button>
      </div>

      {/* Empty State */}
      {totalErrors === 0 && !isLoading && (
        <div className="flex h-64 flex-col items-center justify-center rounded-3xl glass-card text-center p-6 text-slate-400">
          <CheckCircle2 className="h-10 w-10 text-emerald-400 mb-2" />
          <p className="font-heading font-bold text-slate-200">Parabéns! Nenhum erro pendente</p>
          <p className="mt-1 text-xs text-slate-400 max-w-sm">
            Você não possui questões erradas registradas ou ainda não finalizou simulados com gabarito.
          </p>
        </div>
      )}

      {/* Grid of Subject Cards */}
      {subjectStats.length > 0 && (
        <div className="space-y-4">
          <h2 className="font-heading text-lg font-bold text-white">Erros Acumulados por Disciplina</h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {subjectStats.map((item, idx) => (
              <div
                key={idx}
                className="glass-card-interactive p-6 flex flex-col justify-between group hover:border-rose-500/40"
              >
                <div>
                  <div className="flex items-center justify-between">
                    <span className="rounded-xl glass-pill-rose px-3 py-1 font-mono text-xs font-black">
                      {item.count} erro(s)
                    </span>
                    <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Prioridade</span>
                  </div>
                  <h3 className="mt-3.5 font-heading text-base font-bold text-white line-clamp-2 group-hover:text-rose-200 transition">
                    {item.subject}
                  </h3>
                </div>

                <button
                  onClick={() => handleLaunchErrorExam(item.subject)}
                  disabled={Boolean(launchingSubject)}
                  className="mt-6 flex items-center justify-center gap-2 rounded-xl glass-btn-secondary py-3 text-xs font-heading font-bold text-slate-100 hover:text-white hover:border-rose-500/50 transition disabled:opacity-50 shadow-sm"
                >
                  {launchingSubject === item.subject ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Play className="h-3.5 w-3.5 fill-current text-rose-400" />
                  )}
                  <span>Revisar Disciplina</span>
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
