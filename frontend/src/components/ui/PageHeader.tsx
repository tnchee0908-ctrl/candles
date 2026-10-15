import type { ReactNode } from 'react';
import { ChevronRight } from 'lucide-react';
import { Link } from 'react-router-dom';

interface Crumb {
  label: string;
  to?: string;
}

interface PageHeaderProps {
  title: ReactNode;
  /** Бейдж статуса рядом с заголовком */
  badge?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  breadcrumbs?: Crumb[];
}

/** Заголовок страницы, подзаголовок-пояснение, действия справа. */
export function PageHeader({ title, badge, subtitle, actions, breadcrumbs }: PageHeaderProps) {
  return (
    <div className="mb-5">
      {breadcrumbs && (
        <nav aria-label="Навигация" className="mb-1.5 flex items-center gap-1.5 text-sm text-fg-muted">
          {breadcrumbs.map((c, i) => (
            <span key={i} className="inline-flex items-center gap-1.5">
              {i > 0 && <ChevronRight className="size-3" aria-hidden />}
              {c.to ? (
                <Link to={c.to} className="hover:text-fg">
                  {c.label}
                </Link>
              ) : (
                <span>{c.label}</span>
              )}
            </span>
          ))}
        </nav>
      )}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="flex flex-wrap items-center gap-2.5 text-xl font-semibold">
            {title}
            {badge}
          </h1>
          {subtitle && <p className="mt-1 text-fg-secondary">{subtitle}</p>}
        </div>
        {actions && <div className="flex flex-wrap items-start gap-2">{actions}</div>}
      </div>
    </div>
  );
}
