import { isPublicSourceUrl, normalizeSourceUrl, ownedSourceKey, sourceKey } from './source-url.ts';

// PostgREST builders are thenable and expose different operations at each step.
type Database = { from(table: string): any };
type Payload = {
  filename?: string; title?: string; data_base64?: string;
  source_object?: string; source_url?: string;
  gabarito_object?: string; gabarito_url?: string | null; import_key?: string;
};
export class ImportError extends Error {
  constructor(message: string, readonly status = 400) { super(message); }
}

const mediaObject = (value: unknown): string | null => {
  if (!value) return null;
  if (typeof value !== 'string' || !/^exams\/[a-zA-Z0-9/_\-.]+$/.test(value) || value.split('/').includes('..')) {
    throw new ImportError('O caminho do arquivo da prova é inválido.');
  }
  return `oci://${value}`;
};

export function decodeProcessedImport(payload: Payload) {
  let document: Record<string, unknown>;
  try {
    const binary = atob(payload.data_base64 || '');
    document = JSON.parse(new TextDecoder().decode(Uint8Array.from(binary, char => char.charCodeAt(0))));
  } catch { throw new ImportError('Envie o JSON das questões extraídas no dispositivo.'); }
  if (!document || !Array.isArray(document.questions) || document.questions.length < 5) {
    throw new ImportError('A extração deve conter pelo menos cinco questões válidas.');
  }
  const questions = document.questions as Record<string, unknown>[];
  if (questions.some(question => !question || typeof question.statement !== 'string' || !question.statement.trim() ||
      !question.options || typeof question.options !== 'object' || Array.isArray(question.options) ||
      Object.keys(question.options).length < 2 || !/^(?:[A-E]|X)?$/i.test(String(question.correct_answer || '').trim()))) {
    throw new ImportError('A extração contém questões ou alternativas incompletas.');
  }
  return {
    questions,
    title: String(payload.title || document.title || payload.filename || 'Prova importada').slice(0, 300),
    source_url: mediaObject(payload.source_object),
    gabarito_url: mediaObject(payload.gabarito_object) || (isPublicSourceUrl(payload.gabarito_url) ? payload.gabarito_url : null),
  };
}

export async function importIdentity(userId: number, payload: Payload) {
  // An upload is private to its owner. A digest never becomes a public source.
  const value = String(payload.source_object || payload.import_key || '');
  if (!value) return null;
  const bytes = new TextEncoder().encode(`user:${userId}|${value}`);
  const source_key = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(byte => byte.toString(16).padStart(2, '0')).join('');
  return { source_key, source_url: `upload://user-${userId}/${source_key}` };
}

