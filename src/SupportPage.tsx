import { useMemo, useState, type FormEvent } from "react";
import { AlertTriangle, ArrowLeft, Paperclip, Send, Trash2 } from "lucide-react";
import type { BugAttachment, BugCategory } from "./supportApi";
import { SupportApiError, supportApi } from "./supportApi";

type FormState = {
  category: BugCategory;
  title: string;
  what_tried: string;
  expected_result: string;
  actual_result: string;
  error_text: string;
  browser: string;
  windows_version: string;
  gpu: string;
  contact_email: string;
  support_bundle_json: string;
};

const APP_VERSION = (import.meta.env.VITE_APP_VERSION as string | undefined) ?? "web-unknown";
const MAX_ATTACHMENTS = 5;
const MAX_ATTACHMENT_BYTES = 3 * 1024 * 1024;
const MAX_ATTACHMENTS_TOTAL_BYTES = 8 * 1024 * 1024;

const readFileAsDataUrl = (file: File): Promise<string> =>
  new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") {
        resolve(reader.result);
        return;
      }
      reject(new Error(`No se pudo leer ${file.name}`));
    };
    reader.onerror = () => reject(new Error(`No se pudo leer ${file.name}`));
    reader.readAsDataURL(file);
  });

const CATEGORY_TEXT: Record<BugCategory, { title: string; hint: string }> = {
  launcher: {
    title: "Launcher / instalacion / arranque local",
    hint: "Incluye errores de BAT, runtime Python, token o daemon local.",
  },
  web: {
    title: "Web / Railway / navegador / permisos",
    hint: "Incluye Failed to fetch, ORIGIN_NOT_ALLOWED, permisos locales y estados UI.",
  },
  other: {
    title: "Otro bug dificil de clasificar",
    hint: "Tienes un problema raro que no sabes clasificar? Reportalo aqui.",
  },
};

const initialForm: FormState = {
  category: "launcher",
  title: "",
  what_tried: "",
  expected_result: "",
  actual_result: "",
  error_text: "",
  browser: typeof navigator !== "undefined" ? navigator.userAgent : "",
  windows_version: "",
  gpu: "",
  contact_email: "",
  support_bundle_json: "",
};

