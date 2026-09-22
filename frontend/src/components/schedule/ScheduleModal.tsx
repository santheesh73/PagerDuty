import React, { useState, useEffect } from 'react';
import { CreateScheduleInput } from '../../types/schedule';
import { Team } from '../../types/user';
import { Modal } from '../shared/Modal';
import { Button } from '../shared/Button';

export interface ScheduleModalProps {
  isOpen: boolean;
  onClose: () => void;
  teams: Team[];
  onSubmit: (data: CreateScheduleInput) => Promise<void>;
  isLoading?: boolean;
}

const commonTimezones = [
  'UTC',
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'Europe/London',
  'Europe/Paris',
  'Europe/Berlin',
  'Asia/Kolkata',
  'Asia/Singapore',
  'Asia/Tokyo',
  'Australia/Sydney',
];

export const ScheduleModal: React.FC<ScheduleModalProps> = ({
  isOpen,
  onClose,
  teams,
  onSubmit,
  isLoading = false,
}) => {
  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [teamId, setTeamId] = useState<number | ''>('');
  const [timezone, setTimezone] = useState('UTC');
  const [isPrimary, setIsPrimary] = useState(false);
  const [isActive, setIsActive] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      setName('');
      setSlug('');
      setTeamId(teams.length > 0 ? teams[0].id : '');
      setTimezone('UTC');
      setIsPrimary(false);
      setIsActive(true);
      setError(null);
    }
  }, [isOpen, teams]);

  const handleNameChange = (val: string) => {
    setName(val);
    const genSlug = val
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/(^-|-$)/g, '');
    setSlug(genSlug);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!name.trim()) {
      setError('Schedule name is required.');
      return;
    }
    if (!slug.trim()) {
      setError('Schedule slug is required.');
      return;
    }
    if (!teamId) {
      setError('Please select an owning team.');
      return;
    }

    try {
      await onSubmit({
        name: name.trim(),
        slug: slug.trim(),
        team_id: Number(teamId),
        timezone,
        is_primary: isPrimary,
        is_active: isActive,
      });
      onClose();
    } catch (err: unknown) {
      const message =
        err instanceof Error
          ? err.message
          : typeof err === 'object' && err !== null && 'detail' in err
          ? String((err as { detail: unknown }).detail)
          : 'Failed to create schedule. Please check input.';
      setError(message);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Create On-Call Schedule"
      subtitle="Define a new operational rotation calendar for your team."
      maxWidth="md"
    >
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        {error && (
          <div
            role="alert"
            className="p-3 text-xs rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-400 font-medium"
          >
            {error}
          </div>
        )}

        <div>
          <label htmlFor="schedule-name" className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5">
            Schedule Name <span className="text-rose-400">*</span>
          </label>
          <input
            id="schedule-name"
            type="text"
            required
            value={name}
            onChange={(e) => handleNameChange(e.target.value)}
            placeholder="e.g. SRE Primary Tier-1"
            className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>

        <div>
          <label htmlFor="schedule-slug" className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5">
            Identifier (Slug) <span className="text-rose-400">*</span>
          </label>
          <input
            id="schedule-slug"
            type="text"
            required
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            placeholder="e.g. sre-primary-tier-1"
            className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-100 font-mono placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label htmlFor="schedule-team" className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5">
              Owning Team <span className="text-rose-400">*</span>
            </label>
            <select
              id="schedule-team"
              required
              value={teamId}
              onChange={(e) => setTeamId(e.target.value ? Number(e.target.value) : '')}
              className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="" disabled>Select team...</option>
              {teams.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="schedule-tz" className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5">
              Timezone
            </label>
            <select
              id="schedule-tz"
              value={timezone}
              onChange={(e) => setTimezone(e.target.value)}
              className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              {commonTimezones.map((tz) => (
                <option key={tz} value={tz}>
                  {tz}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="space-y-2 pt-2">
          <label className="relative flex items-center gap-2.5 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={isPrimary}
              onChange={(e) => setIsPrimary(e.target.checked)}
              className="w-4 h-4 rounded border-slate-700 bg-slate-800 text-indigo-600 focus:ring-indigo-500 focus:ring-offset-slate-950"
            />
            <span className="text-sm font-medium text-slate-200">
              Set as Team's Primary Schedule
            </span>
          </label>

          <label className="relative flex items-center gap-2.5 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={isActive}
              onChange={(e) => setIsActive(e.target.checked)}
              className="w-4 h-4 rounded border-slate-700 bg-slate-800 text-indigo-600 focus:ring-indigo-500 focus:ring-offset-slate-950"
            />
            <span className="text-sm font-medium text-slate-200">Active Schedule</span>
          </label>
        </div>

        <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-800">
          <Button type="button" variant="outline" onClick={onClose} disabled={isLoading}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" isLoading={isLoading}>
            Create Schedule
          </Button>
        </div>
      </form>
    </Modal>
  );
};
