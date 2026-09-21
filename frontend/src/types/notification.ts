export type NotificationStatus = 'PENDING' | 'SENT' | 'FAILED';

export type NotificationChannel = 'EMAIL';

export interface Notification {
  id: number;
  incident: number;
  incident_title: string;
  recipient: number;
  recipient_username: string;
  recipient_email: string;
  channel: NotificationChannel;
  status: NotificationStatus;
  escalation_level: number | null;
  escalation_level_order: number | null;
  dedupe_key: string;
  attempt_count: number;
  sent_at: string | null;
  failed_at: string | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
}
