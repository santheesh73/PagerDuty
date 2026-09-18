import React, { useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { StatusPage } from './pages/StatusPage';

export interface AppProps {
  client?: QueryClient;
}

const createDefaultQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        refetchOnWindowFocus: false,
      },
    },
  });

export const App: React.FC<AppProps> = ({ client }) => {
  const [queryClient] = useState(() => client || createDefaultQueryClient());

  return (
    <QueryClientProvider client={queryClient}>
      <StatusPage />
    </QueryClientProvider>
  );
};

export default App;
