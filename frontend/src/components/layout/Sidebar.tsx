import {
  BookOpen,
  Bookmark,
  ClipboardList,
  Flame,
  History,
  Layers,
  LogOut,
  Settings,
  MessageSquare,
  Package,
  ScanBarcode,
  Truck,
  type LucideIcon,
} from 'lucide-react';
import { NavLink, useNavigate } from 'react-router-dom';
import { cn } from '@/lib/cn';
import { initials } from '@/lib/format';
import { IconButton } from '@/components/ui';

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  /** Право с сервера; без права пункт скрыт. Не указано — доступно всем. */
  perm?: string;
}

/** Разделы меню. Видимость — по правам пользователя, которые отдаёт бэкенд. */
export const NAV: { group: string; items: NavItem[] }[] = [
  {
    group: 'Склад',
    items: [
      { to: '/batches', label: 'Реестр партий', icon: Package },
      { to: '/stock', label: 'Остатки', icon: Layers },
      { to: '/receipts/new', label: 'Поступление', icon: Truck, perm: 'create_receipt' },
    ],
  },
  {
    group: 'Производство',
    items: [
      { to: '/orders', label: 'Задания', icon: ClipboardList },
      { to: '/recipes', label: 'Рецепты', icon: BookOpen },
      { to: '/marking', label: 'Маркировка', icon: ScanBarcode, perm: 'view_marking' },
    ],
  },
  {
    group: 'Ассистент',
    items: [
      { to: '/assistant', label: 'Чат', icon: MessageSquare },
      { to: '/memory', label: 'Память', icon: Bookmark },
    ],
  },
  {
    group: 'Контроль',
    items: [{ to: '/audit', label: 'Журнал изменений', icon: History, perm: 'view_audit' }],
  },
];

interface SidebarProps {
  fullName: string;
  roleTitle: string;
  can: (perm: string) => boolean;
  onLogout: () => void;
}

/** Боковая навигация на всю высоту окна (sticky), карточка пользователя внизу. */
export function Sidebar({ fullName, roleTitle, can, onLogout }: SidebarProps) {
  const navigate = useNavigate();
  return (
    <div className="w-sidebar shrink-0 border-r border-border bg-surface">
      <aside className="sticky top-0 flex h-screen flex-col">
        <div className="flex items-center gap-2.5 px-4 pb-2 pt-4">
          <div className="flex size-7 shrink-0 items-center justify-center rounded bg-accent text-white">
            <Flame className="size-4" aria-hidden />
          </div>
          <div className="min-w-0">
            <div className="text-base font-semibold leading-[18px]">Свечная мастерская</div>
            <div className="text-xs text-fg-muted">Учёт и ассистент</div>
          </div>
        </div>

        <nav aria-label="Разделы" className="flex-1 overflow-y-auto px-2 pb-4">
          {NAV.map(({ group, items }) => {
            const visible = items.filter((i) => !i.perm || can(i.perm));
            if (!visible.length) return null;
            return (
              <div key={group}>
                <div className="px-2 pb-1.5 pt-4 text-2xs font-medium uppercase tracking-[0.06em] text-fg-subtle">{group}</div>
                {visible.map(({ to, label, icon: Icon }) => (
                  <NavLink
                    key={to}
                    to={to}
                    className={({ isActive }) =>
                      cn(
                        'group flex h-8 items-center gap-2.5 rounded px-2 transition-colors',
                        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30',
                        isActive ? 'bg-accent-50 font-medium text-accent-ink' : 'text-fg-label hover:bg-muted hover:text-fg',
                      )
                    }
                  >
                    {({ isActive }) => (
                      <>
                        <Icon className={cn('size-4 shrink-0', isActive ? 'text-accent' : 'text-fg-subtle')} aria-hidden />
                        {label}
                      </>
                    )}
                  </NavLink>
                ))}
              </div>
            );
          })}
        </nav>

        <div className="flex items-center gap-2.5 border-t border-border-soft py-3 pl-4 pr-2">
          <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-hover text-xs font-semibold text-fg-secondary">
            {initials(fullName)}
          </div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium">{fullName}</div>
            <div className="text-xs text-fg-muted">{roleTitle}</div>
          </div>
          <IconButton label="Настройки" onClick={() => navigate('/settings')}>
            <Settings />
          </IconButton>
          <IconButton label="Выйти" onClick={onLogout}>
            <LogOut />
          </IconButton>
        </div>
      </aside>
    </div>
  );
}
