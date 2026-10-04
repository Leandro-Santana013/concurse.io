import { describe, expect, it } from 'vitest';
import { importProcessedExam } from '../../../supabase/functions/app-gateway/processed-import';

type Row = Record<string, any>;

// Models the service boundary, including unique source keys and a transient
// database failure, so approval, retries and ownership can be checked together.
class MemoryDatabase {
  rows: Record<string, Row[]> = { exams: [], questions: [], user_exams: [], exam_sources: [], exam_catalog: [] };
  nextId = 1;
  failReadyOnce = false;
  approvedWithQuestionCounts: number[] = [];
  from(table: string) { return new Query(this, table); }
}

class Query {
  filters: Array<(row: Row) => boolean> = [];
  operation = 'select';
  values: Row[] = [];
  options: Row = {};
  cap = Infinity;
  constructor(private db: MemoryDatabase, private table: string) {}
  select(_columns: string, options: Row = {}) { this.options = { ...this.options, ...options }; return this; }
  eq(key: string, value: unknown) { this.filters.push(row => row[key] === value); return this; }
  in(key: string, values: unknown[]) { this.filters.push(row => values.includes(row[key])); return this; }
  limit(value: number) { this.cap = value; return this; }
  insert(values: Row | Row[]) { this.operation = 'insert'; this.values = Array.isArray(values) ? values : [values]; return this; }
  upsert(values: Row, options: Row = {}) { this.operation = 'upsert'; this.values = [values]; this.options = options; return this; }
  update(values: Row) { this.operation = 'update'; this.values = [values]; return this; }
  delete() { this.operation = 'delete'; return this; }
  single() { return this.run(true); }
  maybeSingle() { return this.run(true); }
  then(resolve: (value: any) => unknown, reject?: (reason: unknown) => unknown) { return this.run().then(resolve, reject); }
  private async run(single = false) {
    const rows = this.db.rows[this.table];
    let selected = rows.filter(row => this.filters.every(filter => filter(row)));
    if (this.operation === 'insert' || this.operation === 'upsert') {
      selected = [];
      for (const value of this.values) {
        const keys = this.table === 'exam_sources' ? ['source_key'] : String(this.options.onConflict || 'id').split(',');
        const existing = rows.find(row => keys.every(key => value[key] !== undefined && row[key] === value[key]));
        if (existing) {
          if (this.operation === 'insert') return { data: null, error: { code: '23505', message: 'Duplicate source' }, count: null };
          if (!this.options.ignoreDuplicates) Object.assign(existing, value);
          selected.push(existing);
        } else {
          const row = { ...value };
          if (this.table === 'exams') row.id = this.db.nextId++;
          rows.push(row);
          selected.push(row);
        }
      }
    } else if (this.operation === 'update') {
      if (this.table === 'exams' && this.values[0].status === 'Aprovada') {
        if (this.db.failReadyOnce) {
          this.db.failReadyOnce = false;
          return { data: null, error: { message: 'Temporary database failure' }, count: null };
        }
        selected.forEach(exam => this.db.approvedWithQuestionCounts.push(this.db.rows.questions.filter(question => question.exam_id === exam.id).length));
      }
      selected.forEach(row => Object.assign(row, this.values[0]));
    } else if (this.operation === 'delete') {
      this.db.rows[this.table] = rows.filter(row => !selected.includes(row));
    }
    return { data: single ? selected[0] || null : selected.slice(0, this.cap), error: null, count: selected.length };
  }
}

function payload(source_url?: string, source_object = 'exams/uploads/one.pdf') {
  const document = { title: 'Prova de português', questions: Array.from({ length: 5 }, (_, index) => ({
    id: 700 + index, statement: `Questão ${index + 1}`, options: { A: 'Uma', B: 'Outra' },
    correct_answer: 'B', subject: 'Português', images: ['oci://questions/figure.png'],
  })) };
  return { data_base64: btoa(String.fromCharCode(...new TextEncoder().encode(JSON.stringify(document)))),
    source_object, source_url, gabarito_object: 'exams/uploads/key.pdf' };
}
const keepImage = async (value: unknown) => value;