function SupportPage() {
  const [form, setForm] = useState<FormState>(initialForm);
  const [attachments, setAttachments] = useState<BugAttachment[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successId, setSuccessId] = useState<number | null>(null);

  const currentCategory = useMemo(() => CATEGORY_TEXT[form.category], [form.category]);

  const update = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const removeAttachment = (indexToRemove: number) => {
    setAttachments((prev) => prev.filter((_, index) => index !== indexToRemove));
  };

  const handleAttachmentFiles = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setError(null);

    const incoming = Array.from(files);
    if (attachments.length + incoming.length > MAX_ATTACHMENTS) {
      setError(`Puedes adjuntar hasta ${MAX_ATTACHMENTS} archivos.`);
      return;
    }

    for (const file of incoming) {
      if (file.size > MAX_ATTACHMENT_BYTES) {
        setError(`El archivo '${file.name}' supera el limite de ${Math.round(MAX_ATTACHMENT_BYTES / (1024 * 1024))} MB.`);
        return;
      }
    }

    const currentTotal = attachments.reduce((acc, item) => acc + item.size_bytes, 0);
    const incomingTotal = incoming.reduce((acc, file) => acc + file.size, 0);
    if (currentTotal + incomingTotal > MAX_ATTACHMENTS_TOTAL_BYTES) {
      setError(`El total de adjuntos supera ${Math.round(MAX_ATTACHMENTS_TOTAL_BYTES / (1024 * 1024))} MB.`);
      return;
    }

    try {
      const mapped = await Promise.all(
        incoming.map(async (file) => ({
          name: file.name,
          content_type: file.type || "application/octet-stream",
          size_bytes: file.size,
          data_url: await readFileAsDataUrl(file),
        })),
      );
      setAttachments((prev) => [...prev, ...mapped]);
    } catch (fileError) {
      setError(fileError instanceof Error ? fileError.message : "No se pudo adjuntar el archivo.");
    }
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setSuccessId(null);

    if (!form.title.trim() || !form.what_tried.trim() || !form.expected_result.trim() || !form.actual_result.trim()) {
      setError("Completa titulo, que intentabas hacer, resultado esperado y resultado real.");
      return;
    }

    setIsSubmitting(true);
    try {
      const result = await supportApi.submitBugReport({
        category: form.category,
        title: form.title,
        what_tried: form.what_tried,
        expected_result: form.expected_result,
        actual_result: form.actual_result,
        error_text: form.error_text || null,
        browser: form.browser || null,
        windows_version: form.windows_version || null,
        gpu: form.gpu || null,
        contact_email: form.contact_email || null,
        support_bundle_json: form.support_bundle_json || null,
        attachments_json: attachments.length > 0 ? attachments : null,
        origin: window.location.origin,
        app_version: APP_VERSION,
      });
      setSuccessId(result.bug_report.id);
      setAttachments([]);
      setForm((prev) => ({
        ...initialForm,
        category: prev.category,
        browser: prev.browser,
      }));
    } catch (apiError) {
      if (apiError instanceof SupportApiError) {
        setError(`${apiError.code}: ${apiError.message}`);
      } else if (apiError instanceof Error) {
        setError(apiError.message);
      } else {
        setError("No se pudo enviar el reporte.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="app-container">
      <header>
        <h1>Soporte Studio Voice AI</h1>
        <p>
          Modo Pro esta en <strong>preview tecnica</strong>. El objetivo aqui es convertir cada bug en datos utiles.
        </p>
      </header>

      <main className="glass-card">
        <a className="btn-secondary support-back" href="/">
          <ArrowLeft size={14} /> Volver a la app
        </a>

        <div className="alert-box">
          <AlertTriangle color="#eab308" className="shrink-0" />
          <div>
            <strong>Compatibilidad v1</strong>
            <p>Windows 10/11 + Chrome/Edge + launcher local. Safari, Firefox, macOS y Linux quedan fuera en v1.</p>
          </div>
        </div>

        <form className="support-form" onSubmit={(event) => void submit(event)}>
          <div className="control-group">
            <label htmlFor="category">Tipo de bug</label>
            <select
              id="category"
              value={form.category}
              onChange={(event) => update("category", event.target.value as BugCategory)}
            >
              <option value="launcher">Launcher / instalacion / arranque local</option>
              <option value="web">Web / Railway / permisos / UI</option>
              <option value="other">Otro bug dificil de clasificar</option>
            </select>
            <small className="help-text">
              <strong>{currentCategory.title}:</strong> {currentCategory.hint}
            </small>
          </div>

          <div className="control-group">
            <label htmlFor="title">Titulo corto del problema</label>
            <input
              id="title"
              value={form.title}
              onChange={(event) => update("title", event.target.value)}
              placeholder="Ej: Failed to fetch al comprobar motor desde Railway"
              maxLength={180}
              required
            />
          </div>

          <div className="control-group">
            <label htmlFor="what-tried">Que intentabas hacer?</label>
            <textarea
              id="what-tried"
              value={form.what_tried}
              onChange={(event) => update("what_tried", event.target.value)}
              placeholder="Pasos exactos que seguiste"
              required
            />
          </div>

          <div className="control-group">
            <label htmlFor="expected-result">Que esperabas que pasara?</label>
            <textarea
              id="expected-result"
              value={form.expected_result}
              onChange={(event) => update("expected_result", event.target.value)}
              required
            />
          </div>

          <div className="control-group">
            <label htmlFor="actual-result">Que paso realmente?</label>
            <textarea
              id="actual-result"
              value={form.actual_result}
              onChange={(event) => update("actual_result", event.target.value)}
              required
            />
          </div>

          <div className="control-group">
            <label htmlFor="error-text">Texto del error (si existe)</label>
            <textarea
              id="error-text"
              value={form.error_text}
              onChange={(event) => update("error_text", event.target.value)}
              placeholder="Ej: MISSING_TOKEN / ORIGIN_NOT_ALLOWED / Failed to fetch"
            />
          </div>

          <div className="controls-row">
            <div className="control-group">
              <label htmlFor="browser">Navegador</label>
              <input
                id="browser"
                value={form.browser}
                onChange={(event) => update("browser", event.target.value)}
                placeholder="Chrome 124 / Edge 124"
              />
            </div>
            <div className="control-group">
              <label htmlFor="windows-version">Version de Windows</label>
              <input
                id="windows-version"
                value={form.windows_version}
                onChange={(event) => update("windows_version", event.target.value)}
                placeholder="Windows 11 23H2"
              />
            </div>
            <div className="control-group">
              <label htmlFor="gpu">GPU (si la conoces)</label>
              <input
                id="gpu"
                value={form.gpu}
                onChange={(event) => update("gpu", event.target.value)}
                placeholder="Ej: NVIDIA RTX 5070"
              />
            </div>
          </div>

          <div className="controls-row">
            <div className="control-group">
              <label htmlFor="contact-email">Email de contacto (opcional)</label>
              <input
                id="contact-email"
                type="email"
                value={form.contact_email}
                onChange={(event) => update("contact_email", event.target.value)}
                placeholder="tu@email.com"
              />
            </div>
          </div>

          <div className="control-group">
            <label htmlFor="support-bundle">support_bundle.json (opcional, pegado en texto)</label>
            <textarea
              id="support-bundle"
              value={form.support_bundle_json}
              onChange={(event) => update("support_bundle_json", event.target.value)}
              placeholder='Pega aqui el JSON exportado por "Export Studio Voice Diagnostics.bat"'
            />
          </div>

          <div className="control-group">
            <label htmlFor="support-attachments">Adjuntos opcionales (fotos, logs, txt, zip)</label>
            <input
              id="support-attachments"
              type="file"
              multiple
              onChange={(event) => {
                void handleAttachmentFiles(event.target.files);
                event.currentTarget.value = "";
              }}
              accept="image/*,.txt,.log,.json,.zip,.wav,.mp3"
            />
            <small className="help-text">
              Maximo {MAX_ATTACHMENTS} archivos, {Math.round(MAX_ATTACHMENT_BYTES / (1024 * 1024))} MB por archivo,
              {Math.round(MAX_ATTACHMENTS_TOTAL_BYTES / (1024 * 1024))} MB en total.
            </small>
            {attachments.length > 0 ? (
              <div className="support-attachments-list">
                {attachments.map((item, index) => (
                  <div className="support-attachment-row" key={`${item.name}-${item.size_bytes}-${index}`}>
                    <span>
                      <Paperclip size={13} /> {item.name} ({(item.size_bytes / 1024).toFixed(0)} KB)
                    </span>
                    <button type="button" className="btn-secondary" onClick={() => removeAttachment(index)}>
                      <Trash2 size={13} /> Quitar
                    </button>
                  </div>
                ))}
              </div>
            ) : null}
          </div>

          {error ? <div className="support-error">{error}</div> : null}
          {successId ? (
            <div className="support-success">
              Reporte enviado correctamente. ID: <strong>#{successId}</strong>
            </div>
          ) : null}

          <button className="btn-primary" type="submit" disabled={isSubmitting}>
            <Send size={16} />
            {isSubmitting ? "Enviando reporte..." : "Enviar reporte de bug"}
          </button>
        </form>
      </main>
    </div>
  );
}

export default SupportPage;
