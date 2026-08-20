import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { api } from '../services/api';

export type ViewType = 'search' | 'folders' | 'stats' | 'errors' | 'ranking' | 'exam';
export type ThemeMode = 'dark' | 'paper' | 'oled';
export type FontSizeScale = 'sm' | 'base' | 'lg';

export interface ToastMessage {
  id: string;
  type: 'success' | 'error' | 'info' | 'warning';
  title: string;
  message?: string;
}

interface UIContextType {
  // Navigation & Layout
  currentView: ViewType;
  navigateTo: (view: ViewType) => void;
  isMobileSidebarOpen: boolean;
  setMobileSidebarOpen: (open: boolean) => void;
  toggleMobileSidebar: () => void;

  // Study Preferences & Theme
  theme: ThemeMode;
  setTheme: (theme: ThemeMode) => void;
  fontSize: FontSizeScale;
  setFontSize: (size: FontSizeScale) => void;
  enableEliminationMode: boolean;
  toggleEliminationMode: () => void;

  // Live Downloads & Tasks
  activeDownloadsCount: number;
  refreshDownloads: () => Promise<void>;

  // Toast Notifications
  toasts: ToastMessage[];
  showToast: (type: ToastMessage['type'], title: string, message?: string) => void;
  removeToast: (id: string) => void;
}

const UIContext = createContext<UIContextType | undefined>(undefined);

const PREFS_STORAGE_KEY = 'concurse_ui_preferences_v1';

export const UIProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  // Navigation
  const [currentView, setCurrentView] = useState<ViewType>('search');
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);

  // Study Preferences
  const [theme, setThemeState] = useState<ThemeMode>(() => {
    const saved = localStorage.getItem(PREFS_STORAGE_KEY);
    if (saved) {
      try {
        return JSON.parse(saved).theme || 'dark';
      } catch (e) {
        return 'dark';
      }
    }
    return 'dark';
  });

  const [fontSize, setFontSizeState] = useState<FontSizeScale>(() => {
    const saved = localStorage.getItem(PREFS_STORAGE_KEY);
    if (saved) {
      try {
        return JSON.parse(saved).fontSize || 'base';
      } catch (e) {
        return 'base';
      }
    }
    return 'base';
  });

  const [enableEliminationMode, setEnableEliminationMode] = useState<boolean>(() => {
    const saved = localStorage.getItem(PREFS_STORAGE_KEY);
    if (saved) {
      try {
        return JSON.parse(saved).enableEliminationMode ?? true;
      } catch (e) {
        return true;
      }
    }
    return true;
  });

  // Downloads tracking
  const [activeDownloadsCount, setActiveDownloadsCount] = useState(0);

  // Toasts
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  // Persist preferences
  useEffect(() => {
    localStorage.setItem(
      PREFS_STORAGE_KEY,
      JSON.stringify({ theme, fontSize, enableEliminationMode })
    );
  }, [theme, fontSize, enableEliminationMode]);

  // Apply theme class to document root
  useEffect(() => {
    const root = document.documentElement;
    root.classList.remove('theme-dark', 'theme-paper', 'theme-oled');
    root.classList.add(`theme-${theme}`);
  }, [theme]);

  // Periodic active downloads check
  const refreshDownloads = async () => {
    try {
      const downloads = await api.getActiveDownloads();
      setActiveDownloadsCount(downloads.length);
    } catch (e) {
      // silent catch for background polling
    }
  };

  useEffect(() => {
    refreshDownloads();
    const interval = setInterval(refreshDownloads, 4000);
    return () => clearInterval(interval);
  }, []);

  const navigateTo = (view: ViewType) => {
    setCurrentView(view);
    setIsMobileSidebarOpen(false);
  };

  const toggleMobileSidebar = () => {
    setIsMobileSidebarOpen((prev) => !prev);
  };

  const setTheme = (newTheme: ThemeMode) => {
    setThemeState(newTheme);
  };

  const setFontSize = (newSize: FontSizeScale) => {
    setFontSizeState(newSize);
  };

  const toggleEliminationMode = () => {
    setEnableEliminationMode((prev) => !prev);
  };

  const showToast = (type: ToastMessage['type'], title: string, message?: string) => {
    const id = `${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
    setToasts((prev) => [...prev, { id, type, title, message }]);
    setTimeout(() => {
      removeToast(id);
    }, 4000);
  };

  const removeToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  return (
    <UIContext.Provider
      value={{
        currentView,
        navigateTo,
        isMobileSidebarOpen,
        setMobileSidebarOpen: setIsMobileSidebarOpen,
        toggleMobileSidebar,
        theme,
        setTheme,
        fontSize,
        setFontSize,
        enableEliminationMode,
        toggleEliminationMode,
        activeDownloadsCount,
        refreshDownloads,
        toasts,
        showToast,
        removeToast,
      }}
    >
      {children}
    </UIContext.Provider>
  );
};

export const useUI = (): UIContextType => {
  const context = useContext(UIContext);
  if (!context) {
    throw new Error('useUI must be used within a UIProvider');
  }
  return context;
};
