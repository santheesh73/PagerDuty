import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '../../test-utils';
import { Sidebar } from './Sidebar';

describe('Sidebar Navigation', () => {
  it('renders all required platform navigation links', () => {
    renderWithProviders(<Sidebar />, { route: '/' });

    const nav = screen.getByRole('navigation', { name: 'Main Navigation' });
    expect(nav).toBeInTheDocument();

    const expectedItems = [
      { name: 'Dashboard', href: '/' },
      { name: 'Incidents', href: '/incidents' },
      { name: 'Services', href: '/services' },
      { name: 'On-call', href: '/on-call' },
      { name: 'Escalation Policies', href: '/escalation-policies' },
      { name: 'Analytics', href: '/analytics' },
    ];

    for (const item of expectedItems) {
      const link = screen.getByRole('link', { name: item.name });
      expect(link).toBeInTheDocument();
      expect(link).toHaveAttribute('href', item.href);
    }
  });

  it('displays brand header and platform status info', () => {
    renderWithProviders(<Sidebar />, { route: '/' });

    expect(screen.getByText('IncidentPlatform')).toBeInTheDocument();
    expect(screen.getByText('Core Workbench')).toBeInTheDocument();
    expect(screen.getByText(/Phase 6/i)).toBeInTheDocument();
  });
});
