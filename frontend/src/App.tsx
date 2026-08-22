import React from 'react';
import { Sidebar } from './components/layout/Sidebar';
import { Navbar } from './components/layout/Navbar';
import { SearchHub } from './components/dashboard/SearchHub';
import { FoldersView } from './components/dashboard/FoldersView';
import { ExamSimulator } from './components/exam/ExamSimulator';
import { AnalyticsView } from './components/stats/AnalyticsView';
import { ErrorNotebookView } from './components/stats/ErrorNotebookView';
import { RankingView } from './components/stats/RankingView';
import { useUI } from './context/UIContext';
import { useExam } from './context/ExamContext';

export const App: React.FC = () => {
  const { currentView, navigateTo, isMobileSidebarOpen, toggleMobileSidebar, setMobileSidebarOpen } = useUI();
  const { isZenMode, loadAndStartExam } = useExam();

  const handleExamReady = async (examId: number) => {
    try {
      await loadAndStartExam(examId);
      navigateTo('exam');
    } catch (e) {
      console.error('Falha ao abrir prova pronta:', e);
    }
  };

  const handleStartExam = () => {
    navigateTo('exam');
  };

  const handleBackToDashboard = () => {
    navigateTo('folders');
  };

  return (
    <div className="relative flex min-h-screen bg-[#080C14] text-slate-100 antialiased selection:bg-indigo-500 selection:text-white overflow-x-hidden">
      {/* Background Ambient Aurora Orbs for Glassmorphism refraction */}
      <div className="aurora-mesh" aria-hidden="true">
        <div className="aurora-orb-1" />
        <div className="aurora-orb-2" />
        <div className="aurora-orb-3" />
      </div>

      {/* Sidebar (hidden only when in Exam View and Zen Mode is active) */}
      {!(currentView === 'exam' && isZenMode) && (
        <Sidebar
          currentView={currentView}
          onNavigate={(view) => navigateTo(view)}
          isOpenMobile={isMobileSidebarOpen}
          onCloseMobile={() => setMobileSidebarOpen(false)}
        />
      )}

      {/* Main Content Area with Glass z-index hierarchy */}
      <div className="relative z-10 flex flex-1 flex-col overflow-x-hidden">
        {!(currentView === 'exam' && isZenMode) && (
          <Navbar onToggleMobileSidebar={toggleMobileSidebar} />
        )}

        <main className="flex-1 pb-16">
          {currentView === 'search' && <SearchHub onExamReady={handleExamReady} />}
          {currentView === 'folders' && <FoldersView onStartExam={handleStartExam} />}
          {currentView === 'stats' && <AnalyticsView />}
          {currentView === 'errors' && <ErrorNotebookView onStartExam={handleStartExam} />}
          {currentView === 'ranking' && <RankingView />}
          {currentView === 'exam' && (
            <ExamSimulator
              onBackToDashboard={handleBackToDashboard}
              onOpenNotebook={() => navigateTo('errors')}
            />
          )}
        </main>
      </div>
    </div>
  );
};
