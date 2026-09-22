import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent, waitFor } from '@testing-library/react';

import { renderWithProviders } from '../test-utils';
import { OnCallSchedule } from './OnCallSchedule';
import * as scheduleApi from '../api/schedules';
import * as userApi from '../api/users';
import { OnCallResponse, Schedule, ScheduleRotation } from '../types/schedule';
import { Team, User } from '../types/user';

const mockTeams: Team[] = [
  { id: 1, name: 'SRE Team', slug: 'sre-team', is_active: true, description: '', member_count: 5, created_at: '', updated_at: '' },
];

const mockUsers: User[] = [
  { id: 10, username: 'alice', name: 'Alice Smith', email: 'alice@example.com', first_name: 'Alice', last_name: 'Smith', is_active: true, is_staff: false, date_joined: '' },
  { id: 20, username: 'bob', name: 'Bob Jones', email: 'bob@example.com', first_name: 'Bob', last_name: 'Jones', is_active: true, is_staff: false, date_joined: '' },
  { id: 30, username: 'charlie', name: 'Charlie Dave', email: 'charlie@example.com', first_name: 'Charlie', last_name: 'Dave', is_active: true, is_staff: false, date_joined: '' },
];

const mockSchedules: Schedule[] = [
  {
    id: 1,
    name: 'SRE Primary Rotation',
    slug: 'sre-primary',
    timezone: 'UTC',
    team: { id: 1, name: 'SRE Team', slug: 'sre-team', is_active: true },
    is_primary: true,
    is_active: true,
    created_at: '',
    updated_at: '',
  },
  {
    id: 2,
    name: 'SRE Secondary Rotation',
    slug: 'sre-secondary',
    timezone: 'America/New_York',
    team: { id: 1, name: 'SRE Team', slug: 'sre-team', is_active: true },
    is_primary: false,
    is_active: true,
    created_at: '',
    updated_at: '',
  },
];

const mockRotations: ScheduleRotation[] = [
  {
    id: 101,
    schedule: { id: 1, name: 'SRE Primary Rotation', slug: 'sre-primary', timezone: 'UTC', is_primary: true, is_active: true },
    user: { id: 10, username: 'alice', name: 'Alice Smith', email: 'alice@example.com' },
    start_time: '2026-09-21T00:00:00Z',
    end_time: '2026-09-28T00:00:00Z',
    is_override: false,
    created_at: '',
    updated_at: '',
  },
  {
    id: 102,
    schedule: { id: 1, name: 'SRE Primary Rotation', slug: 'sre-primary', timezone: 'UTC', is_primary: true, is_active: true },
    user: { id: 30, username: 'charlie', name: 'Charlie Dave', email: 'charlie@example.com' },
    start_time: '2026-09-21T08:00:00Z',
    end_time: '2026-09-21T16:00:00Z',
    is_override: true,
    created_at: '',
    updated_at: '',
  },
];

// Backend returns Bob Jones (override) proving the UI uses backend authoritative response,
// even though base shift in rotation list is assigned to Alice Smith!
const mockOnCallBobOverride: OnCallResponse = {
  schedule_id: 1,
  at: '2026-09-21T10:00:00Z',
  user: { id: 20, username: 'bob', name: 'Bob Jones' },
  source: 'OVERRIDE',
};

describe('OnCallSchedule Page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(scheduleApi, 'getSchedules').mockResolvedValue(mockSchedules);
    vi.spyOn(scheduleApi, 'getScheduleRotations').mockResolvedValue(mockRotations);
    vi.spyOn(scheduleApi, 'getCurrentOnCall').mockResolvedValue(mockOnCallBobOverride);
    vi.spyOn(userApi, 'getTeams').mockResolvedValue(mockTeams);
    vi.spyOn(userApi, 'getUsers').mockResolvedValue(mockUsers);
  });

  it('renders authoritative backend on-call responder and differentiates override source', async () => {
    renderWithProviders(<OnCallSchedule />);

    expect(screen.getByRole('heading', { level: 1, name: 'On-Call Schedules' })).toBeInTheDocument();

    // The authoritative card MUST display Bob Jones from backend on-call API
    // (even though base rotation is Alice Smith)
    expect(await screen.findByText('Bob Jones')).toBeInTheDocument();
    expect(screen.getByText('@bob')).toBeInTheDocument();
    expect(screen.getByText('Active Override')).toBeInTheDocument();
    expect(screen.getByText('Polled every 30s')).toBeInTheDocument();
  });

  it('shows shifts with clear distinction between Base Shift and Override', async () => {
    renderWithProviders(<OnCallSchedule />);

    await screen.findByText('Bob Jones');

    // Rotations should be rendered in the rotation list
    expect(screen.getByText('Alice Smith')).toBeInTheDocument();
    expect(screen.getByText('Charlie Dave')).toBeInTheDocument();
    expect(screen.getByText('Base Shift')).toBeInTheDocument();
    expect(screen.getByText('Override')).toBeInTheDocument();
  });

  it('allows switching active schedule via schedule dropdown', async () => {
    renderWithProviders(<OnCallSchedule />);

    await screen.findByText('Bob Jones');

    const select = screen.getByLabelText(/Active Schedule:/i);
    fireEvent.change(select, { target: { value: '2' } });

    await waitFor(() => {
      expect(scheduleApi.getCurrentOnCall).toHaveBeenCalledWith(2, undefined);
    });
  });

  it('handles delete rotation action', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    const deleteSpy = vi.spyOn(scheduleApi, 'deleteScheduleRotation').mockResolvedValue();

    renderWithProviders(<OnCallSchedule />);
    await screen.findByText('Bob Jones');

    const deleteBtns = screen.getAllByLabelText(/Delete shift/i);
    fireEvent.click(deleteBtns[0]);

    await waitFor(() => {
      expect(deleteSpy).toHaveBeenCalledWith(101);
    });
  });
});
