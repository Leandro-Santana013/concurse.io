import React, { useEffect, useState } from 'react';
import { useExam } from '../../context/ExamContext';
import { useUI } from '../../context/UIContext';
import { MathRenderer } from './MathRenderer';
import {
  Clock,
  ArrowLeft,
  ArrowRight,
  Maximize2,
  Minimize2,
  Bookmark,
  CheckCircle2,
  XCircle,
  RotateCcw,
  Sparkles,
  Award,
  Eye,
  Zap,
  Scissors,
  LayoutGrid,
  Type,
  HelpCircle,
  X,
} from 'lucide-react';

interface ExamSimulatorProps {
  onBackToDashboard?: () => void;
  onOpenNotebook?: () => void;
}

export const ExamSimulator: React.FC<ExamSimulatorProps> = ({
  onBackToDashboard,
  onOpenNotebook,
}) => {
  const {
    activeExam,
    currentIdx,
    currentQuestion,
    currentQuestionNum,
    totalQuestions,
    progressPercentage,
    answers,
    flaggedQuestions,
    elapsedSeconds,
    isTimerRunning,
    isImmediateFeedback,
    isZenMode,
    isFinished,
    attemptResult,
    eliminatedOptions,
    toggleEliminateOption,
    selectAnswer,
    toggleFlagQuestion,
    setQuestionIdx,
    nextQuestion,
    prevQuestion,
    tickTimer,
    toggleTimer,
    toggleImmediateFeedback,
    toggleZenMode,
    submitExamAttempt,
    resetExam,
    formatTime,
  } = useExam();

  const { fontSize, setFontSize, navigateTo, showToast } = useUI();

  const [selectedImageZoom, setSelectedImageZoom] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [resultFilter, setResultFilter] = useState<'all' | 'errors' | 'correct'>('all');
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [showShortcutsModal, setShowShortcutsModal] = useState(false);

  // Timer Tick
  useEffect(() => {
    if (!isTimerRunning || isFinished) return;
    const interval = setInterval(() => {
      tickTimer();
    }, 1000);
    return () => clearInterval(interval);
  }, [isTimerRunning, isFinished, tickTimer]);

  // Keyboard Shortcuts
  useEffect(() => {
    if (isFinished || !activeExam) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (['INPUT', 'TEXTAREA'].includes((e.target as HTMLElement).tagName)) return;

      const q = activeExam.questions[currentIdx];
      if (!q) return;
      const qNum = q.numero_questao || String(currentIdx + 1);
      const optionKeys = Object.keys(q.options);
      const key = e.key.toUpperCase();

      // Options 1-5 or A-E
      if (['1', 'A'].includes(key) && optionKeys.length >= 1) {
        selectAnswer(qNum, optionKeys[0]);
      } else if (['2', 'B'].includes(key) && optionKeys.length >= 2) {
        selectAnswer(qNum, optionKeys[1]);
      } else if (['3', 'C'].includes(key) && optionKeys.length >= 3) {
        selectAnswer(qNum, optionKeys[2]);
      } else if (['4', 'D'].includes(key) && optionKeys.length >= 4) {
        selectAnswer(qNum, optionKeys[3]);
      } else if (['5', 'E'].includes(key) && optionKeys.length >= 5) {
        selectAnswer(qNum, optionKeys[4]);
      } else if (e.key === 'ArrowRight') {
        nextQuestion();
      } else if (e.key === 'ArrowLeft') {
        prevQuestion();
      } else if (e.code === 'Space') {
        e.preventDefault();
        toggleFlagQuestion(qNum);
      } else if (e.key === 'z' || e.key === 'Z') {
        toggleZenMode();
      } else if (e.key === 'g' || e.key === 'G') {
        setIsDrawerOpen((prev) => !prev);
      } else if (e.key === '?') {
        setShowShortcutsModal((prev) => !prev);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [activeExam, currentIdx, isFinished, selectAnswer, nextQuestion, prevQuestion, toggleFlagQuestion, toggleZenMode]);

  const handleBack = onBackToDashboard || (() => navigateTo('folders'));

  if (!activeExam) {
    return (
      <div className="flex h-96 flex-col items-center justify-center text-slate-400 p-6">
        <p className="font-heading text-lg font-bold text-slate-300">Nenhum simulado ativo no momento.</p>
        <p className="text-xs text-slate-400 mt-1">Escolha uma prova na sua biblioteca para começar a praticar.</p>
        <button
          onClick={handleBack}
          className="mt-6 flex items-center gap-2 rounded-2xl glass-btn-primary px-6 py-3 font-heading font-bold text-sm text-white"
        >
          <ArrowLeft className="h-4 w-4" /> Ir para Minhas Pastas
        </button>
      </div>
    );
  }

  const questions = activeExam.questions;
  const currentQ = questions[currentIdx] || currentQuestion;
  const qNum = currentQ ? (currentQ.numero_questao || String(currentIdx + 1)) : '1';

  const handleFinish = async () => {
    if (isSubmitting) return;
    const unansweredCount = questions.length - Object.keys(answers).filter((k) => answers[k]).length;
    if (unansweredCount > 0) {
      const confirm = window.confirm(
        `Você ainda possui ${unansweredCount} questão(ões) sem resposta. Deseja realmente finalizar o simulado?`
      );
      if (!confirm) return;
    }

    setIsSubmitting(true);
    try {
      await submitExamAttempt();
      showToast('success', 'Simulado Concluído!', 'Confira sua nota e o gabarito detalhado.');
    } catch (e: any) {
      showToast('error', 'Erro ao finalizar simulado', e.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  // --- RESULTS VIEW ---
  if (isFinished && attemptResult) {
    const filteredEntries = Object.entries(attemptResult.detailed_answers).filter(([_, data]) => {
      if (resultFilter === 'errors') return !data.is_correct;
      if (resultFilter === 'correct') return data.is_correct;
      return true;
    });

    const avgSecondsPerQ = Math.round(attemptResult.elapsed_seconds / (attemptResult.total || 1));

    return (
      <div className="mx-auto max-w-6xl animate-fadeIn p-4 sm:p-6 lg:p-8 space-y-8">
        {/* Score Glass Card */}
        <div className="glass-card relative overflow-hidden p-6 sm:p-10 text-center">
          <div className="absolute -top-24 -left-24 h-56 w-56 rounded-full bg-indigo-500/20 blur-3xl pointer-events-none" />
          <div className="absolute -bottom-24 -right-24 h-56 w-56 rounded-full bg-emerald-500/20 blur-3xl pointer-events-none" />

          <div className="inline-flex h-20 w-20 items-center justify-center rounded-3xl glass-pill-indigo text-indigo-300 shadow-inner">
            <Award className="h-10 w-10 text-indigo-400" />
          </div>

          <h1 className="mt-4 font-heading text-3xl font-black text-white">Simulado Concluído!</h1>
          <p className="mt-1 text-sm font-semibold text-slate-300 max-w-xl mx-auto truncate">{activeExam.title}</p>

          {/* KPI Metrics Grid */}
          <div className="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-4">
            <div className="glass-card p-4">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-400">Nota Final</span>
              <p className={`mt-1 font-mono text-3xl sm:text-4xl font-black ${attemptResult.percentage >= 70 ? 'text-emerald-400' : 'text-amber-400'}`}>
                {attemptResult.percentage}%
              </p>
            </div>
            <div className="glass-card p-4">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-400">Total de Acertos</span>
              <p className="mt-1 font-mono text-3xl sm:text-4xl font-black text-emerald-400">
                {attemptResult.score} <span className="text-lg text-slate-400 font-sans">/ {attemptResult.total}</span>
              </p>
            </div>
            <div className="glass-card p-4">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-400">Tempo Total</span>
              <p className="mt-1 font-mono text-3xl sm:text-4xl font-black text-indigo-300">
                {formatTime(attemptResult.elapsed_seconds)}
              </p>
            </div>
            <div className="glass-card p-4">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-400">Média p/ Questão</span>
              <p className="mt-1 font-mono text-3xl sm:text-4xl font-black text-cyan-300">
                {avgSecondsPerQ}s
              </p>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <button
              onClick={() => {
                resetExam();
                handleBack();
              }}
              className="flex items-center gap-2 rounded-2xl glass-btn-secondary px-6 py-3.5 font-heading font-bold text-sm text-slate-200 hover:text-white"
            >
              <ArrowLeft className="h-4 w-4" /> Voltar às Pastas
            </button>
            <button
              onClick={() => {
                const examToRedo = { ...activeExam };
                resetExam();
                useExam().startExam(examToRedo);
              }}
              className="flex items-center gap-2 rounded-2xl glass-btn-primary px-6 py-3.5 font-heading font-bold text-sm text-white"
            >
              <RotateCcw className="h-4 w-4" /> Refazer Simulado
            </button>
            {onOpenNotebook && (
              <button
                onClick={onOpenNotebook}
                className="flex items-center gap-2 rounded-2xl glass-pill-rose px-6 py-3.5 font-heading font-bold text-sm hover:bg-rose-500/20 transition"
              >
                <Bookmark className="h-4 w-4" /> Ver no Caderno de Erros
              </button>
            )}
          </div>
        </div>

        {/* Subject Breakdown Glass Card */}
        <div className="glass-card p-6 sm:p-8">
          <h2 className="font-heading text-lg font-bold text-white mb-4">Desempenho por Disciplina</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {Object.entries(attemptResult.feedback_per_subject).map(([subject, stats]) => (
              <div key={subject} className="flex items-center justify-between rounded-2xl glass-pill p-4">
                <div>
                  <p className="font-heading font-bold text-slate-200">{subject}</p>
                  <p className="text-xs text-slate-400 font-medium">
                    {stats.correct} de {stats.total} questões corretas
                  </p>
                </div>
                <span className={`font-mono text-xl font-black ${stats.percentage >= 70 ? 'text-emerald-400' : 'text-amber-400'}`}>
                  {stats.percentage}%
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Detailed Question Review List */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="font-heading text-lg font-bold text-white">Gabarito e Revisão Detalhada</h2>
            <div className="flex gap-1.5 rounded-2xl glass-pill p-1">
              <button
                onClick={() => setResultFilter('all')}
                className={`rounded-xl px-3.5 py-1.5 text-xs font-bold transition ${resultFilter === 'all' ? 'glass-btn-primary text-white' : 'text-slate-400 hover:text-white'}`}
              >
                Todas ({attemptResult.total})
              </button>
              <button
                onClick={() => setResultFilter('errors')}
                className={`rounded-xl px-3.5 py-1.5 text-xs font-bold transition ${resultFilter === 'errors' ? 'bg-rose-600 text-white shadow-md' : 'text-slate-400 hover:text-white'}`}
              >
                Erros ({attemptResult.total - attemptResult.score})
              </button>
              <button
                onClick={() => setResultFilter('correct')}
                className={`rounded-xl px-3.5 py-1.5 text-xs font-bold transition ${resultFilter === 'correct' ? 'bg-emerald-600 text-white shadow-md' : 'text-slate-400 hover:text-white'}`}
              >
                Acertos ({attemptResult.score})
              </button>
            </div>
          </div>

          <div className="space-y-4">
            {filteredEntries.map(([qIdxStr, data]) => {
              const originalQ = questions.find((q) => (q.numero_questao || String(q.id)) === qIdxStr);
              if (!originalQ) return null;

              return (
                <div
                  key={qIdxStr}
                  className={`rounded-3xl border p-6 transition-all ${
                    data.is_correct
                      ? 'border-emerald-500/30 bg-emerald-950/20 backdrop-blur-md'
                      : 'border-rose-500/30 bg-rose-950/20 backdrop-blur-md'
                  }`}
                >
                  <div className="flex items-center justify-between border-b border-white/10 pb-3">
                    <div className="flex items-center gap-3">
                      {data.is_correct ? (
                        <div className="flex h-8 w-8 items-center justify-center rounded-xl glass-pill-emerald text-emerald-400">
                          <CheckCircle2 className="h-4 w-4" />
                        </div>
                      ) : (
                        <div className="flex h-8 w-8 items-center justify-center rounded-xl glass-pill-rose text-rose-400">
                          <XCircle className="h-4 w-4" />
                        </div>
                      )}
                      <span className="font-heading font-bold text-white">Questão {qIdxStr}</span>
                      <span className="rounded-lg glass-pill px-2.5 py-0.5 text-xs text-slate-300">
                        {data.subject || originalQ.subject}
                      </span>
                    </div>

                    <div className="flex items-center gap-3 text-xs font-mono font-bold">
                      <span className="text-slate-400">Sua resposta: <span className={data.is_correct ? 'text-emerald-400' : 'text-rose-400'}>{data.user_answer || 'Em branco'}</span></span>
                      <span className="text-slate-400">Gabarito: <span className="text-emerald-400">{data.correct_answer}</span></span>
                    </div>
                  </div>

                  <div className="mt-4 text-sm font-reading text-slate-200">
                    <MathRenderer content={originalQ.statement} />
                  </div>

                  {/* Embedded Diagrams in Review */}
                  {originalQ.images && originalQ.images.length > 0 && (
                    <div className="mt-4 space-y-2">
                      {originalQ.images.map((imgSrc, imgIdx) => (
                        <div
                          key={imgIdx}
                          onClick={() => setSelectedImageZoom(imgSrc)}
                          className="group relative cursor-zoom-in overflow-hidden rounded-2xl border border-white/10 bg-black/40 p-2 text-center"
                        >
                          <img
                            src={imgSrc}
                            alt={`Diagrama da Questão ${qIdxStr}`}
                            className="mx-auto max-h-72 rounded-lg object-contain transition group-hover:scale-[1.01]"
                          />
                          <div className="absolute bottom-3 right-3 flex items-center gap-1.5 rounded-xl bg-black/80 px-2.5 py-1 text-xs text-white opacity-0 group-hover:opacity-100 transition">
                            <Eye className="h-3.5 w-3.5" /> Ampliar Imagem
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  <div className="mt-4 space-y-2">
                    {Object.entries(originalQ.options).map(([k, text]) => {
                      const isUser = data.user_answer === k;
                      const isCorrect = data.correct_answer === k;
                      let badge = 'glass-option-default text-slate-300';
                      if (isCorrect) badge = 'glass-option-correct text-emerald-100 font-bold';
                      else if (isUser) badge = 'glass-option-wrong text-rose-100';

                      return (
                        <div key={k} className={`flex items-start gap-3 rounded-2xl p-3.5 text-xs ${badge}`}>
                          <span className="font-mono font-extrabold px-1.5 py-0.5 rounded-lg bg-black/40 shrink-0">{k}</span>
                          <div className="flex-1 font-reading">
                            <MathRenderer content={text} />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    );
  }

  // --- SOLVING VIEW ---
  const fontSizeClass =
    fontSize === 'sm' ? 'font-scale-sm' : fontSize === 'lg' ? 'font-scale-lg' : 'font-scale-base';

  const qEliminated = eliminatedOptions[qNum] || {};

  return (
    <div className={`mx-auto max-w-6xl animate-fadeIn p-4 sm:p-6 lg:p-8 ${isZenMode ? 'max-w-4xl' : ''}`}>
      {/* Top Header Toolbar with Glass Pill Controls */}
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-4">
        <div className="flex items-center gap-3">
          <button
            onClick={handleBack}
            className="flex h-10 w-10 items-center justify-center rounded-2xl glass-btn-secondary text-slate-300 hover:text-white"
            title="Voltar às Pastas"
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div>
            <span className="rounded-md glass-pill-indigo px-2 py-0.5 text-[10px] font-mono font-bold">
              SIMULADO ATIVO
            </span>
            <h1 className="font-heading text-sm sm:text-base font-bold text-white truncate max-w-xs sm:max-w-md" title={activeExam.title}>
              {activeExam.title}
            </h1>
          </div>
        </div>

        {/* Controls Toolbar */}
        <div className="flex items-center gap-2 sm:gap-2.5">
          {/* Question Grid Drawer Toggle */}
          <button
            onClick={() => setIsDrawerOpen((prev) => !prev)}
            className={`flex items-center gap-1.5 rounded-2xl px-3 py-2 text-xs font-bold transition ${
              isDrawerOpen
                ? 'glass-btn-primary text-white'
                : 'glass-btn-secondary text-slate-300 hover:text-white'
            }`}
            title="Abrir Mapa de Questões (Atalho: G)"
          >
            <LayoutGrid className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Mapa ({currentIdx + 1}/{totalQuestions})</span>
          </button>

          {/* Font Scale Adjuster */}
          <div className="flex items-center rounded-2xl glass-pill p-0.5">
            {(['sm', 'base', 'lg'] as const).map((size) => (
              <button
                key={size}
                onClick={() => setFontSize(size)}
                className={`rounded-xl px-2.5 py-1 text-xs font-bold transition ${
                  fontSize === size ? 'glass-btn-primary text-white' : 'text-slate-400 hover:text-white'
                }`}
                title={`Tamanho de fonte: ${size.toUpperCase()}`}
              >
                {size === 'sm' ? 'A-' : size === 'lg' ? 'A+' : 'A'}
              </button>
            ))}
          </div>

          {/* Immediate Feedback Toggle */}
          <button
            onClick={toggleImmediateFeedback}
            className={`flex items-center gap-1.5 rounded-2xl px-3 py-2 text-xs font-bold transition ${
              isImmediateFeedback
                ? 'glass-pill-emerald text-emerald-300'
                : 'glass-btn-secondary text-slate-400 hover:text-slate-200'
            }`}
            title="Modo Gabarito Imediato: Mostra se acertou na hora"
          >
            <Zap className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Gabarito Imediato</span>
          </button>

          {/* Timer Clock */}
          <button
            onClick={toggleTimer}
            className={`flex items-center gap-1.5 rounded-2xl px-3.5 py-2 font-mono text-xs font-bold transition ${
              isTimerRunning
                ? 'glass-pill-indigo text-indigo-300'
                : 'glass-pill-amber text-amber-300 animate-pulse'
            }`}
            title="Pausar / Continuar Cronômetro"
          >
            <Clock className="h-3.5 w-3.5" />
            <span>{formatTime(elapsedSeconds)}</span>
          </button>

          {/* Zen Mode */}
          <button
            onClick={toggleZenMode}
            className={`flex items-center rounded-2xl p-2 text-xs font-bold transition ${
              isZenMode
                ? 'glass-btn-primary text-white'
                : 'glass-btn-secondary text-slate-400 hover:text-white'
            }`}
            title="Modo Zen (Atalho: Z)"
          >
            {isZenMode ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
          </button>

          {/* Finish Button */}
          <button
            onClick={handleFinish}
            disabled={isSubmitting}
            className="flex items-center gap-1.5 rounded-2xl bg-gradient-to-r from-emerald-600 to-teal-600 px-4 py-2 font-heading font-bold text-xs text-white shadow-lg shadow-emerald-600/30 hover:from-emerald-500 hover:to-teal-500 border border-white/20 transition disabled:opacity-50"
          >
            <CheckCircle2 className="h-4 w-4" />
            <span className="hidden sm:inline">Entregar Prova</span>
          </button>
        </div>
      </header>

      {/* Main Layout (Question Card + Question Drawer) */}
      <div className="mt-6 grid gap-6 lg:grid-cols-4">
        {/* Question Area */}
        <div className={isZenMode || !isDrawerOpen ? 'col-span-full' : 'lg:col-span-3'}>
          {/* Progress Bar */}
          <div className="mb-4">
            <div className="flex items-center justify-between text-xs font-bold text-slate-400">
              <span className="font-heading">Questão {currentIdx + 1} de {totalQuestions}</span>
              <span className="font-mono text-indigo-400">{Math.round(progressPercentage)}% concluído</span>
            </div>
            <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-slate-900 border border-white/10">
              <div
                className="h-full bg-gradient-to-r from-indigo-500 via-violet-500 to-cyan-400 transition-all duration-300 shadow-sm"
                style={{ width: `${progressPercentage}%` }}
              />
            </div>
          </div>

          {/* High-Contrast Reading Shield Question Box */}
          <div className="glass-reading-shield p-6 sm:p-8">
            {/* Header tags */}
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-4">
              <div className="flex items-center gap-2.5">
                <span className="rounded-xl glass-pill-indigo px-3 py-1 font-mono text-sm font-black">
                  Questão {qNum}
                </span>
                <span className="rounded-xl glass-pill px-3 py-1 text-xs font-semibold text-slate-300">
                  {currentQ?.subject || 'Conhecimentos Gerais'}
                </span>
              </div>

              {/* Bookmark Flag */}
              <button
                onClick={() => toggleFlagQuestion(qNum)}
                className={`flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-bold transition ${
                  flaggedQuestions[qNum]
                    ? 'glass-pill-amber font-bold'
                    : 'glass-btn-secondary text-slate-400 hover:text-slate-200'
                }`}
                title="Marcar questão para revisão (Atalho: Barra de Espaço)"
              >
                <Bookmark className="h-3.5 w-3.5" />
                <span>{flaggedQuestions[qNum] ? 'Marcada para Revisão' : 'Marcar Dúvida'}</span>
              </button>
            </div>

            {/* Embedded Diagrams (Renderizado no topo do card para visibilidade imediata) */}
            {currentQ?.images && currentQ.images.length > 0 && (
              <div className="mt-5 space-y-3">
                {currentQ.images.map((imgSrc, imgIdx) => (
                  <div
                    key={imgIdx}
                    onClick={() => setSelectedImageZoom(imgSrc)}
                    className="group relative cursor-zoom-in overflow-hidden rounded-2xl border border-white/10 bg-black/40 p-2 text-center"
                  >
                    <img
                      src={imgSrc}
                      alt={`Diagrama da Questão ${qNum}`}
                      className="mx-auto max-h-96 rounded-lg object-contain transition group-hover:scale-[1.01]"
                    />
                    <div className="absolute bottom-3 right-3 flex items-center gap-1.5 rounded-xl bg-black/80 px-2.5 py-1 text-xs text-white opacity-0 group-hover:opacity-100 transition">
                      <Eye className="h-3.5 w-3.5" /> Ampliar Imagem
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Statement / Enunciado */}
            <div className={`mt-6 ${fontSizeClass} font-reading text-slate-100`}>
              <MathRenderer content={currentQ?.statement || ''} />
            </div>

            {/* Options List */}
            <div className="mt-8 space-y-3">
              {currentQ &&
                Object.entries(currentQ.options).map(([optKey, optText]) => {
                  const isSelected = answers[qNum] === optKey;
                  const isCorrect = currentQ.correct_answer === optKey;
                  const isEliminated = Boolean(qEliminated[optKey]);

                  let stateClass = 'glass-option-default text-slate-200';
                  if (isSelected) {
                    stateClass = 'glass-option-selected text-white font-medium';
                  }

                  if (isImmediateFeedback && isSelected) {
                    stateClass = isCorrect
                      ? 'glass-option-correct text-emerald-100'
                      : 'glass-option-wrong text-rose-100';
                  }

                  return (
                    <div
                      key={optKey}
                      className={`group relative flex items-start gap-3 rounded-2xl p-4 transition-all duration-200 ${stateClass} ${
                        isEliminated ? 'eliminated-option' : ''
                      }`}
                    >
                      {/* Main Option Click Area */}
                      <button
                        onClick={() => selectAnswer(qNum, optKey)}
                        className="flex flex-1 items-start gap-3.5 text-left focus:outline-none"
                      >
                        <span
                          className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-xl font-mono text-xs font-black transition ${
                            isSelected
                              ? 'bg-indigo-600 text-white shadow-md'
                              : 'bg-white/10 text-slate-300 group-hover:bg-white/20'
                          }`}
                        >
                          {optKey}
                        </span>
                        <div className={`flex-1 ${fontSizeClass} font-reading pt-0.5`}>
                          <MathRenderer content={optText} />
                        </div>
                      </button>

                      {/* Strikethrough / Elimination Tool Button */}
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleEliminateOption(qNum, optKey);
                        }}
                        className={`p-1.5 rounded-xl border transition ${
                          isEliminated
                            ? 'glass-pill-rose text-rose-400'
                            : 'border-transparent text-slate-500 hover:border-white/10 hover:bg-white/10 hover:text-slate-300'
                        }`}
                        title={isEliminated ? 'Restaurar alternativa' : 'Riscar alternativa (Eliminar hipótese)'}
                      >
                        <Scissors className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  );
                })}
            </div>

            {/* Bottom Nav Buttons */}
            <div className="mt-8 flex items-center justify-between border-t border-white/10 pt-6">
              <button
                onClick={prevQuestion}
                disabled={currentIdx === 0}
                className="flex items-center gap-2 rounded-2xl glass-btn-secondary px-5 py-3 font-heading font-bold text-xs text-slate-300 hover:text-white transition disabled:opacity-40"
              >
                <ArrowLeft className="h-4 w-4" /> Questão Anterior
              </button>

              <button
                onClick={() => setShowShortcutsModal(true)}
                className="hidden sm:flex items-center gap-1.5 text-xs text-slate-400 hover:text-indigo-300 transition"
              >
                <HelpCircle className="h-3.5 w-3.5" /> Atalhos de Teclado (?)
              </button>

              <button
                onClick={nextQuestion}
                disabled={currentIdx === totalQuestions - 1}
                className="flex items-center gap-2 rounded-2xl glass-btn-primary px-5 py-3 font-heading font-bold text-xs text-white transition disabled:opacity-40"
              >
                Próxima Questão <ArrowRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>

        {/* Question Navigator Drawer / Sidebar Grid */}
        {isDrawerOpen && !isZenMode && (
          <div className="glass-card p-5 h-fit space-y-4 lg:col-span-1">
            <div className="flex items-center justify-between border-b border-white/10 pb-3">
              <h3 className="font-heading text-xs font-bold uppercase tracking-wider text-slate-300">
                Mapa da Prova
              </h3>
              <button
                onClick={() => setIsDrawerOpen(false)}
                className="text-slate-400 hover:text-white lg:hidden"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Quick Status Legend */}
            <div className="grid grid-cols-2 gap-1.5 text-[10px] text-slate-400 font-semibold">
              <span className="flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full bg-indigo-600 shadow-sm" /> Respondida
              </span>
              <span className="flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full bg-amber-500 shadow-sm" /> Dúvida
              </span>
            </div>

            {/* Numbers Grid */}
            <div className="grid grid-cols-5 gap-2 max-h-96 overflow-y-auto pr-1">
              {questions.map((q, idx) => {
                const qNumber = q.numero_questao || String(idx + 1);
                const isCurrent = idx === currentIdx;
                const isAnswered = Boolean(answers[qNumber]);
                const isFlagged = Boolean(flaggedQuestions[qNumber]);

                let btnStyle = 'glass-btn-secondary text-slate-400';
                if (isAnswered) btnStyle = 'glass-pill-indigo font-bold text-white';
                if (isFlagged) btnStyle = 'glass-pill-amber font-bold text-white';
                if (isCurrent) btnStyle = 'glass-btn-primary text-white font-black ring-2 ring-indigo-400/50';

                return (
                  <button
                    key={idx}
                    onClick={() => setQuestionIdx(idx)}
                    className={`h-9 rounded-xl font-mono text-xs transition flex items-center justify-center ${btnStyle}`}
                  >
                    {qNumber}
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* Image Zoom Lightbox Modal */}
      {selectedImageZoom && (
        <div
          onClick={() => setSelectedImageZoom(null)}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 p-4 backdrop-blur-md cursor-zoom-out"
        >
          <div className="relative max-h-[90vh] max-w-[90vw]">
            <img src={selectedImageZoom} alt="Zoom" className="max-h-[85vh] rounded-2xl object-contain shadow-2xl" />
            <p className="mt-2 text-center text-xs text-slate-400">Clique em qualquer lugar para fechar</p>
          </div>
        </div>
      )}

      {/* Shortcuts Help Modal */}
      {showShortcutsModal && (
        <div
          onClick={() => setShowShortcutsModal(false)}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-md"
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="glass-card max-w-md w-full p-6 space-y-4 shadow-2xl"
          >
            <div className="flex items-center justify-between border-b border-white/10 pb-3">
              <h3 className="font-heading text-sm font-bold text-white">Atalhos de Teclado</h3>
              <button onClick={() => setShowShortcutsModal(false)} className="text-slate-400 hover:text-white">
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="space-y-2.5 text-xs text-slate-300">
              <div className="flex items-center justify-between">
                <span>Selecionar alternativas</span>
                <span className="font-mono glass-pill px-2 py-0.5 rounded text-indigo-300">[A–E] ou [1–5]</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Próxima questão</span>
                <span className="font-mono glass-pill px-2 py-0.5 rounded text-indigo-300">[Seta Direita →]</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Questão anterior</span>
                <span className="font-mono glass-pill px-2 py-0.5 rounded text-indigo-300">[Seta Esquerda ←]</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Marcar para revisão</span>
                <span className="font-mono glass-pill px-2 py-0.5 rounded text-indigo-300">[Barra de Espaço]</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Alternar Modo Zen</span>
                <span className="font-mono glass-pill px-2 py-0.5 rounded text-indigo-300">[Z]</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Abrir/Fechar Mapa da Prova</span>
                <span className="font-mono glass-pill px-2 py-0.5 rounded text-indigo-300">[G]</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