describe('publicação da extração na biblioteca canônica', () => {
  it('só aprova após persistir as questões e associa o PDF e o gabarito do Oracle', async () => {
    const db = new MemoryDatabase();
    expect(await importProcessedExam(db, 1, payload(), keepImage)).toMatchObject({ exam_id: 1, status: 'Aprovada', reused: false });
    expect(db.approvedWithQuestionCounts).toEqual([5]);
    expect(db.rows.exams[0]).toMatchObject({ source_url: 'oci://exams/uploads/one.pdf', gabarito_url: 'oci://exams/uploads/key.pdf' });
    expect(db.rows.questions[0]).toMatchObject({ exam_id: 1, images: '["oci://questions/figure.png"]' });
    expect(db.rows.questions[0].id).toBeUndefined();
    expect(db.rows.user_exams).toHaveLength(1);
  });

  it('reutiliza uma repetição de upload da mesma conta', async () => {
    const db = new MemoryDatabase();
    await importProcessedExam(db, 1, payload(), keepImage);
    expect(await importProcessedExam(db, 1, payload(), keepImage)).toMatchObject({ exam_id: 1, reused: true });
    expect(db.rows.exams).toHaveLength(1);
    expect(db.rows.questions).toHaveLength(5);
    expect(db.rows.user_exams).toHaveLength(1);
  });

  it('mantém uploads privados separados entre contas', async () => {
    const db = new MemoryDatabase();
    await importProcessedExam(db, 1, payload(), keepImage);
    expect(await importProcessedExam(db, 2, payload(), keepImage)).toMatchObject({ exam_id: 2, reused: false });
    expect(db.rows.exams).toHaveLength(2);
    expect(db.rows.exam_sources.map(row => row.source_key)[0]).not.toBe(db.rows.exam_sources[1].source_key);
  });

  it('compartilha uma prova pública encontrada na busca, mantendo o vínculo de cada conta', async () => {
    const db = new MemoryDatabase();
    const url = 'https://example.com/exam.pdf';
    db.rows.exam_catalog.push({ id: 20, source_url: url });
    await importProcessedExam(db, 1, payload(url), keepImage);
    expect(await importProcessedExam(db, 2, payload(url, 'exams/uploads/two.pdf'), keepImage)).toMatchObject({ exam_id: 1, reused: true });
    expect(db.rows.exams).toHaveLength(1);
    expect(db.rows.questions).toHaveLength(5);
    expect(db.rows.user_exams.map(row => row.user_id)).toEqual([1, 2]);
  });

  it('libera os aliases depois de uma falha e permite reenvio completo', async () => {
    const db = new MemoryDatabase();
    const url = 'https://example.com/exam.pdf';
    db.rows.exam_catalog.push({ id: 20, source_url: url });
    db.failReadyOnce = true;
    await expect(importProcessedExam(db, 1, payload(url), keepImage)).rejects.toThrow('Temporary database failure');
    expect(db.rows.exams[0].status).toBe('Erro');
    expect(db.rows.exam_sources).toHaveLength(0);
    expect(await importProcessedExam(db, 1, payload(url), keepImage)).toMatchObject({ exam_id: 2, status: 'Aprovada' });
    expect(db.rows.exam_sources.every(row => row.exam_id === 2)).toBe(true);
  });

  it('não duplica uma prova pública enquanto outra conta termina o envio', async () => {
    const db = new MemoryDatabase();
    const url = 'https://example.com/exam.pdf';
    db.rows.exam_catalog.push({ id: 20, source_url: url });
    let finish!: () => void;
    let reached!: () => void;
    const blocked = new Promise<void>(resolve => { finish = resolve; });
    const started = new Promise<void>(resolve => { reached = resolve; });
    const first = importProcessedExam(db, 1, payload(url), async value => { reached(); await blocked; return value; });
    await started;
    await expect(importProcessedExam(db, 2, payload(url, 'exams/uploads/two.pdf'), keepImage)).rejects.toMatchObject({ status: 409 });
    finish();
    await first;
    expect(await importProcessedExam(db, 2, payload(url, 'exams/uploads/two.pdf'), keepImage)).toMatchObject({ exam_id: 1, reused: true });
    expect(db.rows.exams).toHaveLength(1);
    expect(db.rows.questions).toHaveLength(5);
  });
});
