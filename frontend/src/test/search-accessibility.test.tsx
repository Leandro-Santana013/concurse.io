import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { axe } from 'vitest-axe';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SearchHub } from '../components/dashboard/SearchHub';
import { ToastViewport } from '../components/ui/ToastViewport';
import { UIProvider } from '../context/UIContext';

const apiMocks = vi.hoisted(() => ({
  claimProcessedExam: vi.fn(),
  getActiveDownloads: vi.fn(async () => []),
  getExamProgress: vi.fn(),
  ingestExam: vi.fn(),
  searchExams: vi.fn(),
}));

vi.mock('../services/api', () => ({ api: apiMocks }));

const SEARCH_PAGE_SIZE = 25;

const searchPage = (items: Array<Record<string, unknown>>, page = 1, total = items.length) => ({
  items,
  page,
  page_size: SEARCH_PAGE_SIZE,
  total,
  total_pages: total > 0 ? Math.ceil(total / SEARCH_PAGE_SIZE) : 0,
  has_previous: page > 1,
  has_next: page * SEARCH_PAGE_SIZE < total,
});

const renderSearch = (onExamReady?: (examId: number) => void | Promise<void>) => render(
  <MemoryRouter initialEntries={['/buscar']}>
    <UIProvider>
      <main>
        <SearchHub onExamReady={onExamReady} />
      </main>
      <ToastViewport />
    </UIProvider>
  </MemoryRouter>,
);

