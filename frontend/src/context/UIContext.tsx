import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { api } from '../services/api';

export type ViewType = 'home' | 'search' | 'folders' | 'stats' | 'errors' | 'ranking' | 'exam';
export type ThemeMode = 'light' | 'dark' | 'oled';
export type FontSizeScale = 'sm' | 'base' | 'lg';

export interface ToastMessage {
  id: string;
  type: 'success' | 'error' | 'info' | 'warning';
  title: string;
  message?: string;
}

export interface DirectIngestInitialData {
  examUrl?: string;
  gabaritoUrl?: string;
  title?: string;
}

interface UIContextType {
  currentView: ViewType;
  navigateTo: (view: ViewType) => void;
  isMobileSidebarOpen: boolean;
  setMobileSidebarOpen: (open: boolean) => void;
  toggleMobileSidebar: () => void;
  theme: ThemeMode;
  setTheme: (theme: ThemeMode) => void;
  fontSize: FontSizeScale;
  setFontSize: (size: FontSizeScale) => void;
  enableEliminationMode: boolean;
  toggleEliminationMode: () => void;
  activeDownloadsCount: number;
  refreshDownloads: () => Promise<void>;
  isDirectIngestModalOpen: boolean;
  directIngestData: DirectIngestInitialData;
  openDirectIngestModal: (data?: DirectIngestInitialData) => void;
  closeDirectIngestModal: () => void;
  toasts: ToastMessage[];
  showToast: (type: ToastMessage['type'], title: string, message?: string) => void;
  removeToast: (id: string) => void;
}

interface StoredPreferences {
  version: 2;
  theme: ThemeMode;
  fontSize: FontSizeScale;
  enableEliminationMode: boolean;
}

const UIContext = createContext<UIContextType | undefined>(undefined);

const PREFS_STORAGE_KEY = 'concurse_ui_preferences_v2';
const LEGACY_PREFS_STORAGE_KEY = 'concurse_ui_preferences_v1';

const viewPaths: Record<ViewType, string> = {
  home: '/',
  folders: '/biblioteca',
  search: '/buscar',
  stats: '/progresso',
  errors: '/progresso/erros',
  ranking: '/progresso/ranking',
  exam: '/prova/ativa',
};

const getViewFromPath = (pathname: string): ViewType => {
  if (pathname.startsWith('/prova/')) return 'exam';
  if (pathname === '/buscar') return 'search';
  if (pathname === '/biblioteca') return 'folders';
  if (pathname === '/progresso/erros') return 'errors';
  if (pathname === '/progresso/ranking') return 'ranking';
  if (pathname.startsWith('/progresso')) return 'stats';
  return 'home';
};

const readPreferences = (): StoredPreferences => {
  const defaults: StoredPreferences = {
    version: 2,
    theme: 'light',
    fontSize: 'base',
    enableEliminationMode: true,
  };

  try {
    const raw = localStorage.getItem(PREFS_STORAGE_KEY) ?? localStorage.getItem(LEGACY_PREFS_STORAGE_KEY);
    if (!raw) return defaults;

    const saved = JSON.parse(raw) as {
      theme?: string;
      fontSize?: string;
      enableEliminationMode?: boolean;
    };
    const theme: ThemeMode = saved.theme === 'paper'
      ? 'light'
      : saved.theme === 'dark' || saved.theme === 'oled' || saved.theme === 'light'
        ? saved.theme
        : defaults.theme;
    const fontSize: FontSizeScale = saved.fontSize === 'sm' || saved.fontSize === 'lg'
      ? saved.fontSize
      : 'base';

    return {
      version: 2,
      theme,
      fontSize,
      enableEliminationMode: saved.enableEliminationMode ?? true,
    };
  } catch {
    return defaults;
  }
};

