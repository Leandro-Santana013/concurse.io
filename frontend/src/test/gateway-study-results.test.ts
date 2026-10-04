import { describe, expect, it } from 'vitest';
import { gradeAttempt, studyOverview } from '../../../supabase/functions/app-gateway/study-results';
import { decodeProcessedImport, importIdentity } from '../../../supabase/functions/app-gateway/processed-import';
import { isPublicSourceUrl, normalizeSourceUrl, sourceKey } from '../../../supabase/functions/app-gateway/source-url';

describe('fluxos centrais de estudo usados no mobile', () => {
  it('corrige por ID, preserva questões anuladas e calcula o feedback por matéria', () => {
    const result = gradeAttempt([
      { id: 45, numero_questao: '1', correct_answer: 'B', subject: 'Português' },
      { id: 46, numero_questao: '2', correct_answer: 'X', subject: 'Português' },
      { id: 47, numero_questao: '3', correct_answer: 'D', subject: 'Matemática' },
    ], { '45': 'b', '1': 'A', '3': 'A' });
    expect(result).toMatchObject({ score: 2, total: 3, percentage: 66.7,
      feedback_per_subject: { Português: { total: 2, correct: 2, percentage: 100 }, Matemática: { total: 1, correct: 0, percentage: 0 } } });
    expect(result.detailed_answers['1']).toMatchObject({ question_id: 45, user_answer: 'B' });
  });

  it('usa tentativas reais para volume, tempo de estudo e sequência de dias', () => {
    const attempts = [
      { exam_id: 9, score: 25, total: 40, elapsed_seconds: 1800, created_at: '2026-10-04T00:20:00Z' },
      { exam_id: 9, score: 30, total: 40, elapsed_seconds: 2400, created_at: '2026-10-02T12:30:00' },
    ];
    expect(studyOverview(attempts, new Date('2026-10-04T12:00:00Z'))).toEqual({
      total_exams: 1, total_questions: 80, total_correct: 55, global_accuracy: 68.8, streak: 2, study_time: '1h 10m',
    });
    expect(studyOverview(attempts, new Date('2026-10-06T12:00:00Z')).streak).toBe(0);
  });

  it('não publica apenas um PDF como se suas questões tivessem sido extraídas', () => {
    expect(() => decodeProcessedImport({ source_object: 'exams/uploads/prova.pdf' })).toThrow('questões extraídas');
    expect(() => decodeProcessedImport({ data_base64: btoa('{"questions":[]}') })).toThrow('cinco questões');
  });

  it('mantém o PDF e o gabarito no Oracle e isola a repetição de uploads por conta', async () => {
    const document = { title: 'Prova', questions: Array.from({ length: 5 }, (_, index) => ({
      statement: `Questão ${index + 1}`, options: { A: 'Um', B: 'Dois' }, correct_answer: 'B',
    })) };
    const bytes = new TextEncoder().encode(JSON.stringify(document));
    const data_base64 = btoa(String.fromCharCode(...bytes));
    const payload = { data_base64, source_object: 'exams/uploads/prova.pdf', gabarito_object: 'exams/uploads/gabarito.pdf' };
    expect(decodeProcessedImport(payload)).toMatchObject({ source_url: 'oci://exams/uploads/prova.pdf', gabarito_url: 'oci://exams/uploads/gabarito.pdf' });
    expect(await importIdentity(1, payload)).toEqual(await importIdentity(1, payload));
    expect(await importIdentity(1, payload)).not.toEqual(await importIdentity(2, payload));
    expect(() => decodeProcessedImport({ ...payload, source_object: 'exams/../private.pdf' })).toThrow('caminho');
  });

  it('reconhece aliases da mesma prova sem incluir fontes privadas na reutilização pública', async () => {
    const first = 'https://EXAMPLE.com:443//prova.pdf/?b=2&utm_source=app&a=1#pagina';
    const second = 'https://example.com/prova.pdf?a=1&b=2';
    expect(normalizeSourceUrl(first)).toBe(second);
    expect(await sourceKey(first)).toBe(await sourceKey(second));
    ['http://127.0.0.1/prova.pdf', 'http://192.168.1.10/prova.pdf', 'upload://user-1/hash', 'https://user:pass@example.com/prova.pdf'].forEach(value => expect(isPublicSourceUrl(value)).toBe(false));
  });
});
