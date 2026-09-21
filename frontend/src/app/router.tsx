import React from 'react';
import { Routes, Route } from 'react-router-dom';
import { AppLayout } from '../components/layout/AppLayout';
import {
  Dashboard,
  Incidents,
  IncidentDetail,
  Services,
  OnCallSchedule,
  EscalationPolicies,
  Analytics,
  NotFound,
  StatusPage,
} from '../pages';

export const AppRoutes: React.FC = () => {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<Dashboard />} />
        <Route path="incidents" element={<Incidents />} />
        <Route path="incidents/:incidentId" element={<IncidentDetail />} />
        <Route path="services" element={<Services />} />
        <Route path="on-call" element={<OnCallSchedule />} />
        <Route path="escalation-policies" element={<EscalationPolicies />} />
        <Route path="analytics" element={<Analytics />} />
        <Route path="status" element={<StatusPage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
};
