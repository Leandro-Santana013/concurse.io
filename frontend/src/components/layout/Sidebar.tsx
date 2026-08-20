import React from 'react';
import {
  Search,
  BookOpen,
  BarChart3,
  Bookmark,
  Trophy,
  GraduationCap,
  Sparkles,
  Flame,
} from 'lucide-react';
import { ViewType, useUI } from '../../context/UIContext';

interface SidebarProps {
  currentView?: ViewType;
  onNavigate?: (view: ViewType) => void;
  isOpenMobile?: boolean;
  onCloseMobile?: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentView: propView,
  onNavigate: propNavigate,
  isOpenMobile: propIsOpen,
  onCloseMobile: propOnClose,
}) => {
  const ui = useUI();
  const currentView = propView || ui.currentView;
  const onNavigate = propNavigate || ui.navigateTo;
  const isOpenMobile = propIsOpen ?? ui.isMobileSidebarOpen;
  const onCloseMobile = propOnClose || (() => ui.setMobileSidebarOpen(false));

  const menuItems = [
    { id: 'search' as ViewType, label: 'Buscar Provas', icon: Search, badge: 'IA' },
    { id: 'folders' as ViewType, label: 'Minhas Pastas', icon: BookOpen },
    { id: 'stats' as ViewType, label: 'Meu Desempenho', icon: BarChart3 },
    { id: 'errors' as ViewType, label: 'Caderno de Erros', icon: Bookmark, badgeColor: 'glass-pill-rose' },
    { id: 'ranking' as ViewType, label: 'Ranking Global', icon: Trophy },
  ];

  return (
    <>
      {/* Mobile Backdrop */}
      {isOpenMobile && (
        <div
          onClick={onCloseMobile}
          className="fixed inset-0 z-40 bg-black/75 backdrop-blur-lg transition-opacity lg:hidden"
          aria-hidden="true"
        />
      )}

      {/* Sidebar Container */}
      <aside
        aria-label="Menu Principal"
        className={`fixed inset-y-0 left-0 z-40 flex w-72 flex-col glass-sidebar transition-transform duration-300 ease-in-out lg:static lg:translate-x-0 ${
          isOpenMobile ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        {/* Brand Logo with Glass Glow */}
        <div className="flex h-20 items-center gap-3.5 px-6 border-b border-white/10">
          <div className="relative flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-tr from-indigo-600 via-indigo-500 to-violet-500 text-white shadow-lg shadow-indigo-600/35 ring-1 ring-white/30">
            <GraduationCap className="h-6 w-6" />
            <div className="absolute -top-0.5 -right-0.5 h-2.5 w-2.5 rounded-full bg-emerald-400 ring-2 ring-[#080C14] shadow-sm" />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="font-heading text-lg font-black tracking-tight text-white">concurse.io</span>
              <span className="rounded-lg bg-indigo-500/20 px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-wider text-indigo-300 border border-indigo-400/30 shadow-sm">
                PRO
              </span>
            </div>
            <span className="block text-[11px] font-medium text-slate-400">
              Treinador de Alto Rendimento
            </span>
          </div>
        </div>

        {/* Navigation Menu */}
        <nav className="flex-1 space-y-1.5 p-4">
          <p className="px-3 pb-2 text-[10px] font-bold uppercase tracking-wider text-slate-400/80">
            Módulos de Estudo
          </p>
          {menuItems.map((item) => {
            const Icon = item.icon;
            const isActive = currentView === item.id;

            return (
              <button
                key={item.id}
                onClick={() => {
                  onNavigate(item.id);
                  onCloseMobile();
                }}
                className={`group flex w-full items-center justify-between rounded-2xl px-4 py-3 text-sm font-semibold transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 ${
                  isActive
                    ? 'bg-gradient-to-r from-indigo-600/90 to-violet-600/90 text-white shadow-lg shadow-indigo-600/30 border border-white/20'
                    : 'text-slate-400 hover:bg-white/[0.06] hover:text-slate-100 hover:border hover:border-white/10'
                }`}
              >
                <div className="flex items-center gap-3.5">
                  <Icon className={`h-4 w-4 shrink-0 transition-transform group-hover:scale-110 ${isActive ? 'text-white' : 'text-slate-400 group-hover:text-indigo-400'}`} />
                  <span className="font-heading tracking-wide">{item.label}</span>
                </div>

                {item.badge && (
                  <span className={`rounded-lg px-2 py-0.5 text-[10px] font-bold tracking-wider ${item.badgeColor || 'glass-pill-indigo'}`}>
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        {/* Bento Widget Footer: Streak & Version */}
        <div className="p-4 border-t border-white/10 space-y-3">
          <div className="rounded-2xl border border-amber-500/30 bg-gradient-to-r from-amber-950/40 via-slate-900/60 to-slate-900/40 p-3.5 flex items-center justify-between backdrop-blur-xl shadow-lg shadow-amber-500/5">
            <div className="flex items-center gap-2.5">
              <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-amber-500/20 text-amber-400 border border-amber-500/30 shadow-inner">
                <Flame className="h-4 w-4 animate-pulse" />
              </div>
              <div>
                <p className="text-xs font-bold text-slate-200 font-heading">Ofensiva Diária</p>
                <p className="text-[10px] text-amber-400 font-semibold">Meta de hoje ativa</p>
              </div>
            </div>
            <span className="text-xs font-mono font-black text-amber-300">⚡ Ativo</span>
          </div>

          <div className="text-center text-[11px] font-medium text-slate-400/80">
            concurse.io v2.0 • AeroGlass UI
          </div>
        </div>
      </aside>
    </>
  );
};
export type { ViewType };
