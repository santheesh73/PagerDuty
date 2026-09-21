import React from 'react';
import { Loader2 } from 'lucide-react';
import { cn } from '../../lib/cn';

export interface LoadingStateProps {
  message?: string;
  className?: string;
}

export const LoadingState: React.FC<LoadingStateProps> = ({
  message = 'Loading...',
  className,
}) => {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        'flex flex-col items-center justify-center py-12 px-4 text-center space-y-3',
        className
      )}
    >
      <Loader2 className="w-8 h-8 text-indigo-500 animate-spin" aria-hidden="true" />
      <p className="text-sm font-medium text-slate-400">{message}</p>
    </div>
  );
};
