import React from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { axe } from 'vitest-axe';
import { Navbar } from '../components/layout/Navbar';
import { UIProvider, useUI } from '../context/UIContext';

const navigationMocks = vi.hoisted(() => ({
  getActiveDownloads: vi.fn<() => Promise<Array<{ id: number }>>>(async () => []),
  activeExam: null as { id: number } | null,
}));
vi.mock('../services/api', () => ({ api: { getActiveDownloads: navigationMocks.getActiveDownloads } }));
vi.mock('../context/AuthContext', () => ({ useAuth: () => ({ user: { id: 1, name: 'Leandro', email: 'leandro@example.com' } }) }));
vi.mock('../context/ExamContext', () => ({ useExam: () => ({ activeExam: navigationMocks.activeExam, isFinished: false }) }));

const StateProbe = () => {
  const location = useLocation();
  const { isDirectIngestModalOpen } = useUI();
  return <output data-testid="navigation-state">{location.pathname}:{isDirectIngestModalOpen ? 'import-open' : 'import-closed'}</output>;
};

const renderNavigation = () => render(
  <MemoryRouter initialEntries={['/']}>
    <UIProvider><Navbar /><StateProbe /></UIProvider>
  </MemoryRouter>,
);

beforeAll(() => {
  // jsdom does not implement the native dialog methods or its top layer.
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', {
    configurable: true, value: function () { this.open = true; },
  });
  Object.defineProperty(HTMLDialogElement.prototype, 'close', {
    configurable: true, value: function () { this.open = false; },
  });
});

describe('navegação mobile', () => {
  beforeEach(() => {
    navigationMocks.activeExam = null;
    navigationMocks.getActiveDownloads.mockResolvedValue([]);
  });

  it('mantém os cinco destinos principais, incluindo Perfil, na barra inferior', async () => {
    const user = userEvent.setup();
    renderNavigation();
    const bottom = screen.getByRole('navigation', { name: 'Navegação principal' });
    expect(within(bottom).getAllByRole('link').map((link) => link.getAttribute('aria-label'))).toEqual([
      'Início', 'Biblioteca', 'Buscar', 'Progresso', 'Perfil',
    ]);
    await user.click(within(bottom).getByRole('link', { name: 'Perfil' }));
    expect(screen.getByTestId('navigation-state')).toHaveTextContent('/perfil:import-closed');
  });

  it('abre o menu, move o foco e restaura foco e rolagem ao cancelar', async () => {
    const user = userEvent.setup();
    renderNavigation();
    const trigger = screen.getByRole('button', { name: 'Abrir mais opções' });
    await user.click(trigger);
    const dialog = screen.getByRole('dialog', { name: 'Mais opções' });
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    expect(within(dialog).getByRole('button', { name: 'Fechar menu' })).toHaveFocus();
    expect(document.body.style.overflow).toBe('hidden');
    fireEvent(dialog, new Event('cancel', { cancelable: true }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(trigger).toHaveFocus();
    expect(document.body.style.overflow).not.toBe('hidden');
  });

  it('abre o ranking pelo menu e fecha o painel após navegar', async () => {
    const user = userEvent.setup();
    renderNavigation();
    await user.click(screen.getByRole('button', { name: 'Abrir mais opções' }));
    await user.click(within(screen.getByRole('dialog')).getByRole('link', { name: 'Ranking' }));
    expect(screen.getByTestId('navigation-state')).toHaveTextContent('/progresso/ranking:import-closed');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('abre o importador e fecha o menu', async () => {
    const user = userEvent.setup();
    renderNavigation();
    await user.click(screen.getByRole('button', { name: 'Abrir mais opções' }));
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Importar prova' }));
    expect(screen.getByTestId('navigation-state')).toHaveTextContent('/:import-open');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('mantém o menu identificável e acessível', async () => {
    const user = userEvent.setup();
    const { container } = renderNavigation();
    await user.click(screen.getByRole('button', { name: 'Abrir mais opções' }));
    expect((await axe(container)).violations).toEqual([]);
  });

  it('reserva o menu a destinos complementares sem repetir os cinco destinos da barra', async () => {
    const user = userEvent.setup();
    renderNavigation();
    const primary = screen.getByRole('navigation', { name: 'Navegação principal' });
    const primaryPaths = within(primary).getAllByRole('link').map((link) => link.getAttribute('href'));
    await user.click(screen.getByRole('button', { name: 'Abrir mais opções' }));
    const secondary = screen.getByRole('navigation', { name: 'Navegação complementar' });
    const secondaryLinks = within(secondary).getAllByRole('link');
    expect(secondaryLinks.map((link) => link.textContent)).toEqual(['Caderno de erros', 'Ranking']);
    expect(secondaryLinks.every((link) => !primaryPaths.includes(link.getAttribute('href')))).toBe(true);
  });

  it('anuncia processamento no atalho compacto e preserva a ação de continuar a prova', async () => {
    navigationMocks.activeExam = { id: 41 };
    navigationMocks.getActiveDownloads.mockResolvedValue([{ id: 1 }, { id: 2 }, { id: 3 }]);
    const user = userEvent.setup();
    renderNavigation();
    const importing = screen.getByRole('button', { name: 'Importar prova por link' });
    expect(await within(screen.getByRole('banner')).findByText('3 arquivos em processamento')).toHaveAttribute('role', 'status');
    expect(importing).toHaveAccessibleDescription('3 arquivos em processamento');
    expect(within(importing).getByText('3')).toHaveAttribute('aria-hidden', 'true');
    await user.click(screen.getByRole('button', { name: 'Continuar prova' }));
    expect(screen.getByTestId('navigation-state')).toHaveTextContent('/prova/41:import-closed');
  });
});
