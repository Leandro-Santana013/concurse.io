import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { api } from '../services/api';
import { useExamStore } from '../store/useExamStore';
import { AuthUser } from '../types/auth';

type AuthStatus = 'loading' | 'authenticated' | 'unauthenticated';

interface AuthContextValue {
  user: AuthUser | null;
  status: AuthStatus;
  error: string | null;
  isLoggingOut: boolean;
  refreshSession: () => Promise<void>;
  logout: () => Promise<void>;
  deleteAccount: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [status, setStatus] = useState<AuthStatus>('loading');
  const [error, setError] = useState<string | null>(null);
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  const refreshSession = useCallback(async () => {
    setError(null);
    try {
      const currentUser = await api.getCurrentUser();
      if (currentUser) {
        useExamStore.getState().bindToUser(currentUser.id);
      } else {
        useExamStore.getState().clearUserData();
      }
      setUser(currentUser);
      setStatus(currentUser ? 'authenticated' : 'unauthenticated');
    } catch (sessionError) {
      useExamStore.getState().clearUserData();
      setUser(null);
      setStatus('unauthenticated');
      setError(sessionError instanceof Error ? sessionError.message : 'Não foi possível verificar sua sessão.');
    }
  }, []);

  useEffect(() => {
    void refreshSession();
  }, [refreshSession]);

  const logout = useCallback(async () => {
    setIsLoggingOut(true);
    setError(null);
    try {
      await api.logout();
      useExamStore.getState().clearUserData();
      setUser(null);
      setStatus('unauthenticated');
    } catch (logoutError) {
      setError(logoutError instanceof Error ? logoutError.message : 'Não foi possível sair da conta.');
      throw logoutError;
    } finally {
      setIsLoggingOut(false);
    }
  }, []);

  const deleteAccount = useCallback(async () => {
    setIsLoggingOut(true);
    setError(null);
    try {
      await api.deleteAccount();
      useExamStore.getState().clearUserData();
      setUser(null);
      setStatus('unauthenticated');
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : 'Não foi possível excluir sua conta.');
      throw deleteError;
    } finally {
      setIsLoggingOut(false);
    }
  }, []);

  const value = useMemo<AuthContextValue>(() => ({
    user,
    status,
    error,
    isLoggingOut,
    refreshSession,
    logout,
    deleteAccount,
  }), [deleteAccount, error, isLoggingOut, logout, refreshSession, status, user]);


  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = (): AuthContextValue => {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth deve ser usado dentro de AuthProvider.');
  return context;
};
