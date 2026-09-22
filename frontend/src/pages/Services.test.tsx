import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import { renderWithProviders } from '../test-utils';
import { Services } from './Services';
import * as serviceApi from '../api/services';
import * as userApi from '../api/users';
import * as escalationApi from '../api/escalationPolicies';
import { Service } from '../types/service';
import { Team } from '../types/user';
import { EscalationPolicy } from '../types/escalation';

const mockTeams: Team[] = [
  { id: 1, name: 'SRE Team', slug: 'sre-team', is_active: true, description: '', member_count: 5, created_at: '', updated_at: '' },
  { id: 2, name: 'Backend Team', slug: 'backend-team', is_active: true, description: '', member_count: 8, created_at: '', updated_at: '' },
];

const mockPolicies: EscalationPolicy[] = [
  { id: 10, name: 'Production High-Severity', slug: 'prod-high', team: 1, team_name: 'SRE Team', is_active: true, levels: [], created_at: '', updated_at: '' },
];

const mockServices: Service[] = [
  {
    id: 1,
    name: 'Auth Gateway',
    slug: 'auth-gateway',
    description: 'Authentication and token exchange microservice',
    status: 'HEALTHY',
    team: { id: 1, name: 'SRE Team', slug: 'sre-team', is_active: true },
    escalation_policy: { id: 10, name: 'Production High-Severity', slug: 'prod-high' },
    is_active: true,
    created_at: '2026-09-21T00:00:00Z',
    updated_at: '2026-09-21T00:00:00Z',
  },
  {
    id: 2,
    name: 'Billing API',
    slug: 'billing-api',
    description: 'Stripe webhook processor',
    status: 'DEGRADED',
    team: { id: 2, name: 'Backend Team', slug: 'backend-team', is_active: true },
    escalation_policy: null,
    is_active: false,
    created_at: '2026-09-21T00:00:00Z',
    updated_at: '2026-09-21T00:00:00Z',
  },
];

describe('Services Catalog Page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(serviceApi, 'getServices').mockResolvedValue(mockServices);
    vi.spyOn(userApi, 'getTeams').mockResolvedValue(mockTeams);
    vi.spyOn(escalationApi, 'getEscalationPolicies').mockResolvedValue(mockPolicies);
  });

  it('renders service table with status, team, and escalation policy', async () => {
    renderWithProviders(<Services />);

    expect(screen.getByRole('heading', { level: 1, name: 'Services' })).toBeInTheDocument();
    expect(await screen.findByText('Auth Gateway')).toBeInTheDocument();
    expect(screen.getByText('auth-gateway')).toBeInTheDocument();
    expect(screen.getByText('Healthy')).toBeInTheDocument();
    expect(screen.getByText('Production High-Severity')).toBeInTheDocument();

    expect(screen.getByText('Billing API')).toBeInTheDocument();
    expect(screen.getByText('Degraded')).toBeInTheDocument();
    expect(screen.getByText('Inactive')).toBeInTheDocument();
  });

  it('filters services based on search text', async () => {
    renderWithProviders(<Services />);

    expect(await screen.findByText('Auth Gateway')).toBeInTheDocument();
    expect(screen.getByText('Billing API')).toBeInTheDocument();

    const searchInput = screen.getByPlaceholderText(/Search by name, slug, or description/i);
    fireEvent.change(searchInput, { target: { value: 'stripe' } });

    expect(screen.queryByText('Auth Gateway')).not.toBeInTheDocument();
    expect(screen.getByText('Billing API')).toBeInTheDocument();
  });

  it('opens create modal and invokes createService API', async () => {
    const createSpy = vi.spyOn(serviceApi, 'createService').mockResolvedValue({
      id: 3,
      name: 'Search Indexer',
      slug: 'search-indexer',
      description: 'Elasticsearch cluster feed',
      status: 'HEALTHY',
      team: { id: 1, name: 'SRE Team', slug: 'sre-team', is_active: true },
      escalation_policy: null,
      is_active: true,
      created_at: '',
      updated_at: '',
    });

    renderWithProviders(<Services />);
    await screen.findByText('Auth Gateway');

    // Click Create Service button
    fireEvent.click(screen.getByRole('button', { name: /Create Service/i }));

    expect(screen.getByRole('heading', { level: 2, name: 'Create New Service' })).toBeInTheDocument();

    // Fill form
    const nameInput = screen.getByLabelText(/Service Name/i);
    fireEvent.change(nameInput, { target: { value: 'Search Indexer' } });

    // Submit
    fireEvent.click(screen.getByTestId('service-form-submit'));


    await waitFor(() => {
      expect(createSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'Search Indexer',
          slug: 'search-indexer',
          team_id: 1,
        })
      );
    });
  });

  it('opens edit modal with existing values', async () => {
    renderWithProviders(<Services />);
    await screen.findByText('Auth Gateway');

    const editBtn = screen.getByRole('button', { name: /Edit Auth Gateway/i });
    fireEvent.click(editBtn);

    expect(screen.getByRole('heading', { level: 2, name: 'Edit Auth Gateway' })).toBeInTheDocument();
    expect(screen.getByLabelText(/Service Name/i)).toHaveValue('Auth Gateway');
  });

});
