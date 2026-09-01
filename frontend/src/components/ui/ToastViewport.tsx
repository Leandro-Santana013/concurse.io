import React from 'react';
import { CheckCircle2, CircleAlert, Info, TriangleAlert, X } from 'lucide-react';
import { useUI, type ToastMessage } from '../../context/UIContext';

const icons: Record<ToastMessage['type'], React.ComponentType<{ 'aria-hidden'?: boolean }>> = {
  success: CheckCircle2,
  error: CircleAlert,
  warning: TriangleAlert,
  info: Info,
};

export const ToastViewport: React.FC = () => {
  const { toasts, removeToast } = useUI();

  return (
    <div className="toast-viewport" aria-live="polite" aria-relevant="additions removals">
      {toasts.map((toast) => {
        const Icon = icons[toast.type];
        return (
          <div
            key={toast.id}
            className={`ui-toast ui-toast-${toast.type}`}
            role={toast.type === 'error' ? 'alert' : 'status'}
          >
            <Icon aria-hidden={true} />
            <div>
              <p className="toast-title">{toast.title}</p>
              {toast.message && <p className="toast-message">{toast.message}</p>}
            </div>
            <button
              type="button"
              className="toast-close"
              onClick={() => removeToast(toast.id)}
              aria-label={`Fechar aviso: ${toast.title}`}
            >
              <X aria-hidden={true} />
            </button>
          </div>
        );
      })}
    </div>
  );
};
