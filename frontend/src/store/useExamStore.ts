import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { AttemptResult, ExamDetail } from '../types/exam';

const EXAM_STORE_VERSION = 4;

interface ExamState {
  ownerUserId: number | null;
  activeExam: ExamDetail | null;
  currentIdx: number;
  answers: Record<string, string>;
  flaggedQuestions: Record<string, boolean>;
  eliminatedOptions: Record<string, Record<string, boolean>>;
  elapsedSeconds: number;
  /** Timestamp of the last elapsed-time snapshot while the timer is running. */
  lastTimerSyncAt: number | null;
  isTimerRunning: boolean;
  isImmediateFeedback: boolean;
  isZenMode: boolean;
  isFinished: boolean;
  attemptResult: AttemptResult | null;

  startExam: (exam: ExamDetail) => void;
  refreshExam: (exam: ExamDetail) => void;
  selectAnswer: (questionNum: string, answer: string) => void;
  toggleFlagQuestion: (questionNum: string) => void;
  toggleEliminateOption: (questionNum: string, optionKey: string) => void;
  clearEliminatedOptions: () => void;
  setQuestionIdx: (idx: number) => void;
  nextQuestion: () => void;
  prevQuestion: () => void;
  tickTimer: () => void;
  syncTimer: () => number;
  toggleTimer: () => void;
  toggleImmediateFeedback: () => void;
  toggleZenMode: () => void;
  finishExam: (result: AttemptResult) => void;
  resetExam: () => void;
  bindToUser: (userId: number) => void;
  clearUserData: () => void;
}

const normalizeExam = (exam: ExamDetail): ExamDetail => ({
  ...exam,
  questions: [...(exam.questions || [])].sort((a, b) => {
    const numA = Number.parseInt(a.numero_questao || '0', 10);
    const numB = Number.parseInt(b.numero_questao || '0', 10);
    if (!Number.isNaN(numA) && !Number.isNaN(numB) && numA !== numB) {
      return numA - numB;
    }
    return (a.numero_questao || '').localeCompare(
      b.numero_questao || '',
      undefined,
      { numeric: true },
    );
  }),
});

type TimerSnapshot = Pick<
  ExamState,
  'elapsedSeconds' | 'lastTimerSyncAt' | 'isTimerRunning' | 'isFinished'
>;

const calculateTimerSnapshot = (state: TimerSnapshot, timestamp: number): TimerSnapshot => {
  if (!state.isTimerRunning || state.isFinished) return state;

  if (!state.lastTimerSyncAt) {
    return { ...state, lastTimerSyncAt: timestamp };
  }

  const deltaSeconds = Math.max(0, Math.floor((timestamp - state.lastTimerSyncAt) / 1000));
  if (deltaSeconds === 0) return state;

  return {
    ...state,
    elapsedSeconds: state.elapsedSeconds + deltaSeconds,
    // Preserve sub-second precision so repeated syncs do not accumulate drift.
    lastTimerSyncAt: state.lastTimerSyncAt + deltaSeconds * 1000,
  };
};

