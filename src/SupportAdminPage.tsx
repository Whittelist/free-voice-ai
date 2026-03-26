import { useEffect, useMemo, useState, type FormEvent } from "react";
import { ArrowLeft, CheckCircle2, LogIn, LogOut, RefreshCw } from "lucide-react";
import type { BugAttachment, BugCategory, BugReportDetail, BugReportListItem, BugStatus } from "./supportApi";
import { SupportApiError, supportApi } from "./supportApi";

type AuthState = "checking" | "logged_out" | "logged_in";

const CATEGORY_OPTIONS: Array<{ value: BugCategory | "all"; label: string }> = [
  { value: "all", label: "Todas" },
  { value: "launcher", label: "Launcher" },
  { value: "web", label: "Web" },
  { value: "other", label: "Other" },
];

const STATUS_OPTIONS: Array<{ value: BugStatus | "all"; label: string }> = [
  { value: "all", label: "Todos" },
  { value: "new", label: "New" },
  { value: "reviewing", label: "Reviewing" },
  { value: "resolved", label: "Resolved" },
];

const statusClass = (status: BugStatus) => {
  if (status === "resolved") return "status-ready";
  if (status === "reviewing") return "status-downloading";
  return "status-stopped";
};

function SupportAdminPage() {
  const [authState, setAuthState] = useState<AuthState>("checking");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [categoryFilter, setCategoryFilter] = useState<BugCategory | "all">("all");
  const [statusFilter, setStatusFilter] = useState<BugStatus | "all">("all");
  const [reports, setReports] = useState<BugReportListItem[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [selectedReport, setSelectedReport] = useState<BugReportDetail | null>(null);
  const [isLoadingList, setIsLoadingList] = useState(false);
  const [isUpdatingStatus, setIsUpdatingStatus] = useState(false);

  const selectedStatus = selectedReport?.status ?? "new";

  const selectedReportPrettyBundle = useMemo(() => {
    if (!selectedReport?.support_bundle_json) return "";
    try {
      return JSON.stringify(selectedReport.support_bundle_json, null, 2);
    } catch {
      return String(selectedReport.support_bundle_json);
    }
  }, [selectedReport]);

  const selectedAttachments = useMemo((): BugAttachment[] => {
    const raw = selectedReport?.attachments_json;
    if (!Array.isArray(raw)) return [];
    return raw
      .filter((item) => item && typeof item === "object")
      .map((item) => {
        const cast = item as Partial<BugAttachment>;
        return {
          name: typeof cast.name === "string" ? cast.name : "attachment",
          content_type: typeof cast.content_type === "string" ? cast.content_type : "application/octet-stream",
          size_bytes: typeof cast.size_bytes === "number" ? cast.size_bytes : 0,
          data_url: typeof cast.data_url === "string" ? cast.data_url : "",
        };
      })
      .filter((item) => item.data_url.startsWith("data:"));
  }, [selectedReport]);

  const loadList = async () => {
    setError(null);
    setIsLoadingList(true);
    try {
      const result = await supportApi.listBugReports({
        category: categoryFilter,
        status: statusFilter,
        limit: 100,
      });
      setReports(result.bug_reports);
      if (result.bug_reports.length === 0) {
        setSelectedId(null);
        setSelectedReport(null);
      } else if (!selectedId || !result.bug_reports.some((item) => item.id === selectedId)) {
        setSelectedId(result.bug_reports[0].id);
      }
    } catch (apiError) {
      if (apiError instanceof SupportApiError && apiError.status === 401) {
        setAuthState("logged_out");
      }
      setError(apiError instanceof Error ? apiError.message : "No se pudo cargar la lista.");
    } finally {
      setIsLoadingList(false);
    }
  };

  const loadDetail = async (id: number) => {
    setError(null);
    try {
      const result = await supportApi.bugReport(id);
      setSelectedReport(result.bug_report);
      setSelectedId(id);
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : "No se pudo cargar el detalle.");
    }
  };

  const checkSession = async () => {
    try {
      await supportApi.session();
      setAuthState("logged_in");
    } catch {
      setAuthState("logged_out");
    }
  };

  useEffect(() => {
    void checkSession();
  }, []);

  useEffect(() => {
    if (authState !== "logged_in") return;
    void loadList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authState, categoryFilter, statusFilter]);

  useEffect(() => {
    if (authState !== "logged_in" || !selectedId) return;
    void loadDetail(selectedId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authState, selectedId]);

  const login = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    try {
      await supportApi.login(password);
      setPassword("");
      setAuthState("logged_in");
    } catch (apiError) {
      if (apiError instanceof SupportApiError) {
        setError(`${apiError.code}: ${apiError.message}`);
      } else {
        setError("No se pudo iniciar sesion.");
      }
    }
  };

  const logout = async () => {
    await supportApi.logout();
    setAuthState("logged_out");
    setSelectedId(null);
    setSelectedReport(null);
    setReports([]);
  };

  const changeStatus = async (status: BugStatus) => {
    if (!selectedReport) return;
    setIsUpdatingStatus(true);
    setError(null);
    try {
      await supportApi.updateBugStatus(selectedReport.id, status);
      setSelectedReport((prev) => (prev ? { ...prev, status } : prev));
      setReports((prev) => prev.map((item) => (item.id === selectedReport.id ? { ...item, status } : item)));
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : "No se pudo actualizar estado.");
    } finally {
      setIsUpdatingStatus(false);
    }
  };

  if (authState === "checking") {
    return (
      <div className="app-container">
        <main className="glass-card">
          <div className="status-text">Comprobando sesion admin...</div>
        </main>
      </div>
    );
  }

  if (authState === "logged_out") {
    return (
      <div className="app-container">
        <header>
          <h1>Support Admin</h1>
          <p>Acceso privado con password unica por entorno.</p>
        </header>
        <main className="glass-card">
          <a className="btn-secondary support-back" href="/">
            <ArrowLeft size={14} /> Volver a la app
          </a>

          <form className="support-form" onSubmit={(event) => void login(event)}>
            <div className="control-group">
              <label htmlFor="admin-password">Password admin</label>
              <input
                id="admin-password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="BUG_REPORTS_ADMIN_PASSWORD"
                required
              />
            </div>
            {error ? <div className="support-error">{error}</div> : null}
            <button className="btn-primary" type="submit">
              <LogIn size={16} /> Entrar al panel
            </button>
          </form>
        </main>
      </div>
    );
  }

  return (
    <div className="app-container support-admin-layout">
      <header>
        <h1>Support Admin</h1>
        <p>Tickets de launcher/web/otros en Railway Postgres.</p>
      </header>

      <main className="glass-card">
        <div className="engine-actions">
          <a className="btn-secondary" href="/">
            <ArrowLeft size={14} /> App
          </a>
          <button className="btn-secondary" type="button" onClick={() => void loadList()} disabled={isLoadingList}>
            <RefreshCw size={14} /> Recargar
          </button>
          <button className="btn-secondary" type="button" onClick={() => void logout()}>
            <LogOut size={14} /> Salir
          </button>
        </div>

        <div className="controls-row">
          <div className="control-group">
            <label htmlFor="filter-category">Filtro categoria</label>
            <select
              id="filter-category"
              value={categoryFilter}
              onChange={(event) => setCategoryFilter(event.target.value as BugCategory | "all")}
            >
              {CATEGORY_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div className="control-group">
            <label htmlFor="filter-status">Filtro estado</label>
            <select
              id="filter-status"
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value as BugStatus | "all")}
            >
              {STATUS_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {error ? <div className="support-error">{error}</div> : null}

        <div className="support-admin-grid">
          <div className="support-admin-list">
            {reports.length === 0 ? <div className="status-text">Sin tickets para este filtro.</div> : null}
            {reports.map((report) => (
              <button
                key={report.id}
                type="button"
                className={`support-admin-item ${selectedId === report.id ? "active" : ""}`}
                onClick={() => void loadDetail(report.id)}
              >
                <div className="support-admin-item-title">
                  #{report.id} {report.title}
                </div>
                <div className="support-admin-item-meta">
                  <span>{new Date(report.created_at).toLocaleString()}</span>
                  <span className={`engine-status ${statusClass(report.status)}`}>{report.status}</span>
                  <span>{report.category}</span>
                  {report.attachments_count ? <span>adjuntos: {report.attachments_count}</span> : null}
                </div>
              </button>
            ))}
          </div>

          <div className="support-admin-detail">
            {!selectedReport ? (
              <div className="status-text">Selecciona un ticket para ver detalle.</div>
            ) : (
              <>
                <div className="engine-header">
                  <strong>
                    #{selectedReport.id} - {selectedReport.title}
                  </strong>
                  <span className={`engine-status ${statusClass(selectedReport.status)}`}>{selectedReport.status}</span>
                </div>

                <div className="controls-row">
                  <div className="control-group">
                    <label>Estado</label>
                    <select
                      value={selectedStatus}
                      onChange={(event) => void changeStatus(event.target.value as BugStatus)}
                      disabled={isUpdatingStatus}
                    >
                      <option value="new">new</option>
                      <option value="reviewing">reviewing</option>
                      <option value="resolved">resolved</option>
                    </select>
                    {isUpdatingStatus ? <small className="help-text">Actualizando estado...</small> : null}
                  </div>
                </div>

                <div className="support-detail-block">
                  <strong>Que intentaba hacer</strong>
                  <p>{selectedReport.what_tried}</p>
                </div>
                <div className="support-detail-block">
                  <strong>Resultado esperado</strong>
                  <p>{selectedReport.expected_result}</p>
                </div>
                <div className="support-detail-block">
                  <strong>Resultado real</strong>
                  <p>{selectedReport.actual_result}</p>
                </div>
                {selectedReport.error_text ? (
                  <div className="support-detail-block">
                    <strong>Error</strong>
                    <p>{selectedReport.error_text}</p>
                  </div>
                ) : null}

                <div className="support-meta-grid">
                  <div>
                    <strong>Categoria:</strong> {selectedReport.category}
                  </div>
                  <div>
                    <strong>Navegador:</strong> {selectedReport.browser || "n/d"}
                  </div>
                  <div>
                    <strong>Windows:</strong> {selectedReport.windows_version || "n/d"}
                  </div>
                  <div>
                    <strong>GPU:</strong> {selectedReport.gpu || "n/d"}
                  </div>
                  <div>
                    <strong>Origin:</strong> {selectedReport.origin || "n/d"}
                  </div>
                  <div>
                    <strong>App Version:</strong> {selectedReport.app_version || "n/d"}
                  </div>
                  <div>
                    <strong>Email:</strong> {selectedReport.contact_email || "n/d"}
                  </div>
                </div>

                {selectedReportPrettyBundle ? (
                  <div className="control-group">
                    <label>support_bundle_json</label>
                    <textarea readOnly value={selectedReportPrettyBundle} />
                  </div>
                ) : null}

                {selectedAttachments.length > 0 ? (
                  <div className="control-group">
                    <label>Adjuntos ({selectedAttachments.length})</label>
                    <div className="support-admin-attachments">
                      {selectedAttachments.map((attachment, index) => {
                        const isImage =
                          attachment.content_type.startsWith("image/") && attachment.data_url.startsWith("data:image/");
                        return (
                          <div className="support-admin-attachment-card" key={`${attachment.name}-${index}`}>
                            <div className="support-admin-attachment-head">
                              <strong>{attachment.name}</strong>
                              <span>{(attachment.size_bytes / 1024).toFixed(0)} KB</span>
                            </div>
                            {isImage ? (
                              <img
                                className="support-admin-attachment-image"
                                src={attachment.data_url}
                                alt={attachment.name}
                                loading="lazy"
                              />
                            ) : null}
                            <a className="btn-secondary" href={attachment.data_url} download={attachment.name}>
                              Descargar adjunto
                            </a>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ) : null}

                {selectedStatus === "resolved" ? (
                  <div className="support-success">
                    <CheckCircle2 size={16} /> Ticket resuelto.
                  </div>
                ) : null}
              </>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}

export default SupportAdminPage;
