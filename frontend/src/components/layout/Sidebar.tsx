import React from 'react';
import { BarChart3, BookOpen, Home, Search, User } from 'lucide-react';
import { Link, NavLink } from 'react-router-dom';

const navigation = [
  { to: '/', label: 'Início', icon: Home, end: true },
  { to: '/biblioteca', label: 'Biblioteca', icon: BookOpen },
  { to: '/buscar', label: 'Buscar', icon: Search },
  { to: '/progresso', label: 'Progresso', icon: BarChart3 },
  { to: '/perfil', label: 'Perfil & Ajustes', icon: User },
];

export const Sidebar: React.FC = () => (
  <aside className="app-sidebar" aria-label="Navegação principal">
    <Link to="/" className="brand-mark" aria-label="concurse.io — Início">
      <span className="brand-symbol" aria-hidden="true">C</span>
      <span className="brand-name">concurse.io</span>
    </Link>

    <nav className="sidebar-nav">
      <p className="sidebar-label">Estudos</p>
      {navigation.map(({ to, label, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          className={({ isActive }) => `sidebar-link${isActive ? ' is-active' : ''}`}
        >
          <Icon aria-hidden="true" />
          <span>{label}</span>
        </NavLink>
      ))}
    </nav>

    <div className="sidebar-footer">
      <BookOpen aria-hidden="true" />
      <p>Um espaço simples para ler, praticar e revisar.</p>
    </div>
  </aside>
);
