import { BarChart3, BookOpen, Home, Search, User, type LucideIcon } from 'lucide-react';

export const primaryNavigation: {
  to: string;
  label: string;
  menuLabel?: string;
  icon: LucideIcon;
  end?: boolean;
}[] = [
  { to: '/', label: 'Início', icon: Home, end: true },
  { to: '/biblioteca', label: 'Biblioteca', icon: BookOpen },
  { to: '/buscar', label: 'Buscar', icon: Search },
  { to: '/progresso', label: 'Progresso', icon: BarChart3 },
  { to: '/perfil', label: 'Perfil', menuLabel: 'Perfil & Ajustes', icon: User },
];
