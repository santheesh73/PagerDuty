import React, { useState } from 'react';
import { Plus } from 'lucide-react';

import {
  CreateEscalationLevelInput,
  CreateEscalationPolicyInput,
  EscalationPolicy,
  UpdateEscalationPolicyInput,
} from '../types/escalation';
import {
  useCreateEscalationLevel,
  useCreateEscalationPolicy,
  useDeleteEscalationLevel,
  useEscalationPolicies,
  useReorderEscalationLevels,
  useUpdateEscalationPolicy,
} from '../hooks/useEscalationPolicies';
import { useTeams, useUsers } from '../hooks/useTeams';
import { PageHeader } from '../components/shared/PageHeader';
import { Button } from '../components/shared/Button';
import { LoadingState } from '../components/shared/LoadingState';
import { ErrorState } from '../components/shared/ErrorState';
import { EmptyState } from '../components/shared/EmptyState';
import { PolicyList } from '../components/escalation/PolicyList';
import { PolicyDetail } from '../components/escalation/PolicyDetail';
import { PolicyModal } from '../components/escalation/PolicyModal';
import { LevelModal } from '../components/escalation/LevelModal';

export const EscalationPolicies: React.FC = () => {
  const [selectedPolicyId, setSelectedPolicyId] = useState<number | null>(null);
  const [policyModalOpen, setPolicyModalOpen] = useState(false);
  const [editingPolicy, setEditingPolicy] = useState<EscalationPolicy | null>(null);
  const [levelModalOpen, setLevelModalOpen] = useState(false);

  // Queries
  const {
    data: policies = [],
    isLoading: policiesLoading,
    isError,
    error,
    refetch,
  } = useEscalationPolicies();
  const { data: teams = [] } = useTeams();
  const { data: users = [] } = useUsers();

  // Pick first policy by default
  const effectivePolicyId = selectedPolicyId ?? (policies[0]?.id ?? null);
  const activePolicy = policies.find((p) => p.id === effectivePolicyId) || null;

  // Mutations
  const createPolicyMutation = useCreateEscalationPolicy();
  const updatePolicyMutation = useUpdateEscalationPolicy();
  const createLevelMutation = useCreateEscalationLevel(effectivePolicyId ?? 0);
  const deleteLevelMutation = useDeleteEscalationLevel(effectivePolicyId ?? 0);
  const reorderLevelsMutation = useReorderEscalationLevels(effectivePolicyId ?? 0);


  const handleOpenCreatePolicy = () => {
    setEditingPolicy(null);
    setPolicyModalOpen(true);
  };

  const handleOpenEditPolicy = () => {
    setEditingPolicy(activePolicy);
    setPolicyModalOpen(true);
  };

  const handleCreatePolicy = async (data: CreateEscalationPolicyInput) => {
    const created = await createPolicyMutation.mutateAsync(data);
    setSelectedPolicyId(created.id);
  };

  const handleUpdatePolicy = async (id: number, data: UpdateEscalationPolicyInput) => {
    await updatePolicyMutation.mutateAsync({ id, data });
  };

  const handleAddLevel = async (data: CreateEscalationLevelInput) => {
    await createLevelMutation.mutateAsync(data);
  };

  const handleDeleteLevel = async (levelId: number) => {
    if (window.confirm('Are you sure you want to delete this escalation step?')) {
      await deleteLevelMutation.mutateAsync(levelId);
    }
  };

  const handleReorderLevels = async (levelIds: number[]) => {
    await reorderLevelsMutation.mutateAsync(levelIds);
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Escalation Policies"
        description="Multi-tier incident escalation paths, delay timers, and responder fallbacks."
        actions={
          <Button variant="primary" onClick={handleOpenCreatePolicy}>
            <Plus className="w-4 h-4 mr-1.5" />
            New Policy
          </Button>
        }
      />

      {policiesLoading ? (
        <LoadingState message="Loading escalation policies..." />
      ) : isError ? (
        <ErrorState
          title="Failed to load escalation policies"
          message={error instanceof Error ? error.message : 'Unknown error occurred.'}
          onRetry={() => refetch()}
        />
      ) : policies.length === 0 ? (
        <EmptyState
          title="No escalation policies found"
          description="Create an escalation policy to define how alerts notify responders."
          action={
            <Button variant="primary" onClick={handleOpenCreatePolicy}>
              <Plus className="w-4 h-4 mr-1.5" />
              Create First Policy
            </Button>
          }
        />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left Column: Policy List */}
          <div className="lg:col-span-1">
            <PolicyList
              policies={policies}
              selectedPolicyId={effectivePolicyId}
              onSelectPolicy={(id) => setSelectedPolicyId(id)}
              onCreatePolicy={handleOpenCreatePolicy}
            />

          </div>

          {/* Right Column: Policy Detail & Level Sequencer */}
          <div className="lg:col-span-2">
            {activePolicy ? (
              <PolicyDetail
                policy={activePolicy}
                onEditPolicy={handleOpenEditPolicy}
                onAddLevel={() => setLevelModalOpen(true)}
                onDeleteLevel={handleDeleteLevel}
                onReorderLevels={handleReorderLevels}
                isReordering={reorderLevelsMutation.isPending}
              />
            ) : (
              <div className="p-12 text-center text-slate-500 bg-slate-900 rounded-xl border border-slate-800">
                Select an escalation policy from the list to view and manage its path.
              </div>
            )}
          </div>
        </div>
      )}

      {/* Policy Create / Edit Modal */}
      <PolicyModal
        isOpen={policyModalOpen}
        onClose={() => {
          setPolicyModalOpen(false);
          setEditingPolicy(null);
        }}
        policy={editingPolicy}
        teams={teams}
        onSubmitCreate={handleCreatePolicy}
        onSubmitUpdate={handleUpdatePolicy}
        isLoading={createPolicyMutation.isPending || updatePolicyMutation.isPending}
      />

      {/* Level Add Modal */}
      {activePolicy && (
        <LevelModal
          isOpen={levelModalOpen}
          onClose={() => setLevelModalOpen(false)}
          policyId={activePolicy.id}
          nextOrder={(activePolicy.levels?.length ?? 0) + 1}
          users={users}
          onSubmit={handleAddLevel}
          isLoading={createLevelMutation.isPending}
        />
      )}
    </div>
  );
};
