import { TextareaHTMLAttributes } from 'react';
import { cva, type VariantProps } from 'class-variance-authority';

const textareaVariants = cva(
  'block w-full rounded-lg border bg-dashboard-card px-3 py-2 text-sm text-dashboard-text shadow-sm placeholder:text-dashboard-muted transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 min-h-[100px] resize-y',
  {
    variants: {
      variant: {
        default: 'border-dashboard-border focus:border-primary-500 focus:ring-primary-500/20 focus:ring-offset-dashboard-bg',
        outline: 'border-dashboard-border focus:border-primary-500 focus:ring-primary-500/20 focus:ring-offset-dashboard-bg',
        ghost: 'border-transparent hover:border-dashboard-border focus:border-primary-500 focus:bg-dashboard-card focus:ring-primary-500/20 focus:ring-offset-dashboard-bg',
      },
      size: {
        sm: 'px-3 py-1.5 text-xs',
        md: 'px-3 py-2 text-sm',
        lg: 'px-4 py-3 text-base',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'md',
    },
  }
);

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement>, VariantProps<typeof textareaVariants> {
  label?: string;
  error?: string;
  rows?: number;
  containerClassName?: string;
}

export function Textarea({ 
  label, 
  error, 
  variant,
  size,
  rows = 4,
  className = '',
  containerClassName = '',
  ...props 
}: TextareaProps) {
  return (
    <div className={`space-y-1.5 ${containerClassName}`}>
      {label && (
        <label className="block text-sm font-medium text-dashboard-text-secondary">
          {label}
        </label>
      )}
      <textarea
        className={textareaVariants({ variant, size, className })}
        rows={rows}
        {...props}
      />
      {error && <p className="text-xs text-red-400">{error}</p>}
    </div>
  );
}
