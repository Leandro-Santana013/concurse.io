import React, { useState } from 'react';
import {
  Check,
  Clipboard,
  ExternalLink,
  FileCheck2,
  FileSearch,
  Loader2,
  RefreshCw,
  Search,
} from 'lucide-react';
import { api } from '../../services/api';
import { AsyncStatus, SearchResultItem } from '../../types/exam';
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

export const SearchHub: React.FC<SearchHubProps> = ({ onExamReady }) => {
  const { openDirectIngestModal, showToast } = useUI();
  const [query, setQuery] = useState('');
  const [selectedSource, setSelectedSource] = useState('all');
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [status, setStatus] = useState<AsyncStatus>('idle');
  const [error, setError] = useState<string | null>(null);
  const [copiedUrl, setCopiedUrl] = useState<string | null>(null);
  const [addingUrl, setAddingUrl] = useState<string | null>(null);

  const executeSearch = async (searchQuery = query) => {
    const cleaned = searchQuery.trim();
    if (!cleaned) {
      setError('Digite o cargo, órgão ou banca que deseja encontrar.');
      setStatus('error');
      return;
    }

    setQuery(cleaned);
    setStatus('loading');
    setError(null);
    try {
      const source = selectedSource === 'all' ? undefined : selectedSource;
      const data = await api.searchExams(cleaned, source);
      setResults(data);
      setStatus(data.length > 0 ? 'success' : 'empty');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Não foi possível concluir a busca.';
      setError(message);
      setStatus('error');
    }
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    void executeSearch();
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

  const handleUseReadyExam = async (item: SearchResultItem) => {
    setAddingUrl(item.url);
    try {
      if (!item.id) throw new Error('A prova processada não possui um identificador válido.');
      const response = await api.claimProcessedExam(item.id);

      setResults((current) => current.filter((result) => result.url !== item.url));
      if (results.length <= 1) setStatus('empty');
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

  return (
    <div className="page-shell space-y-8">
      <header className="max-w-3xl">
        <p className="eyebrow">Descobrir</p>
        <h1 className="page-title">Encontre sua próxima prova</h1>
        <p className="page-description">Busque por cargo, órgão ou banca. Antes de importar, confira a fonte e a disponibilidade do gabarito.</p>
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
              <button type="submit" className="button-primary search-submit" disabled={status === 'loading'} aria-label="Buscar provas">
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

      <section aria-labelledby="results-title" aria-live="polite">
        <div className="mb-4 flex items-center justify-between gap-4">
          <h2 id="results-title" className="section-title">
            {status === 'idle' ? 'Resultados' : status === 'success' ? `${results.length} prova${results.length === 1 ? '' : 's'} encontrada${results.length === 1 ? '' : 's'}` : 'Resultados'}
          </h2>
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
            {results.map((item, index) => (
              <article key={`${item.url}-${index}`} className="border-b border-[var(--border)] p-4 last:border-b-0 sm:p-5">
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap gap-2 text-xs">
                      <span className="status-neutral">{item.source || 'Web'}</span>
                      <span className={item.has_gabarito_link ? 'status-success' : 'status-warning'}>
                        <FileCheck2 aria-hidden="true" /> {item.has_gabarito_link ? 'Gabarito localizado' : 'Gabarito não localizado'}
                      </span>
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
                      <button className="button-primary" onClick={() => openDirectIngestModal({ examUrl: item.url, gabaritoUrl: item.gabarito_url || '', title: item.title })}>Importar</button>
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
      </section>
    </div>
  );
};
