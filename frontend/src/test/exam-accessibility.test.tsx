import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { axe } from 'vitest-axe';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ExamSimulator } from '../components/exam/ExamSimulator';
import { ExamProvider } from '../context/ExamContext';
import { UIProvider } from '../context/UIContext';
import { useExamStore } from '../store/useExamStore';
import type { ExamDetail } from '../types/exam';

const apiMocks = vi.hoisted(() => ({
  getActiveDownloads: vi.fn(async () => []),
  submitAttempt: vi.fn(),
}));

vi.mock('../services/api', () => ({ api: apiMocks }));

const exam: ExamDetail = {
  id: 99,
  title: 'Prova acessível',
  status: 'Sessão',
  has_official_answers: true,
  gabarito_coverage: 100,
  questions: [
    {
      id: 1,
      numero_questao: '1',
      context_text: 'Texto de apoio importante.',
      statement: 'Selecione uma resposta.',
      options: { A: 'Opção A', B: 'Opção B' },
      correct_answer: 'B',
      subject: 'Português',
      has_official_answer: true,
      latex_support: false,
    },
    {
      id: 2,
      numero_questao: '2',
      statement: 'Segunda questão.',
      options: { A: 'Opção A', B: 'Opção B' },
      correct_answer: 'A',
      subject: 'Direito',
      has_official_answer: true,
      latex_support: false,
    },
  ],
};

describe('simulador acessível', () => {
  beforeEach(() => {
    localStorage.clear();
    useExamStore.getState().resetExam();
    useExamStore.getState().startExam(exam);
  });

  it('usa rádios sem desmarcar e mostra pendências antes da entrega', async () => {
    const user = userEvent.setup();
    const { container } = render(
      <MemoryRouter>
        <UIProvider>
          <ExamProvider>
            <ExamSimulator />
          </ExamProvider>
        </UIProvider>
      </MemoryRouter>,
    );

    const optionA = await screen.findByRole('radio', { name: /Opção A/ });
    await user.click(optionA);
    await user.click(optionA);
    expect(optionA).toBeChecked();

    await user.click(screen.getByRole('button', { name: 'Eliminar alternativa B' }));
    expect(screen.getByRole('button', { name: 'Restaurar alternativa B' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );

    await user.click(screen.getByRole('button', { name: 'Entregar simulado' }));
    const dialog = screen.getByRole('dialog', { name: 'Entregar simulado?' });
    expect(dialog).toHaveTextContent('Em branco (1)');
    expect(screen.getByRole('button', { name: 'Ir para questão 2 em branco' })).toBeVisible();

    const audit = await axe(container, {
      rules: { 'color-contrast': { enabled: false } },
    });
    expect(audit.violations).toEqual([]);
  });

  it('exibe resultado completo e refaz a prova pela ação do contexto', async () => {
    const user = userEvent.setup();
    useExamStore.setState({
      answers: { '1': 'B', '2': 'A' },
      isFinished: true,
      isTimerRunning: false,
      attemptResult: {
        attempt_id: 12,
        exam_id: 99,
        score: 2,
        total: 2,
        percentage: 100,
        elapsed_seconds: 75,
        detailed_answers: {
          '1': {
            question_id: 1,
            user_answer: 'B',
            correct_answer: 'B',
            is_correct: true,
            subject: 'Português',
          },
          '2': {
            question_id: 2,
            user_answer: 'A',
            correct_answer: 'A',
            is_correct: true,
            subject: 'Direito',
          },
        },
        feedback_per_subject: {
          Português: { total: 1, correct: 1, percentage: 100 },
          Direito: { total: 1, correct: 1, percentage: 100 },
        },
      },
    });

    render(
      <MemoryRouter>
        <UIProvider>
          <ExamProvider>
            <ExamSimulator />
          </ExamProvider>
        </UIProvider>
      </MemoryRouter>,
    );

    expect(screen.getAllByText('100%')[0]).toBeVisible();
    await user.click(screen.getByText('Questão 1'));
    expect(screen.getByText('Texto de apoio importante.')).toBeVisible();

    await user.click(screen.getByRole('button', { name: 'Refazer simulado' }));
    expect(await screen.findByRole('heading', { name: 'Questão 1' })).toBeVisible();
    expect(useExamStore.getState().isFinished).toBe(false);
    expect(useExamStore.getState().answers).toEqual({});
  });
});
