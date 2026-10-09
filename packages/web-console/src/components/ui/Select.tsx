import { ReactNode } from 'react';

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  error?: string;
  children: ReactNode;
  containerClassName?: string;
  variant?: 'default' | 'outline' | 'ghost';
}

export function Select({ 
  label, 
  error, 
  children, 
  variant = 'default',
  className = '', 
  containerClassName = '',
  ...props 
}: SelectProps) {
  const variantClasses: Record<string, string> = {
    default: 'border-dashboard-border focus:border-primary-500 focus:ring-primary-500/20 focus:ring-offset-dashboard-bg',
    outline: 'border-dashboard-border focus:border-primary-500 focus:ring-primary-500/20 focus:ring-offset-dashboard-bg',
    ghost: 'border-transparent hover:border-dashboard-border focus:border-primary-500 focus:bg-dashboard-card focus:ring-primary-500/20 focus:ring-offset-dashboard-bg',
  };

  const baseClass = 'block w-full rounded-lg border bg-dashboard-card px-3 py-2 text-sm text-dashboard-text shadow-sm transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 appearance-none';

  return (
    <div className={`space-y-1.5 ${containerClassName}`}>
      {label && (
        <label className="block text-sm font-medium text-dashboard-text-secondary">
          {label}
        </label>
      )}
      <div className="relative">
        <select
          className={`${baseClass} ${variantClasses[variant]} ${className} pr-10`}
          {...props}
        >
          {children}
        </select>
        <div className="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none">
          <svg className="h-4 w-4 text-dashboard-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </div>
      {error && <p className="text-xs text-red-400">{error}</p>}
    </div>
  );
}
