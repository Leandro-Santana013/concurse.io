import React, { useEffect, useRef, useState } from 'react';
import { BookOpen, Check, Clipboard, ExternalLink, FileText, X } from 'lucide-react';

export interface SourceModalData {
  title: string;
  source_url?: string | null;
  gabarito_url?: string | null;
}

interface SourceModalProps {
  isOpen: boolean;
  onClose: () => void;
  data: SourceModalData | null;
}

export const SourceModal: React.FC<SourceModalProps> = ({ isOpen, onClose, data }) => {
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const [copiedField, setCopiedField] = useState<'source' | 'gabarito' | null>(null);

  useEffect(() => {
    if (!isOpen) return;

    previousFocusRef.current = document.activeElement as HTMLElement | null;
    closeButtonRef.current?.focus();

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      previousFocusRef.current?.focus();
    };
  }, [isOpen, onClose]);

  if (!isOpen || !data) return null;

  const hasSource = Boolean(data.source_url && data.source_url.trim());
  const hasGabarito = Boolean(data.gabarito_url && data.gabarito_url.trim());

  const handleCopy = async (url: string, field: 'source' | 'gabarito') => {
    try {
      await navigator.clipboard.writeText(url);
      setCopiedField(field);
      setTimeout(() => setCopiedField(null), 2000);
    } catch {
      // Fallback if clipboard API is restricted
      const textarea = document.createElement('textarea');
      textarea.value = url;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopiedField(field);
      setTimeout(() => setCopiedField(null), 2000);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--scrim)] p-3 sm:p-6"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="source-modal-title"
        className="max-h-[calc(100vh-2rem)] w-full max-w-xl overflow-y-auto rounded-xl border border-[var(--border)] bg-[var(--surface)] shadow-2xl"
      >
        {/* Header */}
        <header className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-[var(--border)] bg-[var(--surface)] p-5">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-[var(--primary)]/10 text-[var(--primary)]">
              <BookOpen className="h-5 w-5" aria-hidden="true" />
            </div>
            <div>
              <h2 id="source-modal-title" className="text-lg font-semibold text-[var(--text)]">
                Fontes da Prova
              </h2>
              <p className="mt-0.5 text-xs text-[var(--text-muted)] line-clamp-1" title={data.title}>
                {data.title}
              </p>
            </div>
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            className="icon-button"
            onClick={onClose}
            aria-label="Fechar modal de fontes"
          >
            <X aria-hidden="true" />
          </button>
        </header>

        {/* Content */}
        <div className="space-y-4 p-5 sm:p-6">
          {/* Card 1: Caderno de Questões */}
          <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-subtle)] p-4 sm:p-5">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 font-medium text-[var(--text)]">
                <FileText className="h-4 w-4 text-[var(--primary)]" aria-hidden="true" />
                <span>Caderno de Questões (Prova)</span>
              </div>
              <span
                className={`text-xs px-2.5 py-0.5 rounded-full font-medium ${
                  hasSource ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                }`}
              >
                {hasSource ? 'Disponível' : 'Indisponível'}
              </span>
            </div>

            {hasSource ? (
              <div className="mt-3 flex flex-col gap-3">
                <p className="break-all font-mono text-xs text-[var(--text-muted)] bg-[var(--surface)] p-2.5 rounded-lg border border-[var(--border)]">
                  {data.source_url}
                </p>
                <div className="flex flex-wrap items-center gap-2">
                  <a
                    href={data.source_url!}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="button-primary text-xs py-2 px-3 inline-flex items-center gap-1.5"
                  >
                    <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                    Abrir Prova (PDF)
                  </a>
                  <button
                    type="button"
                    className="button-secondary text-xs py-2 px-3 inline-flex items-center gap-1.5"
                    onClick={() => handleCopy(data.source_url!, 'source')}
                  >
                    {copiedField === 'source' ? (
                      <>
                        <Check className="h-3.5 w-3.5 text-emerald-400" aria-hidden="true" /> Copiado!
                      </>
                    ) : (
                      <>
                        <Clipboard className="h-3.5 w-3.5" aria-hidden="true" /> Copiar Link
                      </>
                    )}
                  </button>
                </div>
              </div>
            ) : (
              <p className="mt-2 text-xs text-[var(--text-muted)]">
                O link para o arquivo PDF original desta prova não está cadastrado.
              </p>
            )}
          </div>

          {/* Card 2: Gabarito Oficial */}
          <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-subtle)] p-4 sm:p-5">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 font-medium text-[var(--text)]">
                <FileText className="h-4 w-4 text-[var(--primary)]" aria-hidden="true" />
                <span>Gabarito Oficial</span>
              </div>
              <span
                className={`text-xs px-2.5 py-0.5 rounded-full font-medium ${
                  hasGabarito ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                }`}
              >
                {hasGabarito ? 'Disponível' : 'Indisponível'}
              </span>
            </div>

            {hasGabarito ? (
              <div className="mt-3 flex flex-col gap-3">
                <p className="break-all font-mono text-xs text-[var(--text-muted)] bg-[var(--surface)] p-2.5 rounded-lg border border-[var(--border)]">
                  {data.gabarito_url}
                </p>
                <div className="flex flex-wrap items-center gap-2">
                  <a
                    href={data.gabarito_url!}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="button-primary text-xs py-2 px-3 inline-flex items-center gap-1.5"
                  >
                    <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                    Abrir Gabarito (PDF)
                  </a>
                  <button
                    type="button"
                    className="button-secondary text-xs py-2 px-3 inline-flex items-center gap-1.5"
                    onClick={() => handleCopy(data.gabarito_url!, 'gabarito')}
                  >
                    {copiedField === 'gabarito' ? (
                      <>
                        <Check className="h-3.5 w-3.5 text-emerald-400" aria-hidden="true" /> Copiado!
                      </>
                    ) : (
                      <>
                        <Clipboard className="h-3.5 w-3.5" aria-hidden="true" /> Copiar Link
                      </>
                    )}
                  </button>
                </div>
              </div>
            ) : (
              <p className="mt-2 text-xs text-[var(--text-muted)]">
                O link para o PDF do gabarito oficial não está cadastrado nesta prova.
              </p>
            )}
          </div>
        </div>

        {/* Footer */}
        <footer className="flex justify-end border-t border-[var(--border)] p-4 sm:p-5">
          <button type="button" className="button-secondary text-sm" onClick={onClose}>
            Fechar
          </button>
        </footer>
      </div>
    </div>
  );
};