export const useExamStore = create<ExamState>()(
  persist(
    (set, get) => ({
      ownerUserId: null,
      activeExam: null,
      currentIdx: 0,
      answers: {},
      flaggedQuestions: {},
      eliminatedOptions: {},
      elapsedSeconds: 0,
      lastTimerSyncAt: null,
      isTimerRunning: false,
      isImmediateFeedback: false,
      isZenMode: false,
      isFinished: false,
      attemptResult: null,

      startExam: (exam) => {
        set({
          activeExam: normalizeExam(exam),
          currentIdx: 0,
          answers: {},
          flaggedQuestions: {},
          eliminatedOptions: {},
          elapsedSeconds: 0,
          lastTimerSyncAt: Date.now(),
          isTimerRunning: true,
          isFinished: false,
          attemptResult: null,
        });
      },

      refreshExam: (exam) => set((state) => {
        if (state.activeExam?.id !== exam.id) return state;
        const normalizedExam = normalizeExam(exam);
        return {
          activeExam: normalizedExam,
          currentIdx: Math.min(
            state.currentIdx,
            Math.max(normalizedExam.questions.length - 1, 0),
          ),
        };
      }),

      selectAnswer: (qNum, answer) =>
        set((state) => ({
          answers: {
            ...state.answers,
            [qNum]: answer,
          },
        })),

      toggleFlagQuestion: (qNum) =>
        set((state) => ({
          flaggedQuestions: {
            ...state.flaggedQuestions,
            [qNum]: !state.flaggedQuestions[qNum],
          },
        })),

      toggleEliminateOption: (qNum, optionKey) =>
        set((state) => ({
          eliminatedOptions: {
            ...state.eliminatedOptions,
            [qNum]: {
              ...(state.eliminatedOptions[qNum] || {}),
              [optionKey]: !state.eliminatedOptions[qNum]?.[optionKey],
            },
          },
        })),

      clearEliminatedOptions: () => set({ eliminatedOptions: {} }),

      setQuestionIdx: (idx) => {
        const { activeExam } = get();
        if (!activeExam || activeExam.questions.length === 0) return;
        set({ currentIdx: Math.max(0, Math.min(idx, activeExam.questions.length - 1)) });
      },

      nextQuestion: () => {
        const { currentIdx, activeExam } = get();
        if (activeExam && currentIdx < activeExam.questions.length - 1) {
          set({ currentIdx: currentIdx + 1 });
        }
      },

      prevQuestion: () => {
        const { currentIdx } = get();
        if (currentIdx > 0) set({ currentIdx: currentIdx - 1 });
      },

      syncTimer: () => {
        let syncedElapsed = get().elapsedSeconds;
        set((state) => {
          const snapshot = calculateTimerSnapshot(state, Date.now());
          syncedElapsed = snapshot.elapsedSeconds;
          if (
            snapshot.elapsedSeconds === state.elapsedSeconds &&
            snapshot.lastTimerSyncAt === state.lastTimerSyncAt
          ) {
            return state;
          }
          return snapshot;
        });
        return syncedElapsed;
      },

      tickTimer: () => {
        get().syncTimer();
      },

      toggleTimer: () =>
        set((state) => {
          if (!state.activeExam || state.isFinished) return state;

          if (state.isTimerRunning) {
            const snapshot = calculateTimerSnapshot(state, Date.now());
            return {
              ...snapshot,
              isTimerRunning: false,
              lastTimerSyncAt: null,
            };
          }

          return {
            isTimerRunning: true,
            lastTimerSyncAt: Date.now(),
          };
        }),

      toggleImmediateFeedback: () =>
        set((state) => ({ isImmediateFeedback: !state.isImmediateFeedback })),

      toggleZenMode: () => set((state) => ({ isZenMode: !state.isZenMode })),

      finishExam: (result) =>
        set((state) => {
          const snapshot = calculateTimerSnapshot(state, Date.now());
          return {
            ...snapshot,
            elapsedSeconds: result.elapsed_seconds,
            lastTimerSyncAt: null,
            isFinished: true,
            isTimerRunning: false,
            attemptResult: result,
          };
        }),

      resetExam: () =>
        set({
          activeExam: null,
          currentIdx: 0,
          answers: {},
          flaggedQuestions: {},
          eliminatedOptions: {},
          elapsedSeconds: 0,
          lastTimerSyncAt: null,
          isTimerRunning: false,
          isFinished: false,
          attemptResult: null,
        }),

      bindToUser: (userId) =>
        set((state) => {
          if (state.ownerUserId === userId) return state;
          return {
            ownerUserId: userId,
            activeExam: null,
            currentIdx: 0,
            answers: {},
            flaggedQuestions: {},
            eliminatedOptions: {},
            elapsedSeconds: 0,
            lastTimerSyncAt: null,
            isTimerRunning: false,
            isFinished: false,
            attemptResult: null,
          };
        }),

      clearUserData: () =>
        set({
          ownerUserId: null,
          activeExam: null,
          currentIdx: 0,
          answers: {},
          flaggedQuestions: {},
          eliminatedOptions: {},
          elapsedSeconds: 0,
          lastTimerSyncAt: null,
          isTimerRunning: false,
          isFinished: false,
          attemptResult: null,
        }),
    }),
    {
      name: 'concurse-active-exam-storage',
      version: EXAM_STORE_VERSION,
      migrate: (persistedState, persistedVersion) => {
        const state = persistedState as Partial<ExamState>;
        if (persistedVersion < 4) {
          return {
            ...state,
            ownerUserId: null,
            activeExam: null,
            currentIdx: 0,
            answers: {},
            flaggedQuestions: {},
            eliminatedOptions: {},
            elapsedSeconds: 0,
            lastTimerSyncAt: null,
            isTimerRunning: false,
            isFinished: false,
            attemptResult: null,
          } as ExamState;
        }
        const shouldResume = Boolean(state.activeExam && state.isTimerRunning && !state.isFinished);

        return {
          ...state,
          elapsedSeconds: Math.max(0, Number(state.elapsedSeconds) || 0),
          eliminatedOptions:
            state.eliminatedOptions && typeof state.eliminatedOptions === 'object'
              ? state.eliminatedOptions
              : {},
          lastTimerSyncAt:
            typeof state.lastTimerSyncAt === 'number'
              ? state.lastTimerSyncAt
              : shouldResume
                ? Date.now()
                : null,
        } as ExamState;
      },
    },
  ),
);
