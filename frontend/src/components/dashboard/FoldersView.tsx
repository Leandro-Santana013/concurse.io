import React, { useEffect, useState } from 'react';
import { api } from '../../services/api';
import { Folder } from '../../types/exam';
import { useExam } from '../../context/ExamContext';
import { useUI } from '../../context/UIContext';
import {
  Folder as FolderIcon,
  Play,
  Award,
  Sparkles,
  FileQuestion,
  Loader2,
  CheckCircle2,
  BookOpen,
  Layers,
  ArrowUpRight,
} from 'lucide-react';

interface FoldersViewProps {
  onStartExam?: () => void;
}

export const FoldersView: React.FC<FoldersViewProps> = ({ onStartExam }) => {
  const [folders, setFolders] = useState<Folder[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadingExamId, setLoadingExamId] = useState<number | null>(null);
  const { loadAndStartExam, generateCustomExam } = useExam();
  const { navigateTo, showToast } = useUI();

  const handleStart = onStartExam || (() => navigateTo('exam'));

  const loadFolders = async () => {
    setIsLoading(true);
    try {
      const data = await api.getFolders();
      setFolders(data);
    } catch (e: any) {
      console.error('Erro ao carregar pastas:', e);
      showToast('error', 'Erro ao carregar pastas', e.message);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadFolders();
  }, []);

  const handleLaunchExam = async (examId: number) => {
    setLoadingExamId(examId);
    try {
      await loadAndStartExam(examId);
      handleStart();
    } catch (e: any) {
      showToast('error', 'Falha ao abrir simulado', e.message);
    } finally {
      setLoadingExamId(null);
    }
  };

  const handleGenerateCustom = async () => {
    setIsLoading(true);
    try {
      await generateCustomExam(20);
      showToast('success', 'Simulado Gerado', '20 questões selecionadas aleatoriamente.');
      handleStart();
    } catch (e: any) {
      showToast('error', 'Erro ao gerar simulado', e.message);
    } finally {
      setIsLoading(false);
    }
  };

  const totalExamsCount = folders.reduce((acc, f) => acc + f.exams.length, 0);

  if (isLoading && folders.length === 0) {
    return (
      <div className="flex h-96 flex-col items-center justify-center text-slate-400">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-400" />
        <p className="mt-3 font-heading font-medium text-sm text-slate-300">Carregando sua biblioteca de provas...</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl animate-fadeIn p-4 sm:p-6 lg:p-8 space-y-8">
      {/* Top Bento Header with Glassmorphism */}
      <div className="grid gap-4 md:grid-cols-3">
        {/* Main Banner Card (2 Cols) */}
        <div className="glass-card relative overflow-hidden p-6 sm:p-8 md:col-span-2 flex flex-col justify-between">
          <div className="absolute -right-12 -top-12 h-48 w-48 rounded-full bg-indigo-500/15 blur-2xl pointer-events-none" />
          <div className="relative z-10">
            <span className="inline-flex items-center gap-1.5 rounded-full glass-pill-indigo px-3.5 py-1 text-xs font-bold">
              <Layers className="h-3.5 w-3.5" /> Biblioteca de Simulados
            </span>
            <h1 className="mt-3 font-heading text-2xl sm:text-3xl font-black text-white">
              Minhas Provas & Pastas
            </h1>
            <p className="mt-2 text-sm text-slate-300 font-reading leading-relaxed">
              Acesse seus cadernos organizados por banca examinadora e órgão, ou gere um simulado rápido de 20 questões mistas com cronômetro oficial.
            </p>
          </div>

          <div className="mt-6 pt-4 border-t border-white/10 flex items-center gap-4 relative z-10">
            <button
              onClick={handleGenerateCustom}
              className="flex items-center gap-2 rounded-2xl glass-btn-primary px-6 py-3.5 font-heading font-bold text-sm text-white"
            >
              <Sparkles className="h-4 w-4" />
              <span>Gerar Simulado Geral (20q)</span>
            </button>
          </div>
        </div>

        {/* Quick Metric Bento Card (1 Col) */}
        <div className="glass-card p-6 flex flex-col justify-between">
          <div>
            <span className="text-xs font-bold uppercase tracking-wider text-slate-400">Resumo da Biblioteca</span>
            <div className="mt-4 flex items-baseline gap-2">
              <span className="font-heading text-3xl font-black text-white">{totalExamsCount}</span>
              <span className="text-xs font-semibold text-slate-400">provas salvas</span>
            </div>
            <div className="mt-1 flex items-baseline gap-2">
              <span className="font-heading text-2xl font-bold text-indigo-400">{folders.length}</span>
              <span className="text-xs font-semibold text-slate-400">pastas de bancas</span>
            </div>
          </div>

          <div className="mt-4 rounded-2xl glass-pill px-3.5 py-2.5 flex items-center justify-between">
            <span className="text-xs font-medium text-slate-300">Modo de Treino</span>
            <span className="text-xs font-mono font-bold text-emerald-400">Oficial + Gabarito</span>
          </div>
        </div>
      </div>

      {folders.length === 0 && !isLoading && (
        <div className="flex h-64 flex-col items-center justify-center rounded-3xl glass-card text-center p-6 text-slate-400">
          <FolderIcon className="h-10 w-10 stroke-[1.5] text-slate-500 mb-2" />
          <p className="font-heading font-semibold text-slate-200">Nenhuma prova salva ainda</p>
          <p className="mt-1 text-xs text-slate-400 max-w-sm">
            Vá até a aba "Buscar Provas" para indexar sua primeira prova ou concurso.
          </p>
          <button
            onClick={() => navigateTo('search')}
            className="mt-4 flex items-center gap-1.5 rounded-xl glass-btn-primary px-4 py-2 text-xs font-bold text-white"
          >
            Buscar Novas Provas <ArrowUpRight className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {/* Folders List in Bento Layout */}
      <div className="space-y-8">
        {folders.map((folder) => (
          <div key={folder.id} className="glass-card p-6 sm:p-7">
            {/* Folder Header */}
            <div className="flex items-center justify-between border-b border-white/10 pb-4">
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-2xl glass-pill-indigo text-indigo-400">
                  <FolderIcon className="h-5 w-5" />
                </div>
                <div>
                  <h2 className="font-heading text-lg font-bold text-white">{folder.name}</h2>
                  <p className="text-xs font-semibold text-slate-400">{folder.exams.length} caderno(s) disponível(is)</p>
                </div>
              </div>
            </div>

            {/* Exams Cards Grid */}
            <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {folder.exams.map((exam) => (
                <div
                  key={exam.id}
                  className="glass-card-interactive p-5 flex flex-col justify-between group"
                >
                  <div>
                    <div className="flex items-center justify-between">
                      <span className="flex items-center gap-1.5 text-xs font-mono font-bold text-indigo-300">
                        <FileQuestion className="h-3.5 w-3.5 text-indigo-400" /> {exam.question_count} Qs
                      </span>
                      {exam.best_score !== null && (
                        <span className="rounded-lg glass-pill-emerald px-2 py-0.5 text-xs font-mono font-bold">
                          Melhor: {exam.best_score}%
                        </span>
                      )}
                    </div>
                    <h3 className="mt-3 font-heading text-sm font-bold text-white line-clamp-2 group-hover:text-indigo-300 transition" title={exam.title}>
                      {exam.title}
                    </h3>
                  </div>

                  <div className="mt-5 flex items-center justify-between border-t border-white/10 pt-4">
                    <span className="text-[11px] font-semibold text-slate-400">
                      {exam.attempt_count > 0 ? `${exam.attempt_count} tentativa(s)` : 'Não iniciado'}
                    </span>
                    <button
                      onClick={() => handleLaunchExam(exam.id)}
                      disabled={loadingExamId === exam.id}
                      className="flex items-center gap-1.5 rounded-xl glass-btn-primary px-4 py-2 text-xs font-heading font-bold text-white disabled:opacity-50"
                    >
                      {loadingExamId === exam.id ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Play className="h-3.5 w-3.5 fill-current" />
                      )}
                      Iniciar Prova
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