export const UIProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const initialPreferences = useMemo(readPreferences, []);
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);
  const [theme, setTheme] = useState<ThemeMode>(initialPreferences.theme);
  const [fontSize, setFontSize] = useState<FontSizeScale>(initialPreferences.fontSize);
  const [enableEliminationMode, setEnableEliminationMode] = useState(
    initialPreferences.enableEliminationMode,
  );
  const [activeDownloadsCount, setActiveDownloadsCount] = useState(0);
  const [isDirectIngestModalOpen, setIsDirectIngestModalOpen] = useState(false);
  const [directIngestData, setDirectIngestData] = useState<DirectIngestInitialData>({});
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const currentView = getViewFromPath(location.pathname);

  useEffect(() => {
    const preferences: StoredPreferences = {
      version: 2,
      theme,
      fontSize,
      enableEliminationMode,
    };
    localStorage.setItem(PREFS_STORAGE_KEY, JSON.stringify(preferences));
  }, [theme, fontSize, enableEliminationMode]);

  useEffect(() => {
    const root = document.documentElement;
    root.classList.remove('theme-light', 'theme-dark', 'theme-paper', 'theme-oled');
    root.classList.add(`theme-${theme}`);
    root.dataset.theme = theme;
    root.style.colorScheme = theme === 'light' ? 'light' : 'dark';
  }, [theme]);

  useEffect(() => {
    const root = document.documentElement;
    root.classList.remove('font-scale-ui-sm', 'font-scale-ui-base', 'font-scale-ui-lg');
    root.classList.add(`font-scale-ui-${fontSize}`);
  }, [fontSize]);

  useEffect(() => {
    setIsMobileSidebarOpen(false);
  }, [location.pathname]);

  const refreshDownloads = useCallback(async () => {
    try {
      const downloads = await api.getActiveDownloads();
      setActiveDownloadsCount(downloads.length);
    } catch {
      setActiveDownloadsCount(0);
    }
  }, []);

  useEffect(() => {
    void refreshDownloads();
    const interval = window.setInterval(() => void refreshDownloads(), 4000);
    return () => window.clearInterval(interval);
  }, [refreshDownloads]);

  const navigateTo = useCallback((view: ViewType) => {
    navigate(viewPaths[view]);
    setIsMobileSidebarOpen(false);
  }, [navigate]);

  const openDirectIngestModal = useCallback((data?: DirectIngestInitialData) => {
    setDirectIngestData(data ?? {});
    setIsDirectIngestModalOpen(true);
  }, []);

  const closeDirectIngestModal = useCallback(() => {
    setIsDirectIngestModalOpen(false);
    setDirectIngestData({});
  }, []);

  const removeToast = useCallback((id: string) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const showToast = useCallback((
    type: ToastMessage['type'],
    title: string,
    message?: string,
  ) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
    setToasts((current) => [...current.slice(-3), { id, type, title, message }]);
    window.setTimeout(() => removeToast(id), 5000);
  }, [removeToast]);

  const value = useMemo<UIContextType>(() => ({
    currentView,
    navigateTo,
    isMobileSidebarOpen,
    setMobileSidebarOpen: setIsMobileSidebarOpen,
    toggleMobileSidebar: () => setIsMobileSidebarOpen((open) => !open),
    theme,
    setTheme,
    fontSize,
    setFontSize,
    enableEliminationMode,
    toggleEliminationMode: () => setEnableEliminationMode((enabled) => !enabled),
    activeDownloadsCount,
    refreshDownloads,
    isDirectIngestModalOpen,
    directIngestData,
    openDirectIngestModal,
    closeDirectIngestModal,
    toasts,
    showToast,
    removeToast,
  }), [
    activeDownloadsCount,
    closeDirectIngestModal,
    currentView,
    directIngestData,
    enableEliminationMode,
    fontSize,
    isDirectIngestModalOpen,
    isMobileSidebarOpen,
    navigateTo,
    openDirectIngestModal,
    refreshDownloads,
    removeToast,
    showToast,
    theme,
    toasts,
  ]);

  return <UIContext.Provider value={value}>{children}</UIContext.Provider>;
};

export const useUI = (): UIContextType => {
  const context = useContext(UIContext);
  if (!context) throw new Error('useUI must be used within a UIProvider');
  return context;
};
