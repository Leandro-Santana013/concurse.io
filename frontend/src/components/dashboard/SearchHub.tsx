import React, { useEffect, useRef, useState } from 'react';
import {
  Check,
  ChevronLeft,
  ChevronRight,
  Clipboard,
  ExternalLink,
  FileCheck2,
  FileSearch,
  Loader2,
  RefreshCw,
  Search,
} from 'lucide-react';
import { api } from '../../services/api';
import { AsyncStatus, ExamProgress, SearchResultItem, SearchResultsPage } from '../../types/exam';
import { useUI } from '../../context/UIContext';

interface SearchHubProps {
  onExamReady?: (examId: number) => void | Promise<void>;
}

const SOURCE_OPTIONS = [
  { id: 'all', label: 'Todas' },
  { id: 'idcap', label: 'IDCAP' },
  { id: 'pci', label: 'PCI Concursos' },
  { id: 'web', label: 'Web' },
];

const POPULAR_QUERIES = ['FGV', 'Cebraspe', 'Polícia Federal', 'Tribunais'];
const SEARCH_PAGE_SIZE = 25;
const IDCAP_PATTERN = /\b(?:id\s*cap|idecap)\b/i;
const TERMINAL_IMPORT_ERRORS = new Set(['erro', 'falha']);
const IDCAP_PROGRESS_POLL_INTERVAL_MS = 1500;
const MAX_IDCAP_PROGRESS_POLLS = 600;

const isIdcapResult = (item: SearchResultItem) =>
  IDCAP_PATTERN.test(`${item.source || ''} ${item.title} ${item.url}`);

const wait = (milliseconds: number) =>
  new Promise<void>((resolve) => window.setTimeout(resolve, milliseconds));

const waitForIdcapImport = async (examId: number): Promise<ExamProgress> => {
  for (let attempt = 0; attempt < MAX_IDCAP_PROGRESS_POLLS; attempt += 1) {
    const snapshot = await api.getExamProgress(examId);
    const normalizedStatus = String(snapshot.status || '').trim().toLowerCase();

    if (snapshot.progress >= 100 || normalizedStatus === 'aprovada') return snapshot;
    if (snapshot.progress < 0 || snapshot.error_type || TERMINAL_IMPORT_ERRORS.has(normalizedStatus)) {
      throw new Error(snapshot.status || 'O processamento da prova falhou.');
    }

    await wait(IDCAP_PROGRESS_POLL_INTERVAL_MS);
  }

  throw new Error('O processamento excedeu o tempo de acompanhamento. A biblioteca continuará sendo atualizada em segundo plano.');
};

