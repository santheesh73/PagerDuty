import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import { renderWithProviders } from '../test-utils';
import { EscalationPolicies } from './EscalationPolicies';
import * as escalationApi from '../api/escalationPolicies';
import * as userApi from '../api/users';
import { EscalationPolicy } from '../types/escalation';
import { Team, User } from '../types/user';

const mockTeams: Team[] = [
  { id: 1, name: 'SRE Team', slug: 'sre-team', is_active: true, description: '', member_count: 4, created_at: '', updated_at: '' },
];

const mockUsers: User[] = [
  { id: 5, username: 'charlie', name: 'Charlie Dave', email: 'charlie@example.com', first_name: 'Charlie', last_name: 'Dave', is_active: true, is_staff: false, date_joined: '' },
];

const mockPolicies: EscalationPolicy[] = [
  {
    id: 1,
    name: 'Production Critical',
    slug: 'prod-critical',
    team: 1,
    team_name: 'SRE Team',
    is_active: true,
    levels: [
      {
        id: 10,
        policy: 1,
        order: 1,
        target_type: 'CURRENT_ON_CALL',
        target_user: null,
        target_username: null,
        wait_minutes: 5,
        created_at: '',
        updated_at: '',
      },
      {
        id: 20,
        policy: 1,
        order: 2,
        target_type: 'USER',
        target_user: 5,
        target_username: 'charlie',
        wait_minutes: 15,
        created_at: '',
        updated_at: '',
      },
    ],
    created_at: '',
    updated_at: '',
  },
];

describe('EscalationPolicies Page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(escalationApi, 'getEscalationPolicies').mockResolvedValue(mockPolicies);
    vi.spyOn(userApi, 'getTeams').mockResolvedValue(mockTeams);
    vi.spyOn(userApi, 'getUsers').mockResolvedValue(mockUsers);
  });

  it('renders escalation policies and step sequencing', async () => {
    renderWithProviders(<EscalationPolicies />);

    expect(screen.getByRole('heading', { level: 1, name: 'Escalation Policies' })).toBeInTheDocument();
    expect(await screen.findByTestId('policy-item-1')).toBeInTheDocument();

    // Verify step 1: Current On-Call Responder
    expect(screen.getByText('Step 1')).toBeInTheDocument();
    expect(screen.getByText('Current On-Call Responder')).toBeInTheDocument();
    expect(screen.getByText('5 min')).toBeInTheDocument();

    // Verify step 2: Designated User Charlie
    expect(screen.getByText('Step 2')).toBeInTheDocument();
    expect(screen.getByText(/User: charlie/i)).toBeInTheDocument();
    expect(screen.getByText('15 min')).toBeInTheDocument();

  });

  it('reorders escalation levels when Move Down / Move Up clicked', async () => {
    const reorderSpy = vi
      .spyOn(escalationApi, 'reorderEscalationLevels')
      .mockResolvedValue(mockPolicies[0]);

    renderWithProviders(<EscalationPolicies />);
    await screen.findByTestId('policy-item-1');

    // Click Move Down on Step 1
    const moveDownBtn = screen.getByLabelText('Move Step 1 down');
    fireEvent.click(moveDownBtn);

    await waitFor(() => {
      expect(reorderSpy).toHaveBeenCalledWith(1, [20, 10]);
    });
  });

  it('opens level modal and submits new level', async () => {
    const createLevelSpy = vi.spyOn(escalationApi, 'createEscalationLevel').mockResolvedValue({
      id: 30,
      policy: 1,
      order: 3,
      target_type: 'CURRENT_ON_CALL',
      target_user: null,
      target_username: null,
      wait_minutes: 20,
      created_at: '',
      updated_at: '',
    });

    renderWithProviders(<EscalationPolicies />);
    await screen.findByTestId('policy-item-1');


    // Click Add Escalation Step
    fireEvent.click(screen.getByRole('button', { name: /Add Escalation Step/i }));

    expect(screen.getByRole('heading', { level: 2, name: /Add Step 3 to Escalation Path/i })).toBeInTheDocument();

    // Submit
    fireEvent.click(screen.getByRole('button', { name: 'Add Step 3' }));

    await waitFor(() => {
      expect(createLevelSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          policy: 1,
          order: 3,
          target_type: 'CURRENT_ON_CALL',
        })
      );
    });
  });
});
