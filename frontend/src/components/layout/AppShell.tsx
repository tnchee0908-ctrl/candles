import type { ReactNode } from 'react';
import { Outlet } from 'react-router-dom';
import { cn } from '@/lib/cn';
import { useAuth } from '@/auth';
import { Sidebar } from './Sidebar';

/** Каркас: сайдбар 240 px на всю высоту + контент. Ассистент рендерит свою колонку сам. */
export function AppShell() {
  const { user, can, logout } = useAuth();
  return (
    <div className="flex min-h-screen">
      <Sidebar fullName={user?.full_name ?? ''} roleTitle={user?.role_title ?? ''} can={can} onLogout={logout} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Outlet />
      </div>
    </div>
  );
}

/**
 * Контентная область страницы. `wide` — для реестров (таблица на всю ширину),
 * иначе карточки ограничены 1200 px.
 */
export function Page({ children, wide, narrow }: { children: ReactNode; wide?: boolean; narrow?: boolean }) {
  return (
    <main className="min-w-0 flex-1 px-7 pb-12 pt-7">
      <div className={cn(!wide && (narrow ? 'max-w-[760px]' : 'max-w-content'))}>{children}</div>
    </main>
  );
}