export async function importProcessedExam(db: Database, userId: number, payload: Payload,
  resolveImage: (value: unknown, examId: number, questionIndex: number, slot: string) => Promise<unknown>) {
  const document = decodeProcessedImport(payload);
  const identity = await importIdentity(userId, payload);
  const aliases: Array<{ source_key: string; source_url: string; shared: boolean }> = [];
  if (isPublicSourceUrl(payload.source_url)) {
    const normalized = normalizeSourceUrl(payload.source_url);
    const { data: catalog, error: catalogError } = await db.from('exam_catalog').select('id')
      .in('source_url', [payload.source_url, normalized]).limit(1);
    if (catalogError) throw new Error(catalogError.message);
    if (catalog?.length) aliases.push({ source_key: await sourceKey(payload.source_url), source_url: normalized.slice(0, 500), shared: true });
    const key = await ownedSourceKey(userId, payload.source_url);
    aliases.push({ source_key: key, source_url: `upload://user-${userId}/${key}`, shared: false });
  }
  if (identity) aliases.push({ ...identity, shared: false });
  const link = async (examId: number) => {
    const { error } = await db.from('user_exams').upsert({ user_id: userId, exam_id: examId, created_at: new Date().toISOString() }, { onConflict: 'user_id,exam_id' });
    if (error) throw new Error(error.message);
  };
  const existingImport = async () => {
    for (const source of aliases) {
    const { data: alias, error } = await db.from('exam_sources').select('exam_id,created_at').eq('source_key', source.source_key).maybeSingle();
    if (error) throw new Error(error.message);
    if (!alias) continue;
    const { data: exam, error: examError } = await db.from('exams').select('id,title,status,user_id,doc_type').eq('id', alias.exam_id).single();
    if (examError) throw new Error(examError.message);
    if (!source.shared && Number(exam.user_id) !== userId) throw new ImportError('Importação não atribuída à sua conta.', 403);
    if (exam.doc_type === 'generated_session') throw new ImportError('Um simulado não pode substituir a prova original.');
    if (exam.status !== 'Aprovada') {
      const started = new Date(alias.created_at).valueOf();
      if (exam.status === 'Erro' || (Number.isFinite(started) && Date.now() - started > 600000)) {
        await db.from('exams').update({ status: 'Erro', progress: -1, error_type: 'sync_interrupted', progress_message: 'Envio interrompido; uma nova tentativa foi iniciada' }).eq('id', exam.id);
        const { error: releaseError } = await db.from('exam_sources').delete().eq('source_key', source.source_key).eq('exam_id', exam.id);
        if (releaseError) throw new Error(releaseError.message);
        continue;
      }
      throw new ImportError('O envio anterior ainda não terminou. Tente novamente em instantes.', 409);
    }
    const { count, error: countError } = await db.from('questions').select('id', { count: 'exact', head: true }).eq('exam_id', exam.id);
    if (countError) throw new Error(countError.message);
    if (!count || count < 5) {
      const { error: releaseError } = await db.from('exam_sources').delete().eq('source_key', source.source_key).eq('exam_id', exam.id);
      if (releaseError) throw new Error(releaseError.message);
      continue;
    }
    await link(Number(exam.id));
    return { exam_id: Number(exam.id), title: String(exam.title), status: 'Aprovada', progress: 100, reused: true, already_in_library: true, message: 'Prova já sincronizada na biblioteca.' };
    }
    return null;
  };
  const existing = await existingImport();
  if (existing) return existing;
  const hasAnswers = document.questions.filter(question => String(question.correct_answer || '').trim()).length;
  const { data: created, error } = await db.from('exams').insert({
    title: document.title, status: 'Processando', user_id: userId,
    source_url: document.source_url, gabarito_url: document.gabarito_url,
    has_official_answers: hasAnswers === document.questions.length ? 1 : 0,
    answer_key_source: hasAnswers ? 'imported' : 'none', doc_type: 'caderno_questoes',
    gabarito_coverage: 100 * hasAnswers / document.questions.length,
    progress: 95, progress_message: 'Recebendo questões e arquivos do dispositivo',
  }).select('id').single();
  if (error || !created) throw new Error(error?.message || 'Não foi possível criar a prova.');
  const examId = Number(created.id);
  // Reserve every source before inserting questions. Concurrent processing
  // of a public proof shares one canonical record, with per-user ownership.
  for (const { shared: _shared, ...alias } of aliases) {
    const { error: identityError } = await db.from('exam_sources').insert({ ...alias, exam_id: examId, created_at: new Date().toISOString() });
    if (identityError) {
      await db.from('exam_sources').delete().eq('exam_id', examId);
      await db.from('exams').delete().eq('id', examId).eq('user_id', userId);
      const raced = await existingImport();
      if (raced) return raced;
      throw new Error(identityError.message);
    }
  }
  try {
    const rows = [];
    for (const [index, question] of document.questions.entries()) {
      const optionImages: Record<string, unknown[]> = {};
      for (const [key, values] of Object.entries(question.option_images || {})) {
        optionImages[key] = await Promise.all((Array.isArray(values) ? values : []).map((value, slot) => resolveImage(value, examId, index + 1, `o${key}${slot}`)));
      }
      rows.push({
        exam_id: examId, statement: question.statement, options: JSON.stringify(question.options),
        correct_answer: String(question.correct_answer || '').trim().toUpperCase(), subject: String(question.subject || 'Geral').slice(0, 100),
        images: JSON.stringify(await Promise.all((Array.isArray(question.images) ? question.images : []).map(value => resolveImage(value, examId, index + 1, 'q')))),
        option_images: JSON.stringify(optionImages), numero_questao: String(question.numero_questao || index + 1),
        question_index: index, latex_support: question.latex_support ? 1 : 0,
      });
    }
    const { error: questionsError } = await db.from('questions').insert(rows);
    if (questionsError) throw new Error(questionsError.message);
    await link(examId);
    const { error: readyError } = await db.from('exams').update({ status: 'Aprovada', progress: 100, progress_message: 'Prova pronta', error_type: null }).eq('id', examId);
    if (readyError) throw new Error(readyError.message);
  } catch (failure) {
    // A failed partial import is never a reusable approved proof. Release its
    // key so a retry can succeed, preserving the failed record for diagnosis.
    await db.from('exams').update({ status: 'Erro', progress: -1, progress_message: 'O envio da extração falhou', error_type: 'sync_failed' }).eq('id', examId);
    await db.from('exam_sources').delete().eq('exam_id', examId);
    throw failure;
  }
  return { exam_id: examId, title: document.title, status: 'Aprovada', progress: 100, reused: false, already_in_library: true, message: 'Prova e arquivos sincronizados na biblioteca.' };
}
