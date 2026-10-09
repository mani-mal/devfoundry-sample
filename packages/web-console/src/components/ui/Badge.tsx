import { ReactNode } from 'react';
import { cva, type VariantProps } from 'class-variance-authority';

const badgeVariants = cva(
  'inline-flex items-center justify-center px-2.5 py-0.5 rounded-full text-xs font-medium transition-all duration-200',
  {
    variants: {
      variant: {
        default: 'bg-dashboard-muted text-white',
        primary: 'bg-primary-500/20 text-primary-300 border border-primary-500/30',
        secondary: 'bg-dashboard-card text-dashboard-text border border-dashboard-border',
        success: 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30',
        warning: 'bg-amber-500/20 text-amber-300 border border-amber-500/30',
        danger: 'bg-red-500/20 text-red-300 border border-red-500/30',
        info: 'bg-blue-500/20 text-blue-300 border border-blue-500/30',
        outline: 'border border-dashboard-border text-dashboard-text bg-transparent',
        ghost: 'bg-transparent text-dashboard-muted hover:bg-dashboard-muted/50',
      },
      size: {
        xs: 'px-1.5 py-0.5 text-[10px]',
        sm: 'px-2 py-0.5 text-xs',
        md: 'px-2.5 py-0.5 text-xs',
        lg: 'px-3 py-1 text-sm',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'md',
    },
  }
);

interface BadgeProps extends VariantProps<typeof badgeVariants> {
  children: ReactNode;
  className?: string;
  icon?: ReactNode;
}

export function Badge({ children, variant, size, className = '', icon }: BadgeProps) {
  return (
    <span className={`${badgeVariants({ variant, size, className })}`}>
      {icon && <span className="mr-1.5">{icon}</span>}
      {children}
    </span>
  );
}

export function TaskBadge({ phase }: { phase: string }) {
  const phaseColors: Record<string, VariantProps<typeof badgeVariants>['variant']> = {
    Submitted: 'default',
    Qualified: 'primary',
    Running: 'primary',
    Validating: 'info',
    AwaitingReview: 'warning',
    Completed: 'success',
    Failed: 'danger',
    Cancelled: 'default',
    Paused: 'warning',
  };

  return (
    <Badge variant={phaseColors[phase] || 'default'}>
      {phase}
    </Badge>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const statusColors: Record<string, VariantProps<typeof badgeVariants>['variant']> = {
    Pending: 'warning',
    InProgress: 'primary',
    Completed: 'success',
    Failed: 'danger',
    Cancelled: 'default',
  };

  return (
    <Badge variant={statusColors[status] || 'default'}>
      {status}
    </Badge>
  );
}