describe('busca acessível de provas', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.getActiveDownloads.mockResolvedValue([]);
    apiMocks.getExamProgress.mockReset();
    apiMocks.ingestExam.mockReset();
    apiMocks.searchExams.mockResolvedValue(searchPage([
      {
        title: 'Auditor Fiscal — FGV 2025',
        url: 'https://example.test/prova-fgv',
        gabarito_url: 'https://example.test/gabarito-fgv',
        has_gabarito_link: true,
        match_score: 94,
        source: 'FGV',
      },
    ]));
  });

  it('permite filtrar, buscar e comparar um resultado sem violações axe', async () => {
    const user = userEvent.setup();
    const { container } = renderSearch();

    const initialAudit = await axe(container, {
      rules: { 'color-contrast': { enabled: false } },
    });
    expect(initialAudit.violations).toEqual([]);

    await user.click(screen.getByRole('button', { name: 'IDCAP' }));
    expect(screen.getByRole('button', { name: 'IDCAP' })).toHaveAttribute('aria-pressed', 'true');

    await user.type(screen.getByRole('textbox', { name: /^Cargo, órgão ou banca/ }), 'Auditor FGV');
    await user.click(screen.getByRole('button', { name: 'Buscar provas' }));

    expect(apiMocks.searchExams).toHaveBeenCalledWith('Auditor FGV', 'idcap', false, 1, SEARCH_PAGE_SIZE);
    expect(await screen.findByRole('heading', { name: 'Auditor Fiscal — FGV 2025' })).toBeVisible();
    expect(screen.getByRole('link', { name: 'Ver origem' })).toHaveAttribute(
      'href',
      'https://example.test/prova-fgv',
    );
    expect(screen.getByText('Gabarito localizado')).toBeVisible();
    const resultAudit = await axe(container, {
      rules: { 'color-contrast': { enabled: false } },
    });
    expect(resultAudit.violations).toEqual([]);
  }, 30_000);

  it('adiciona uma prova pronta sem abrir um novo processamento', async () => {
    const user = userEvent.setup();
    const onExamReady = vi.fn();
    apiMocks.searchExams.mockResolvedValueOnce(searchPage([
      {
        id: 42,
        title: 'Auditor Fiscal — FGV 2025',
        url: 'https://example.test/prova-fgv',
        gabarito_url: 'https://example.test/gabarito-fgv',
        has_gabarito_link: true,
        match_score: 94,
        source: 'Acervo',
        status: 'Aprovada',
        reuse_available: true,
      },
    ]));
    apiMocks.claimProcessedExam.mockResolvedValueOnce({
      exam_id: 42,
      title: 'Auditor Fiscal — FGV 2025',
      status: 'Aprovada',
      progress: 100,
      message: 'Prova pronta recuperada do banco, sem nova extração.',
      reused: true,
      already_in_library: false,
    });

    renderSearch(onExamReady);
    await user.type(screen.getByRole('textbox', { name: /^Cargo, órgão ou banca/ }), 'Auditor FGV');
    await user.click(screen.getByRole('button', { name: 'Buscar provas' }));
    expect(await screen.findByText('Já processada')).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Adicionar à biblioteca' }));

    expect(apiMocks.claimProcessedExam).toHaveBeenCalledWith(42);
    expect(apiMocks.ingestExam).not.toHaveBeenCalled();
    expect(onExamReady).toHaveBeenCalledWith(42);
    expect(await screen.findByText('Nenhuma prova encontrada')).toBeVisible();
  });

  it('navega entre páginas de resultados de forma acessível', async () => {
    const user = userEvent.setup();
    const firstPage = Array.from({ length: SEARCH_PAGE_SIZE }, (_, index) => ({
      title: `Auditor ${index}`,
      url: `https://example.test/prova-${index}`,
      has_gabarito_link: false,
      match_score: 80,
      source: 'Web',
    }));
    const secondPage = [{
      title: 'Auditor 25',
      url: 'https://example.test/prova-25',
      has_gabarito_link: false,
      match_score: 80,
      source: 'Web',
    }];
    apiMocks.searchExams
      .mockResolvedValueOnce(searchPage(firstPage, 1, 26))
      .mockResolvedValueOnce(searchPage(secondPage, 2, 26));

    renderSearch();
    await user.type(screen.getByRole('textbox', { name: /^Cargo, órgão ou banca/ }), 'Auditor FGV');
    await user.click(screen.getByRole('button', { name: 'Buscar provas' }));

    expect(await screen.findByText('Auditor 0')).toBeVisible();
    expect(screen.getByText('Página 1 de 2')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Próxima página' })).toBeEnabled();

    await user.click(screen.getByRole('button', { name: 'Próxima página' }));

    expect(await screen.findByRole('heading', { name: 'Auditor 25' })).toBeVisible();
    expect(screen.getByText('Página 2 de 2')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Página anterior' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Próxima página' })).toBeDisabled();
    expect(apiMocks.searchExams).toHaveBeenNthCalledWith(2, 'Auditor FGV', undefined, false, 2, SEARCH_PAGE_SIZE);
  });

  it('processa uma prova IDCAP sem abrir modal e avisa quando termina', async () => {
    const user = userEvent.setup();
    apiMocks.searchExams.mockResolvedValueOnce(searchPage([{
      title: 'IDCAP - Prefeitura de Exemplo - Enfermeiro',
      url: 'https://idcap.selecao.net.br/provas/enfermeiro.pdf',
      has_gabarito_link: false,
      match_score: 95,
      source: 'idcap',
    }]));
    apiMocks.ingestExam.mockResolvedValueOnce({
      exam_id: 73,
      title: 'Enfermeiro',
      status: 'Processando',
      progress: 5,
      message: 'Processamento assíncrono iniciado com sucesso.',
      reused: false,
      already_in_library: false,
    });
    apiMocks.getExamProgress.mockResolvedValueOnce({
      status: 'Prova concluída com sucesso!',
      progress: 100,
      error_type: null,
    });

    renderSearch();
    await user.type(screen.getByRole('textbox', { name: /^Cargo, órgão ou banca/ }), 'Enfermeiro IDCAP');
    await user.click(screen.getByRole('button', { name: 'Buscar provas' }));
    expect(await screen.findByRole('heading', { name: 'IDCAP - Prefeitura de Exemplo - Enfermeiro' })).toBeVisible();
    expect(screen.queryByText(/gabarito/i)).not.toBeInTheDocument();
    await user.click(await screen.findByRole('button', { name: 'Importar' }));

    expect(apiMocks.ingestExam).toHaveBeenCalledWith(
      'https://idcap.selecao.net.br/provas/enfermeiro.pdf',
      'IDCAP - Prefeitura de Exemplo - Enfermeiro',
    );
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(await screen.findByText('Prova IDCAP processada')).toBeVisible();
  });

  it('avisa no popup quando o processamento IDCAP falha', async () => {
    const user = userEvent.setup();
    apiMocks.searchExams.mockResolvedValueOnce(searchPage([{
      title: 'IDCAP - Prefeitura de Exemplo - Técnico',
      url: 'https://idcap.selecao.net.br/provas/tecnico.pdf',
      has_gabarito_link: false,
      match_score: 95,
      source: 'idcap',
    }]));
    apiMocks.ingestExam.mockResolvedValueOnce({
      exam_id: 74,
      title: 'Técnico',
      status: 'Processando',
      progress: 5,
      message: 'Processamento assíncrono iniciado com sucesso.',
      reused: false,
      already_in_library: false,
    });
    apiMocks.getExamProgress.mockResolvedValueOnce({
      status: 'Erro na extração de questões.',
      progress: -1,
      error_type: 'EXTRACTION_ERROR',
    });

    renderSearch();
    await user.type(screen.getByRole('textbox', { name: /^Cargo, órgão ou banca/ }), 'Técnico IDCAP');
    await user.click(screen.getByRole('button', { name: 'Buscar provas' }));
    await user.click(await screen.findByRole('button', { name: 'Importar' }));

    expect(await screen.findByText('Falha ao processar prova IDCAP')).toBeVisible();
  });
});
