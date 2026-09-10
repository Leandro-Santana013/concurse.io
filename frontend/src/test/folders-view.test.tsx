import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { FoldersView } from '../components/dashboard/FoldersView';
import { ExamProvider } from '../context/ExamContext';
import { UIProvider } from '../context/UIContext';

const apiMocks = vi.hoisted(() => ({
  getFolders: vi.fn(),
  getCustomSimulations: vi.fn(),
  getActiveDownloads: vi.fn(),
}));

vi.mock('../services/api', () => ({
  api: apiMocks,
  AuthRequiredError: class AuthRequiredError extends Error {},
}));

const exam = (id: number, title: string, questionCount: number) => ({
  id,
  title,
  status: 'Aprovada',
  question_count: questionCount,
  best_score: null,
  last_score: null,
  attempt_count: 0,
  has_official_answers: true,
  answer_key_source: 'official',
  gabarito_coverage: 100,
});

const renderLibrary = () => render(
  <MemoryRouter initialEntries={['/biblioteca']}>
    <UIProvider>
      <ExamProvider>
        <FoldersView />
      </ExamProvider>
    </UIProvider>
  </MemoryRouter>,
);

describe('ordenação da biblioteca', () => {
  beforeEach(() => {
    apiMocks.getFolders.mockResolvedValue([
      {
        id: 1,
        name: 'Grupo A',
        exams: [
          exam(1, 'Prova pequena', 10),
          exam(2, 'Prova grande', 30),
        ],
      },
      {
        id: 2,
        name: 'Grupo B',
        exams: [exam(3, 'Prova média', 40)],
      },
    ]);
    apiMocks.getCustomSimulations.mockResolvedValue([]);
    apiMocks.getActiveDownloads.mockResolvedValue([]);
  });

  it('aplica Mais questões dentro dos grupos e entre os grupos', async () => {
    const user = userEvent.setup();
    renderLibrary();

    const sortSelect = await screen.findByRole('combobox', { name: 'Ordenar provas' });
    await user.selectOptions(sortSelect, 'questions');

    await waitFor(() => {
      expect(screen.getAllByRole('heading', { level: 3 }).map((heading) => heading.textContent)).toEqual([
        'Prova média',
        'Prova grande',
        'Prova pequena',
      ]);
    });
  });
});
