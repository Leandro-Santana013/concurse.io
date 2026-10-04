export type StudyQuestion = {
  id: number;
  numero_questao?: string;
  correct_answer?: string;
  subject?: string;
};

export function gradeAttempt(questions: StudyQuestion[], answers: Record<string, unknown>) {
  let score = 0;
  const detailed_answers: Record<string, unknown> = {};
  const feedback_per_subject: Record<string, { total: number; correct: number; percentage: number }> = {};
  questions.forEach((question, index) => {
    const key = question.numero_questao || String(index + 1);
    const user_answer = String(answers[String(question.id)] || answers[key] || answers[String(index + 1)] || '').trim().toUpperCase();
    const correct_answer = String(question.correct_answer || '').trim().toUpperCase();
    const is_correct = Boolean(correct_answer && (correct_answer === 'X' || user_answer === correct_answer));
    const subject = question.subject || 'Geral';
    if (is_correct) score += 1;
    detailed_answers[key] = { question_id: question.id, user_answer, correct_answer, is_correct, subject };
    const feedback = feedback_per_subject[subject] ||= { total: 0, correct: 0, percentage: 0 };
    feedback.total += 1;
    if (is_correct) feedback.correct += 1;
  });
  Object.values(feedback_per_subject).forEach(feedback => {
    feedback.percentage = Number((100 * feedback.correct / feedback.total).toFixed(1));
  });
  return { score, total: questions.length, percentage: questions.length ? Number((100 * score / questions.length).toFixed(1)) : 0, detailed_answers, feedback_per_subject };
}

type Attempt = { exam_id: unknown; score?: unknown; total?: unknown; elapsed_seconds?: unknown; created_at?: unknown };
const dayKey = (date: Date) => new Intl.DateTimeFormat('en-CA', {
  timeZone: 'America/Sao_Paulo', year: 'numeric', month: '2-digit', day: '2-digit',
}).format(date);

export function studyOverview(attempts: Attempt[], now = new Date()) {
  const total_questions = attempts.reduce((sum, item) => sum + Number(item.total || 0), 0);
  const total_correct = attempts.reduce((sum, item) => sum + Number(item.score || 0), 0);
  const seconds = attempts.reduce((sum, item) => sum + Math.max(0, Number(item.elapsed_seconds || 0)), 0);
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor(seconds % 3600 / 60);
  const days = new Set(attempts.map(item => {
    const text = String(item.created_at || '');
    if (/Z$|[+-]\d\d:\d\d$/.test(text)) {
      const parsed = new Date(text);
      return Number.isFinite(parsed.valueOf()) ? dayKey(parsed) : '';
    }
    return /^\d{4}-\d{2}-\d{2}/.test(text) ? text.slice(0, 10) : '';
  }));
  const cursor = new Date(`${dayKey(now)}T12:00:00Z`);
  if (!days.has(dayKey(cursor))) cursor.setUTCDate(cursor.getUTCDate() - 1);
  let streak = 0;
  while (days.has(dayKey(cursor))) {
    streak += 1;
    cursor.setUTCDate(cursor.getUTCDate() - 1);
  }
  return {
    total_exams: new Set(attempts.map(item => Number(item.exam_id))).size,
    total_questions, total_correct,
    global_accuracy: total_questions ? Number((100 * total_correct / total_questions).toFixed(1)) : 0,
    streak, study_time: hours ? `${hours}h ${minutes}m` : `${minutes}m`,
  };
}
