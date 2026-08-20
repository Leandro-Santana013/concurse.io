import React from 'react';
import { Menu, CloudDownload, Sparkles, BookOpen, Flame, ChevronRight } from 'lucide-react';
import { useUI } from '../../context/UIContext';
import { useExam } from '../../context/ExamContext';

interface NavbarProps {
  onToggleMobileSidebar?: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({ onToggleMobileSidebar }) => {
  const { toggleMobileSidebar: uiToggle, activeDownloadsCount, navigateTo } = useUI();
  const { activeExam } = useExam();
  const handleToggle = onToggleMobileSidebar || uiToggle;

  return (
    <header className="sticky top-0 z-30 flex h-20 items-center justify-between glass-navbar px-4 sm:px-8">
      <div className="flex items-center gap-3">
        <button
          onClick={handleToggle}
          aria-label="Abrir Menu de Navegação"
          className="flex h-10 w-10 items-center justify-center rounded-2xl glass-btn-secondary text-slate-300 hover:text-white transition lg:hidden"
        >
          <Menu className="h-5 w-5" />
        </button>

        {/* Active Exam Floating Pill with Glass Glow if exam is running in background */}
        {activeExam && (
          <button
            onClick={() => navigateTo('exam')}
            className="hidden md:flex items-center gap-2 rounded-2xl glass-pill-indigo px-4 py-2 text-xs font-semibold hover:bg-indigo-600/20 transition group"
          >
            <BookOpen className="h-4 w-4 text-indigo-400 group-hover:scale-110 transition-transform" />
            <span className="max-w-[220px] truncate font-heading">{activeExam.title}</span>
            <span className="rounded-full bg-indigo-500/30 px-2 py-0.5 text-[10px] font-bold text-indigo-200 border border-indigo-400/30">
              Em andamento
            </span>
            <ChevronRight className="h-3.5 w-3.5 text-indigo-400 group-hover:translate-x-0.5 transition-transform" />
          </button>
        )}
      </div>

      <div className="flex items-center gap-4">
        {/* Active Downloads SSE Indicator */}
        {activeDownloadsCount > 0 && (
          <div className="flex items-center gap-2 rounded-2xl glass-pill-cyan px-3.5 py-1.5 text-xs font-bold animate-pulse">
            <CloudDownload className="h-4 w-4 text-cyan-300" />
            <span>{activeDownloadsCount} processando PDF</span>
          </div>
        )}

        {/* User Profile Bento Pill */}
        <div className="flex items-center gap-3 border-l border-white/10 pl-4">
          <div className="relative">
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-gradient-to-tr from-indigo-600 via-indigo-500 to-violet-500 font-black text-sm text-white shadow-lg shadow-indigo-500/30 ring-1 ring-white/30">
              C
            </div>
            <div className="absolute -bottom-0.5 -right-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-amber-400 text-[9px] text-slate-950 font-black ring-2 ring-[#080C14] shadow-sm">
              ★
            </div>
          </div>
          <div className="hidden sm:block text-left">
            <p className="text-xs font-bold text-white font-heading tracking-wide">Concurseiro</p>
            <p className="text-[10px] font-semibold text-emerald-400 flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-ping" /> Plano Pro Ativo
            </p>
          </div>
        </div>
      </div>
    </header>
  );
};
