export type SessionActivityItem = {
  id: string;
  title: string;
  status: "pending" | "in_progress" | "completed";
};

export type SessionActivity = {
  list_type?: string | null;
  headline?: string | null;
  items: SessionActivityItem[];
};

const STATUS_LABELS: Record<SessionActivityItem["status"], string> = {
  pending: "待开始",
  in_progress: "进行中",
  completed: "已完成",
};

export function activityStatusLabel(status: string): string {
  if (status in STATUS_LABELS) {
    return STATUS_LABELS[status as SessionActivityItem["status"]];
  }
  return status;
}
