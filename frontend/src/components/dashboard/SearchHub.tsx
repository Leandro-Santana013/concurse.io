import React, { useState } from 'react';
import { api } from '../../services/api';
import { SearchResultItem } from '../../types/exam';
import { useUI } from '../../context/UIContext';
import {
  Search,
  DownloadCloud,
  FileText,
  CheckCircle2,
  Sparkles,
  Loader2,
  AlertCircle,
  Building2,
  ExternalLink,
  ArrowRight,
  GraduationCap,
} from 'lucide-react';

interface SearchHubProps {
  onExamReady?: (examId: number) => void;
}

export const SearchHub: React.FC<SearchHubProps> = ({ onExamReady }) => {
  const { showToast, navigateTo } = useUI();
  const [query, setQuery] = useState('');
  const [selectedSource, setSelectedSource] = useState('all');
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [ingestingUrls, setIngestingUrls] = useState<
    Record<string, { examId?: number; progress: number; statusMsg: string }>
  >({});
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const popularBancas = ['Cebraspe', 'FGV', 'FCC', 'IBAM', 'Vunesp', 'IDCAP', 'Cesgranrio'];

  const handleSearch = async (e?: React.FormEvent, directQuery?: string) => {
    if (e) e.preventDefault();
    const searchQuery = directQuery !== undefined ? directQuery : query;
    if (!searchQuery.trim()) return;

    if (directQuery) setQuery(directQuery);

    setIsLoading(true);
    setErrorMsg(null);
    try {
      const sourceParam = selectedSource === 'all' ? undefined : selectedSource;
      const data = await api.searchExams(searchQuery, sourceParam);
      setResults(data);
    } catch (err: any) {
      setErrorMsg(err.message || 'Erro ao realizar busca de provas.');
      showToast('error', 'Falha na busca', err.message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleIngest = async (item: SearchResultItem) => {
    const key = item.url;
    setIngestingUrls((prev) => ({
      ...prev,
      [key]: { progress: 10, statusMsg: 'Iniciando download do PDF...' },
    }));

    try {
      const res = await api.ingestExam(item.url, item.title, item.gabarito_url || undefined);
      const examId = res.exam_id;

      // Start Server-Sent Events (SSE) Listener
      const eventSource = new EventSource(`/api/v1/exams/${examId}/progress/stream`);

      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          const progress = data.progress || 0;
          const statusMsg = data.status || 'Processando com IA...';

          setIngestingUrls((prev) => ({
            ...prev,
            [key]: { examId, progress, statusMsg },
          }));

          if (progress >= 100) {
            eventSource.close();
            showToast('success', 'Prova Pronta!', `"${item.title.substring(0, 40)}..." foi indexada com sucesso.`);
            if (onExamReady) onExamReady(examId);
          } else if (progress === -1) {
            eventSource.close();
            showToast('error', 'Falha no processamento', statusMsg);
          }
        } catch (e) {
          console.error('SSE Parse Error:', e);
        }
      };

      eventSource.onerror = () => {
        eventSource.close();
      };
    } catch (e: any) {
      setIngestingUrls((prev) => ({
        ...prev,
        [key]: { progress: -1, statusMsg: `Erro: ${e.message}` },
      }));
      showToast('error', 'Erro ao iniciar download', e.message);
    }
  };

  return (
    <div className="mx-auto max-w-6xl animate-fadeIn p-4 sm:p-6 lg:p-8 space-y-8">
      {/* Bento Hero Banner with Frosted Glass & Light Glow */}
      <div className="relative overflow-hidden rounded-3xl border border-white/15 bg-gradient-to-br from-indigo-950/40 via-[#0E1626]/85 to-[#080C14]/90 p-6 sm:p-10 shadow-2xl backdrop-blur-2xl">
        <div className="absolute -top-24 -right-24 h-64 w-64 rounded-full bg-indigo-500/20 blur-3xl pointer-events-none" />
        <div className="absolute -bottom-24 -left-24 h-64 w-64 rounded-full bg-cyan-500/15 blur-3xl pointer-events-none" />

        <div className="relative z-10 max-w-3xl">
          <div className="inline-flex items-center gap-2 rounded-full glass-pill-indigo px-3.5 py-1.5 text-xs font-bold">
            <Sparkles className="h-3.5 w-3.5 text-indigo-400" />
            <span>Motor de Busca & Indexação IA</span>
          </div>

          <h1 className="mt-4 font-heading text-2xl sm:text-4xl font-black tracking-tight text-white">
            Encontre Qualquer Prova Oficial
          </h1>
          <p className="mt-2 text-sm sm:text-base text-slate-300 font-reading leading-relaxed">
            Pesquise por cargo, banca examinadora ou órgão público. O motor extrai enunciados, fórmulas matemáticas e gabaritos oficiais para você resolver no simulador.
          </p>

          {/* Search Form with Glass Input & Primary Glass Button */}
          <form onSubmit={handleSearch} className="mt-7 flex flex-col sm:flex-row gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Ex: IBAM Enfermeiro, Polícia Federal Agente, FGV Auditor, TJ..."
                className="w-full glass-input rounded-2xl py-4 pl-12 pr-4 text-sm font-medium placeholder-slate-400"
              />
            </div>
            <button
              type="submit"
              disabled={isLoading || !query.trim()}
              className="flex items-center justify-center gap-2 rounded-2xl glass-btn-primary px-7 py-4 font-heading font-bold text-sm text-white disabled:opacity-50"
            >
              {isLoading ? <Loader2 className="h-5 w-5 animate-spin" /> : <Search className="h-5 w-5" />}
              <span>Buscar Provas</span>
            </button>
          </form>

          {/* Quick Banca Chips */}
          <div className="mt-5 flex flex-wrap items-center gap-2">
            <span className="text-xs font-bold text-slate-400 mr-1">Bancas Populares:</span>
            {popularBancas.map((banca) => (
              <button
                key={banca}
                onClick={() => handleSearch(undefined, banca)}
                className="rounded-xl glass-btn-secondary px-3 py-1 text-xs font-semibold text-slate-300 hover:text-white transition"
              >
                {banca}
              </button>
            ))}
          </div>

          {/* Source Filter Tabs */}
          <div className="mt-4 flex flex-wrap gap-2 pt-3 border-t border-white/10">
            {[
              { id: 'all', label: 'Todas as Fontes' },
              { id: 'idcap', label: 'IDCAP' },
              { id: 'pci', label: 'PCI Concursos' },
              { id: 'web', label: 'Web Geral' },
            ].map((chip) => (
              <button
                key={chip.id}
                onClick={() => setSelectedSource(chip.id)}
                className={`rounded-xl px-3.5 py-1.5 text-xs font-bold transition ${
                  selectedSource === chip.id
                    ? 'glass-btn-primary text-white shadow-md'
                    : 'glass-btn-secondary text-slate-400 hover:text-slate-200'
                }`}
              >
                {chip.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Error Message Alert */}
      {errorMsg && (
        <div className="flex items-center gap-3 rounded-2xl glass-pill-rose p-4 text-sm font-medium shadow-lg">
          <AlertCircle className="h-5 w-5 shrink-0 text-rose-400" />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* Search Results Area */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-heading text-lg font-bold text-white">
            Resultados Encontrados {results.length > 0 && <span className="text-indigo-400 font-mono">({results.length})</span>}
          </h2>
        </div>

        {results.length === 0 && !isLoading && (
          <div className="flex h-64 flex-col items-center justify-center rounded-3xl glass-card text-center p-6 text-slate-400">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl glass-btn-secondary text-slate-300 mb-3">
              <FileText className="h-6 w-6 stroke-[1.5]" />
            </div>
            <p className="font-heading font-semibold text-slate-200">Nenhuma busca realizada</p>
            <p className="mt-1 text-xs text-slate-400 max-w-sm">
              Digite um cargo ou banca examinadora acima para pesquisar cadernos de questões reais.
            </p>
          </div>
        )}

        {isLoading && (
          <div className="flex h-64 flex-col items-center justify-center rounded-3xl glass-card text-slate-400">
            <Loader2 className="h-8 w-8 animate-spin text-indigo-400" />
            <p className="mt-3 font-heading text-sm font-semibold text-slate-200">Pesquisando cadernos e gabaritos...</p>
            <p className="text-xs text-slate-400 mt-1">Varrendo repositórios oficiais e organizando questões</p>
          </div>
        )}

        {results.length > 0 && (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {results.map((item, idx) => {
              const ingestStatus = ingestingUrls[item.url];
              const isDone = ingestStatus && ingestStatus.progress >= 100;
              const isError = ingestStatus && ingestStatus.progress === -1;
              const isProcessing = ingestStatus && ingestStatus.progress > 0 && ingestStatus.progress < 100;

              return (
                <div
                  key={idx}
                  className="glass-card-interactive flex flex-col justify-between p-5 group"
                >
                  <div>
                    <div className="flex items-center justify-between gap-2 flex-wrap">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="rounded-lg glass-pill-indigo px-2.5 py-0.5 text-[11px] font-mono font-bold">
                          {item.source.toUpperCase()}
                        </span>
                        {item.match_score !== undefined && item.match_score > 0 && (
                          <span
                            className={`rounded-lg px-2 py-0.5 text-[10px] font-mono font-bold transition ${
                              item.match_score >= 80
                                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 shadow-sm shadow-emerald-500/10'
                                : item.match_score >= 50
                                ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/40'
                                : 'bg-slate-700/40 text-slate-400 border border-white/10'
                            }`}
                          >
                            {item.match_score}% Match
                          </span>
                        )}
                      </div>
                      {item.has_gabarito_link && (
                        <span className="rounded-lg glass-pill-emerald px-2 py-0.5 text-[10px] font-bold">
                          Gabarito Vinculado
                        </span>
                      )}
                    </div>

                    <h3 className="mt-3.5 font-heading text-sm font-bold text-white leading-snug line-clamp-2 group-hover:text-indigo-300 transition" title={item.title}>
                      {item.title}
                    </h3>
                  </div>

                  {/* Actions & Progress Area */}
                  <div className="mt-5 border-t border-white/10 pt-4">
                    {isProcessing && (
                      <div className="space-y-2">
                        <div className="flex items-center justify-between text-xs font-semibold text-slate-300">
                          <span className="truncate pr-2">{ingestStatus.statusMsg}</span>
                          <span className="text-indigo-400 font-mono font-bold">{ingestStatus.progress}%</span>
                        </div>
                        <div className="h-2 w-full overflow-hidden rounded-full bg-slate-900 border border-white/10">
                          <div
                            className="h-full bg-gradient-to-r from-indigo-500 via-violet-500 to-cyan-400 transition-all duration-300 shadow-sm"
                            style={{ width: `${ingestStatus.progress}%` }}
                          />
                        </div>
                      </div>
                    )}

                    {isDone && (
                      <button
                        onClick={() => ingestStatus.examId && onExamReady && onExamReady(ingestStatus.examId)}
                        className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-emerald-600 to-emerald-700 py-2.5 text-xs font-bold text-white shadow-lg shadow-emerald-600/30 hover:from-emerald-500 hover:to-emerald-600 border border-white/20 transition"
                      >
                        <CheckCircle2 className="h-4 w-4" /> Abrir Simulado
                      </button>
                    )}

                    {isError && (
                      <div className="rounded-xl glass-pill-rose p-2.5 text-xs">
                        {ingestStatus.statusMsg}
                      </div>
                    )}

                    {!ingestStatus && (
                      <button
                        onClick={() => handleIngest(item)}
                        className="flex w-full items-center justify-center gap-2 rounded-xl glass-btn-secondary py-2.5 text-xs font-bold text-slate-100 hover:text-white transition shadow"
                      >
                        <DownloadCloud className="h-4 w-4 text-indigo-400" />
                        <span>Baixar & Treinar Prova</span>
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
