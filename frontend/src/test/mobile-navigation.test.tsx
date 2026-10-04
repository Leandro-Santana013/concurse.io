import React from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { beforeAll, describe, expect, it, vi } from 'vitest';
import { axe } from 'vitest-axe';
import { Navbar } from '../components/layout/Navbar';
import { UIProvider, useUI } from '../context/UIContext';

vi.mock('../services/api', () => ({ api: { getActiveDownloads: vi.fn(async () => []) } }));
vi.mock('../context/AuthContext', () => ({ useAuth: () => ({ user: { id: 1, name: 'Leandro', email: 'leandro@example.com' } }) }));
vi.mock('../context/ExamContext', () => ({ useExam: () => ({ activeExam: null, isFinished: false }) }));

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
    const trigger = screen.getByRole('button', { name: 'Abrir menu' });
    await user.click(trigger);
    const dialog = screen.getByRole('dialog', { name: 'Menu' });
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
    await user.click(screen.getByRole('button', { name: 'Abrir menu' }));
    await user.click(within(screen.getByRole('dialog')).getByRole('link', { name: 'Ranking' }));
    expect(screen.getByTestId('navigation-state')).toHaveTextContent('/progresso/ranking:import-closed');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('abre o importador e fecha o menu', async () => {
    const user = userEvent.setup();
    renderNavigation();
    await user.click(screen.getByRole('button', { name: 'Abrir menu' }));
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Importar prova' }));
    expect(screen.getByTestId('navigation-state')).toHaveTextContent('/:import-open');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('mantém o menu identificável e acessível', async () => {
    const user = userEvent.setup();
    const { container } = renderNavigation();
    await user.click(screen.getByRole('button', { name: 'Abrir menu' }));
    expect((await axe(container)).violations).toEqual([]);
  });
});
