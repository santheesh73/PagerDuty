import React from 'react';
import { QueryClient } from '@tanstack/react-query';
import { AppProviders } from './app/providers';
import { AppRoutes } from './app/router';

export interface AppProps {
  client?: QueryClient;
}

export const App: React.FC<AppProps> = ({ client }) => {
  return (
    <AppProviders queryClient={client}>
      <AppRoutes />
    </AppProviders>
  );
};

export default App;
