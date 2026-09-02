import React, { useState } from 'react';
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  CheckSquare,
  LogOut,
  Moon,
  Palette,
  Shield,
  Sun,
  Trash2,
  Type,
  User,
  X,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { FontSizeScale, ThemeMode, useUI } from '../../context/UIContext';

const THEME_OPTIONS: { id: ThemeMode; label: string; description: string; preview: { bg: string; surface: string; text: string; primary: string } }[] = [
  {
    id: 'light',
    label: 'Claro',
    description: 'Modo dia com contraste equilibrado',
    preview: { bg: '#f7f7f5', surface: '#ffffff', text: '#1f1f1d', primary: '#242422' },
  },
  {
    id: 'dark',
    label: 'Escuro',
    description: 'Confortável para leituras em ambientes escuros',
    preview: { bg: '#181816', surface: '#222220', text: '#f1f1ed', primary: '#f0f0ec' },
  },
  {
    id: 'oled',
    label: 'OLED',
    description: 'Preto absoluto para telas AMOLED',
    preview: { bg: '#000000', surface: '#090909', text: '#f5f5f2', primary: '#ffffff' },
  },
  {
    id: 'sepia',
    label: 'Papel Sépia',
    description: 'Tons quentes que reduzem a fadiga ocular',
    preview: { bg: '#f6efe0', surface: '#fffbf2', text: '#2c221a', primary: '#47321c' },
  },
  {
    id: 'emerald',
    label: 'Esmeralda',
    description: 'Verde moderno e profissional',
    preview: { bg: '#081715', surface: '#0e221f', text: '#e6f7f4', primary: '#10b981' },
  },
  {
    id: 'dracula',
    label: 'Dracula',
    description: 'Roxo e azul escuro inspirado no VS Code',
    preview: { bg: '#282a36', surface: '#44475a', text: '#f8f8f2', primary: '#bd93f9' },
  },
];

const FONT_OPTIONS: { id: FontSizeScale; label: string; detail: string }[] = [
  { id: 'sm', label: 'Pequeno', detail: 'Compacto (16px)' },
  { id: 'base', label: 'Médio', detail: 'Padrão (18px)' },
  { id: 'lg', label: 'Grande', detail: 'Confortável (20px)' },
  { id: 'xl', label: 'Extra Grande', detail: 'Acessibilidade (22px)' },
];

