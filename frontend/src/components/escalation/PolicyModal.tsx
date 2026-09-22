import React, { useState, useEffect } from 'react';
import { CreateEscalationPolicyInput, EscalationPolicy, UpdateEscalationPolicyInput } from '../../types/escalation';
import { Team } from '../../types/user';
import { Modal } from '../shared/Modal';
import { Button } from '../shared/Button';

export interface PolicyModalProps {
  isOpen: boolean;
  onClose: () => void;
  policy?: EscalationPolicy | null;
  teams: Team[];
  onSubmitCreate: (data: CreateEscalationPolicyInput) => Promise<void>;
  onSubmitUpdate: (id: number, data: UpdateEscalationPolicyInput) => Promise<void>;
  isLoading?: boolean;
}

export const PolicyModal: React.FC<PolicyModalProps> = ({
  isOpen,
  onClose,
  policy,
  teams,
  onSubmitCreate,
  onSubmitUpdate,
  isLoading = false,
}) => {
  const isEditing = Boolean(policy);

  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [teamId, setTeamId] = useState<number | ''>('');
  const [isActive, setIsActive] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (policy) {
      setName(policy.name);
      setSlug(policy.slug);
      setTeamId(policy.team);
      setIsActive(policy.is_active);
    } else {
      setName('');
      setSlug('');
      setTeamId(teams.length > 0 ? teams[0].id : '');
      setIsActive(true);
    }
    setError(null);
  }, [policy, isOpen, teams]);

  const handleNameChange = (val: string) => {
    setName(val);
    if (!isEditing) {
      const genSlug = val
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/(^-|-$)/g, '');
      setSlug(genSlug);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!name.trim()) {
      setError('Policy name is required.');
      return;
    }
    if (!slug.trim()) {
      setError('Policy slug is required.');
      return;
    }
    if (!teamId) {
      setError('Please select an owning team.');
      return;
    }

    try {
      if (isEditing && policy) {
        await onSubmitUpdate(policy.id, {
          name: name.trim(),
          slug: slug.trim(),
          team: Number(teamId),
          is_active: isActive,
        });
      } else {
        await onSubmitCreate({
          name: name.trim(),
          slug: slug.trim(),
          team: Number(teamId),
          is_active: isActive,
        });
      }
      onClose();
    } catch (err: unknown) {
      const message =
        err instanceof Error
          ? err.message
          : typeof err === 'object' && err !== null && 'detail' in err
          ? String((err as { detail: unknown }).detail)
          : 'Failed to save escalation policy.';
      setError(message);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={isEditing ? `Edit ${policy?.name}` : 'Create Escalation Policy'}
      subtitle="Define incident escalation targets and step transitions."
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
          <label htmlFor="policy-name" className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5">
            Policy Name <span className="text-rose-400">*</span>
          </label>
          <input
            id="policy-name"
            type="text"
            required
            value={name}
            onChange={(e) => handleNameChange(e.target.value)}
            placeholder="e.g. Production Default Escalation"
            className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>

        <div>
          <label htmlFor="policy-slug" className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5">
            Identifier (Slug) <span className="text-rose-400">*</span>
          </label>
          <input
            id="policy-slug"
            type="text"
            required
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            placeholder="e.g. production-default-escalation"
            className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-100 font-mono placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>

        <div>
          <label htmlFor="policy-team" className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5">
            Owning Team <span className="text-rose-400">*</span>
          </label>
          <select
            id="policy-team"
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

        <div className="pt-2">
          <label className="relative flex items-center gap-2.5 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={isActive}
              onChange={(e) => setIsActive(e.target.checked)}
              className="w-4 h-4 rounded border-slate-700 bg-slate-800 text-indigo-600 focus:ring-indigo-500 focus:ring-offset-slate-950"
            />
            <span className="text-sm font-medium text-slate-200">Active Policy</span>
          </label>
        </div>

        <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-800">
          <Button type="button" variant="outline" onClick={onClose} disabled={isLoading}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" isLoading={isLoading}>
            {isEditing ? 'Save Changes' : 'Create Policy'}
          </Button>
        </div>
      </form>
    </Modal>
  );
};
