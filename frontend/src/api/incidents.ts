import { apiClient } from './client';
import { Incident, IncidentEvent } from '../types/incident';

export interface IncidentFilters {
  status?: string;
  service?: number;
  severity?: string;
  active?: boolean;
}

export const getIncidents = async (filters?: IncidentFilters): Promise<Incident[]> => {
  return apiClient.get<Incident[]>('/incidents/', { params: filters as Record<string, string | number | boolean> });
};

export const getIncident = async (id: number): Promise<Incident> => {
  return apiClient.get<Incident>(`/incidents/${id}/`);
};

export const getIncidentEvents = async (id: number): Promise<IncidentEvent[]> => {
  return apiClient.get<IncidentEvent[]>(`/incidents/${id}/events/`);
};

export const acknowledgeIncident = async (id: number): Promise<Incident> => {
  return apiClient.post<Incident>(`/incidents/${id}/acknowledge/`);
};

export const resolveIncident = async (id: number): Promise<Incident> => {
  return apiClient.post<Incident>(`/incidents/${id}/resolve/`);
};

export const reopenIncident = async (id: number): Promise<Incident> => {
  return apiClient.post<Incident>(`/incidents/${id}/reopen/`);
};
