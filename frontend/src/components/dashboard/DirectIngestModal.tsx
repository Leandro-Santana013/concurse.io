import React, { useEffect, useRef, useState } from 'react';
import { CheckCircle2, Clipboard, ExternalLink, FileText, Loader2, RefreshCw, X } from 'lucide-react';
import { api } from '../../services/api';
import { ImportStage } from '../../types/exam';
import { useUI } from '../../context/UIContext';

interface DirectIngestModalProps {
  isOpen: boolean;
  onClose: () => void;
  onExamReady?: (examId: number) => void;
  initialExamUrl?: string;
  initialGabaritoUrl?: string;
  initialTitle?: string;
}

const TERMINAL_ERRORS = new Set(['Erro', 'Falha']);

export const DirectIngestModal: React.FC<DirectIngestModalProps> = ({
  isOpen,
  onClose,
  onExamReady,
  initialExamUrl = '',
  initialGabaritoUrl = '',
  initialTitle = '',
}) => {
  const { showToast } = useUI();
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const retryTimerRef = useRef<number | null>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const [examUrl, setExamUrl] = useState('');
  const [gabaritoUrl, setGabaritoUrl] = useState('');
  const [customTitle, setCustomTitle] = useState('');
  const [stage, setStage] = useState<ImportStage>('form');
  const [progress, setProgress] = useState(0);
  const [statusMessage, setStatusMessage] = useState('');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [readyExamId, setReadyExamId] = useState<number | null>(null);

  const stopWatching = () => {
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
    if (retryTimerRef.current !== null) window.clearTimeout(retryTimerRef.current);
    retryTimerRef.current = null;
  };

  useEffect(() => {
    if (!isOpen) {
      stopWatching();
      return;
    }

    previousFocusRef.current = document.activeElement as HTMLElement | null;
    setExamUrl(initialExamUrl);
    setGabaritoUrl(initialGabaritoUrl);
    setCustomTitle(initialTitle);
    setStage('form');
    setProgress(0);
    setStatusMessage('');
    setErrorMessage(null);
    setReadyExamId(null);
    document.body.style.overflow = 'hidden';
    window.setTimeout(() => closeButtonRef.current?.focus(), 0);

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== 'Tab' || !dialogRef.current) return;
      const controls = Array.from(dialogRef.current.querySelectorAll<HTMLElement>('button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'));
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
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = '';
      stopWatching();
      previousFocusRef.current?.focus();
    };
  }, [isOpen, initialExamUrl, initialGabaritoUrl, initialTitle, onClose]);

  if (!isOpen) return null;

  const updateProgress = (examId: number, data: { progress?: number; status?: string; error_type?: string | null }) => {
    const nextProgress = data.progress ?? 0;
    const nextStatus = data.status || 'Processando prova...';
    setProgress(Math.max(0, nextProgress));
    setStatusMessage(nextStatus);
    if (nextProgress >= 100 || nextStatus === 'Aprovada') {
      stopWatching();
      setReadyExamId(examId);
      setStage('ready');
    } else if (nextProgress < 0 || data.error_type || TERMINAL_ERRORS.has(nextStatus)) {
      stopWatching();
      setStage('error');
      setErrorMessage(nextStatus || 'O processamento da prova falhou.');
    }
  };

  const watchProgress = (examId: number, attempt = 0) => {
    stopWatching();
    const source = new EventSource(
      `/api/v1/exams/${examId}/progress/stream`,
      { withCredentials: true },
    );
    eventSourceRef.current = source;
    source.onmessage = (event) => {
      try {
        updateProgress(examId, JSON.parse(event.data));
      } catch {
        setStatusMessage('Recebendo atualizações do processamento...');
      }
    };
    source.onerror = async () => {
      source.close();
      eventSourceRef.current = null;
      try {
        const snapshot = await api.getExamProgress(examId);
        updateProgress(examId, snapshot);
        if (snapshot.progress >= 100 || snapshot.progress < 0 || snapshot.error_type) return;
      } catch {
        // A reconexão limitada abaixo fornece uma segunda chance à conexão.
      }
      if (attempt < 2) {
        setStatusMessage('Reconectando ao processamento...');
        retryTimerRef.current = window.setTimeout(() => watchProgress(examId, attempt + 1), 1200 * (attempt + 1));
      } else {
        setStage('error');
        setErrorMessage('Perdemos a conexão com o processamento. Tente acompanhar novamente.');
      }
    };
  };

  const pasteInto = async (setter: (value: string) => void) => {
    try {
      const value = (await navigator.clipboard.readText()).trim();
      if (value) setter(value);
    } catch {
      showToast('warning', 'Cole manualmente usando Ctrl+V');
    }
  };

  const startImport = async () => {
    const cleanUrl = examUrl.trim();
    if (!cleanUrl) {
      setErrorMessage('Informe o link da prova.');
      setStage('error');
      return;
    }
    setStage('submitting');
    setProgress(5);
    setErrorMessage(null);
    setStatusMessage('Criando a prova...');
    try {
      const response = await api.ingestExam(cleanUrl, customTitle.trim() || 'Nova Prova de Concurso', gabaritoUrl.trim() || undefined);
      if (response.status === 'Aprovada') {
        setProgress(100);
        setStatusMessage(response.reused ? response.message : 'Prova pronta para começar.');
        setReadyExamId(response.exam_id);
        setStage('ready');
        return;
      }
      setStage('processing');
      setStatusMessage(response.reused ? response.message : 'Baixando e organizando as questões...');
      watchProgress(response.exam_id);
    } catch (error) {
      setStage('error');
      setErrorMessage(error instanceof Error ? error.message : 'Não foi possível iniciar a importação.');
    }
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    void startImport();
  };

  const isBusy = stage === 'submitting' || stage === 'processing';
  const pciUrl = examUrl.trim().startsWith('http') ? examUrl.trim() : 'https://www.pciconcursos.com.br/provas/';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--scrim)] p-3 sm:p-6" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="import-title" aria-describedby="import-description" className="max-h-[calc(100vh-1.5rem)] w-full max-w-2xl overflow-y-auto rounded-xl border border-[var(--border)] bg-[var(--surface)] shadow-2xl">
        <header className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-[var(--border)] bg-[var(--surface)] p-5">
          <div>
            <h2 id="import-title" className="text-lg font-semibold text-[var(--text)]">Importar prova</h2>
            <p id="import-description" className="mt-1 text-sm text-[var(--text-muted)]">Cole o link da prova e, se tiver, o link do gabarito oficial.</p>
          </div>
          <button ref={closeButtonRef} type="button" className="icon-button" onClick={onClose} aria-label="Fechar importação"><X aria-hidden="true" /></button>
        </header>

        <form onSubmit={handleSubmit} className="space-y-5 p-5 sm:p-6">
          <div className="block">
            <label className="field-label" htmlFor="exam-url">Link da prova</label>
            <div className="mt-2 flex gap-2">
              <input id="exam-url" type="url" required className="input-control font-mono text-sm" disabled={isBusy} value={examUrl} onChange={(event) => setExamUrl(event.target.value)} placeholder="https://.../prova.pdf" />
              <button type="button" className="button-secondary shrink-0" disabled={isBusy} onClick={() => void pasteInto(setExamUrl)}><Clipboard aria-hidden="true" /> Colar</button>
            </div>
          </div>

          <div className="block">
            <label className="field-label" htmlFor="answer-url">Link do gabarito <span className="font-normal text-[var(--text-muted)]">(opcional)</span></label>
            <div className="mt-2 flex gap-2">
              <input id="answer-url" type="url" className="input-control font-mono text-sm" disabled={isBusy} value={gabaritoUrl} onChange={(event) => setGabaritoUrl(event.target.value)} placeholder="https://.../gabarito.pdf" />
              <button type="button" className="button-secondary shrink-0" disabled={isBusy} onClick={() => void pasteInto(setGabaritoUrl)}><Clipboard aria-hidden="true" /> Colar</button>
            </div>
          </div>

          <label className="block" htmlFor="exam-title">
            <span className="field-label">Título <span className="font-normal text-[var(--text-muted)]">(opcional)</span></span>
            <input id="exam-title" className="input-control mt-2" disabled={isBusy} value={customTitle} onChange={(event) => setCustomTitle(event.target.value)} placeholder="Ex.: FGV 2025 — Auditor" />
          </label>

          {(stage === 'submitting' || stage === 'processing') && (
            <section className="rounded-lg border border-[var(--border)] bg-[var(--surface-subtle)] p-4" aria-live="polite" aria-busy="true">
              <div className="flex items-center justify-between gap-4 text-sm"><span className="flex items-center gap-2 font-medium text-[var(--text)]"><Loader2 aria-hidden="true" />{statusMessage}</span><span className="font-mono">{progress}%</span></div>
              <progress className="mt-3 h-2 w-full" max="100" value={Math.max(5, progress)}>{progress}%</progress>
              <p className="mt-2 text-xs text-[var(--text-muted)]">Você pode fechar esta janela; o processamento continuará em segundo plano.</p>
            </section>
          )}

          {stage === 'ready' && (
            <section className="rounded-lg border border-[var(--success)] bg-[var(--success-subtle)] p-4 text-[var(--text)]" aria-live="polite">
              <div className="flex gap-3"><CheckCircle2 className="text-[var(--success)]" aria-hidden="true" /><div><h3 className="font-semibold">Prova pronta</h3><p className="mt-1 text-sm">{statusMessage || 'As questões foram organizadas e já podem ser resolvidas.'}</p></div></div>
            </section>
          )}

          {stage === 'error' && errorMessage && (
            <section className="rounded-lg border border-[var(--danger)] bg-[var(--danger-subtle)] p-4" role="alert">
              <h3 className="font-semibold text-[var(--text)]">Não foi possível concluir</h3><p className="mt-1 text-sm text-[var(--text-muted)]">{errorMessage}</p>
              <button type="button" className="button-secondary mt-3" onClick={() => void startImport()}><RefreshCw aria-hidden="true" /> Tentar novamente</button>
            </section>
          )}

          <footer className="flex flex-col-reverse gap-3 border-t border-[var(--border)] pt-5 sm:flex-row sm:items-center sm:justify-between">
            <a className="text-link inline-flex min-h-11 items-center gap-2" href={pciUrl} target="_blank" rel="noreferrer"><ExternalLink aria-hidden="true" /> Abrir no PCI Concursos</a>
            <div className="flex flex-wrap justify-end gap-2">
              <button type="button" className="button-ghost" onClick={onClose}>{isBusy ? 'Fechar e acompanhar' : 'Cancelar'}</button>
              {stage === 'ready' && readyExamId ? (
                <button type="button" className="button-primary" onClick={() => { onClose(); onExamReady?.(readyExamId); }}><FileText aria-hidden="true" /> Iniciar simulado</button>
              ) : (
                <button type="submit" className="button-primary" disabled={isBusy || !examUrl.trim()}>{isBusy ? <Loader2 aria-hidden="true" /> : <FileText aria-hidden="true" />} Processar prova</button>
              )}
            </div>
          </footer>
        </form>
      </div>
    </div>
  );
};
