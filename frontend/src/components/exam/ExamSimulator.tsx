import React, {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from 'react';
import clsx from 'clsx';
import {
  ArrowLeft,
  ArrowRight,
  Bookmark,
  BookOpen,
  CheckCircle2,
  Clock3,
  Eye,
  HelpCircle,
  LayoutGrid,
  Maximize2,
  Minimize2,
  Pause,
  Play,
  RotateCcw,
  Scissors,
  Settings2,
  X,
  XCircle,
} from 'lucide-react';
import { useExam } from '../../context/ExamContext';
import { useUI } from '../../context/UIContext';
import type { AttemptResult, ExamDetail, Question } from '../../types/exam';
import { MathRenderer } from './MathRenderer';
import { SourceModal, SourceModalData } from '../ui/SourceModal';

interface ExamSimulatorProps {
  onBackToDashboard?: () => void;
  onOpenNotebook?: () => void;
}

interface AccessibleDialogProps {
  open: boolean;
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  placement?: 'center' | 'bottom';
  panelClassName?: string;
  dismissDisabled?: boolean;
}

interface QuestionMapProps {
  questions: Question[];
  currentIdx: number;
  answers: Record<string, string>;
  flaggedQuestions: Record<string, boolean>;
  onSelect: (idx: number) => void;
}

interface ExamResultsProps {
  exam: ExamDetail;
  result: AttemptResult;
  filter: 'all' | 'errors' | 'correct';
  onFilterChange: (filter: 'all' | 'errors' | 'correct') => void;
  formatTime: (seconds: number) => string;
  onBack: () => void;
  onRedo: () => void;
  onOpenNotebook?: () => void;
  onOpenSource?: () => void;
  onOpenImage: (src: string) => void;
}

const focusRing =
  'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus)]';
const quietButton = clsx(
  'inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border border-[var(--border)]',
  'bg-[var(--surface)] px-3 text-sm font-semibold text-[var(--text)]',
  'transition-colors duration-150 hover:bg-[var(--surface-hover)] disabled:cursor-not-allowed disabled:opacity-45',
  focusRing,
);
const primaryButton = clsx(
  'inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border border-[var(--primary)]',
  'bg-[var(--primary)] px-4 text-sm font-semibold text-[var(--primary-contrast)]',
  'transition-opacity duration-150 hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-45',
  focusRing,
);

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

const AccessibleDialog: React.FC<AccessibleDialogProps> = ({
  open,
  title,
  onClose,
  children,
  placement = 'center',
  panelClassName,
  dismissDisabled = false,
}) => {
  const titleId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;

    previousFocusRef.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const frame = window.requestAnimationFrame(() => {
      const panel = panelRef.current;
      const initialTarget =
        panel?.querySelector<HTMLElement>('[data-autofocus]') ||
        panel?.querySelector<HTMLElement>(FOCUSABLE_SELECTOR) ||
        panel;
      initialTarget?.focus();
    });

    return () => {
      window.cancelAnimationFrame(frame);
      document.body.style.overflow = previousOverflow;
      previousFocusRef.current?.focus();
    };
  }, [open]);

  if (!open) return null;

  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      if (!dismissDisabled) onClose();
      return;
    }
    if (event.key !== 'Tab') return;

    const panel = panelRef.current;
    if (!panel) return;
    const focusable = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
      (element) => !element.hasAttribute('disabled') && element.getAttribute('aria-hidden') !== 'true',
    );
    if (focusable.length === 0) {
      event.preventDefault();
      panel.focus();
      return;
    }

    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && (document.activeElement === first || document.activeElement === panel)) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  return (
    <div
      className={clsx(
        'fixed inset-0 z-[70] flex bg-[var(--scrim)] p-4',
        placement === 'bottom' ? 'items-end sm:items-center sm:justify-center' : 'items-center justify-center',
      )}
      onMouseDown={(event) => {
        if (!dismissDisabled && event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onKeyDown={handleKeyDown}
        className={clsx(
          'w-full border border-[var(--border)] bg-[var(--surface)] text-[var(--text)] shadow-xl',
          placement === 'bottom'
            ? 'max-h-[82vh] rounded-t-xl sm:max-w-lg sm:rounded-xl'
            : 'max-h-[90vh] max-w-lg rounded-xl',
          panelClassName,
          focusRing,
        )}
      >
        <div className="flex min-h-14 items-center justify-between gap-4 border-b border-[var(--border)] px-5">
          <h2 id={titleId} className="text-base font-semibold">
            {title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            disabled={dismissDisabled}
            aria-label={'Fechar ' + title.toLowerCase()}
            className={clsx('grid h-11 w-11 place-items-center rounded-lg hover:bg-[var(--surface-hover)]', focusRing)}
          >
            <X aria-hidden="true" className="h-5 w-5" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
};

const QuestionMap: React.FC<QuestionMapProps> = ({
  questions,
  currentIdx,
  answers,
  flaggedQuestions,
  onSelect,
}) => (
  <nav aria-label="Mapa de questões">
    <div className="mb-4 grid grid-cols-2 gap-x-3 gap-y-2 text-xs text-[var(--text-muted)]">
      <span className="flex items-center gap-2">
        <span aria-hidden="true" className="h-3 w-3 rounded-sm border-2 border-[var(--primary)]" />
        Atual
      </span>
      <span className="flex items-center gap-2">
        <CheckCircle2 aria-hidden="true" className="h-3.5 w-3.5 text-[var(--success)]" />
        Respondida
      </span>
      <span className="flex items-center gap-2">
        <span aria-hidden="true" className="h-3 w-3 rounded-full border border-[var(--border)]" />
        Em branco
      </span>
      <span className="flex items-center gap-2">
        <Bookmark aria-hidden="true" className="h-3.5 w-3.5 text-[var(--warning)]" />
        Marcada
      </span>
    </div>
    <ol className="grid grid-cols-5 gap-2">
      {questions.map((question, idx) => {
        const questionNumber = question.numero_questao || String(idx + 1);
        const isCurrent = idx === currentIdx;
        const isAnswered = Boolean(answers[questionNumber]);
        const isFlagged = Boolean(flaggedQuestions[questionNumber]);
        const states = [
          isCurrent ? 'atual' : '',
          isAnswered ? 'respondida' : 'em branco',
          isFlagged ? 'marcada para revisão' : '',
        ].filter(Boolean);

        return (
          <li key={(question.id || questionNumber) + '-' + idx}>
            <button
              type="button"
              onClick={() => onSelect(idx)}
              aria-current={isCurrent ? 'step' : undefined}
              aria-label={'Questão ' + questionNumber + ': ' + states.join(', ')}
              title={'Questão ' + questionNumber + ': ' + states.join(', ')}
              className={clsx(
                'relative flex h-11 w-full items-center justify-center rounded-lg border bg-[var(--surface)]',
                'font-mono text-xs font-semibold text-[var(--text-muted)] transition-colors duration-150',
                'hover:bg-[var(--surface-hover)]',
                isAnswered && 'border-[var(--success)] bg-[var(--success-subtle)] text-[var(--success)]',
                isFlagged && 'border-[var(--warning)]',
                isCurrent && 'outline outline-2 outline-offset-1 outline-[var(--primary)]',
                focusRing,
              )}
            >
              {questionNumber}
              <span aria-hidden="true" className="absolute bottom-0.5 right-0.5 flex gap-0.5">
                {isAnswered && <CheckCircle2 className="h-2.5 w-2.5 text-[var(--success)]" />}
                {isFlagged && <Bookmark className="h-2.5 w-2.5 fill-current text-[var(--warning)]" />}
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  </nav>
);

const ImagePreviewDialog: React.FC<{
  src: string | null;
  onClose: () => void;
}> = ({ src, onClose }) => (
  <AccessibleDialog
    open={Boolean(src)}
    title="Visualização ampliada da imagem"
    onClose={onClose}
    panelClassName="max-w-5xl overflow-auto"
  >
    <div className="p-4">
      {src && (
        <img
          src={src}
          alt="Imagem da questão em tamanho ampliado"
          className="mx-auto max-h-[75vh] max-w-full object-contain"
        />
      )}
    </div>
  </AccessibleDialog>
);

const ExamResults: React.FC<ExamResultsProps> = ({
  exam,
  result,
  filter,
  onFilterChange,
  formatTime,
  onBack,
  onRedo,
  onOpenNotebook,
  onOpenSource,
  onOpenImage,
}) => {
  const filteredEntries = Object.entries(result.detailed_answers).filter(([, data]) => {
    if (filter === 'errors') return !data.is_correct;
    if (filter === 'correct') return data.is_correct;
    return true;
  });
  const averageSeconds = Math.round(result.elapsed_seconds / Math.max(result.total, 1));
  const passedReference = result.percentage >= 70;

  return (
    <main className="min-h-screen bg-[var(--background)] px-4 py-8 text-[var(--text)] sm:px-6 lg:px-8">
      <div className="mx-auto max-w-5xl space-y-8">
        <section className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6 sm:p-8">
          <p className="text-sm font-medium text-[var(--text-muted)]">Resultado do simulado</p>
          <h1 className="mt-1 text-2xl font-semibold sm:text-3xl">{exam.title}</h1>
          <p
            className={clsx(
              'mt-4 inline-flex items-center gap-2 rounded-full px-3 py-1 text-sm font-semibold',
              passedReference
                ? 'bg-[var(--success-subtle)] text-[var(--success)]'
                : 'bg-[var(--warning-subtle)] text-[var(--warning)]',
            )}
          >
            {passedReference ? (
              <CheckCircle2 aria-hidden="true" className="h-4 w-4" />
            ) : (
              <RotateCcw aria-hidden="true" className="h-4 w-4" />
            )}
            {passedReference ? 'Bom desempenho' : 'Continue praticando'}
          </p>

          <dl className="mt-7 grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--border)] lg:grid-cols-4">
            {[
              ['Nota', result.percentage + '%'],
              ['Acertos', result.score + ' de ' + result.total],
              ['Tempo', formatTime(result.elapsed_seconds)],
              ['Média por questão', averageSeconds + 's'],
            ].map(([label, value]) => (
              <div key={label} className="bg-[var(--surface)] p-4 sm:p-5">
                <dt className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                  {label}
                </dt>
                <dd className="mt-2 font-mono text-xl font-semibold sm:text-2xl">{value}</dd>
              </div>
            ))}
          </dl>

          <div className="mt-6 flex flex-wrap gap-3">
            <button type="button" onClick={onBack} className={quietButton}>
              <ArrowLeft aria-hidden="true" className="h-4 w-4" />
              Voltar à biblioteca
            </button>
            <button type="button" onClick={onRedo} className={primaryButton}>
              <RotateCcw aria-hidden="true" className="h-4 w-4" />
              Refazer simulado
            </button>
            {onOpenNotebook && (
              <button type="button" onClick={onOpenNotebook} className={quietButton}>
                <Bookmark aria-hidden="true" className="h-4 w-4" />
                Caderno de erros
              </button>
            )}
            {onOpenSource && (
              <button type="button" onClick={onOpenSource} className={quietButton}>
                <BookOpen aria-hidden="true" className="h-4 w-4" />
                Fonte
              </button>
            )}
          </div>
        </section>

        <section aria-labelledby="subject-performance-title">
          <h2 id="subject-performance-title" className="text-lg font-semibold">
            Desempenho por disciplina
          </h2>
          <div className="mt-3 overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface)]">
            {Object.entries(result.feedback_per_subject).map(([subject, stats], idx) => (
              <div
                key={subject}
                className={clsx(
                  'grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 px-4 py-4 sm:px-5',
                  idx > 0 && 'border-t border-[var(--border)]',
                )}
              >
                <div className="min-w-0">
                  <p className="truncate font-medium">{subject}</p>
                  <p className="mt-1 text-sm text-[var(--text-muted)]">
                    {stats.correct} de {stats.total} corretas
                  </p>
                </div>
                <span className="font-mono text-lg font-semibold">{stats.percentage}%</span>
              </div>
            ))}
          </div>
        </section>

        <section aria-labelledby="review-title">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <h2 id="review-title" className="text-lg font-semibold">
                Revisão das questões
              </h2>
              <p className="mt-1 text-sm text-[var(--text-muted)]">
                Abra uma questão para conferir enunciado, resposta e gabarito.
              </p>
            </div>
            <div
              role="group"
              aria-label="Filtrar questões da revisão"
              className="inline-flex w-fit rounded-lg border border-[var(--border)] bg-[var(--surface)] p-1"
            >
              {[
                ['all', 'Todas', result.total],
                ['errors', 'Erros', result.total - result.score],
                ['correct', 'Acertos', result.score],
              ].map(([value, label, count]) => (
                <button
                  key={String(value)}
                  type="button"
                  aria-pressed={filter === value}
                  onClick={() => onFilterChange(value as 'all' | 'errors' | 'correct')}
                  className={clsx(
                    'min-h-10 rounded-md px-3 text-sm font-medium transition-colors duration-150',
                    filter === value
                      ? 'bg-[var(--primary)] text-[var(--primary-contrast)]'
                      : 'text-[var(--text-muted)] hover:bg-[var(--surface-hover)] hover:text-[var(--text)]',
                    focusRing,
                  )}
                >
                  {label} ({count})
                </button>
              ))}
            </div>
          </div>

          <div className="mt-4 space-y-3">
            {filteredEntries.map(([questionNumber, data]) => {
              const originalQuestion =
                exam.questions.find(
                  (question) =>
                    (question.numero_questao || String(question.id)) === questionNumber,
                ) || exam.questions.find((question) => question.id === data.question_id);
              if (!originalQuestion) return null;

              return (
                <details
                  key={questionNumber}
                  className="group rounded-xl border border-[var(--border)] bg-[var(--surface)]"
                >
                  <summary
                    className={clsx(
                      'flex min-h-14 cursor-pointer list-none items-center justify-between gap-4 rounded-xl px-4 py-3',
                      'hover:bg-[var(--surface-hover)] [&::-webkit-details-marker]:hidden',
                      focusRing,
                    )}
                  >
                    <span className="flex min-w-0 items-center gap-3">
                      {data.is_correct ? (
                        <CheckCircle2 aria-hidden="true" className="h-5 w-5 shrink-0 text-[var(--success)]" />
                      ) : (
                        <XCircle aria-hidden="true" className="h-5 w-5 shrink-0 text-[var(--danger)]" />
                      )}
                      <span>
                        <span className="block font-semibold">Questão {questionNumber}</span>
                        <span className="block truncate text-xs text-[var(--text-muted)]">
                          {data.subject || originalQuestion.subject} ·{' '}
                          {data.is_correct ? 'Resposta correta' : 'Resposta incorreta'}
                        </span>
                      </span>
                    </span>
                    <span className="shrink-0 text-sm text-[var(--text-muted)] group-open:hidden">
                      Abrir
                    </span>
                    <span className="hidden shrink-0 text-sm text-[var(--text-muted)] group-open:inline">
                      Fechar
                    </span>
                  </summary>

                  <div className="border-t border-[var(--border)] px-4 py-5 sm:px-6">
                    <div className="mb-5 flex flex-wrap gap-x-5 gap-y-2 text-sm">
                      <span>
                        <span className="text-[var(--text-muted)]">Sua resposta: </span>
                        <strong>{data.user_answer || 'Em branco'}</strong>
                      </span>
                      <span>
                        <span className="text-[var(--text-muted)]">Gabarito: </span>
                        <strong>{data.correct_answer}</strong>
                      </span>
                    </div>

                    {originalQuestion.context_text && (
                      <section className="mb-5 rounded-lg border border-[var(--border)] bg-[var(--surface-subtle)] p-4">
                        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                          Texto de apoio
                        </p>
                        <div className="font-reading leading-[1.7]">
                          <MathRenderer content={originalQuestion.context_text} />
                        </div>
                      </section>
                    )}

                    <div className="font-reading leading-[1.7]">
                      <MathRenderer content={originalQuestion.statement} />
                    </div>

                    {originalQuestion.images && originalQuestion.images.length > 0 && (
                      <div className="mt-5 grid gap-3">
                        {originalQuestion.images.map((src, imageIdx) => (
                          <button
                            key={src + imageIdx}
                            type="button"
                            onClick={() => onOpenImage(src)}
                            className={clsx(
                              'group/image relative overflow-hidden rounded-lg border border-[var(--border)]',
                              'bg-[var(--surface-subtle)] p-2 text-center',
                              focusRing,
                            )}
                          >
                            <img
                              src={src}
                              alt={'Imagem da questão ' + questionNumber}
                              className="mx-auto max-h-72 object-contain"
                            />
                            <span className="mt-2 inline-flex items-center gap-2 text-xs text-[var(--text-muted)]">
                              <Eye aria-hidden="true" className="h-3.5 w-3.5" />
                              Ampliar imagem
                            </span>
                          </button>
                        ))}
                      </div>
                    )}

                    <div className="mt-6 space-y-2">
                      {Object.entries(originalQuestion.options).map(([key, text]) => {
                        const isCorrect = data.correct_answer === key;
                        const isUserAnswer = data.user_answer === key;
                        return (
                          <div
                            key={key}
                            className={clsx(
                              'flex items-start gap-3 rounded-lg border p-3',
                              isCorrect
                                ? 'border-[var(--success)] bg-[var(--success-subtle)]'
                                : isUserAnswer
                                  ? 'border-[var(--danger)] bg-[var(--danger-subtle)]'
                                  : 'border-[var(--border)]',
                            )}
                          >
                            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-current font-mono text-xs font-semibold">
                              {key}
                            </span>
                            <div className="min-w-0 flex-1 font-reading text-sm leading-[1.65]">
                              <MathRenderer content={text} />
                              {(isCorrect || isUserAnswer) && (
                                <p
                                  className={clsx(
                                    'mt-2 text-xs font-semibold',
                                    isCorrect ? 'text-[var(--success)]' : 'text-[var(--danger)]',
                                  )}
                                >
                                  {isCorrect ? 'Alternativa correta' : 'Sua alternativa'}
                                </p>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </details>
              );
            })}
            {filteredEntries.length === 0 && (
              <p className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6 text-sm text-[var(--text-muted)]">
                Nenhuma questão corresponde a este filtro.
              </p>
            )}
          </div>
        </section>
      </div>
    </main>
  );
};

export const ExamSimulator: React.FC<ExamSimulatorProps> = ({
  onBackToDashboard,
  onOpenNotebook,
}) => {
  const {
    activeExam,
    currentIdx,
    currentQuestion,
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
    toggleTimer,
    toggleImmediateFeedback,
    toggleZenMode,
    submitExamAttempt,
    resetExam,
    startExam,
    formatTime,
  } = useExam();
  const {
    fontSize,
    setFontSize,
    theme,
    setTheme,
    enableEliminationMode,
    toggleEliminationMode,
    navigateTo,
    showToast,
  } = useUI();

  const [selectedImageZoom, setSelectedImageZoom] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [resultFilter, setResultFilter] = useState<'all' | 'errors' | 'correct'>('all');
  const [isMobileMapOpen, setIsMobileMapOpen] = useState(false);
  const [isShortcutsOpen, setIsShortcutsOpen] = useState(false);
  const [isSubmitDialogOpen, setIsSubmitDialogOpen] = useState(false);
  const [isPreferencesOpen, setIsPreferencesOpen] = useState(false);

  const questionHeadingRef = useRef<HTMLHeadingElement>(null);
  const desktopMapRef = useRef<HTMLElement>(null);
  const preferencesRef = useRef<HTMLDivElement>(null);
  const preferencesButtonRef = useRef<HTMLButtonElement>(null);

  const questions = activeExam?.questions || [];
  const currentQ = questions[currentIdx] || currentQuestion;
  const qNum = currentQ?.numero_questao || String(currentIdx + 1);
  const qEliminated = eliminatedOptions[qNum] || {};
  const answeredCount = questions.reduce((count, question, idx) => {
    const number = question.numero_questao || String(idx + 1);
    return count + (answers[number] ? 1 : 0);
  }, 0);

  const unansweredQuestions = useMemo(
    () =>
      questions
        .map((question, idx) => ({
          idx,
          number: question.numero_questao || String(idx + 1),
        }))
        .filter((question) => !answers[question.number]),
    [answers, questions],
  );
  const markedQuestions = useMemo(
    () =>
      questions
        .map((question, idx) => ({
          idx,
          number: question.numero_questao || String(idx + 1),
        }))
        .filter((question) => flaggedQuestions[question.number]),
    [flaggedQuestions, questions],
  );

  const [sourceModalData, setSourceModalData] = useState<SourceModalData | null>(null);
  const [isSourceModalOpen, setIsSourceModalOpen] = useState(false);

  const handleBack = onBackToDashboard || (() => navigateTo('folders'));
  const overlayOpen =
    Boolean(selectedImageZoom) ||
    isMobileMapOpen ||
    isShortcutsOpen ||
    isSubmitDialogOpen ||
    isPreferencesOpen ||
    isSourceModalOpen;

  const openSourceModal = useCallback(() => {
    if (!activeExam) return;
    setSourceModalData({
      title: activeExam.title,
      source_url: activeExam.source_url,
      gabarito_url: activeExam.gabarito_url,
    });
    setIsSourceModalOpen(true);
  }, [activeExam]);

  const openQuestionMap = useCallback(() => {
    if (window.matchMedia('(min-width: 1024px)').matches) {
      desktopMapRef.current?.focus();
    } else {
      setIsMobileMapOpen(true);
    }
  }, []);

  useEffect(() => {
    if (!activeExam || isFinished || !currentQ) return;
    const frame = window.requestAnimationFrame(() => {
      questionHeadingRef.current?.focus({ preventScroll: true });
      questionHeadingRef.current?.scrollIntoView({ block: 'start' });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [activeExam, currentIdx, currentQ, isFinished]);

  useEffect(() => {
    if (!isPreferencesOpen) return;
    const handlePointerDown = (event: PointerEvent) => {
      if (!preferencesRef.current?.contains(event.target as Node)) {
        setIsPreferencesOpen(false);
      }
    };
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsPreferencesOpen(false);
        preferencesButtonRef.current?.focus();
      }
    };
    document.addEventListener('pointerdown', handlePointerDown);
    document.addEventListener('keydown', handleEscape);
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [isPreferencesOpen]);

  useEffect(() => {
    if (isFinished || !activeExam || overlayOpen) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      if (
        target?.isContentEditable ||
        target?.closest(
          'input, textarea, select, button, a, [contenteditable="true"], [role="dialog"], [role="menu"]',
        )
      ) {
        return;
      }

      const question = activeExam.questions[currentIdx];
      if (!question) return;
      const number = question.numero_questao || String(currentIdx + 1);
      const optionKeys = Object.keys(question.options);
      const key = event.key.toUpperCase();
      if (event.repeat && (event.code === 'Space' || key === 'Z' || key === 'G' || event.key === '?')) {
        return;
      }
      const optionIndex = ['1', '2', '3', '4', '5'].indexOf(key);
      const letterIndex = ['A', 'B', 'C', 'D', 'E'].indexOf(key);
      const selectedIndex = optionIndex >= 0 ? optionIndex : letterIndex;

      if (selectedIndex >= 0 && optionKeys[selectedIndex]) {
        event.preventDefault();
        selectAnswer(number, optionKeys[selectedIndex]);
      } else if (event.key === 'ArrowRight') {
        event.preventDefault();
        nextQuestion();
      } else if (event.key === 'ArrowLeft') {
        event.preventDefault();
        prevQuestion();
      } else if (event.code === 'Space') {
        event.preventDefault();
        toggleFlagQuestion(number);
      } else if (key === 'Z') {
        event.preventDefault();
        toggleZenMode();
      } else if (key === 'G') {
        event.preventDefault();
        openQuestionMap();
      } else if (event.key === '?') {
        event.preventDefault();
        setIsShortcutsOpen(true);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [
    activeExam,
    currentIdx,
    isFinished,
    nextQuestion,
    openQuestionMap,
    overlayOpen,
    prevQuestion,
    selectAnswer,
    toggleFlagQuestion,
    toggleZenMode,
  ]);

  const submitAttempt = async () => {
    if (isSubmitting) return;
    setIsSubmitting(true);
    try {
      await submitExamAttempt();
      showToast('success', 'Simulado concluído', 'Sua correção já está disponível.');
    } catch (error) {
      showToast(
        'error',
        'Não foi possível entregar o simulado',
        error instanceof Error ? error.message : 'Tente novamente em alguns instantes.',
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const goToQuestion = (idx: number) => {
    setIsMobileMapOpen(false);
    setIsSubmitDialogOpen(false);
    setQuestionIdx(idx);
  };

  const normalizedTheme = String(theme) === 'paper' ? 'light' : String(theme);
  const setThemeValue = (value: 'light' | 'dark' | 'oled') => {
    setTheme(value as Parameters<typeof setTheme>[0]);
  };
  const fontSizeClass =
    fontSize === 'sm'
      ? 'text-[1rem] leading-[1.65]'
      : fontSize === 'lg'
        ? 'text-[1.1875rem] leading-[1.75]'
        : 'text-[1.0625rem] leading-[1.7]';

  if (!activeExam) {
    return (
      <main className="grid min-h-[60vh] place-items-center bg-[var(--background)] px-4 text-[var(--text)]">
        <section className="max-w-md rounded-xl border border-[var(--border)] bg-[var(--surface)] p-8 text-center">
          <h1 className="text-xl font-semibold">Nenhum simulado em andamento</h1>
          <p className="mt-2 text-sm leading-relaxed text-[var(--text-muted)]">
            Escolha uma prova na biblioteca para começar a estudar.
          </p>
          <button type="button" onClick={handleBack} className={clsx(primaryButton, 'mt-6')}>
            <ArrowLeft aria-hidden="true" className="h-4 w-4" />
            Ir para a biblioteca
          </button>
        </section>
      </main>
    );
  }

  if (isFinished && attemptResult) {
    const examToRedo = { ...activeExam, questions: [...activeExam.questions] };
    return (
      <>
        <ExamResults
          exam={activeExam}
          result={attemptResult}
          filter={resultFilter}
          onFilterChange={setResultFilter}
          formatTime={formatTime}
          onBack={() => {
            resetExam();
            handleBack();
          }}
          onRedo={() => {
            resetExam();
            startExam(examToRedo);
          }}
          onOpenNotebook={onOpenNotebook}
          onOpenSource={openSourceModal}
          onOpenImage={setSelectedImageZoom}
        />
        <ImagePreviewDialog src={selectedImageZoom} onClose={() => setSelectedImageZoom(null)} />
      </>
    );
  }

  if (!currentQ) {
    return (
      <main className="grid min-h-[60vh] place-items-center bg-[var(--background)] px-4 text-[var(--text)]">
        <section className="max-w-md rounded-xl border border-[var(--border)] bg-[var(--surface)] p-8 text-center">
          <h1 className="text-xl font-semibold">Esta prova não possui questões</h1>
          <p className="mt-2 text-sm text-[var(--text-muted)]">
            Volte à biblioteca e escolha outra prova.
          </p>
          <button type="button" onClick={handleBack} className={clsx(quietButton, 'mt-6')}>
            <ArrowLeft aria-hidden="true" className="h-4 w-4" />
            Voltar
          </button>
        </section>
      </main>
    );
  }

  return (
    <div className="min-h-screen bg-[var(--background)] text-[var(--text)]">
      <header className="sticky top-0 z-40 border-b border-[var(--border)] bg-[var(--surface)]">
        <div className="mx-auto flex min-h-14 max-w-[1280px] items-center gap-2 px-3 sm:px-5">
          <button
            type="button"
            onClick={handleBack}
            aria-label="Voltar à biblioteca"
            className={clsx('grid h-11 w-11 shrink-0 place-items-center rounded-lg hover:bg-[var(--surface-hover)]', focusRing)}
          >
            <ArrowLeft aria-hidden="true" className="h-5 w-5" />
          </button>

          <div className="min-w-0 flex-1">
            <h1 className="truncate text-sm font-semibold sm:text-base" title={activeExam.title}>
              {activeExam.title}
            </h1>
            <p className="text-xs text-[var(--text-muted)]">
              {answeredCount} de {totalQuestions} respondidas
            </p>
          </div>

          <button
            type="button"
            onClick={openSourceModal}
            aria-label="Ver fonte da prova"
            className={clsx(
              'inline-flex h-11 items-center gap-1.5 rounded-lg px-2 text-xs font-semibold sm:px-3 sm:text-sm',
              'text-[var(--text)] hover:bg-[var(--surface-hover)]',
              focusRing,
            )}
          >
            <BookOpen aria-hidden="true" className="h-4 w-4 text-[var(--primary)]" />
            <span className="hidden sm:inline">Fonte</span>
          </button>

          <button
            type="button"
            onClick={toggleTimer}
            aria-label={
              (isTimerRunning ? 'Pausar' : 'Retomar') +
              ' cronômetro. Tempo atual: ' +
              formatTime(elapsedSeconds)
            }
            className={clsx(
              'inline-flex h-11 items-center gap-2 rounded-lg px-2 font-mono text-xs font-semibold',
              'text-[var(--text)] hover:bg-[var(--surface-hover)] sm:px-3 sm:text-sm',
              !isTimerRunning && 'text-[var(--warning)]',
              focusRing,
            )}
          >
            {isTimerRunning ? (
              <Pause aria-hidden="true" className="h-4 w-4" />
            ) : (
              <Play aria-hidden="true" className="h-4 w-4" />
            )}
            <span>{formatTime(elapsedSeconds)}</span>
          </button>

          {!isZenMode && (
            <button
              type="button"
              onClick={openQuestionMap}
              aria-label="Abrir mapa de questões"
              aria-expanded={isMobileMapOpen}
              className={clsx('grid h-11 w-11 place-items-center rounded-lg hover:bg-[var(--surface-hover)]', focusRing)}
            >
              <LayoutGrid aria-hidden="true" className="h-5 w-5" />
            </button>
          )}

          <div ref={preferencesRef} className="relative">
            <button
              ref={preferencesButtonRef}
              type="button"
              onClick={() => setIsPreferencesOpen((open) => !open)}
              aria-label="Preferências de leitura"
              aria-expanded={isPreferencesOpen}
              aria-controls="exam-reading-preferences"
              className={clsx(
                'inline-flex h-11 min-w-11 items-center justify-center gap-1 rounded-lg px-2 hover:bg-[var(--surface-hover)]',
                focusRing,
              )}
            >
              <span aria-hidden="true" className="font-serif text-sm font-semibold">
                Aa
              </span>
              <Settings2 aria-hidden="true" className="h-3.5 w-3.5 text-[var(--text-muted)]" />
            </button>

            {isPreferencesOpen && (
              <div
                id="exam-reading-preferences"
                role="region"
                aria-label="Preferências de leitura"
                className="absolute right-0 top-12 z-50 w-[min(18rem,calc(100vw-2rem))] rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4 shadow-xl"
              >
                <fieldset>
                  <legend className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                    Tema
                  </legend>
                  <div className="mt-2 grid grid-cols-3 gap-2">
                    {[
                      ['light', 'Claro'],
                      ['dark', 'Escuro'],
                      ['oled', 'OLED'],
                    ].map(([value, label]) => (
                      <label
                        key={value}
                        className={clsx(
                          'flex min-h-11 cursor-pointer items-center justify-center rounded-lg border text-xs font-semibold',
                          normalizedTheme === value
                            ? 'border-[var(--primary)] bg-[var(--surface-subtle)] text-[var(--primary)]'
                            : 'border-[var(--border)] hover:bg-[var(--surface-hover)]',
                          focusRing,
                        )}
                      >
                        <input
                          type="radio"
                          name="exam-theme"
                          value={value}
                          checked={normalizedTheme === value}
                          onChange={() => setThemeValue(value as 'light' | 'dark' | 'oled')}
                          className="sr-only"
                        />
                        {label}
                      </label>
                    ))}
                  </div>
                </fieldset>

                <fieldset className="mt-5">
                  <legend className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                    Tamanho do texto
                  </legend>
                  <div className="mt-2 grid grid-cols-3 gap-2">
                    {(['sm', 'base', 'lg'] as const).map((size) => (
                      <button
                        key={size}
                        type="button"
                        aria-pressed={fontSize === size}
                        onClick={() => setFontSize(size)}
                        className={clsx(
                          'min-h-11 rounded-lg border text-sm font-semibold',
                          fontSize === size
                            ? 'border-[var(--primary)] bg-[var(--primary)] text-[var(--primary-contrast)]'
                            : 'border-[var(--border)] hover:bg-[var(--surface-hover)]',
                          focusRing,
                        )}
                      >
                        {size === 'sm' ? 'A−' : size === 'lg' ? 'A+' : 'A'}
                      </button>
                    ))}
                  </div>
                </fieldset>

                <div className="mt-5 space-y-2 border-t border-[var(--border)] pt-4">
                  {[
                    {
                      label: 'Gabarito imediato',
                      checked: isImmediateFeedback,
                      onChange: toggleImmediateFeedback,
                    },
                    {
                      label: 'Modo Zen',
                      checked: isZenMode,
                      onChange: toggleZenMode,
                    },
                    {
                      label: 'Eliminar alternativas',
                      checked: enableEliminationMode,
                      onChange: toggleEliminationMode,
                    },
                  ].map((preference) => (
                    <button
                      key={preference.label}
                      type="button"
                      role="switch"
                      aria-checked={preference.checked}
                      onClick={preference.onChange}
                      className={clsx(
                        'flex min-h-11 w-full items-center justify-between rounded-lg px-2 text-left text-sm',
                        'hover:bg-[var(--surface-hover)]',
                        focusRing,
                      )}
                    >
                      {preference.label}
                      <span
                        aria-hidden="true"
                        className={clsx(
                          'relative h-6 w-11 rounded-full border transition-colors duration-150',
                          preference.checked
                            ? 'border-[var(--primary)] bg-[var(--primary)]'
                            : 'border-[var(--border)] bg-[var(--surface-subtle)]',
                        )}
                      >
                        <span
                          className={clsx(
                            'absolute top-0.5 h-4 w-4 rounded-full bg-[var(--primary-contrast)] transition-[left] duration-150',
                            preference.checked ? 'left-5' : 'left-1',
                          )}
                        />
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={() => setIsSubmitDialogOpen(true)}
            disabled={isSubmitting}
            aria-label="Entregar simulado"
            className={clsx(primaryButton, 'shrink-0 px-3 sm:px-4')}
          >
            <CheckCircle2 aria-hidden="true" className="h-4 w-4" />
            <span className="hidden sm:inline">Entregar</span>
          </button>
        </div>

        <div
          role="progressbar"
          aria-label="Progresso de respostas"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(progressPercentage)}
          className="h-1 bg-[var(--surface-subtle)]"
        >
          <div
            className="h-full bg-[var(--primary)] transition-[width] duration-150"
            style={{ width: progressPercentage + '%' }}
          />
        </div>
      </header>

      <main
        className={clsx(
          'mx-auto w-full max-w-[1180px] px-4 pb-32 pt-6 sm:px-6 lg:pb-12 lg:pt-8',
          !isZenMode && 'lg:grid lg:grid-cols-[minmax(0,1fr)_17rem] lg:gap-8',
        )}
      >
        <article
          className={clsx(
            'mx-auto w-full max-w-[72ch] rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5 sm:p-8',
            isZenMode && 'lg:max-w-[72ch]',
          )}
        >
          <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[var(--border)] pb-4">
            <div className="min-w-0">
              <h2
                ref={questionHeadingRef}
                tabIndex={-1}
                className={clsx('scroll-mt-24 text-lg font-semibold', focusRing)}
              >
                Questão {qNum}
              </h2>
              <p className="mt-1 text-sm text-[var(--text-muted)]">
                {currentQ.subject || 'Conhecimentos gerais'} · {currentIdx + 1} de {totalQuestions}
              </p>
            </div>
            <button
              type="button"
              onClick={() => toggleFlagQuestion(qNum)}
              aria-pressed={Boolean(flaggedQuestions[qNum])}
              className={clsx(
                quietButton,
                'px-3',
                flaggedQuestions[qNum] &&
                  'border-[var(--warning)] bg-[var(--warning-subtle)] text-[var(--warning)]',
              )}
            >
              <Bookmark
                aria-hidden="true"
                className={clsx('h-4 w-4', flaggedQuestions[qNum] && 'fill-current')}
              />
              {flaggedQuestions[qNum] ? 'Marcada' : 'Marcar'}
            </button>
          </div>

          {currentQ.context_text && (
            <aside
              aria-label="Texto de apoio"
              className="mt-6 rounded-lg border-l-4 border-[var(--primary)] bg-[var(--surface-subtle)] px-4 py-4"
            >
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                Texto de apoio
              </p>
              <div className={clsx('font-reading', fontSizeClass)}>
                <MathRenderer content={currentQ.context_text} />
              </div>
            </aside>
          )}

          {currentQ.images && currentQ.images.length > 0 && (
            <div className="mt-6 grid gap-3">
              {currentQ.images.map((src, imageIdx) => (
                <button
                  key={src + imageIdx}
                  type="button"
                  onClick={() => setSelectedImageZoom(src)}
                  className={clsx(
                    'rounded-lg border border-[var(--border)] bg-[var(--surface-subtle)] p-2 text-center',
                    'hover:bg-[var(--surface-hover)]',
                    focusRing,
                  )}
                >
                  <img
                    src={src}
                    alt={'Imagem da questão ' + qNum}
                    className="mx-auto max-h-96 max-w-full object-contain"
                  />
                  <span className="mt-2 inline-flex items-center gap-2 text-xs text-[var(--text-muted)]">
                    <Eye aria-hidden="true" className="h-3.5 w-3.5" />
                    Ampliar imagem
                  </span>
                </button>
              ))}
            </div>
          )}

          <div className={clsx('mt-7 font-reading', fontSizeClass)}>
            <MathRenderer content={currentQ.statement} />
          </div>

          <fieldset className="mt-8 min-w-0">
            <legend className="mb-3 text-sm font-semibold text-[var(--text-muted)]">
              Escolha uma alternativa
            </legend>
            <div className="space-y-3">
              {Object.entries(currentQ.options).map(([optionKey, optionText], optionIdx) => {
                const isSelected = answers[qNum] === optionKey;
                const isCorrect = currentQ.correct_answer === optionKey;
                const isEliminated =
                  enableEliminationMode && Boolean(qEliminated[optionKey]);
                const showCorrectFeedback = isImmediateFeedback && isSelected && isCorrect;
                const showWrongFeedback = isImmediateFeedback && isSelected && !isCorrect;
                const statusId = 'question-' + currentIdx + '-option-' + optionIdx + '-status';

                return (
                  <div
                    key={optionKey}
                    className={clsx(
                      'flex items-stretch rounded-xl border bg-[var(--surface)] transition-colors duration-150',
                      isSelected
                        ? 'border-[var(--primary)] bg-[var(--surface-subtle)]'
                        : 'border-[var(--border)] hover:bg-[var(--surface-hover)]',
                      showCorrectFeedback &&
                        'border-[var(--success)] bg-[var(--success-subtle)]',
                      showWrongFeedback && 'border-[var(--danger)] bg-[var(--danger-subtle)]',
                      isEliminated && 'opacity-65',
                      focusRing,
                    )}
                  >
                    <label className="flex min-h-14 min-w-0 flex-1 cursor-pointer items-start gap-3 px-4 py-4">
                      <input
                        type="radio"
                        name={'question-' + currentIdx}
                        value={optionKey}
                        checked={isSelected}
                        aria-describedby={
                          isEliminated || showCorrectFeedback || showWrongFeedback
                            ? statusId
                            : undefined
                        }
                        onChange={() => selectAnswer(qNum, optionKey)}
                        className="mt-1 h-5 w-5 shrink-0 accent-[var(--primary)]"
                      />
                      <span
                        aria-hidden="true"
                        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-[var(--border)] font-mono text-xs font-semibold"
                      >
                        {optionKey}
                      </span>
                      <span
                        className={clsx(
                          'min-w-0 flex-1 font-reading',
                          fontSizeClass,
                          isEliminated && 'line-through',
                        )}
                      >
                        <MathRenderer content={optionText} />
                        {(isEliminated || showCorrectFeedback || showWrongFeedback) && (
                          <span
                            id={statusId}
                            className={clsx(
                              'mt-2 block text-xs font-semibold no-underline',
                              showCorrectFeedback && 'text-[var(--success)]',
                              showWrongFeedback && 'text-[var(--danger)]',
                              isEliminated &&
                                !showCorrectFeedback &&
                                !showWrongFeedback &&
                                'text-[var(--text-muted)]',
                            )}
                          >
                            {showCorrectFeedback
                              ? 'Resposta correta'
                              : showWrongFeedback
                                ? 'Resposta incorreta'
                                : 'Alternativa eliminada'}
                          </span>
                        )}
                      </span>
                    </label>

                    {enableEliminationMode && (
                      <button
                        type="button"
                        onClick={() => toggleEliminateOption(qNum, optionKey)}
                        aria-pressed={isEliminated}
                        aria-label={
                          (isEliminated ? 'Restaurar' : 'Eliminar') +
                          ' alternativa ' +
                          optionKey
                        }
                        className={clsx(
                          'm-1.5 grid min-h-11 w-11 shrink-0 place-items-center rounded-lg',
                          'text-[var(--text-muted)] hover:bg-[var(--surface-hover)] hover:text-[var(--text)]',
                          isEliminated &&
                            'bg-[var(--danger-subtle)] text-[var(--danger)]',
                          focusRing,
                        )}
                      >
                        <Scissors aria-hidden="true" className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          </fieldset>

          <div className="mt-8 hidden items-center justify-between border-t border-[var(--border)] pt-6 lg:flex">
            <button
              type="button"
              onClick={prevQuestion}
              disabled={currentIdx === 0}
              className={quietButton}
            >
              <ArrowLeft aria-hidden="true" className="h-4 w-4" />
              Anterior
            </button>
            <button
              type="button"
              onClick={() => setIsShortcutsOpen(true)}
              className={clsx(
                'inline-flex min-h-11 items-center gap-2 rounded-lg px-3 text-xs text-[var(--text-muted)]',
                'hover:bg-[var(--surface-hover)] hover:text-[var(--text)]',
                focusRing,
              )}
            >
              <HelpCircle aria-hidden="true" className="h-4 w-4" />
              Atalhos (?)
            </button>
            <button
              type="button"
              onClick={nextQuestion}
              disabled={currentIdx === totalQuestions - 1}
              className={primaryButton}
            >
              Próxima
              <ArrowRight aria-hidden="true" className="h-4 w-4" />
            </button>
          </div>
        </article>

        {!isZenMode && (
          <aside
            ref={desktopMapRef}
            tabIndex={-1}
            aria-label="Mapa da prova"
            className={clsx(
              'sticky top-24 hidden max-h-[calc(100vh-7rem)] self-start overflow-y-auto rounded-xl',
              'border border-[var(--border)] bg-[var(--surface)] p-4 lg:block',
              focusRing,
            )}
          >
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h2 className="text-sm font-semibold">Mapa da prova</h2>
                <p className="mt-1 text-xs text-[var(--text-muted)]">
                  {answeredCount} de {totalQuestions} respondidas
                </p>
              </div>
              <LayoutGrid aria-hidden="true" className="h-4 w-4 text-[var(--text-muted)]" />
            </div>
            <QuestionMap
              questions={questions}
              currentIdx={currentIdx}
              answers={answers}
              flaggedQuestions={flaggedQuestions}
              onSelect={setQuestionIdx}
            />
          </aside>
        )}
      </main>

      <nav
        aria-label="Navegação entre questões"
        className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-3 gap-2 border-t border-[var(--border)] bg-[var(--surface)] px-3 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] lg:hidden"
      >
        <button
          type="button"
          onClick={prevQuestion}
          disabled={currentIdx === 0}
          className={quietButton}
        >
          <ArrowLeft aria-hidden="true" className="h-5 w-5" />
          <span className="sr-only sm:not-sr-only">Anterior</span>
        </button>
        <button type="button" onClick={openQuestionMap} className={quietButton}>
          <LayoutGrid aria-hidden="true" className="h-5 w-5" />
          <span>{currentIdx + 1}/{totalQuestions}</span>
        </button>
        <button
          type="button"
          onClick={nextQuestion}
          disabled={currentIdx === totalQuestions - 1}
          className={primaryButton}
        >
          <span className="sr-only sm:not-sr-only">Próxima</span>
          <ArrowRight aria-hidden="true" className="h-5 w-5" />
        </button>
      </nav>

      <AccessibleDialog
        open={isMobileMapOpen}
        title="Mapa da prova"
        onClose={() => setIsMobileMapOpen(false)}
        placement="bottom"
        panelClassName="lg:hidden"
      >
        <div className="max-h-[65vh] overflow-y-auto p-5">
          <QuestionMap
            questions={questions}
            currentIdx={currentIdx}
            answers={answers}
            flaggedQuestions={flaggedQuestions}
            onSelect={goToQuestion}
          />
        </div>
      </AccessibleDialog>

      <AccessibleDialog
        open={isSubmitDialogOpen}
        title="Entregar simulado?"
        onClose={() => {
          if (!isSubmitting) setIsSubmitDialogOpen(false);
        }}
        dismissDisabled={isSubmitting}
        panelClassName="overflow-y-auto"
      >
        <div className="space-y-5 p-5" aria-busy={isSubmitting}>
          <p className="text-sm leading-relaxed text-[var(--text-muted)]">
            Você respondeu {answeredCount} de {totalQuestions} questões. Depois da entrega,
            as respostas não poderão ser alteradas.
          </p>

          <section aria-labelledby="unanswered-title">
            <h3 id="unanswered-title" className="text-sm font-semibold">
              Em branco ({unansweredQuestions.length})
            </h3>
            {unansweredQuestions.length > 0 ? (
              <div className="mt-2 flex flex-wrap gap-2">
                {unansweredQuestions.map((question) => (
                  <button
                    key={'blank-' + question.idx}
                    type="button"
                    onClick={() => goToQuestion(question.idx)}
                    disabled={isSubmitting}
                    aria-label={'Ir para questão ' + question.number + ' em branco'}
                    className={quietButton}
                  >
                    {question.number}
                  </button>
                ))}
              </div>
            ) : (
              <p className="mt-1 text-sm text-[var(--success)]">Todas foram respondidas.</p>
            )}
          </section>

          <section aria-labelledby="marked-title">
            <h3 id="marked-title" className="text-sm font-semibold">
              Marcadas para revisão ({markedQuestions.length})
            </h3>
            {markedQuestions.length > 0 ? (
              <div className="mt-2 flex flex-wrap gap-2">
                {markedQuestions.map((question) => (
                  <button
                    key={'marked-' + question.idx}
                    type="button"
                    onClick={() => goToQuestion(question.idx)}
                    disabled={isSubmitting}
                    aria-label={'Ir para questão ' + question.number + ' marcada para revisão'}
                    className={clsx(
                      quietButton,
                      'border-[var(--warning)] text-[var(--warning)]',
                    )}
                  >
                    <Bookmark aria-hidden="true" className="h-3.5 w-3.5 fill-current" />
                    {question.number}
                  </button>
                ))}
              </div>
            ) : (
              <p className="mt-1 text-sm text-[var(--text-muted)]">Nenhuma questão marcada.</p>
            )}
          </section>

          <div className="flex flex-col-reverse gap-2 border-t border-[var(--border)] pt-4 sm:flex-row sm:justify-end">
            <button
              type="button"
              data-autofocus
              onClick={() => setIsSubmitDialogOpen(false)}
              disabled={isSubmitting}
              className={quietButton}
            >
              Continuar prova
            </button>
            <button
              type="button"
              onClick={submitAttempt}
              disabled={isSubmitting}
              className={primaryButton}
            >
              <CheckCircle2 aria-hidden="true" className="h-4 w-4" />
              {isSubmitting ? 'Entregando…' : 'Confirmar entrega'}
            </button>
          </div>
        </div>
      </AccessibleDialog>

      <AccessibleDialog
        open={isShortcutsOpen}
        title="Atalhos de teclado"
        onClose={() => setIsShortcutsOpen(false)}
      >
        <dl className="space-y-3 p-5 text-sm">
          {[
            ['A–E ou 1–5', 'Selecionar alternativa'],
            ['← / →', 'Questão anterior ou próxima'],
            ['Espaço', 'Marcar para revisão'],
            ['Z', 'Alternar modo Zen'],
            ['G', 'Abrir o mapa da prova'],
            ['?', 'Abrir esta ajuda'],
          ].map(([keys, description]) => (
            <div key={keys} className="flex items-center justify-between gap-5">
              <dt className="text-[var(--text-muted)]">{description}</dt>
              <dd>
                <kbd className="rounded border border-[var(--border)] bg-[var(--surface-subtle)] px-2 py-1 font-mono text-xs">
                  {keys}
                </kbd>
              </dd>
            </div>
          ))}
        </dl>
      </AccessibleDialog>

      <ImagePreviewDialog src={selectedImageZoom} onClose={() => setSelectedImageZoom(null)} />
      <SourceModal
        isOpen={isSourceModalOpen}
        onClose={() => setIsSourceModalOpen(false)}
        data={sourceModalData}
      />
    </div>
  );
};
