export type BugCategory = "launcher" | "web" | "other";
export type BugStatus = "new" | "reviewing" | "resolved";

export type BugAttachment = {
  name: string;
  content_type: string;
  size_bytes: number;
  data_url: string;
};

export type BugReportPayload = {
  category: BugCategory;
  title: string;
  what_tried: string;
  expected_result: string;
  actual_result: string;
  error_text?: string | null;
  browser?: string | null;
  windows_version?: string | null;
  gpu?: string | null;
  contact_email?: string | null;
  support_bundle_json?: string | object | null;
  attachments_json?: BugAttachment[] | null;
  origin?: string | null;
  app_version?: string | null;
};

export type BugReportListItem = {
  id: number;
  created_at: string;
  category: BugCategory;
  status: BugStatus;
  title: string;
  browser?: string | null;
  windows_version?: string | null;
  gpu?: string | null;
  origin?: string | null;
  app_version?: string | null;
  attachments_count?: number;
};

export type BugReportDetail = BugReportListItem & {
  what_tried: string;
  expected_result: string;
  actual_result: string;
  error_text?: string | null;
  contact_email?: string | null;
  support_bundle_json?: unknown;
  attachments_json?: BugAttachment[] | null;
};

export class SupportApiError extends Error {
  status: number;
  code: string;

  constructor(message: string, status: number, code: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

const parseError = (payload: unknown, status: number): SupportApiError => {
  if (
    payload &&
    typeof payload === "object" &&
    "error" in payload &&
    payload.error &&
    typeof payload.error === "object"
  ) {
    const errorObj = payload.error as Record<string, unknown>;
    const code = typeof errorObj.code === "string" ? errorObj.code : "UNKNOWN_ERROR";
    const message = typeof errorObj.message === "string" ? errorObj.message : `HTTP ${status}`;
    return new SupportApiError(message, status, code);
  }
  return new SupportApiError(`HTTP ${status}`, status, "UNKNOWN_ERROR");
};

const requestJson = async <T>(url: string, init?: RequestInit): Promise<T> => {
  const response = await fetch(url, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    ...init,
  });
  const text = await response.text();
  const payload = text ? JSON.parse(text) : null;
  if (!response.ok) {
    throw parseError(payload, response.status);
  }
  return payload as T;
};

export const supportApi = {
  submitBugReport(payload: BugReportPayload): Promise<{ bug_report: { id: number; created_at: string; status: BugStatus } }> {
    return requestJson("/api/bug-reports", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  login(password: string): Promise<{ status: string }> {
    return requestJson("/api/admin/login", {
      method: "POST",
      body: JSON.stringify({ password }),
    });
  },

  logout(): Promise<{ status: string }> {
    return requestJson("/api/admin/logout", { method: "POST", body: "{}" });
  },

  session(): Promise<{ authenticated: boolean }> {
    return requestJson("/api/admin/session");
  },

  listBugReports(filters: {
    category?: BugCategory | "all";
    status?: BugStatus | "all";
    limit?: number;
    offset?: number;
  }): Promise<{ bug_reports: BugReportListItem[] }> {
    const params = new URLSearchParams();
    if (filters.category && filters.category !== "all") params.set("category", filters.category);
    if (filters.status && filters.status !== "all") params.set("status", filters.status);
    if (typeof filters.limit === "number") params.set("limit", String(filters.limit));
    if (typeof filters.offset === "number") params.set("offset", String(filters.offset));
    return requestJson(`/api/admin/bug-reports?${params.toString()}`);
  },

  bugReport(id: number): Promise<{ bug_report: BugReportDetail }> {
    return requestJson(`/api/admin/bug-reports/${id}`);
  },

  updateBugStatus(id: number, status: BugStatus): Promise<{ bug_report: { id: number; status: BugStatus } }> {
    return requestJson(`/api/admin/bug-reports/${id}/status`, {
      method: "POST",
      body: JSON.stringify({ status }),
    });
  },
};
