import React, { useMemo, useState } from 'react';
import { Plus, Search, Filter } from 'lucide-react';
import { CreateServiceInput, Service, UpdateServiceInput } from '../types/service';

import { useCreateService, useServices, useUpdateService } from '../hooks/useServices';
import { useTeams } from '../hooks/useTeams';
import { useEscalationPolicies } from '../hooks/useEscalationPolicies';
import { PageHeader } from '../components/shared/PageHeader';
import { Button } from '../components/shared/Button';
import { LoadingState } from '../components/shared/LoadingState';
import { ErrorState } from '../components/shared/ErrorState';
import { ServiceTable } from '../components/service/ServiceTable';
import { ServiceModal } from '../components/service/ServiceModal';

export const Services: React.FC = () => {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedTeam, setSelectedTeam] = useState<string>('');
  const [selectedStatus, setSelectedStatus] = useState<string>('');
  const [selectedActive, setSelectedActive] = useState<string>('all');

  const [modalOpen, setModalOpen] = useState(false);
  const [editingService, setEditingService] = useState<Service | null>(null);

  // Queries
  const { data: services, isLoading, isError, error, refetch } = useServices();
  const { data: teams = [] } = useTeams();
  const { data: policies = [] } = useEscalationPolicies();

  // Mutations
  const createMutation = useCreateService();
  const updateMutation = useUpdateService();

  const filteredServices = useMemo(() => {
    if (!services) return [];
    return services.filter((srv) => {
      // Search term filter
      if (searchTerm.trim()) {
        const query = searchTerm.toLowerCase();
        const matchesName = srv.name.toLowerCase().includes(query);
        const matchesSlug = srv.slug.toLowerCase().includes(query);
        const matchesDesc = srv.description?.toLowerCase().includes(query) ?? false;
        if (!matchesName && !matchesSlug && !matchesDesc) return false;
      }

      // Team filter
      if (selectedTeam && srv.team?.id !== Number(selectedTeam)) {
        return false;
      }

      // Status filter
      if (selectedStatus && srv.status !== selectedStatus) {
        return false;
      }

      // Active filter
      if (selectedActive === 'active' && !srv.is_active) return false;
      if (selectedActive === 'inactive' && srv.is_active) return false;

      return true;
    });
  }, [services, searchTerm, selectedTeam, selectedStatus, selectedActive]);

  const handleOpenCreate = () => {
    setEditingService(null);
    setModalOpen(true);
  };

  const handleOpenEdit = (srv: Service) => {
    setEditingService(srv);
    setModalOpen(true);
  };

  const handleCloseModal = () => {
    setModalOpen(false);
    setEditingService(null);
  };

  const handleCreateService = async (data: CreateServiceInput) => {
    await createMutation.mutateAsync(data);
  };

  const handleUpdateService = async (id: number, data: UpdateServiceInput) => {
    await updateMutation.mutateAsync({ id, data });
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Services"
        description="Service catalog, team ownership, and escalation policy mapping."
        actions={
          <Button variant="primary" onClick={handleOpenCreate}>
            <Plus className="w-4 h-4 mr-1.5" />
            Create Service
          </Button>
        }
      />

      {/* Filter Bar */}
      <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 p-4 rounded-xl bg-slate-900 border border-slate-800">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-500" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search by name, slug, or description..."
            className="w-full pl-9 pr-4 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <div className="flex items-center gap-1.5 text-xs text-slate-400">
            <Filter className="w-3.5 h-3.5" />
            <span>Filters:</span>
          </div>

          <select
            value={selectedTeam}
            onChange={(e) => setSelectedTeam(e.target.value)}
            aria-label="Filter by Team"
            className="px-2.5 py-1.5 bg-slate-800 border border-slate-700 rounded-lg text-xs text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="">All Teams</option>
            {teams.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>

          <select
            value={selectedStatus}
            onChange={(e) => setSelectedStatus(e.target.value)}
            aria-label="Filter by Status"
            className="px-2.5 py-1.5 bg-slate-800 border border-slate-700 rounded-lg text-xs text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="">All Statuses</option>
            <option value="HEALTHY">HEALTHY</option>
            <option value="DEGRADED">DEGRADED</option>
            <option value="DOWN">DOWN</option>
            <option value="MAINTENANCE">MAINTENANCE</option>
          </select>

          <select
            value={selectedActive}
            onChange={(e) => setSelectedActive(e.target.value)}
            aria-label="Filter by Active State"
            className="px-2.5 py-1.5 bg-slate-800 border border-slate-700 rounded-lg text-xs text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="all">All States</option>
            <option value="active">Active Only</option>
            <option value="inactive">Inactive Only</option>
          </select>
        </div>
      </div>

      {/* Main Content */}
      {isLoading ? (
        <LoadingState message="Loading service catalog..." />
      ) : isError ? (
        <ErrorState
          title="Failed to load services"
          message={error instanceof Error ? error.message : 'Unknown error occurred.'}
          onRetry={() => refetch()}
        />
      ) : (
        <ServiceTable services={filteredServices} onEdit={handleOpenEdit} />
      )}

      {/* Create / Edit Modal */}
      <ServiceModal
        isOpen={modalOpen}
        onClose={handleCloseModal}
        service={editingService}
        teams={teams}
        escalationPolicies={policies}
        onSubmitCreate={handleCreateService}
        onSubmitUpdate={handleUpdateService}
        isLoading={createMutation.isPending || updateMutation.isPending}
      />
    </div>
  );
};
