import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import { ErrorBoundary } from '../components/shared/ErrorBoundary';
import { createDefaultQueryClient } from './queryClient';

export interface AppProvidersProps {
  children: React.ReactNode;
  queryClient?: QueryClient;
}

export const AppProviders: React.FC<AppProvidersProps> = ({
  children,
  queryClient,
}) => {
  const [client] = React.useState(() => queryClient || createDefaultQueryClient());

  return (
    <ErrorBoundary>
      <QueryClientProvider client={client}>
        <BrowserRouter>{children}</BrowserRouter>
      </QueryClientProvider>
    </ErrorBoundary>
  );
};
