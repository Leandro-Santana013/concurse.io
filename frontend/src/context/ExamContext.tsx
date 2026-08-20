import React, { createContext, useContext, useState, useEffect, ReactNode, useCallback } from 'react';
import { useExamStore } from '../store/useExamStore';
import { ExamDetail, AttemptResult, Question } from '../types/exam';
import { api } from '../services/api';

interface ExamContextType {
  // Active exam state from Zustand store
  activeExam: ExamDetail | null;
  currentIdx: number;
  currentQuestion: Question | null;
  currentQuestionNum: string;
  totalQuestions: number;
  progressPercentage: number;
  answers: Record<string, string>;
  flaggedQuestions: Record<string, boolean>;
  elapsedSeconds: number;
  isTimerRunning: boolean;
  isImmediateFeedback: boolean;
  isZenMode: boolean;
  isFinished: boolean;
  attemptResult: AttemptResult | null;
  isLoadingExam: boolean;

  // Elimination / Cross-out state for options
  eliminatedOptions: Record<string, Record<string, boolean>>; // { "1": { "A": true } }
  toggleEliminateOption: (qNum: string, optKey: string) => void;
  clearEliminatedOptions: () => void;

  // Actions
  startExam: (exam: ExamDetail) => void;
  loadAndStartExam: (examId: number) => Promise<void>;
  generateCustomExam: (count?: number) => Promise<void>;
  loadErrorNotebookExam: (subject?: string) => Promise<void>;
  selectAnswer: (qNum: string, answer: string) => void;
  toggleFlagQuestion: (qNum: string) => void;
  setQuestionIdx: (idx: number) => void;
  nextQuestion: () => void;
  prevQuestion: () => void;
  tickTimer: () => void;
  toggleTimer: () => void;
  toggleImmediateFeedback: () => void;
  toggleZenMode: () => void;
  submitExamAttempt: () => Promise<AttemptResult>;
  resetExam: () => void;
  formatTime: (seconds: number) => string;
}

const ExamContext = createContext<ExamContextType | undefined>(undefined);

export const ExamProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const store = useExamStore();
  const [isLoadingExam, setIsLoadingExam] = useState(false);
  const [eliminatedOptions, setEliminatedOptions] = useState<Record<string, Record<string, boolean>>>({});

  // Computed values
  const currentQuestion = store.activeExam?.questions[store.currentIdx] || null;
  const currentQuestionNum = currentQuestion
    ? currentQuestion.numero_questao || String(store.currentIdx + 1)
    : '1';
  const totalQuestions = store.activeExam?.questions.length || 0;
  const answeredCount = Object.keys(store.answers).filter((k) => store.answers[k]).length;
  const progressPercentage = totalQuestions > 0 ? (answeredCount / totalQuestions) * 100 : 0;

  // Format Seconds to HH:MM:SS or MM:SS
  const formatTime = useCallback((secs: number) => {
    const h = Math.floor(secs / 3600);
    const m = Math.floor((secs % 3600) / 60);
    const s = secs % 60;
    if (h > 0) {
      return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
    }
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  }, []);

  // Option Elimination (Riscar alternativa)
  const toggleEliminateOption = (qNum: string, optKey: string) => {
    setEliminatedOptions((prev) => {
      const qEliminated = prev[qNum] || {};
      const nextState = !qEliminated[optKey];
      return {
        ...prev,
        [qNum]: {
          ...qEliminated,
          [optKey]: nextState,
        },
      };
    });
  };

  const clearEliminatedOptions = () => {
    setEliminatedOptions({});
  };

  // Start exam from ID
  const loadAndStartExam = async (examId: number) => {
    setIsLoadingExam(true);
    try {
      const examDetail = await api.getExam(examId);
      clearEliminatedOptions();
      store.startExam(examDetail);
    } finally {
      setIsLoadingExam(false);
    }
  };

  // Generate mixed exam
  const generateCustomExam = async (count: number = 20) => {
    setIsLoadingExam(true);
    try {
      const customExam = await api.generateCustomExam(count);
      clearEliminatedOptions();
      store.startExam(customExam);
    } finally {
      setIsLoadingExam(false);
    }
  };

  // Load error notebook exam
  const loadErrorNotebookExam = async (subject?: string) => {
    setIsLoadingExam(true);
    try {
      const errorExam = await api.getErrorNotebookExam(subject);
      if (!errorExam.questions || errorExam.questions.length === 0) {
        throw new Error('Nenhuma questão errada encontrada para revisão nesta disciplina.');
      }
      clearEliminatedOptions();
      store.startExam(errorExam);
    } finally {
      setIsLoadingExam(false);
    }
  };

  // Submit attempt
  const submitExamAttempt = async (): Promise<AttemptResult> => {
    if (!store.activeExam) {
      throw new Error('Nenhum simulado ativo para envio.');
    }

    const result = await api.submitAttempt({
      exam_id: store.activeExam.id,
      elapsed_seconds: store.elapsedSeconds,
      answers: store.answers,
    });

    store.finishExam(result);
    return result;
  };

  return (
    <ExamContext.Provider
      value={{
        activeExam: store.activeExam,
        currentIdx: store.currentIdx,
        currentQuestion,
        currentQuestionNum,
        totalQuestions,
        progressPercentage,
        answers: store.answers,
        flaggedQuestions: store.flaggedQuestions,
        elapsedSeconds: store.elapsedSeconds,
        isTimerRunning: store.isTimerRunning,
        isImmediateFeedback: store.isImmediateFeedback,
        isZenMode: store.isZenMode,
        isFinished: store.isFinished,
        attemptResult: store.attemptResult,
        isLoadingExam,
        eliminatedOptions,
        toggleEliminateOption,
        clearEliminatedOptions,
        startExam: store.startExam,
        loadAndStartExam,
        generateCustomExam,
        loadErrorNotebookExam,
        selectAnswer: store.selectAnswer,
        toggleFlagQuestion: store.toggleFlagQuestion,
        setQuestionIdx: store.setQuestionIdx,
        nextQuestion: store.nextQuestion,
        prevQuestion: store.prevQuestion,
        tickTimer: store.tickTimer,
        toggleTimer: store.toggleTimer,
        toggleImmediateFeedback: store.toggleImmediateFeedback,
        toggleZenMode: store.toggleZenMode,
        submitExamAttempt,
        resetExam: () => {
          clearEliminatedOptions();
          store.resetExam();
        },
        formatTime,
      }}
    >
      {children}
    </ExamContext.Provider>
  );
};

export const useExam = (): ExamContextType => {
  const context = useContext(ExamContext);
  if (!context) {
    throw new Error('useExam must be used within an ExamProvider');
  }
  return context;
};
