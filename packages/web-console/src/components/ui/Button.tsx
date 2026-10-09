import { ReactNode } from 'react';
import { cva, type VariantProps } from 'class-variance-authority';

const buttonVariants = cva(
  'inline-flex items-center justify-center rounded-md font-medium transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.98]',
  {
    variants: {
      variant: {
        primary: 'bg-primary-600 text-white hover:bg-primary-700 hover:shadow-lg hover:shadow-primary-500/20 focus:ring-primary-500 border border-transparent',
        secondary: 'bg-dashboard-card text-dashboard-text hover:bg-dashboard-muted hover:border-dashboard-text-secondary border border-dashboard-border focus:ring-primary-500',
        danger: 'bg-red-600 text-white hover:bg-red-700 hover:shadow-lg hover:shadow-red-500/20 focus:ring-red-500 border border-transparent',
        ghost: 'bg-transparent hover:bg-dashboard-muted text-dashboard-text-secondary hover:text-dashboard-text',
        outline: 'bg-transparent border border-dashboard-border text-dashboard-text hover:bg-dashboard-card hover:border-dashboard-text-secondary',
      },
      size: {
        xs: 'px-2 py-1 text-xs',
        sm: 'px-3 py-1.5 text-xs',
        md: 'px-4 py-2 text-sm',
        lg: 'px-6 py-3 text-base',
        xl: 'px-8 py-4 text-lg',
      },
    },
    defaultVariants: {
      variant: 'primary',
      size: 'md',
    },
  }
);

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  children: ReactNode;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
}

export function Button({ 
  children, 
  variant, 
  size, 
  leftIcon,
  rightIcon,
  className = '', 
  ...props 
}: ButtonProps) {
  return (
    <button
      className={`${buttonVariants({ variant, size, className })}`}
      {...props}
    >
      {leftIcon && <span className="mr-2">{leftIcon}</span>}
      {children}
      {rightIcon && <span className="ml-2">{rightIcon}</span>}
    </button>
  );
}
