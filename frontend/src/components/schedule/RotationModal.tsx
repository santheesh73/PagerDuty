import React, { useState, useEffect } from 'react';
import { CreateRotationInput } from '../../types/schedule';
import { User } from '../../types/user';
import { ApiError } from '../../types/api';
import { Modal } from '../shared/Modal';
import { Button } from '../shared/Button';

export interface RotationModalProps {
  isOpen: boolean;
  onClose: () => void;
  scheduleId: number;
  initialIsOverride?: boolean;
  users: User[];
  onSubmit: (data: CreateRotationInput) => Promise<void>;
  isLoading?: boolean;
}

export const RotationModal: React.FC<RotationModalProps> = ({
  isOpen,
  onClose,
  scheduleId,
  initialIsOverride = false,
  users,
  onSubmit,
  isLoading = false,
}) => {
  const [userId, setUserId] = useState<number | ''>('');
  const [startTime, setStartTime] = useState('');
  const [endTime, setEndTime] = useState('');
  const [isOverride, setIsOverride] = useState(initialIsOverride);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  useEffect(() => {
    setIsOverride(initialIsOverride);
    if (isOpen) {
      setUserId(users.length > 0 ? users[0].id : '');
      const now = new Date();
      const inOneHour = new Date(now.getTime() + 60 * 60 * 1000);
      const inOneDay = new Date(now.getTime() + 24 * 60 * 60 * 1000);

      const toLocalISO = (d: Date) => {
        const offset = d.getTimezoneOffset() * 60000;
        return new Date(d.getTime() - offset).toISOString().slice(0, 16);
      };

      setStartTime(toLocalISO(inOneHour));
      setEndTime(toLocalISO(inOneDay));
      setError(null);
      setFieldErrors({});
    }
  }, [isOpen, initialIsOverride, users]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setFieldErrors({});

    if (!userId) {
      setError('Please select an assigned user.');
      return;
    }
    if (!startTime || !endTime) {
      setError('Start time and end time are required.');
      return;
    }

    const startDate = new Date(startTime);
    const endDate = new Date(endTime);

    if (endDate <= startDate) {
      setError('End time must be strictly after start time.');
      return;
    }

    try {
      await onSubmit({
        schedule_id: scheduleId,
        user_id: Number(userId),
        start_time: startDate.toISOString(),
        end_time: endDate.toISOString(),
        is_override: isOverride,
      });
      onClose();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.fieldErrors && Object.keys(err.fieldErrors).length > 0) {
          setFieldErrors(err.fieldErrors);
        }
        if (!err.fieldErrors || Object.keys(err.fieldErrors).length === 0 || err.fieldErrors.non_field_errors) {
          setError(err.message);
        }
      } else {
        const message =
          err instanceof Error
            ? err.message
            : typeof err === 'object' && err !== null && 'detail' in err
            ? String((err as { detail: unknown }).detail)
            : 'Failed to create schedule shift. Please check input parameters.';
        setError(message);
      }
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={isOverride ? 'Schedule Temporary Override' : 'Add Rotation Shift'}
      subtitle={
        isOverride
          ? 'Overrides take absolute priority over base rotations for their active window.'
          : 'Assign a baseline on-call rotation window for a responder.'
      }
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
          <label
            htmlFor="rotation-user"
            className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5"
          >
            Assigned Responder <span className="text-rose-400">*</span>
          </label>
          <select
            id="rotation-user"
            required
            value={userId}
            onChange={(e) => setUserId(e.target.value ? Number(e.target.value) : '')}
            className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="" disabled>Select responder...</option>
            {users.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name || u.username} (@{u.username})
              </option>
            ))}
          </select>
          {fieldErrors.user_id && (
            <p className="mt-1 text-xs text-rose-400 font-medium">{fieldErrors.user_id[0]}</p>
          )}
          {fieldErrors.user && (
            <p className="mt-1 text-xs text-rose-400 font-medium">{fieldErrors.user[0]}</p>
          )}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label
              htmlFor="rotation-start"
              className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5"
            >
              Start Time <span className="text-rose-400">*</span>
            </label>
            <input
              id="rotation-start"
              type="datetime-local"
              required
              value={startTime}
              onChange={(e) => setStartTime(e.target.value)}
              className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
            {fieldErrors.start_time && (
              <p className="mt-1 text-xs text-rose-400 font-medium">{fieldErrors.start_time[0]}</p>
            )}
          </div>

          <div>
            <label
              htmlFor="rotation-end"
              className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5"
            >
              End Time <span className="text-rose-400">*</span>
            </label>
            <input
              id="rotation-end"
              type="datetime-local"
              required
              value={endTime}
              onChange={(e) => setEndTime(e.target.value)}
              className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
            {fieldErrors.end_time && (
              <p className="mt-1 text-xs text-rose-400 font-medium">{fieldErrors.end_time[0]}</p>
            )}
          </div>
        </div>

        <div className="pt-2">
          <label className="relative flex items-center gap-2.5 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={isOverride}
              onChange={(e) => setIsOverride(e.target.checked)}
              className="w-4 h-4 rounded border-slate-700 bg-slate-800 text-indigo-600 focus:ring-indigo-500 focus:ring-offset-slate-950"
            />
            <div>
              <span className="text-sm font-medium text-slate-200">
                Mark as Manual Override
              </span>
              <p className="text-xs text-slate-400">
                Override shifts take precedence over all baseline rotations.
              </p>
            </div>
          </label>
        </div>

        <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-800">
          <Button type="button" variant="outline" onClick={onClose} disabled={isLoading}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" isLoading={isLoading}>
            {isOverride ? 'Create Override' : 'Create Shift'}
          </Button>
        </div>
      </form>
    </Modal>
  );
};
