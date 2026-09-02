import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { ExamProvider } from '../context/ExamContext';
import { AuthProvider } from '../context/AuthContext';
import { UIProvider } from '../context/UIContext';
import { useExamStore } from '../store/useExamStore';
import type { ExamDetail } from '../types/exam';

const apiMocks = vi.hoisted(() => ({
  getActiveDownloads: vi.fn(async () => []),
  getFolders: vi.fn(async () => []),
  getCurrentUser: vi.fn(async () => ({
    id: 1,
    email: 'estudante@example.com',
    name: 'Estudante',
    picture: '',
    is_authenticated: true,
  })),
  logout: vi.fn(async () => undefined),
  getNotebookStats: vi.fn(async () => []),
  getExam: vi.fn(),
}));

vi.mock('../services/api', () => ({ api: apiMocks }));

const LocationProbe = () => {
  const location = useLocation();
  return <output data-testid="current-path">{location.pathname}</output>;
};

const renderApp = (path: string) => render(
  <MemoryRouter initialEntries={[path]}>
    <AuthProvider>
      <UIProvider>
        <ExamProvider>
          <App />
          <LocationProbe />
        </ExamProvider>
      </UIProvider>
    </AuthProvider>
  </MemoryRouter>,
);

const cachedExam: ExamDetail = {
  id: 41,
  title: 'Prova privada em andamento',
  status: 'Aprovada',
  has_official_answers: true,
  gabarito_coverage: 100,
  questions: [{
    id: 1,
    numero_questao: '1',
    statement: 'Questão protegida',
    options: { A: 'Alternativa A', B: 'Alternativa B' },
    correct_answer: 'A',
    subject: 'Geral',
    images: ['/static/images/questions/private.png'],
    has_official_answer: true,
    latex_support: false,
  }],
};

describe('rotas e preferências da aplicação', () => {
  beforeEach(() => {
    localStorage.clear();
    apiMocks.getActiveDownloads.mockResolvedValue([]);
    apiMocks.getFolders.mockResolvedValue([]);
    apiMocks.getCurrentUser.mockResolvedValue({
      id: 1,
      email: 'estudante@example.com',
      name: 'Estudante',
      picture: '',
      is_authenticated: true,
    });
    apiMocks.getNotebookStats.mockResolvedValue([]);
    apiMocks.getExam.mockResolvedValue({
      ...cachedExam,
      questions: [{
        ...cachedExam.questions[0],
        images: ['/api/v1/exams/41/media/private.png'],
      }],
    });
  });

  it('migra a preferência paper para sepia e navega por URLs reais', async () => {
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
      expect(document.documentElement).toHaveClass('theme-sepia', 'font-scale-ui-lg');
      expect(document.documentElement).toHaveAttribute('data-theme', 'sepia');
    });

    const migrated = JSON.parse(localStorage.getItem('concurse_ui_preferences_v2') ?? '{}');
    expect(migrated).toMatchObject({
      version: 2,
      theme: 'sepia',
      fontSize: 'lg',
      enableEliminationMode: false,
    });

    const desktopNavigation = screen.getByRole('complementary', { name: 'Navegação principal' });
    await user.click(within(desktopNavigation).getByRole('link', { name: 'Biblioteca' }));

    expect(await screen.findByRole('heading', { name: 'Suas provas' })).toBeVisible();
    expect(screen.getByTestId('current-path')).toHaveTextContent('/biblioteca');
    expect(within(desktopNavigation).getByRole('link', { name: 'Biblioteca' })).toHaveClass('is-active');
  });

  it('revalida uma prova persistida e preserva o progresso autorizado', async () => {
    const store = useExamStore.getState();
    store.bindToUser(1);
    store.startExam(cachedExam);
    store.selectAnswer('1', 'B');

    renderApp('/prova/41');

    expect(await screen.findByRole('heading', { name: 'Prova privada em andamento' })).toBeVisible();
    await waitFor(() => expect(apiMocks.getExam).toHaveBeenCalledWith(41));
    const refreshedState = useExamStore.getState();
    expect(refreshedState.answers).toEqual({ '1': 'B' });
    expect(refreshedState.activeExam?.questions[0].images).toEqual([
      '/api/v1/exams/41/media/private.png',
    ]);
  });

  it('apaga a prova persistida quando o servidor nega o acesso', async () => {
    const store = useExamStore.getState();
    store.bindToUser(1);
    store.startExam(cachedExam);
    apiMocks.getExam.mockRejectedValueOnce(new Error('Falha ao carregar exame'));

    renderApp('/prova/41');

    expect(await screen.findByRole('heading', { name: 'Não foi possível abrir a prova.' })).toBeVisible();
    expect(useExamStore.getState().activeExam).toBeNull();
  });
});
