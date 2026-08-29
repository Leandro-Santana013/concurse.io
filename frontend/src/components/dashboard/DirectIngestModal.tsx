import React, { useState, useEffect } from 'react';
import { api } from '../../services/api';
import { useUI } from '../../context/UIContext';
import { X, ExternalLink, Loader2 } from 'lucide-react';

interface DirectIngestModalProps {
  isOpen: boolean;
  onClose: () => void;
  onExamReady?: (examId: number) => void;
  initialExamUrl?: string;
  initialGabaritoUrl?: string;
  initialTitle?: string;
}

export const DirectIngestModal: React.FC<DirectIngestModalProps> = ({
  isOpen,
  onClose,
  onExamReady,
  initialExamUrl = '',
  initialGabaritoUrl = '',
  initialTitle = '',
}) => {
  const { showToast } = useUI();
  const [examUrl, setExamUrl] = useState(initialExamUrl);
  const [gabaritoUrl, setGabaritoUrl] = useState(initialGabaritoUrl);
  const [customTitle, setCustomTitle] = useState(initialTitle);
  
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [progress, setProgress] = useState(0);
  const [statusMsg, setStatusMsg] = useState('');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [readyExamId, setReadyExamId] = useState<number | null>(null);
  const [eventSource, setEventSource] = useState<EventSource | null>(null);

  useEffect(() => {
    if (isOpen) {
      setExamUrl(initialExamUrl || '');
      setGabaritoUrl(initialGabaritoUrl || '');
      setCustomTitle(initialTitle || '');
      setProgress(0);
      setStatusMsg('');
      setErrorMsg(null);
      setReadyExamId(null);
      setIsSubmitting(false);
    } else {
      if (eventSource) {
        eventSource.close();
        setEventSource(null);
      }
    }
  }, [isOpen, initialExamUrl, initialGabaritoUrl, initialTitle]);

  if (!isOpen) return null;

  const handlePasteExam = async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) {
        setExamUrl(text.trim());
      }
    } catch {
      showToast('warning', 'Cole manualmente usando Ctrl+V.');
    }
  };

  const handlePasteGabarito = async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) {
        setGabaritoUrl(text.trim());
      }
    } catch {
      showToast('warning', 'Cole manualmente usando Ctrl+V.');
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanUrl = examUrl.trim();
    if (!cleanUrl) {
      setErrorMsg('Informe o link da prova.');
      return;
    }

    setIsSubmitting(true);
    setErrorMsg(null);
    setProgress(5);
    setStatusMsg('Iniciando processamento...');

    try {
      const titleToSend = customTitle.trim() || 'Nova Prova de Concurso';
      const gabaritoToSend = gabaritoUrl.trim() || undefined;

      const res = await api.ingestExam(cleanUrl, titleToSend, gabaritoToSend);
      const examId = res.exam_id;

      if (res.status === 'Aprovada') {
        setProgress(100);
        setStatusMsg('Prova pronta para o simulado!');
        setReadyExamId(examId);
        return;
      }

      const sse = new EventSource(`/api/v1/exams/${examId}/progress/stream`);
      setEventSource(sse);

      sse.onmessage = (evt) => {
        try {
          const data = JSON.parse(evt.data);
          const prog = data.progress ?? 0;
          const msg = data.status || 'Processando...';

          setProgress(prog);
          setStatusMsg(msg);

          if (prog >= 100) {
            sse.close();
            setReadyExamId(examId);
          } else if (prog === -1) {
            sse.close();
            setIsSubmitting(false);
            setErrorMsg(msg || 'Erro ao processar arquivo.');
          }
        } catch (err) {
          console.error('SSE Error:', err);
        }
      };

      sse.onerror = () => {
        sse.close();
      };
    } catch (err: any) {
      setIsSubmitting(false);
      setErrorMsg(err.message || 'Erro de conexão.');
    }
  };

  const handleStartSimulado = () => {
    if (readyExamId && onExamReady) {
      onClose();
      onExamReady(readyExamId);
    }
  };

  // URL para redirect externo do PCI Concursos
  const pciRedirectUrl = examUrl.trim().startsWith('http')
    ? examUrl.trim()
    : 'https://www.pciconcursos.com.br/provas/';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fadeIn">
      <div className="relative w-full max-w-xl rounded-2xl border border-slate-800 bg-[#0c121e] p-6 shadow-2xl text-slate-100">
        
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800/80 pb-4">
          <h2 className="text-lg font-bold text-white">
            Importar Prova & Gabarito
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
            aria-label="Fechar"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="mt-5 space-y-4">
          {/* Field 1: Exam URL */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-300">
              Link da Prova (PCI Concursos ou PDF)
            </label>
            <div className="relative flex items-center">
              <input
                type="url"
                required
                disabled={isSubmitting}
                value={examUrl}
                onChange={(e) => setExamUrl(e.target.value)}
                placeholder="https://www.pciconcursos.com.br/provas/... ou link do PDF"
                className="w-full rounded-xl border border-slate-700 bg-slate-900/90 py-2.5 pl-3.5 pr-20 text-xs font-mono text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none disabled:opacity-60"
              />
              <button
                type="button"
                disabled={isSubmitting}
                onClick={handlePasteExam}
                className="absolute right-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 px-2.5 py-1 text-[11px] font-medium text-slate-300 transition"
              >
                Colar
              </button>
            </div>
          </div>

          {/* Field 2: Gabarito URL */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-300">
              Link do Gabarito Oficial <span className="text-slate-500 font-normal">(Opcional)</span>
            </label>
            <div className="relative flex items-center">
              <input
                type="url"
                disabled={isSubmitting}
                value={gabaritoUrl}
                onChange={(e) => setGabaritoUrl(e.target.value)}
                placeholder="https://.../gabarito.pdf"
                className="w-full rounded-xl border border-slate-700 bg-slate-900/90 py-2.5 pl-3.5 pr-20 text-xs font-mono text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none disabled:opacity-60"
              />
              <button
                type="button"
                disabled={isSubmitting}
                onClick={handlePasteGabarito}
                className="absolute right-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 px-2.5 py-1 text-[11px] font-medium text-slate-300 transition"
              >
                Colar
              </button>
            </div>
          </div>

          {/* Field 3: Title */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-300">
              Título / Cargo <span className="text-slate-500 font-normal">(Opcional)</span>
            </label>
            <input
              type="text"
              disabled={isSubmitting}
              value={customTitle}
              onChange={(e) => setCustomTitle(e.target.value)}
              placeholder="Ex: IBAM 2024 - Enfermeiro"
              className="w-full rounded-xl border border-slate-700 bg-slate-900/90 py-2.5 px-3.5 text-xs text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none disabled:opacity-60"
            />
          </div>

          {/* Error Alert */}
          {errorMsg && (
            <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-300 font-medium">
              {errorMsg}
            </div>
          )}

          {/* Progress Bar */}
          {isSubmitting && (
            <div className="space-y-1.5 rounded-xl border border-slate-800 bg-slate-950/60 p-3">
              <div className="flex items-center justify-between text-xs font-medium text-slate-300">
                <span className="flex items-center gap-2">
                  {progress < 100 && <Loader2 className="h-3.5 w-3.5 animate-spin text-indigo-400" />}
                  {statusMsg || 'Processando...'}
                </span>
                <span className="font-mono text-slate-100">{progress}%</span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-slate-800">
                <div
                  className="h-full bg-indigo-600 transition-all duration-300"
                  style={{ width: `${Math.max(5, progress)}%` }}
                />
              </div>
            </div>
          )}

          {/* Footer Actions */}
          <div className="mt-6 flex items-center justify-between border-t border-slate-800/80 pt-4">
            {/* Redirect link to PCI Concursos */}
            <a
              href={pciRedirectUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 transition"
              title="Abrir página no PCI Concursos em nova aba"
            >
              <span>Abrir no PCI Concursos</span>
              <ExternalLink className="h-3 w-3" />
            </a>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={onClose}
                disabled={isSubmitting && progress < 100}
                className="rounded-xl border border-slate-700 bg-slate-800/60 hover:bg-slate-800 px-4 py-2 text-xs font-medium text-slate-300 hover:text-white transition disabled:opacity-50"
              >
                Cancelar
              </button>

              {readyExamId ? (
                <button
                  type="button"
                  onClick={handleStartSimulado}
                  className="rounded-xl bg-emerald-600 hover:bg-emerald-500 px-5 py-2 text-xs font-semibold text-white shadow transition"
                >
                  Iniciar Simulado
                </button>
              ) : (
                <button
                  type="submit"
                  disabled={isSubmitting || !examUrl.trim()}
                  className="rounded-xl bg-indigo-600 hover:bg-indigo-500 px-5 py-2 text-xs font-semibold text-white shadow transition disabled:opacity-50"
                >
                  {isSubmitting ? 'Processando...' : 'Processar Prova'}
                </button>
              )}
            </div>
          </div>
        </form>
      </div>
    </div>
  );
};
