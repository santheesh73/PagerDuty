import React, { useState, useEffect } from 'react';
import { CreateEscalationLevelInput, EscalationTargetType } from '../../types/escalation';
import { User } from '../../types/user';
import { ApiError } from '../../types/api';
import { Modal } from '../shared/Modal';
import { Button } from '../shared/Button';

export interface LevelModalProps {
  isOpen: boolean;
  onClose: () => void;
  policyId: number;
  nextOrder: number;
  users: User[];
  onSubmit: (data: CreateEscalationLevelInput) => Promise<void>;
  isLoading?: boolean;
}

export const LevelModal: React.FC<LevelModalProps> = ({
  isOpen,
  onClose,
  policyId,
  nextOrder,
  users,
  onSubmit,
  isLoading = false,
}) => {
  const [targetType, setTargetType] = useState<EscalationTargetType>('CURRENT_ON_CALL');
  const [targetUser, setTargetUser] = useState<number | ''>('');
  const [waitMinutes, setWaitMinutes] = useState<number>(15);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  useEffect(() => {
    if (isOpen) {
      setTargetType('CURRENT_ON_CALL');
      setTargetUser(users.length > 0 ? users[0].id : '');
      setWaitMinutes(15);
      setError(null);
      setFieldErrors({});
    }
  }, [isOpen, users]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setFieldErrors({});

    if (targetType === 'USER' && !targetUser) {
      setError('Please select a target user for direct escalation.');
      return;
    }

    if (waitMinutes < 0) {
      setError('Wait minutes must be greater than or equal to 0.');
      return;
    }

    try {
      await onSubmit({
        policy: policyId,
        order: nextOrder,
        target_type: targetType,
        target_user: targetType === 'USER' && targetUser ? Number(targetUser) : null,
        wait_minutes: Number(waitMinutes),
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
            : 'Failed to add escalation step.';
        setError(message);
      }
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={`Add Step ${nextOrder} to Escalation Path`}
      subtitle="Determine which responder is notified and how long to wait before escalating."
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
          <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5">
            Target Type <span className="text-rose-400">*</span>
          </label>
          <div className="grid grid-cols-2 gap-3">
            <button
              type="button"
              onClick={() => setTargetType('CURRENT_ON_CALL')}
              className={`p-3 rounded-lg border text-left transition-colors ${
                targetType === 'CURRENT_ON_CALL'
                  ? 'bg-indigo-600/20 border-indigo-500 text-white'
                  : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-slate-200'
              }`}
            >
              <div className="font-semibold text-sm">Current On-Call</div>
              <p className="text-xs text-slate-400 mt-0.5">
                Dynamic rotation lookup from schedule.
              </p>
            </button>

            <button
              type="button"
              onClick={() => setTargetType('USER')}
              className={`p-3 rounded-lg border text-left transition-colors ${
                targetType === 'USER'
                  ? 'bg-indigo-600/20 border-indigo-500 text-white'
                  : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-slate-200'
              }`}
            >
              <div className="font-semibold text-sm">Designated User</div>
              <p className="text-xs text-slate-400 mt-0.5">
                Always notify a specific team member.
              </p>
            </button>
          </div>
        </div>

        {targetType === 'USER' && (
          <div>
            <label
              htmlFor="step-user"
              className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5"
            >
              Designated User <span className="text-rose-400">*</span>
            </label>
            <select
              id="step-user"
              required
              value={targetUser}
              onChange={(e) => setTargetUser(e.target.value ? Number(e.target.value) : '')}
              className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="" disabled>Select target user...</option>
              {users.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.name || u.username} (@{u.username})
                </option>
              ))}
            </select>
            {fieldErrors.target_user && (
              <p className="mt-1 text-xs text-rose-400 font-medium">{fieldErrors.target_user[0]}</p>
            )}
          </div>
        )}

        <div>
          <label
            htmlFor="step-wait"
            className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5"
          >
            Escalation Timeout (Minutes) <span className="text-rose-400">*</span>
          </label>
          <input
            id="step-wait"
            type="number"
            min="0"
            required
            value={waitMinutes}
            onChange={(e) => setWaitMinutes(Number(e.target.value))}
            placeholder="15"
            className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
          {fieldErrors.wait_minutes && (
            <p className="mt-1 text-xs text-rose-400 font-medium">{fieldErrors.wait_minutes[0]}</p>
          )}
          <p className="text-xs text-slate-500 mt-1">
            Minutes the engine waits before advancing to Step {nextOrder + 1} if unacknowledged.
          </p>
        </div>

        <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-800">
          <Button type="button" variant="outline" onClick={onClose} disabled={isLoading}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" isLoading={isLoading}>
            Add Step {nextOrder}
          </Button>
        </div>
      </form>
    </Modal>
  );
};
