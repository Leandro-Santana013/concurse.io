import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { ExamDetail, AttemptResult } from '../types/exam';

interface ExamState {
  activeExam: ExamDetail | null;
  currentIdx: number;
  answers: Record<string, string>; // { "1": "A", "2": "C" }
  flaggedQuestions: Record<string, boolean>; // { "1": true }
  elapsedSeconds: number;
  isTimerRunning: boolean;
  isImmediateFeedback: boolean;
  isZenMode: boolean;
  isFinished: boolean;
  attemptResult: AttemptResult | null;

  // Actions
  startExam: (exam: ExamDetail) => void;
  selectAnswer: (questionNum: string, answer: string) => void;
  toggleFlagQuestion: (questionNum: string) => void;
  setQuestionIdx: (idx: number) => void;
  nextQuestion: () => void;
  prevQuestion: () => void;
  tickTimer: () => void;
  toggleTimer: () => void;
  toggleImmediateFeedback: () => void;
  toggleZenMode: () => void;
  finishExam: (result: AttemptResult) => void;
  resetExam: () => void;
}

export const useExamStore = create<ExamState>()(
  persist(
    (set, get) => ({
      activeExam: null,
      currentIdx: 0,
      answers: {},
      flaggedQuestions: {},
      elapsedSeconds: 0,
      isTimerRunning: false,
      isImmediateFeedback: false,
      isZenMode: false,
      isFinished: false,
      attemptResult: null,

      startExam: (exam) => set({
        activeExam: exam,
        currentIdx: 0,
        answers: {},
        flaggedQuestions: {},
        elapsedSeconds: 0,
        isTimerRunning: true,
        isFinished: false,
        attemptResult: null,
      }),

      selectAnswer: (qNum, answer) => set((state) => ({
        answers: {
          ...state.answers,
          [qNum]: state.answers[qNum] === answer ? '' : answer, // Click again to unselect
        }
      })),

      toggleFlagQuestion: (qNum) => set((state) => ({
        flaggedQuestions: {
          ...state.flaggedQuestions,
          [qNum]: !state.flaggedQuestions[qNum],
        }
      })),

      setQuestionIdx: (idx) => {
        const { activeExam } = get();
        if (!activeExam) return;
        const maxIdx = activeExam.questions.length - 1;
        const safeIdx = Math.max(0, Math.min(idx, maxIdx));
        set({ currentIdx: safeIdx });
      },

      nextQuestion: () => {
        const { currentIdx, activeExam } = get();
        if (!activeExam) return;
        if (currentIdx < activeExam.questions.length - 1) {
          set({ currentIdx: currentIdx + 1 });
        }
      },

      prevQuestion: () => {
        const { currentIdx } = get();
        if (currentIdx > 0) {
          set({ currentIdx: currentIdx - 1 });
        }
      },

      tickTimer: () => set((state) => ({
        elapsedSeconds: state.isTimerRunning && !state.isFinished ? state.elapsedSeconds + 1 : state.elapsedSeconds,
      })),

      toggleTimer: () => set((state) => ({
        isTimerRunning: !state.isTimerRunning,
      })),

      toggleImmediateFeedback: () => set((state) => ({
        isImmediateFeedback: !state.isImmediateFeedback,
      })),

      toggleZenMode: () => set((state) => ({
        isZenMode: !state.isZenMode,
      })),

      finishExam: (result) => set({
        isFinished: true,
        isTimerRunning: false,
        attemptResult: result,
      }),

      resetExam: () => set({
        activeExam: null,
        currentIdx: 0,
        answers: {},
        flaggedQuestions: {},
        elapsedSeconds: 0,
        isTimerRunning: false,
        isFinished: false,
        attemptResult: null,
      }),
    }),
    {
      name: 'concurse-active-exam-storage',
    }
  )
);
