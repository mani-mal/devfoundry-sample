import { ReactNode, InputHTMLAttributes } from 'react';

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  icon?: ReactNode;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
  containerClassName?: string;
  variant?: 'default' | 'outline' | 'ghost' | 'error';
}

export function Input({ 
  label, 
  error, 
  icon, 
  leftIcon, 
  rightIcon,
  variant = 'default',
  className = '', 
  containerClassName = '',
  ...props 
}: InputProps) {
  const variantClasses: Record<string, string> = {
    default: 'border-dashboard-border focus:border-primary-500 focus:ring-primary-500/20 focus:ring-offset-dashboard-bg',
    outline: 'border-dashboard-border focus:border-primary-500 focus:ring-primary-500/20 focus:ring-offset-dashboard-bg',
    ghost: 'border-transparent hover:border-dashboard-border focus:border-primary-500 focus:bg-dashboard-card focus:ring-primary-500/20 focus:ring-offset-dashboard-bg',
    error: 'border-red-500/50 focus:border-red-500 focus:ring-red-500/20 focus:ring-offset-dashboard-bg bg-red-500/5',
  };

  const baseClass = 'block w-full rounded-lg border bg-dashboard-card px-3 py-2 text-sm text-dashboard-text shadow-sm placeholder:text-dashboard-muted transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50';

  return (
    <div className={`space-y-1.5 ${containerClassName}`}>
      {label && (
        <label className="block text-sm font-medium text-dashboard-text-secondary">
          {label}
        </label>
      )}
      <div className="relative">
        {leftIcon && (
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
            {leftIcon}
          </div>
        )}
        <input
          className={`${baseClass} ${variantClasses[variant]} ${className}`}
          {...props}
        />
        {rightIcon && (
          <div className="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none">
            {rightIcon}
          </div>
        )}
      </div>
      {error && <p className="text-xs text-red-400">{error}</p>}
    </div>
  );
}
