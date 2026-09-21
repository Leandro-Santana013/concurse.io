import React, { useEffect, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { BarChart3, BookOpen, CheckCircle2, Layers3, RefreshCw, Target } from 'lucide-react';
import { api } from '../../services/api';
import { IbamAnalysis, IbamCategoryAverage, IbamExamAnalysis, IbamExamCategory } from '../../types/exam';

const formatPercentage = (value: number) => `${value.toLocaleString('pt-BR', {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
})}%`;

const formatQuestionCount = (value: number) => `${value} ${value === 1 ? 'questão' : 'questões'}`;

const shortCategoryName = (name: string) => {
  if (name === 'Conhecimentos Específicos') return 'Específicos';
  if (name === 'Conhecimentos Gerais / Atualidades') return 'Gerais / Atualidades';
  if (name === 'Matemática e Raciocínio Lógico') return 'Matemática / Raciocínio';
  return name;
};

const CategoryTable: React.FC<{ categories: IbamExamCategory[]; caption: string }> = ({ categories, caption }) => (
  <div className="overflow-x-auto">
    <table className="data-table">
      <caption className="sr-only">{caption}</caption>
      <thead>
        <tr>
          <th className="w-16">Índice</th>
          <th>Categoria</th>
          <th>Questões</th>
          <th className="text-right">Peso</th>
        </tr>
      </thead>
      <tbody>
        {categories.map((category) => (
          <tr key={`${category.name}-${category.question_range}`}>
            <td className="font-mono font-bold">{category.rank}º</td>
            <td>
              <span className="font-semibold text-[var(--text)]">{category.name}</span>
              <span className="mt-1 block text-xs text-[var(--text-muted)]">Questões {category.question_range}</span>
            </td>
            <td className="font-mono">{category.question_count}</td>
            <td className="text-right font-mono font-bold text-[var(--primary)]">{formatPercentage(category.percentage)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

const AverageTable: React.FC<{ categories: IbamCategoryAverage[] }> = ({ categories }) => (
  <div className="overflow-x-auto">
    <table className="data-table">
      <caption className="sr-only">Média de peso por categoria nas provas IBAM analisadas</caption>
      <thead>
        <tr>
          <th className="w-16">Índice</th>
          <th>Categoria</th>
          <th className="text-right">Média por prova</th>
          <th className="text-right">Peso no conjunto</th>
        </tr>
      </thead>
      <tbody>
        {categories.map((category) => (
          <tr key={category.name}>
            <td className="font-mono font-bold">{category.rank}º</td>
            <td>
              <span className="font-semibold text-[var(--text)]">{category.name}</span>
              <span className="mt-1 block text-xs text-[var(--text-muted)]">
                média de {category.average_question_count.toLocaleString('pt-BR')} questões
              </span>
            </td>
            <td className="text-right font-mono font-bold text-[var(--primary)]">
              {formatPercentage(category.average_weight_percentage)}
            </td>
            <td className="text-right font-mono">{formatPercentage(category.aggregate_percentage)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

const ExamCategoryList: React.FC<{ exam: IbamExamAnalysis }> = ({ exam }) => (
  <div className="ibam-category-list" aria-label={`Categorias de ${exam.title}`}>
    {exam.categories.map((category) => (
      <div className="ibam-category-row" key={`${exam.exam_id}-${category.name}`}>
        <div className="ibam-category-row-heading">
          <div className="flex min-w-0 items-start gap-3">
            <span className="ibam-rank-badge" aria-hidden="true">{category.rank}</span>
            <div className="min-w-0">
              <h4>{category.name}</h4>
              <p>Questões {category.question_range} · {formatQuestionCount(category.question_count)}</p>
            </div>
          </div>
          <strong>{formatPercentage(category.percentage)}</strong>
        </div>
        <progress
          className="ibam-weight-progress"
          max={100}
          value={category.percentage}
          aria-label={`${category.name}: ${formatPercentage(category.percentage)}`}
        />
      </div>
    ))}
  </div>
);

export const IbamAnalysisView: React.FC = () => {
  const [analysis, setAnalysis] = useState<IbamAnalysis | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadAnalysis = async () => {
    setIsLoading(true);
    setError(null);
    try {
      setAnalysis(await api.getIbamAnalysis());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Não foi possível carregar a análise IBAM.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => { void loadAnalysis(); }, []);

  if (isLoading) {
    return (
      <div className="space-y-5" aria-busy="true">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">{[1, 2, 3, 4].map((item) => <div key={item} className="skeleton h-28" />)}</div>
        <div className="skeleton h-80" />
        <div className="skeleton h-64" />
      </div>
    );
  }

  if (error || !analysis) {
    return (
      <div className="state-card" role="alert">
        <RefreshCw aria-hidden="true" />
        <div>
          <h2>Não foi possível carregar a análise IBAM</h2>
          <p>{error || 'A resposta da análise não está disponível.'}</p>
        </div>
        <button className="button-secondary" onClick={() => void loadAnalysis()}>Tentar novamente</button>
      </div>
    );
  }

  if (!analysis.available || analysis.exams.length === 0) {
    return (
      <div className="state-card text-center">
        <BookOpen className="mx-auto" aria-hidden="true" />
        <h2>Nenhuma prova IBAM indexada</h2>
        <p>Adicione uma prova IBAM aprovada à sua biblioteca para visualizar o peso das categorias.</p>
      </div>
    );
  }

  const dominant = analysis.dominant_category;
  const chartData = analysis.category_averages.slice(0, 8).map((category) => ({
    ...category,
    chart_label: shortCategoryName(category.name),
  }));
  const topCategorySummary = dominant
    ? `${dominant.name} lidera com média de ${formatPercentage(dominant.average_weight_percentage)} por prova.`
    : 'Ainda não há uma categoria dominante.';

  return (
    <div className="space-y-6">
      <section className="ibam-analysis-intro" aria-labelledby="ibam-analysis-title">
        <div>
          <p className="eyebrow">Índice de conteúdo</p>
          <h1 id="ibam-analysis-title" className="page-title">Peso das categorias · IBAM</h1>
          <p className="page-description">Veja quais categorias concentram mais questões em cada prova e qual é a média de peso entre as provas IBAM indexadas.</p>
        </div>
        <div className="ibam-analysis-intro-mark" aria-hidden="true"><BarChart3 /></div>
      </section>

      <section className="grid grid-cols-2 gap-3 md:grid-cols-4" aria-label="Resumo da análise IBAM">
        <article className="metric-card"><BookOpen aria-hidden="true" /><span>Provas analisadas</span><strong>{analysis.exam_count}</strong></article>
        <article className="metric-card"><Target aria-hidden="true" /><span>Questões indexadas</span><strong>{analysis.question_count}</strong></article>
        <article className="metric-card"><CheckCircle2 aria-hidden="true" /><span>Cobertura categorizada</span><strong>{formatPercentage(analysis.coverage_percentage)}</strong></article>
        <article className="metric-card ibam-leader-card"><Layers3 aria-hidden="true" /><span>Maior média de peso</span><strong>{dominant ? formatPercentage(dominant.average_weight_percentage) : '—'}</strong><small>{dominant?.name || 'Sem categoria'}</small></article>
      </section>

      <section className="ibam-analysis-panel" aria-labelledby="ibam-average-title">
        <div className="section-heading-row">
          <div>
            <h2 id="ibam-average-title" className="section-title">Média de peso por categoria</h2>
            <p className="mt-1 text-sm text-[var(--text-muted)]">{topCategorySummary}</p>
          </div>
          <span className="status-neutral">{analysis.exam_count} provas</span>
        </div>

        <div className="ibam-chart" aria-hidden="true">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} layout="vertical" margin={{ top: 8, right: 16, left: 8, bottom: 8 }}>
              <CartesianGrid stroke="var(--border)" horizontal={false} />
              <XAxis type="number" domain={[0, 'dataMax + 8']} tickFormatter={(value) => `${value}%`} stroke="var(--text-muted)" fontSize={11} tickLine={false} />
              <YAxis type="category" dataKey="chart_label" width={142} stroke="var(--text-muted)" fontSize={11} tickLine={false} />
              <Tooltip
                cursor={{ fill: 'var(--surface-subtle)' }}
                contentStyle={{ background: 'var(--surface)', color: 'var(--text)', border: '1px solid var(--border)', borderRadius: 8 }}
                formatter={(value) => [formatPercentage(Number(value)), 'Média por prova']}
              />
              <Bar dataKey="average_weight_percentage" name="Média por prova" fill="var(--primary)" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <p className="sr-only">{topCategorySummary} A tabela abaixo contém os valores exatos.</p>
        <AverageTable categories={analysis.category_averages} />
      </section>

      <section aria-labelledby="ibam-exams-title">
        <div className="section-heading-row mb-3">
          <div>
            <h2 id="ibam-exams-title" className="section-title">Categorias por prova</h2>
            <p className="mt-1 text-sm text-[var(--text-muted)]">Cada prova está ordenada do maior para o menor peso de questões.</p>
          </div>
        </div>
        <div className="grid gap-4 xl:grid-cols-2">
          {analysis.exams.map((exam, index) => (
            <article className="ibam-exam-card" key={exam.exam_id}>
              <header className="ibam-exam-card-heading">
                <div className="min-w-0">
                  <span className="eyebrow">#{index + 1} · {formatQuestionCount(exam.question_count)}</span>
                  <h3>{exam.title}</h3>
                </div>
                {exam.top_category && <span className="status-success">Maior: {formatPercentage(exam.top_category.percentage)}</span>}
              </header>
              <ExamCategoryList exam={exam} />
              <CategoryTable categories={exam.categories} caption={`Índice detalhado de ${exam.title}`} />
            </article>
          ))}
        </div>
      </section>

      <aside className="ibam-methodology" aria-labelledby="ibam-methodology-title">
        <h2 id="ibam-methodology-title" className="section-title">Como ler este índice</h2>
        <p>{analysis.methodology.average_definition}</p>
        <p>{analysis.methodology.category_source}</p>
        {analysis.unclassified_question_count > 0 && (
          <p className="status-warning">{analysis.unclassified_question_count} {analysis.unclassified_question_count === 1 ? 'questão ficou' : 'questões ficaram'} sem categoria confiável.</p>
        )}
      </aside>
    </div>
  );
};
