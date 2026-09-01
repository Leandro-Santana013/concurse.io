import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { axe } from 'vitest-axe';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SearchHub } from '../components/dashboard/SearchHub';
import { UIProvider } from '../context/UIContext';

const apiMocks = vi.hoisted(() => ({
  claimProcessedExam: vi.fn(),
  getActiveDownloads: vi.fn(async () => []),
  ingestExam: vi.fn(),
  searchExams: vi.fn(),
}));

vi.mock('../services/api', () => ({ api: apiMocks }));

const renderSearch = (onExamReady?: (examId: number) => void | Promise<void>) => render(
  <MemoryRouter initialEntries={['/buscar']}>
    <UIProvider>
      <main>
        <SearchHub onExamReady={onExamReady} />
      </main>
    </UIProvider>
  </MemoryRouter>,
);

describe('busca acessível de provas', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.getActiveDownloads.mockResolvedValue([]);
    apiMocks.searchExams.mockResolvedValue([
      {
        title: 'Auditor Fiscal — FGV 2025',
        url: 'https://example.test/prova-fgv',
        gabarito_url: 'https://example.test/gabarito-fgv',
        has_gabarito_link: true,
        match_score: 94,
        source: 'FGV',
      },
    ]);
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

    expect(apiMocks.searchExams).toHaveBeenCalledWith('Auditor FGV', 'idcap');
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
  });

  it('adiciona uma prova pronta sem abrir um novo processamento', async () => {
    const user = userEvent.setup();
    const onExamReady = vi.fn();
    apiMocks.searchExams.mockResolvedValueOnce([
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
    ]);
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
});
