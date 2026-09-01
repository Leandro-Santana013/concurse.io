import React from 'react';
import { NavLink, Outlet } from 'react-router-dom';

const tabs = [
  { to: '/progresso', label: 'Resumo', end: true },
  { to: '/progresso/erros', label: 'Caderno de erros' },
  { to: '/progresso/ranking', label: 'Ranking' },
];

export const ProgressLayout: React.FC = () => (
  <div className="progress-layout">
    <nav className="ui-tabs" aria-label="Seções de progresso">
      {tabs.map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          end={tab.end}
          className={({ isActive }) => `ui-tab${isActive ? ' is-active' : ''}`}
        >
          {tab.label}
        </NavLink>
      ))}
    </nav>
    <Outlet />
  </div>
);
