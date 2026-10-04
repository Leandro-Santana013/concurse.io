import React, { useEffect, useRef } from 'react';
import { Import, NotebookPen, Trophy, X } from 'lucide-react';
import { NavLink } from 'react-router-dom';
import { useUI } from '../../context/UIContext';

const reviewNavigation = [
  { to: '/progresso/erros', label: 'Caderno de erros', icon: NotebookPen },
  { to: '/progresso/ranking', label: 'Ranking', icon: Trophy },
];

export const MobileMenu: React.FC = () => {
  const { isMobileSidebarOpen, setMobileSidebarOpen, openDirectIngestModal } = useUI();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const close = () => setMobileSidebarOpen(false);
  const keepFocusInMenu = (event: React.KeyboardEvent<HTMLDialogElement>) => {
    if (event.key !== 'Tab') return;
    const controls = event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled), a[href]');
    const first = controls[0];
    const last = controls[controls.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last?.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first?.focus();
    }
  };

  useEffect(() => {
    if (!isMobileSidebarOpen) return;
    const dialog = dialogRef.current;
    if (!dialog) return;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    dialog.showModal();
    closeRef.current?.focus();
    return () => {
      if (dialog.open) dialog.close();
      document.body.style.overflow = previousOverflow;
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, [isMobileSidebarOpen]);

  useEffect(() => {
    const desktop = window.matchMedia('(min-width: 1024px)');
    const closeOnDesktop = () => { if (desktop.matches) setMobileSidebarOpen(false); };
    desktop.addEventListener('change', closeOnDesktop);
    return () => desktop.removeEventListener('change', closeOnDesktop);
  }, [setMobileSidebarOpen]);

  return (
    <dialog
      ref={dialogRef}
      id="mobile-menu"
      className="mobile-menu"
      aria-labelledby="mobile-menu-title"
      aria-modal="true"
      onKeyDown={keepFocusInMenu}
      onCancel={(event) => { event.preventDefault(); close(); }}
      onClose={close}
      onClick={(event) => { if (event.target === event.currentTarget) close(); }}
    >
      <div className="mobile-menu-panel">
        <div className="mobile-menu-header">
          <h2 id="mobile-menu-title">Mais opções</h2>
          <button ref={closeRef} type="button" className="mobile-menu-toggle" aria-label="Fechar menu" onClick={close}>
            <X aria-hidden="true" />
          </button>
        </div>
        <nav className="mobile-menu-navigation" aria-label="Navegação complementar">
          <p className="sidebar-label mobile-menu-section">Revisão</p>
          {reviewNavigation.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} onClick={close} className={({ isActive }) => `sidebar-link${isActive ? ' is-active' : ''}`}>
              <Icon aria-hidden="true" /><span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="mobile-menu-footer">
          <button type="button" className="ui-button ui-button-primary" onClick={() => { close(); openDirectIngestModal(); }}>
            <Import aria-hidden="true" /><span>Importar prova</span>
          </button>
        </div>
      </div>
    </dialog>
  );
};