export const ProfileView: React.FC = () => {
  const { user, logout, isLoggingOut, deleteAccount } = useAuth();
  const { theme, setTheme, fontSize, setFontSize, enableEliminationMode, toggleEliminationMode, showToast } = useUI();

  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [confirmInput, setConfirmInput] = useState('');
  const [isDeleting, setIsDeleting] = useState(false);
  const [imgError, setImgError] = useState(false);

  const userInitial = (user?.name || user?.email || 'C').trim().charAt(0).toUpperCase();

  const handleLogout = async () => {
    try {
      await logout();
      showToast('info', 'Sessão encerrada', 'Você saiu da sua conta.');
    } catch (err) {
      showToast('error', 'Falha ao sair', err instanceof Error ? err.message : 'Tente novamente.');
    }
  };

  const handleDeleteAccount = async () => {
    if (confirmInput.trim().toUpperCase() !== 'EXCLUIR') return;
    setIsDeleting(true);
    try {
      await deleteAccount();
      showToast('success', 'Conta excluída', 'Sua conta e seus dados foram removidos.');
    } catch (err) {
      showToast('error', 'Falha ao excluir', err instanceof Error ? err.message : 'Tente novamente.');
      setIsDeleting(false);
    }
  };

  return (
    <div className="mx-auto max-w-4xl space-y-8 pb-12">
      {/* Cabeçalho do Perfil */}
      <section className="relative overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-6 shadow-sm md:p-8">
        <div className="flex flex-col items-center gap-6 sm:flex-row sm:items-start justify-between">
          <div className="flex flex-col items-center gap-6 sm:flex-row sm:items-start min-w-0 flex-1">
            <div className="relative shrink-0">
              {user?.picture && !imgError ? (
                <img
                  src={user.picture}
                  alt=""
                  className="h-24 w-24 rounded-full border-2 border-[var(--border)] object-cover shadow-md"
                  referrerPolicy="no-referrer"
                  onError={() => setImgError(true)}
                />
              ) : (
                <div className="flex h-24 w-24 items-center justify-center rounded-full border-2 border-[var(--border)] bg-[var(--surface-subtle)] font-mono text-3xl font-bold text-[var(--text)] shadow-md">
                  {userInitial}
                </div>
              )}
              <span className="absolute bottom-1 right-1 flex h-6 w-6 items-center justify-center rounded-full bg-[var(--primary)] text-[var(--on-primary)] shadow" title="Conta Verificada">
                <Check className="h-3.5 w-3.5 stroke-[3]" />
              </span>
            </div>

            <div className="min-w-0 flex-1 text-center sm:text-left">
              <div className="flex flex-wrap items-center justify-center gap-2 sm:justify-start">
                <h1 className="text-2xl font-bold tracking-tight text-[var(--text)] md:text-3xl">
                  {user?.name || 'Concurseiro'}
                </h1>
                <span className="inline-flex items-center gap-1 rounded-full bg-[var(--surface-subtle)] px-2.5 py-0.5 text-xs font-semibold text-[var(--text-muted)] border border-[var(--border)]">
                  <Shield className="h-3 w-3 text-[var(--primary)]" /> Google OAuth
                </span>
              </div>
              <p className="mt-1 font-mono text-sm text-[var(--text-muted)] truncate">{user?.email}</p>
              <p className="mt-3 text-xs text-[var(--text-subtle)]">
                ID da Conta: <code className="rounded bg-[var(--surface-subtle)] px-1.5 py-0.5 font-mono">{user?.id}</code>
              </p>
            </div>
          </div>

          <div className="mt-4 sm:mt-0 shrink-0">
            <button
              type="button"
              onClick={() => void handleLogout()}
              disabled={isLoggingOut}
              className="inline-flex items-center gap-2 rounded-xl border border-[var(--border)] bg-[var(--surface-subtle)] px-4 py-2.5 text-sm font-semibold text-[var(--text)] hover:border-[var(--border-strong)] hover:bg-[var(--surface-hover)] transition active:scale-95 disabled:opacity-50"
            >
              {isLoggingOut ? <span className="ui-loader" aria-hidden="true" /> : <LogOut className="h-4 w-4" />}
              <span>Sair da Conta</span>
            </button>
          </div>
        </div>
      </section>

      {/* Presets de Cor do Site */}
      <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-6 shadow-sm md:p-8 space-y-5">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--surface-subtle)] text-[var(--primary)]">
            <Palette className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-[var(--text)]">Tema & Presets de Cor</h2>
            <p className="text-sm text-[var(--text-muted)]">Escolha a paleta visual ideal para seu ambiente de estudo.</p>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {THEME_OPTIONS.map((opt) => {
            const isSelected = theme === opt.id;
            return (
              <button
                key={opt.id}
                type="button"
                onClick={() => setTheme(opt.id)}
                className={`group relative flex flex-col justify-between rounded-xl border p-4 text-left transition-all ${
                  isSelected
                    ? 'border-[var(--primary)] bg-[var(--surface-subtle)] ring-2 ring-[var(--focus)]'
                    : 'border-[var(--border)] bg-[var(--surface)] hover:border-[var(--border-strong)]'
                }`}
              >
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-semibold text-[var(--text)]">{opt.label}</span>
                    {isSelected && <CheckCircle2 className="h-4 w-4 text-[var(--primary)]" />}
                  </div>
                  <p className="text-xs text-[var(--text-muted)] leading-relaxed">{opt.description}</p>
                </div>

                {/* Swatch de cores */}
                <div className="mt-4 flex items-center gap-1.5 rounded-lg border border-black/10 p-2" style={{ backgroundColor: opt.preview.bg }}>
                  <div className="h-4 w-4 rounded-full border border-black/20" style={{ backgroundColor: opt.preview.surface }} title="Superfície" />
                  <div className="h-4 flex-1 rounded" style={{ backgroundColor: opt.preview.text }} title="Texto" />
                  <div className="h-4 w-6 rounded" style={{ backgroundColor: opt.preview.primary }} title="Acento" />
                </div>
              </button>
            );
          })}
        </div>
      </section>

      {/* Tamanho das Letras */}
      <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-6 shadow-sm md:p-8 space-y-5">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--surface-subtle)] text-[var(--primary)]">
            <Type className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-[var(--text)]">Tamanho das Letras</h2>
            <p className="text-sm text-[var(--text-muted)]">Ajuste o tamanho do texto da interface e dos cadernos de questões.</p>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {FONT_OPTIONS.map((opt) => {
            const isSelected = fontSize === opt.id;
            return (
              <button
                key={opt.id}
                type="button"
                onClick={() => setFontSize(opt.id)}
                className={`flex flex-col items-center justify-center rounded-xl border p-4 text-center transition-all ${
                  isSelected
                    ? 'border-[var(--primary)] bg-[var(--surface-subtle)] font-bold ring-2 ring-[var(--focus)]'
                    : 'border-[var(--border)] bg-[var(--surface)] text-[var(--text-muted)] hover:border-[var(--border-strong)]'
                }`}
              >
                <span className="text-base font-semibold text-[var(--text)]">{opt.label}</span>
                <span className="text-xs text-[var(--text-subtle)] mt-1">{opt.detail}</span>
              </button>
            );
          })}
        </div>

        {/* Demonstração visual de leitura */}
        <div className="mt-4 rounded-xl border border-[var(--border)] bg-[var(--surface-subtle)] p-5">
          <p className="text-xs font-bold uppercase tracking-wider text-[var(--text-subtle)] mb-2">Pré-visualização do Texto de Questão:</p>
          <div className={`font-reading text-[var(--text)] font-scale-${fontSize}`}>
            "Art. 1º A República Federativa do Brasil, formada pela união indissolúvel dos Estados e Municípios e do Distrito Federal, constitui-se em Estado Democrático de Direito..."
          </div>
        </div>
      </section>

      {/* Preferências de Estudo */}
      <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-6 shadow-sm md:p-8 space-y-5">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--surface-subtle)] text-[var(--primary)]">
            <CheckSquare className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-[var(--text)]">Recursos do Simulador</h2>
            <p className="text-sm text-[var(--text-muted)]">Personalize ferramentas durante a resolução das provas.</p>
          </div>
        </div>

        <div className="flex items-center justify-between gap-4 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4">
          <div>
            <p className="font-semibold text-[var(--text)]">Modo de Eliminação de Alternativas</p>
            <p className="text-xs text-[var(--text-muted)]">Permite riscar alternativas com o mouse/toque durante o simulado.</p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={enableEliminationMode}
            onClick={toggleEliminationMode}
            className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-[var(--focus)] ${
              enableEliminationMode ? 'bg-[var(--primary)]' : 'bg-[var(--border)]'
            }`}
          >
            <span
              className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                enableEliminationMode ? 'translate-x-5' : 'translate-x-0'
              }`}
            />
          </button>
        </div>
      </section>

      {/* Zona de Perigo: Exclusão da Conta */}
      <section className="rounded-2xl border border-[var(--danger)]/30 bg-[var(--danger-surface)]/20 p-6 shadow-sm md:p-8 space-y-4">
        <div className="flex items-center gap-3 text-[var(--danger)]">
          <AlertTriangle className="h-6 w-6 shrink-0" />
          <div>
            <h2 className="text-xl font-bold">Zona de Perigo</h2>
            <p className="text-sm opacity-90">Ações irreversíveis relacionadas à sua conta.</p>
          </div>
        </div>

        <p className="text-sm text-[var(--text-muted)] leading-relaxed">
          Ao excluir sua conta, todas as suas pastas, provas salvas, estatísticas de progresso e histórico de tentativas serão apagados permanentemente do servidor. Esta ação não poderá ser desfeita.
        </p>

        <button
          type="button"
          onClick={() => setIsDeleteModalOpen(true)}
          className="inline-flex items-center gap-2 rounded-xl bg-[var(--danger)] px-5 py-2.5 text-sm font-semibold text-white transition hover:opacity-90 active:scale-95"
        >
          <Trash2 className="h-4 w-4" />
          Excluir Minha Conta
        </button>
      </section>

      {/* Modal de Confirmação de Exclusão */}
      {isDeleteModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--overlay)] p-4 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-md rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-6 shadow-xl space-y-5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-[var(--danger)]">
                <AlertTriangle className="h-5 w-5" />
                <h3 className="text-lg font-bold">Confirmar Exclusão</h3>
              </div>
              <button
                type="button"
                onClick={() => setIsDeleteModalOpen(false)}
                className="rounded-lg p-1.5 text-[var(--text-muted)] hover:bg-[var(--surface-subtle)]"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <p className="text-sm text-[var(--text-muted)] leading-relaxed">
              Esta ação apaga <strong>todos os seus dados de forma permanente</strong>. Para confirmar, digite <code className="font-mono font-bold text-[var(--danger)]">EXCLUIR</code> na caixa abaixo:
            </p>

            <input
              type="text"
              value={confirmInput}
              onChange={(e) => setConfirmInput(e.target.value)}
              placeholder="Digite EXCLUIR para confirmar"
              className="w-full rounded-xl border border-[var(--border)] bg-[var(--canvas)] px-4 py-2.5 font-mono text-sm text-[var(--text)] focus:border-[var(--danger)] focus:outline-none focus:ring-2 focus:ring-[var(--danger)]/30"
              autoFocus
            />

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setIsDeleteModalOpen(false)}
                className="rounded-xl border border-[var(--border)] px-4 py-2 text-sm font-semibold text-[var(--text)] hover:bg-[var(--surface-subtle)]"
                disabled={isDeleting}
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={() => void handleDeleteAccount()}
                disabled={confirmInput.trim().toUpperCase() !== 'EXCLUIR' || isDeleting}
                className="inline-flex items-center gap-2 rounded-xl bg-[var(--danger)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-40 hover:opacity-90"
              >
                {isDeleting ? <span className="ui-loader" /> : <Trash2 className="h-4 w-4" />}
                Excluir Definitivamente
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
