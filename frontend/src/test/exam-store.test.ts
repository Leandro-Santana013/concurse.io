import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useExamStore } from '../store/useExamStore';
import type { ExamDetail } from '../types/exam';

const exam: ExamDetail = {
  id: 42,
  title: 'Simulado de teste',
  status: 'Sessão',
  has_official_answers: true,
  gabarito_coverage: 100,
  questions: [
    {
      id: 7,
      numero_questao: '1',
      statement: 'Qual é a alternativa correta?',
      options: { A: 'Primeira', B: 'Segunda' },
      correct_answer: 'B',
      subject: 'Português',
      has_official_answer: true,
      latex_support: false,
    },
  ],
};

describe('estado persistido da prova', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-08-31T12:00:00Z'));
    localStorage.clear();
    useExamStore.getState().clearUserData();
  });

  afterEach(() => {
    useExamStore.getState().clearUserData();
    vi.useRealTimers();
  });

  it('mantém respostas de rádio idempotentes, eliminações e tempo por timestamp', () => {
    const store = useExamStore.getState();
    store.startExam(exam);

    store.selectAnswer('1', 'A');
    store.selectAnswer('1', 'A');
    store.toggleEliminateOption('1', 'B');

    vi.advanceTimersByTime(65_400);
    expect(useExamStore.getState().syncTimer()).toBe(65);

    const state = useExamStore.getState();
    expect(state.answers).toEqual({ '1': 'A' });
    expect(state.eliminatedOptions).toEqual({ '1': { B: true } });
    expect(state.elapsedSeconds).toBe(65);
    expect(state.lastTimerSyncAt).not.toBeNull();

    const persisted = JSON.parse(localStorage.getItem('concurse-active-exam-storage') ?? '{}');
    expect(persisted.version).toBe(4);
    expect(persisted.state.activeExam.id).toBe(42);
    expect(persisted.state.eliminatedOptions).toEqual({ '1': { B: true } });
  });

  it('descarta prova e respostas quando a conta autenticada muda', () => {
    const store = useExamStore.getState();
    store.bindToUser(1);
    store.startExam(exam);
    store.selectAnswer('1', 'B');

    useExamStore.getState().bindToUser(2);

    const state = useExamStore.getState();
    expect(state.ownerUserId).toBe(2);
    expect(state.activeExam).toBeNull();
    expect(state.answers).toEqual({});
    expect(state.attemptResult).toBeNull();
  });
});
