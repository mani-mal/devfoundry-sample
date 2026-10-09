import { ReactNode } from 'react';
import { cva, type VariantProps } from 'class-variance-authority';

const cardVariants = cva(
  'bg-dashboard-card border border-dashboard-border rounded-xl shadow-sm transition-all duration-200',
  {
    variants: {
      variant: {
        default: '',
        elevated: 'hover:shadow-lg hover:shadow-primary-500/10 border-primary-500/20',
        outline: 'border-dashed',
        ghost: 'border-transparent shadow-none bg-dashboard-card/50',
      },
      padding: {
        none: '',
        sm: 'p-4',
        DEFAULT: 'p-6',
        lg: 'p-8',
      },
    },
    defaultVariants: {
      variant: 'default',
      padding: 'DEFAULT',
    },
  }
);

const cardHeaderVariants = cva('px-6 py-4 border-b border-dashboard-border', {
  variants: {
    variant: {
      default: '',
      divider: 'border-dashed',
    },
  },
  defaultVariants: {
    variant: 'default',
  },
});

const cardContentVariants = cva('', {
  variants: {
    variant: {
      compact: 'p-4',
      DEFAULT: 'p-6',
      spacious: 'p-8',
    },
  },
  defaultVariants: {
    variant: 'DEFAULT',
  },
});

interface CardProps extends VariantProps<typeof cardVariants> {
  children: ReactNode;
  className?: string;
  title?: string;
  description?: string;
  action?: ReactNode;
  headerVariant?: VariantProps<typeof cardHeaderVariants>['variant'];
}

export function Card({ 
  children, 
  className = '', 
  title, 
  description, 
  action,
  variant,
  padding,
  headerVariant = 'default',
}: CardProps) {
  return (
    <div className={`${cardVariants({ variant, padding, className })}`}>
      {(title || description || action) && (
        <div className={`${cardHeaderVariants({ variant: headerVariant })}`}>
          <div className="flex items-start justify-between">
            <div className="flex-1">
              {title && <h3 className="text-lg font-semibold text-dashboard-text">{title}</h3>}
              {description && <p className="mt-1 text-sm text-dashboard-muted">{description}</p>}
            </div>
            {action && <div className="ml-4">{action}</div>}
          </div>
        </div>
      )}
      <div className={`${cardContentVariants({ variant: padding === 'none' ? 'DEFAULT' : padding === 'sm' ? 'compact' : padding === 'lg' ? 'spacious' : 'DEFAULT' })} ${!padding ? 'p-6' : ''}`}>
        {children}
      </div>
    </div>
  );
}

export function CardHeader({ 
  children, 
  className = '' 
}: { 
  children: ReactNode; 
  className?: string;
}) {
  return (
    <div className={`${cardHeaderVariants()} ${className}`}>
      {children}
    </div>
  );
}

export function CardContent({ 
  children, 
  className = '' 
}: { 
  children: ReactNode; 
  className?: string;
}) {
  return (
    <div className={`p-6 ${className}`}>
      {children}
    </div>
  );
}

export function CardFooter({ 
  children, 
  className = '' 
}: { 
  children: ReactNode; 
  className?: string;
}) {
  return (
    <div className="px-6 py-4 border-t border-dashboard-border bg-dashboard-card/50 rounded-b-xl">
      {children}
    </div>
  );
}

export function CardTitle({ children }: { children: ReactNode }) {
  return <h3 className="text-lg font-semibold text-dashboard-text">{children}</h3>;
}

export function CardDescription({ children }: { children: ReactNode }) {
  return <p className="mt-1 text-sm text-dashboard-muted">{children}</p>;
}

export function CardActions({ children }: { children: ReactNode }) {
  return <div className="flex items-center justify-end gap-2">{children}</div>;
}
