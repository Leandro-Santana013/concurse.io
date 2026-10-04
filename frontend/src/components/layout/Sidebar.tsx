import React from 'react';
import { BookOpen } from 'lucide-react';
import { Link, NavLink } from 'react-router-dom';
import { primaryNavigation } from './navigation';
import { BrandIcon } from '../ui/BrandIcon';

export const Sidebar: React.FC = () => (
  <aside className="app-sidebar" aria-label="Navegação principal">
    <Link to="/" className="brand-mark" aria-label="concurse.io — Início">
      <BrandIcon className="brand-symbol brand-logo-image" width={28} height={28} />
      <span className="brand-name">concurse.io</span>
    </Link>

    <nav className="sidebar-nav">
      <p className="sidebar-label">Estudos</p>
      {primaryNavigation.map(({ to, label, menuLabel, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          className={({ isActive }) => `sidebar-link${isActive ? ' is-active' : ''}`}
        >
          <Icon aria-hidden="true" />
          <span>{menuLabel || label}</span>
        </NavLink>
      ))}
    </nav>

    <div className="sidebar-footer">
      <BookOpen aria-hidden="true" />
      <p>Um espaço simples para ler, praticar e revisar.</p>
    </div>
  </aside>
);
