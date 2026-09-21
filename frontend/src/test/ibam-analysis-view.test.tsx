import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { IbamAnalysisView } from '../components/stats/IbamAnalysisView';

const apiMocks = vi.hoisted(() => ({
  getIbamAnalysis: vi.fn(),
}));

vi.mock('../services/api', () => ({
  api: apiMocks,
  AuthRequiredError: class AuthRequiredError extends Error {},
}));

vi.mock('recharts', () => {
  const passthrough = ({ children }: React.PropsWithChildren) => <div>{children}</div>;
  return {
    Bar: () => <div />,
    BarChart: passthrough,
    CartesianGrid: () => <div />,
    ResponsiveContainer: passthrough,
    Tooltip: () => <div />,
    XAxis: () => <div />,
    YAxis: () => <div />,
  };
});

const category = (name: string, count: number, percentage: number, rank: number, questionRange = '1–10') => ({
  name,
  category_group: name,
  question_count: count,
  percentage,
  question_range: questionRange,
  rank,
});

describe('análise de categorias IBAM', () => {
  beforeEach(() => {
    apiMocks.getIbamAnalysis.mockResolvedValue({
      available: true,
      exam_count: 1,
      question_count: 40,
      classified_question_count: 40,
      unclassified_question_count: 0,
      coverage_percentage: 100,
      dominant_category: {
        name: 'Informática',
        exam_count: 1,
        average_question_count: 14,
        average_weight_percentage: 35,
        question_count: 14,
        aggregate_percentage: 35,
        exam_weights: [{ exam_id: 5, question_count: 14, percentage: 35 }],
        rank: 1,
      },
      category_averages: [
        {
          name: 'Informática',
          exam_count: 1,
          average_question_count: 14,
          average_weight_percentage: 35,
          question_count: 14,
          aggregate_percentage: 35,
          exam_weights: [{ exam_id: 5, question_count: 14, percentage: 35 }],
          rank: 1,
        },
        {
          name: 'Língua Portuguesa',
          exam_count: 1,
          average_question_count: 10,
          average_weight_percentage: 25,
          question_count: 10,
          aggregate_percentage: 25,
          exam_weights: [{ exam_id: 5, question_count: 10, percentage: 25 }],
          rank: 2,
        },
        {
          name: 'Administração',
          exam_count: 1,
          average_question_count: 4,
          average_weight_percentage: 10,
          question_count: 4,
          aggregate_percentage: 10,
          exam_weights: [{ exam_id: 5, question_count: 4, percentage: 10 }],
          rank: 3,
        },
        {
          name: 'Redação Oficial',
          exam_count: 1,
          average_question_count: 3,
          average_weight_percentage: 7.5,
          question_count: 3,
          aggregate_percentage: 7.5,
          exam_weights: [{ exam_id: 5, question_count: 3, percentage: 7.5 }],
          rank: 4,
        },
        {
          name: 'Arquivologia',
          exam_count: 1,
          average_question_count: 1,
          average_weight_percentage: 2.5,
          question_count: 1,
          aggregate_percentage: 2.5,
          exam_weights: [{ exam_id: 5, question_count: 1, percentage: 2.5 }],
          rank: 5,
        },
      ],
      exams: [{
        exam_id: 5,
        title: 'IBAM · 2020 · Prefeitura de Santos — Oficial de Administração',
        source_title: 'Prova 2020',
        year: 2020,
        question_count: 40,
        classified_question_count: 40,
        unclassified_question_count: 0,
        coverage_percentage: 100,
        top_category: category('Informática', 14, 35, 1, '19–32'),
        categories: [
          category('Informática', 14, 35, 1, '19–32'),
          category('Língua Portuguesa', 10, 25, 2, '1–10'),
          category('Administração', 4, 10, 3, '33–35, 39'),
          category('Redação Oficial', 3, 7.5, 4, '36–38'),
          category('Arquivologia', 1, 2.5, 5, '40'),
        ],
      }],
      methodology: {
        category_source: 'Faixas documentadas',
        average_definition: 'Média aritmética do percentual de cada categoria em cada prova.',
        ranking_definition: 'Maior peso primeiro.',
      },
    });
  });

  it('exibe a média e ordena as categorias da prova pelo maior peso', async () => {
    render(<IbamAnalysisView />);

    expect(await screen.findByRole('heading', { name: 'Peso das categorias · IBAM' })).toBeInTheDocument();
    expect(screen.getByText('Maior média de peso')).toBeInTheDocument();
    expect(screen.getAllByText('35,0%').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Administração').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Redação Oficial').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Arquivologia').length).toBeGreaterThan(0);
    expect(screen.getByText('Questões 1–10 · 10 questões')).toBeInTheDocument();
    await waitFor(() => expect(apiMocks.getIbamAnalysis).toHaveBeenCalledTimes(1));
  });
});
