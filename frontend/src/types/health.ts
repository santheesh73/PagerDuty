export interface HealthDependencies {
  database?: string;
  redis?: string;
  [key: string]: string | undefined;
}

export interface HealthResponse {
  status: 'ok' | 'degraded' | string;
  dependencies?: HealthDependencies;
}
