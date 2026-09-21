import React from 'react';
import { cn } from '../../lib/cn';

export interface PageContainerProps {
  children: React.ReactNode;
  className?: string;
}

export const PageContainer: React.FC<PageContainerProps> = ({ children, className }) => {
  return (
    <main
      className={cn(
        'flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6',
        className
      )}
    >
      {children}
    </main>
  );
};
