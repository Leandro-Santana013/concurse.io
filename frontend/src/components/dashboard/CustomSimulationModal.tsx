import React, { useEffect, useRef, useState } from 'react';
import { Check, Loader2, Shuffle, SlidersHorizontal, X } from 'lucide-react';
import { api } from '../../services/api';
import type {
  CustomSimulationOptions,
  CustomSimulationRequest,
} from '../../types/exam';

interface CustomSimulationModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (request: CustomSimulationRequest) => Promise<void>;
}

const MIN_QUESTIONS = 5;
const MAX_QUESTIONS = 100;
const QUICK_COUNTS = [10, 20, 30, 50];

export const CustomSimulationModal: React.FC<CustomSimulationModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
}) => {
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const isSubmittingRef = useRef(false);
  const [options, setOptions] = useState<CustomSimulationOptions | null>(null);
  const [count, setCount] = useState('20');
  const [selectedSubjects, setSelectedSubjects] = useState<string[]>([]);
  const [sourceExamId, setSourceExamId] = useState('');
  const [isLoadingOptions, setIsLoadingOptions] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    isSubmittingRef.current = isSubmitting;
  }, [isSubmitting]);

  useEffect(() => {
    if (!isOpen) return undefined;

    let cancelled = false;
    previousFocusRef.current = document.activeElement as HTMLElement | null;
    setCount('20');
    setSelectedSubjects([]);
    setSourceExamId('');
    setOptions(null);
    setErrorMessage(null);
    setIsLoadingOptions(true);
    document.body.style.overflow = 'hidden';
    window.setTimeout(() => closeButtonRef.current?.focus(), 0);

    void api.getCustomSimulationOptions()
      .then((data) => {
        if (!cancelled) setOptions(data);
      })
      .catch((error) => {
        if (!cancelled) {
          setErrorMessage(error instanceof Error ? error.message : 'Não foi possível carregar os filtros.');
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoadingOptions(false);
      });

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !isSubmittingRef.current) {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== 'Tab' || !dialogRef.current) return;
      const controls = Array.from(
        dialogRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      );
      if (controls.length === 0) return;
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      cancelled = true;
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = '';
      previousFocusRef.current?.focus();
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const parsedCount = Number.parseInt(count, 10);
  const availableQuestions = options?.available_questions ?? 0;
  const isCountValid = Number.isInteger(parsedCount)
    && parsedCount >= MIN_QUESTIONS
    && parsedCount <= MAX_QUESTIONS;
  const canSubmit = !isLoadingOptions
    && !isSubmitting
    && isCountValid
    && availableQuestions >= parsedCount;

  const toggleSubject = (subject: string) => {
    setSelectedSubjects((current) => current.includes(subject)
      ? current.filter((item) => item !== subject)
      : [...current, subject]);
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!isCountValid) {
      setErrorMessage(`Escolha entre ${MIN_QUESTIONS} e ${MAX_QUESTIONS} questões.`);
      return;
    }
    if (availableQuestions < parsedCount) {
      setErrorMessage('A biblioteca não possui questões válidas suficientes para essa quantidade.');
      return;
    }

    setErrorMessage(null);
    setIsSubmitting(true);
    try {
      await onSubmit({
        count: parsedCount,
        subjects: selectedSubjects,
        sourceExamId: sourceExamId ? Number(sourceExamId) : null,
      });
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Não foi possível gerar o simulado.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--scrim)] p-3 sm:p-6"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !isSubmitting) onClose();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="custom-simulation-title"
        aria-describedby="custom-simulation-description"
        className="max-h-[calc(100vh-1.5rem)] w-full max-w-2xl overflow-y-auto rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-2xl"
      >
        <header className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-[var(--border)] bg-[var(--surface)] p-5 sm:p-6">
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold text-[var(--primary)]">
              <SlidersHorizontal aria-hidden="true" className="h-4 w-4" />
              Motor de questões
            </div>
            <h2 id="custom-simulation-title" className="mt-1 text-xl font-semibold text-[var(--text)]">
              Montar simulado personalizado
            </h2>
            <p id="custom-simulation-description" className="mt-1 text-sm text-[var(--text-muted)]">
              Escolha o tamanho, as disciplinas e, se quiser, a prova de origem.
            </p>
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            className="icon-button"
            onClick={onClose}
            disabled={isSubmitting}
            aria-label="Fechar simulado personalizado"
          >
            <X aria-hidden="true" />
          </button>
        </header>

        <form onSubmit={handleSubmit} className="space-y-6 p-5 sm:p-6">
          <section aria-labelledby="custom-count-title">
            <div className="flex items-end justify-between gap-4">
              <div>
                <h3 id="custom-count-title" className="font-semibold text-[var(--text)]">Quantidade de questões</h3>
                <p className="mt-1 text-sm text-[var(--text-muted)]">Entre {MIN_QUESTIONS} e {MAX_QUESTIONS} questões.</p>
              </div>
              <label className="flex items-center gap-2" htmlFor="custom-question-count">
                <span className="sr-only">Quantidade de questões</span>
                <input
                  id="custom-question-count"
                  type="number"
                  min={MIN_QUESTIONS}
                  max={MAX_QUESTIONS}
                  step="1"
                  inputMode="numeric"
                  className="input-control w-24 text-center font-mono"
                  value={count}
                  onChange={(event) => setCount(event.target.value)}
                  disabled={isSubmitting}
                />
              </label>
            </div>
            <div className="mt-3 flex flex-wrap gap-2" aria-label="Quantidades rápidas">
              {QUICK_COUNTS.map((quickCount) => (
                <button
                  key={quickCount}
                  type="button"
                  className={`min-h-10 rounded-lg border px-3 text-sm font-semibold transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus)] ${Number(count) === quickCount ? 'border-[var(--primary)] bg-[var(--primary-subtle)] text-[var(--primary)]' : 'border-[var(--border)] text-[var(--text-muted)] hover:bg-[var(--surface-hover)] hover:text-[var(--text)]'}`}
                  onClick={() => setCount(String(quickCount))}
                  disabled={isSubmitting}
                  aria-pressed={Number(count) === quickCount}
                >
                  {quickCount}
                </button>
              ))}
            </div>
          </section>

          <section aria-labelledby="custom-subject-title">
            <div className="flex items-end justify-between gap-4">
              <div>
                <h3 id="custom-subject-title" className="font-semibold text-[var(--text)]">Disciplinas ou categorias</h3>
                <p className="mt-1 text-sm text-[var(--text-muted)]">Sem seleção, o motor mistura toda a biblioteca.</p>
              </div>
              {selectedSubjects.length > 0 && (
                <button type="button" className="text-link text-sm" onClick={() => setSelectedSubjects([])} disabled={isSubmitting}>
                  Limpar
                </button>
              )}
            </div>
            {isLoadingOptions ? (
              <div className="mt-3 flex items-center gap-2 text-sm text-[var(--text-muted)]" role="status">
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> Carregando categorias…
              </div>
            ) : options?.subjects.length ? (
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                {options.subjects.map((subject) => {
                  const selected = selectedSubjects.includes(subject.name);
                  return (
                    <button
                      key={subject.name}
                      type="button"
                      className={`flex min-h-11 items-center justify-between gap-3 rounded-lg border px-3 text-left text-sm transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus)] ${selected ? 'border-[var(--primary)] bg-[var(--primary-subtle)] text-[var(--text)]' : 'border-[var(--border)] text-[var(--text-muted)] hover:bg-[var(--surface-hover)] hover:text-[var(--text)]'}`}
                      onClick={() => toggleSubject(subject.name)}
                      disabled={isSubmitting}
                      aria-pressed={selected}
                    >
                      <span className="min-w-0 truncate">{subject.name}</span>
                      <span className="flex shrink-0 items-center gap-2 text-xs text-[var(--text-muted)]">
                        {subject.count}
                        {selected && <Check aria-hidden="true" className="h-4 w-4 text-[var(--primary)]" />}
                      </span>
                    </button>
                  );
                })}
              </div>
            ) : (
              <p className="mt-3 text-sm text-[var(--text-muted)]">Nenhuma categoria disponível nas questões válidas.</p>
            )}
          </section>

          <section aria-labelledby="custom-source-title">
            <label className="block" htmlFor="custom-source">
              <span id="custom-source-title" className="field-label">Origem das questões <span className="font-normal text-[var(--text-muted)]">(opcional)</span></span>
              <select
                id="custom-source"
                className="input-control mt-2"
                value={sourceExamId}
                onChange={(event) => setSourceExamId(event.target.value)}
                disabled={isSubmitting || isLoadingOptions}
              >
                <option value="">Todas as provas da biblioteca</option>
                {(options?.sources || []).map((source) => (
                  <option key={source.id} value={source.id}>
                    {source.title} · {source.count} questões
                  </option>
                ))}
              </select>
            </label>
          </section>

          <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-subtle)] p-4" role="status" aria-live="polite">
            <div className="flex items-start gap-3">
              <Shuffle aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-[var(--primary)]" />
              <div>
                <p className="font-semibold text-[var(--text)]">
                  {availableQuestions > 0 ? `${availableQuestions} questões válidas disponíveis` : 'Nenhuma questão disponível'}
                </p>
                <p className="mt-1 text-sm text-[var(--text-muted)]">
                  As questões serão embaralhadas e o teste ficará salvo em “Testes personalizados”.
                </p>
              </div>
            </div>
          </div>

          {errorMessage && (
            <section className="rounded-lg border border-[var(--danger)] bg-[var(--danger-subtle)] p-4 text-sm" role="alert">
              {errorMessage}
            </section>
          )}

          <footer className="flex flex-col-reverse gap-3 border-t border-[var(--border)] pt-5 sm:flex-row sm:items-center sm:justify-end">
            <button type="button" className="button-ghost" onClick={onClose} disabled={isSubmitting}>
              Cancelar
            </button>
            <button type="submit" className="button-primary" disabled={!canSubmit}>
              {isSubmitting ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Shuffle aria-hidden="true" />}
              {isSubmitting ? 'Montando…' : 'Gerar simulado'}
            </button>
          </footer>
        </form>
      </div>
    </div>
  );
};
