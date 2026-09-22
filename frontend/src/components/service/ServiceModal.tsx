import React, { useState, useEffect } from 'react';
import { CreateServiceInput, Service, ServiceStatus, UpdateServiceInput } from '../../types/service';
import { Team } from '../../types/user';
import { EscalationPolicy } from '../../types/escalation';
import { ApiError } from '../../types/api';
import { Modal } from '../shared/Modal';
import { Button } from '../shared/Button';

export interface ServiceModalProps {
  isOpen: boolean;
  onClose: () => void;
  service?: Service | null;
  teams: Team[];
  escalationPolicies: EscalationPolicy[];
  onSubmitCreate: (data: CreateServiceInput) => Promise<void>;
  onSubmitUpdate: (id: number, data: UpdateServiceInput) => Promise<void>;
  isLoading?: boolean;
}

export const ServiceModal: React.FC<ServiceModalProps> = ({
  isOpen,
  onClose,
  service,
  teams,
  escalationPolicies,
  onSubmitCreate,
  onSubmitUpdate,
  isLoading = false,
}) => {
  const isEditing = Boolean(service);

  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [description, setDescription] = useState('');
  const [teamId, setTeamId] = useState<number | ''>('');
  const [escalationPolicyId, setEscalationPolicyId] = useState<number | ''>('');
  const [status, setStatus] = useState<ServiceStatus>('HEALTHY');
  const [isActive, setIsActive] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  useEffect(() => {
    if (service) {
      setName(service.name);
      setSlug(service.slug);
      setDescription(service.description || '');
      setTeamId(service.team?.id ?? '');
      setEscalationPolicyId(service.escalation_policy?.id ?? '');
      setStatus(service.status);
      setIsActive(service.is_active);
    } else {
      setName('');
      setSlug('');
      setDescription('');
      setTeamId(teams.length > 0 ? teams[0].id : '');
      setEscalationPolicyId('');
      setStatus('HEALTHY');
      setIsActive(true);
    }
    setError(null);
    setFieldErrors({});
  }, [service, isOpen, teams]);

  const handleNameChange = (val: string) => {
    setName(val);
    if (!isEditing) {
      const generatedSlug = val
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/(^-|-$)/g, '');
      setSlug(generatedSlug);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setFieldErrors({});

    if (!name.trim()) {
      setError('Service name is required.');
      return;
    }
    if (!slug.trim()) {
      setError('Slug is required.');
      return;
    }
    if (!teamId) {
      setError('Please select an owning team.');
      return;
    }

    try {
      if (isEditing && service) {
        await onSubmitUpdate(service.id, {
          name: name.trim(),
          slug: slug.trim(),
          description: description.trim(),
          team_id: Number(teamId),
          escalation_policy_id: escalationPolicyId ? Number(escalationPolicyId) : null,
          status,
          is_active: isActive,
        });
      } else {
        await onSubmitCreate({
          name: name.trim(),
          slug: slug.trim(),
          description: description.trim(),
          team_id: Number(teamId),
          escalation_policy_id: escalationPolicyId ? Number(escalationPolicyId) : null,
          status,
          is_active: isActive,
        });
      }
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
            : 'Failed to save service. Please try again.';
        setError(message);
      }
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={isEditing ? `Edit ${service?.name}` : 'Create New Service'}
      subtitle="Define operational services monitored by the platform."
      maxWidth="lg"
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
          <label htmlFor="service-name" className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5">
            Service Name <span className="text-rose-400">*</span>
          </label>
          <input
            id="service-name"
            type="text"
            required
            value={name}
            onChange={(e) => handleNameChange(e.target.value)}
            placeholder="e.g. Payments Gateway"
            className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
          />
          {fieldErrors.name && (
            <p className="mt-1 text-xs text-rose-400 font-medium">{fieldErrors.name[0]}</p>
          )}
        </div>

        <div>
          <label htmlFor="service-slug" className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5">
            Service Identifier (Slug) <span className="text-rose-400">*</span>
          </label>
          <input
            id="service-slug"
            type="text"
            required
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            placeholder="e.g. payments-gateway"
            className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-100 font-mono placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
          />
          {fieldErrors.slug && (
            <p className="mt-1 text-xs text-rose-400 font-medium">{fieldErrors.slug[0]}</p>
          )}
        </div>

        <div>
          <label htmlFor="service-desc" className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5">
            Description
          </label>
          <textarea
            id="service-desc"
            rows={2}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Operational purpose and service dependencies..."
            className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent resize-none"
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label htmlFor="service-team" className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5">
              Owning Team <span className="text-rose-400">*</span>
            </label>
            <select
              id="service-team"
              required
              value={teamId}
              onChange={(e) => setTeamId(e.target.value ? Number(e.target.value) : '')}
              className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="" disabled>Select a team...</option>
              {teams.map((team) => (
                <option key={team.id} value={team.id}>
                  {team.name}
                </option>
              ))}
            </select>
            {fieldErrors.team_id && (
              <p className="mt-1 text-xs text-rose-400 font-medium">{fieldErrors.team_id[0]}</p>
            )}
            {fieldErrors.team && (
              <p className="mt-1 text-xs text-rose-400 font-medium">{fieldErrors.team[0]}</p>
            )}
          </div>

          <div>
            <label htmlFor="service-policy" className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5">
              Escalation Policy
            </label>
            <select
              id="service-policy"
              value={escalationPolicyId}
              onChange={(e) => setEscalationPolicyId(e.target.value ? Number(e.target.value) : '')}
              className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="">No explicit policy (Default)</option>
              {escalationPolicies.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-1">
          <div>
            <label htmlFor="service-status" className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5">
              Current Status
            </label>
            <select
              id="service-status"
              value={status}
              onChange={(e) => setStatus(e.target.value as ServiceStatus)}
              className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="HEALTHY">HEALTHY</option>
              <option value="DEGRADED">DEGRADED</option>
              <option value="DOWN">DOWN</option>
              <option value="MAINTENANCE">MAINTENANCE</option>
            </select>
          </div>

          <div className="flex items-center pt-6">
            <label className="relative flex items-center gap-2.5 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={isActive}
                onChange={(e) => setIsActive(e.target.checked)}
                className="w-4 h-4 rounded border-slate-700 bg-slate-800 text-indigo-600 focus:ring-indigo-500 focus:ring-offset-slate-950"
              />
              <span className="text-sm font-medium text-slate-200">Active Service</span>
            </label>
          </div>
        </div>

        <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-800">
          <Button type="button" variant="outline" onClick={onClose} disabled={isLoading}>
            Cancel
          </Button>
          <Button
            type="submit"
            variant="primary"
            isLoading={isLoading}
            data-testid="service-form-submit"
          >
            {isEditing ? 'Save Changes' : 'Create Service'}
          </Button>

        </div>
      </form>
    </Modal>
  );
};
