import React from 'react';
import {
  BarChart3,
  BookOpen,
  CloudDownload,
  Home,
  Import,
  LogOut,
  Search,
  User,
} from 'lucide-react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import { useExam } from '../../context/ExamContext';
import { useUI } from '../../context/UIContext';
import { useAuth } from '../../context/AuthContext';

const navigation = [
  { to: '/', label: 'Início', icon: Home, end: true },
  { to: '/biblioteca', label: 'Biblioteca', icon: BookOpen },
  { to: '/buscar', label: 'Buscar', icon: Search },
  { to: '/progresso', label: 'Progresso', icon: BarChart3 },
  { to: '/perfil', label: 'Perfil', icon: User },
];

const getPageTitle = (pathname: string) => {
  if (pathname === '/perfil') return 'Perfil & Configurações';
  if (pathname === '/biblioteca') return 'Biblioteca';
  if (pathname === '/buscar') return 'Buscar provas';
  if (pathname === '/progresso/erros') return 'Caderno de erros';
  if (pathname === '/progresso/ranking') return 'Ranking';
  if (pathname.startsWith('/progresso')) return 'Progresso';
  return 'Início';
};

export const Navbar: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { activeDownloadsCount, openDirectIngestModal } = useUI();
  const { activeExam, isFinished } = useExam();
  const { user } = useAuth();

  const activeExamPath = activeExam
    ? `/prova/${activeExam.id}${isFinished ? '/resultado' : ''}`
    : '/biblioteca';
  const userInitial = (user?.name || user?.email || 'C').trim().charAt(0).toUpperCase();

  return (
    <>
      <header className="app-navbar">
        <div className="navbar-title-group">
          <span className="mobile-brand" aria-hidden="true">C</span>
          <p>{getPageTitle(location.pathname)}</p>
        </div>

        <div className="navbar-actions">
          {activeDownloadsCount > 0 && (
            <div className="download-status" role="status" aria-live="polite">
              <CloudDownload aria-hidden="true" />
              <span>{activeDownloadsCount} {activeDownloadsCount === 1 ? 'arquivo' : 'arquivos'}</span>
              <span className="desktop-only"> em processamento</span>
            </div>
          )}

          {activeExam && (
            <button
              type="button"
              className="ui-button ui-button-secondary active-exam-button"
              onClick={() => navigate(activeExamPath)}
            >
              <BookOpen aria-hidden="true" />
              <span className="desktop-only">{isFinished ? 'Ver resultado' : 'Continuar prova'}</span>
            </button>
          )}

          <button
            type="button"
            className="ui-button ui-button-primary navbar-import-button"
            onClick={() => openDirectIngestModal()}
            aria-label="Importar prova por link"
          >
            <Import aria-hidden="true" />
            <span className="desktop-only">Importar</span>
          </button>

          <div className="account-control">
            <button
              type="button"
              className="account-identity hover:opacity-90 transition cursor-pointer"
              onClick={() => navigate('/perfil')}
              title="Acessar Perfil & Configurações"
            >
              {user?.picture ? (
                <img src={user.picture} alt="" width="32" height="32" referrerPolicy="no-referrer" />
              ) : (
                <span className="account-avatar" aria-hidden="true">{userInitial}</span>
              )}
              <span className="account-name desktop-only">{user?.name || 'Concurseiro'}</span>
            </button>
          </div>
        </div>
      </header>

      <nav className="mobile-bottom-nav" aria-label="Navegação principal">
        {navigation.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) => `bottom-nav-link${isActive ? ' is-active' : ''}`}
          >
            <Icon aria-hidden="true" />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>
    </>
  );
};
