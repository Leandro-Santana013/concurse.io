import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { ExamProvider } from '../context/ExamContext';
import { UIProvider } from '../context/UIContext';

const apiMocks = vi.hoisted(() => ({
  getActiveDownloads: vi.fn(async () => []),
  getFolders: vi.fn(async () => []),
  getNotebookStats: vi.fn(async () => []),
}));

vi.mock('../services/api', () => ({ api: apiMocks }));

const LocationProbe = () => {
  const location = useLocation();
  return <output data-testid="current-path">{location.pathname}</output>;
};

const renderApp = (path: string) => render(
  <MemoryRouter initialEntries={[path]}>
    <UIProvider>
      <ExamProvider>
        <App />
        <LocationProbe />
      </ExamProvider>
    </UIProvider>
  </MemoryRouter>,
);

describe('rotas e preferências da aplicação', () => {
  beforeEach(() => {
    localStorage.clear();
    apiMocks.getActiveDownloads.mockResolvedValue([]);
    apiMocks.getFolders.mockResolvedValue([]);
    apiMocks.getNotebookStats.mockResolvedValue([]);
  });

  it('migra a preferência paper para light e navega por URLs reais', async () => {
    localStorage.setItem('concurse_ui_preferences_v1', JSON.stringify({
      theme: 'paper',
      fontSize: 'lg',
      enableEliminationMode: false,
    }));

    const user = userEvent.setup();
    renderApp('/buscar');

    expect(await screen.findByRole('heading', { name: 'Encontre sua próxima prova' })).toBeVisible();
    expect(screen.getByTestId('current-path')).toHaveTextContent('/buscar');

    await waitFor(() => {
      expect(document.documentElement).toHaveClass('theme-light', 'font-scale-ui-lg');
      expect(document.documentElement).toHaveAttribute('data-theme', 'light');
    });

    const migrated = JSON.parse(localStorage.getItem('concurse_ui_preferences_v2') ?? '{}');
    expect(migrated).toMatchObject({
      version: 2,
      theme: 'light',
      fontSize: 'lg',
      enableEliminationMode: false,
    });

    const desktopNavigation = screen.getByRole('complementary', { name: 'Navegação principal' });
    await user.click(within(desktopNavigation).getByRole('link', { name: 'Biblioteca' }));

    expect(await screen.findByRole('heading', { name: 'Suas provas' })).toBeVisible();
    expect(screen.getByTestId('current-path')).toHaveTextContent('/biblioteca');
    expect(within(desktopNavigation).getByRole('link', { name: 'Biblioteca' })).toHaveClass('is-active');
  });
});