export const SearchHub: React.FC<SearchHubProps> = ({ onExamReady }) => {
  const { openDirectIngestModal, refreshDownloads, showToast } = useUI();
  const [query, setQuery] = useState('');
  const [selectedSource, setSelectedSource] = useState('all');
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [status, setStatus] = useState<AsyncStatus>('idle');
  const [error, setError] = useState<string | null>(null);
  const [copiedUrl, setCopiedUrl] = useState<string | null>(null);
  const [addingUrl, setAddingUrl] = useState<string | null>(null);
  const [pagination, setPagination] = useState<SearchResultsPage | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [isPageLoading, setIsPageLoading] = useState(false);
  const [processingIdcapUrl, setProcessingIdcapUrl] = useState<string | null>(null);
  const requestIdRef = useRef(0);
  const focusResultsRef = useRef(false);
  const resultsHeadingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (!focusResultsRef.current || status !== 'success') return;
    focusResultsRef.current = false;
    resultsHeadingRef.current?.focus();
  }, [currentPage, status]);

  const executeSearch = async (searchQuery = query, nextPage = 1, preserveResults = false) => {
    const cleaned = searchQuery.trim();
    if (!cleaned) {
      setError('Digite o cargo, órgão ou banca que deseja encontrar.');
      setStatus('error');
      return;
    }

    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setQuery(cleaned);
    setError(null);
    if (preserveResults) {
      setIsPageLoading(true);
      focusResultsRef.current = true;
    } else {
      setStatus('loading');
      setResults([]);
      setPagination(null);
      setCurrentPage(1);
      setIsPageLoading(false);
    }

    try {
      const source = selectedSource === 'all' ? undefined : selectedSource;
      const data = await api.searchExams(cleaned, source, false, nextPage, SEARCH_PAGE_SIZE);
      if (requestId !== requestIdRef.current) return;
      setResults(data.items);
      setPagination(data);
      setCurrentPage(data.page);
      setStatus(data.items.length > 0 ? 'success' : 'empty');
    } catch (err) {
      if (requestId !== requestIdRef.current) return;
      const message = err instanceof Error ? err.message : 'Não foi possível concluir a busca.';
      setError(message);
      setStatus('error');
      focusResultsRef.current = false;
    } finally {
      if (requestId === requestIdRef.current) setIsPageLoading(false);
    }
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    void executeSearch();
  };

  const handlePageChange = (nextPage: number) => {
    if (!pagination || isPageLoading || nextPage < 1 || nextPage > pagination.total_pages) return;
    void executeSearch(query, nextPage, true);
  };

  const handleCopy = async (url: string) => {
    try {
      await navigator.clipboard.writeText(url);
      setCopiedUrl(url);
      window.setTimeout(() => setCopiedUrl((current) => current === url ? null : current), 1800);
    } catch {
      showToast('warning', 'Não foi possível copiar o link', 'Selecione o endereço e copie manualmente.');
    }
  };

  const removeResultFromCurrentPage = (url: string) => {
    const nextResults = results.filter((result) => result.url !== url);
    const currentPageSize = pagination?.page_size ?? SEARCH_PAGE_SIZE;
    const totalAfterRemoval = Math.max(0, (pagination?.total ?? results.length) - 1);
    const totalPagesAfterRemoval = totalAfterRemoval > 0
      ? Math.ceil(totalAfterRemoval / currentPageSize)
      : 0;

    setResults(nextResults);
    if (totalAfterRemoval === 0) {
      setStatus('empty');
      setPagination(null);
      setCurrentPage(1);
    } else if (nextResults.length === 0 && currentPage > totalPagesAfterRemoval) {
      void executeSearch(query, totalPagesAfterRemoval, true);
    } else {
      setPagination((current) => {
        if (!current) return current;
        return {
          ...current,
          total: totalAfterRemoval,
          total_pages: totalPagesAfterRemoval,
          has_previous: current.page > 1 && totalAfterRemoval > 0,
          has_next: current.page < totalPagesAfterRemoval,
        };
      });
    }
  };

  const handleUseReadyExam = async (item: SearchResultItem) => {
    setAddingUrl(item.url);
    try {
      if (!item.id) throw new Error('A prova processada não possui um identificador válido.');
      const response = await api.claimProcessedExam(item.id);

      removeResultFromCurrentPage(item.url);
      showToast('success', 'Prova adicionada à biblioteca', 'Nenhum download ou nova extração foi iniciado.');
      await onExamReady?.(response.exam_id);
    } catch (err) {
      showToast(
        'error',
        'Não foi possível adicionar a prova',
        err instanceof Error ? err.message : 'Tente novamente em instantes.',
      );
    } finally {
      setAddingUrl(null);
    }
  };

  const handleIdcapImport = async (item: SearchResultItem) => {
    if (processingIdcapUrl) return;

    setProcessingIdcapUrl(item.url);
    showToast('info', 'Processando prova IDCAP', 'A prova será adicionada à biblioteca sem abrir outra janela.');
    try {
      const response = await api.ingestExam(item.url, item.title);
      if (response.progress < 100 && response.status !== 'Aprovada') {
        await waitForIdcapImport(response.exam_id);
      }

      removeResultFromCurrentPage(item.url);
      showToast('success', 'Prova IDCAP processada', 'A prova foi adicionada à sua biblioteca.');
    } catch (err) {
      showToast(
        'error',
        'Falha ao processar prova IDCAP',
        err instanceof Error ? err.message : 'Tente novamente em instantes.',
      );
    } finally {
      setProcessingIdcapUrl(null);
      void refreshDownloads();
    }
  };

  const totalResults = pagination?.total ?? results.length;
  const pageSize = pagination?.page_size ?? SEARCH_PAGE_SIZE;
  const firstResult = totalResults > 0 ? ((currentPage - 1) * pageSize) + 1 : 0;
  const lastResult = totalResults > 0 ? Math.min(currentPage * pageSize, totalResults) : 0;

  return (
    <div className="page-shell space-y-8">
      <header className="max-w-3xl">
        <p className="eyebrow">Descobrir</p>
        <h1 className="page-title">Encontre sua próxima prova</h1>
        <p className="page-description">Busque por cargo, órgão ou banca. Antes de importar, confira a fonte.</p>
      </header>

      <section className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4 sm:p-6" aria-labelledby="search-title">
        <h2 id="search-title" className="sr-only">Buscar provas</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="block">
            <label className="field-label" htmlFor="exam-search">Cargo, órgão ou banca</label>
            <div className="search-control mt-2">
              <Search className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-[var(--text-muted)]" aria-hidden="true" />
              <input
                id="exam-search"
                className="input-control search-input text-base"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Ex.: FGV Auditor, TJ Técnico, Polícia Federal"
                aria-describedby="search-help"
              />
              <button type="submit" className="button-primary search-submit" disabled={status === 'loading' || isPageLoading} aria-label="Buscar provas">
                {status === 'loading' ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Search aria-hidden="true" />}
                <span className="hidden sm:inline">Buscar</span>
              </button>
            </div>
            <span id="search-help" className="mt-2 block text-sm text-[var(--text-muted)]">Tente combinar banca, cargo e ano para resultados mais precisos.</span>
          </div>

          <div className="flex flex-col gap-3 border-t border-[var(--border)] pt-4 md:flex-row md:items-center md:justify-between">
            <fieldset>
              <legend className="field-label mb-2">Fontes</legend>
              <div className="flex flex-wrap gap-2">
                {SOURCE_OPTIONS.map((source) => (
                  <button
                    key={source.id}
                    type="button"
                    aria-pressed={selectedSource === source.id}
                    className={selectedSource === source.id ? 'filter-chip filter-chip-active' : 'filter-chip'}
                    onClick={() => setSelectedSource(source.id)}
                  >
                    {source.label}
                  </button>
                ))}
              </div>
            </fieldset>
            <button type="button" className="button-secondary" onClick={() => openDirectIngestModal()}>
              <Clipboard aria-hidden="true" /> Importar um link direto
            </button>
          </div>
        </form>

        <div className="mt-4 flex flex-wrap items-center gap-2 text-sm">
          <span className="text-[var(--text-muted)]">Buscas comuns:</span>
          {POPULAR_QUERIES.map((suggestion) => (
            <button key={suggestion} type="button" className="text-link" onClick={() => void executeSearch(suggestion)}>{suggestion}</button>
          ))}
        </div>
      </section>

      <section aria-labelledby="results-title" aria-live="polite" aria-busy={isPageLoading || status === 'loading'}>
        <div className="mb-4 flex items-center justify-between gap-4">
          <div>
            <h2 id="results-title" ref={resultsHeadingRef} tabIndex={-1} className="section-title">
              {status === 'idle' ? 'Resultados' : status === 'success' ? `${totalResults} prova${totalResults === 1 ? '' : 's'} encontrada${totalResults === 1 ? '' : 's'}` : 'Resultados'}
            </h2>
            {status === 'success' && pagination && (
              <p className="mt-1 text-sm text-[var(--text-muted)]">Mostrando {firstResult}–{lastResult}</p>
            )}
          </div>
          {isPageLoading && (
            <span className="flex items-center gap-2 text-sm text-[var(--text-muted)]" role="status">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              Atualizando página…
            </span>
          )}
        </div>

        {status === 'idle' && (
          <div className="state-card text-center"><FileSearch className="mx-auto" aria-hidden="true" /><h3>Comece com uma busca</h3><p>Os resultados aparecerão aqui, organizados para comparação rápida.</p></div>
        )}

        {status === 'loading' && (
          <div className="space-y-3" aria-busy="true">{[1, 2, 3].map((item) => <div key={item} className="skeleton h-32 w-full" />)}</div>
        )}

        {status === 'empty' && (
          <div className="state-card text-center"><FileSearch className="mx-auto" aria-hidden="true" /><h3>Nenhuma prova encontrada</h3><p>Tente remover o ano, trocar a banca ou consultar todas as fontes.</p></div>
        )}

        {status === 'error' && (
          <div className="state-card" role="alert">
            <RefreshCw aria-hidden="true" /><div><h3>Não foi possível buscar</h3><p>{error}</p></div>
            {query && <button className="button-secondary" onClick={() => void executeSearch()}>Tentar novamente</button>}
          </div>
        )}

        {status === 'success' && (
          <div className="overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface)]">
            {results.map((item) => (
              <article key={item.id ? `exam-${item.id}` : item.url} className="border-b border-[var(--border)] p-4 last:border-b-0 sm:p-5">
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap gap-2 text-xs">
                      <span className="status-neutral">{item.source || 'Web'}</span>
                      {!isIdcapResult(item) && (
                        <span className={item.has_gabarito_link ? 'status-success' : 'status-warning'}>
                          <FileCheck2 aria-hidden="true" /> {item.has_gabarito_link ? 'Gabarito localizado' : 'Gabarito não localizado'}
                        </span>
                      )}
                      {item.reuse_available && <span className="status-success"><Check aria-hidden="true" /> Já processada</span>}
                      {item.match_score > 0 && <span className="status-neutral">Compatibilidade {item.match_score}%</span>}
                    </div>
                    <h3 className="mt-3 text-base font-semibold leading-snug text-[var(--text)]">{item.title}</h3>
                    <details className="mt-3 text-sm text-[var(--text-muted)]">
                      <summary className="cursor-pointer font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus)]">Detalhes da fonte</summary>
                      <p className="mt-2 break-all font-mono text-xs">{item.url}</p>
                    </details>
                  </div>
                  <div className="flex flex-wrap gap-2 lg:justify-end">
                    {item.reuse_available ? (
                      <button
                        className="button-primary"
                        disabled={addingUrl !== null}
                        aria-busy={addingUrl === item.url}
                        onClick={() => void handleUseReadyExam(item)}
                      >
                        {addingUrl === item.url ? <Loader2 aria-hidden="true" /> : <FileCheck2 aria-hidden="true" />}
                        {addingUrl === item.url ? 'Adicionando…' : 'Adicionar à biblioteca'}
                      </button>
                    ) : (
                      <button
                        className="button-primary"
                        disabled={processingIdcapUrl !== null}
                        aria-busy={processingIdcapUrl === item.url}
                        onClick={() => {
                          if (isIdcapResult(item)) {
                            void handleIdcapImport(item);
                          } else {
                            openDirectIngestModal({ examUrl: item.url, gabaritoUrl: item.gabarito_url || '', title: item.title });
                          }
                        }}
                      >
                        {processingIdcapUrl === item.url && <Loader2 className="animate-spin" aria-hidden="true" />}
                        {processingIdcapUrl === item.url ? 'Processando…' : 'Importar'}
                      </button>
                    )}
                    <a className="button-secondary" href={item.url} target="_blank" rel="noreferrer"><ExternalLink aria-hidden="true" /> Ver origem</a>
                    <button className="button-ghost" onClick={() => void handleCopy(item.url)}>
                      {copiedUrl === item.url ? <Check aria-hidden="true" /> : <Clipboard aria-hidden="true" />}
                      {copiedUrl === item.url ? 'Copiado' : 'Copiar link'}
                    </button>
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}

        {status === 'success' && pagination && pagination.total_pages > 1 && (
          <nav className="mt-5 flex items-center justify-between gap-4" aria-label="Paginação dos resultados" aria-busy={isPageLoading}>
            <button
              type="button"
              className="button-secondary"
              onClick={() => handlePageChange(pagination.page - 1)}
              disabled={isPageLoading || !pagination.has_previous}
              aria-label="Página anterior"
            >
              <ChevronLeft aria-hidden="true" />
              <span>Anterior</span>
            </button>
            <span className="text-sm font-semibold text-[var(--text-muted)]" aria-live="polite">
              Página {pagination.page} de {pagination.total_pages}
            </span>
            <button
              type="button"
              className="button-secondary"
              onClick={() => handlePageChange(pagination.page + 1)}
              disabled={isPageLoading || !pagination.has_next}
              aria-label="Próxima página"
            >
              <span>Próxima</span>
              <ChevronRight aria-hidden="true" />
            </button>
          </nav>
        )}
      </section>
    </div>
  );
};
