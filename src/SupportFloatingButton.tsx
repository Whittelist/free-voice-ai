import { useState } from "react";
import { AlertTriangle, ExternalLink, Send, X } from "lucide-react";
import { SupportApiError, supportApi } from "./supportApi";

type SupportFloatingButtonProps = {
  currentPath: string;
};

const APP_VERSION = (import.meta.env.VITE_APP_VERSION as string | undefined) ?? "web-unknown";

function SupportFloatingButton({ currentPath }: SupportFloatingButtonProps) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (currentPath.startsWith("/support")) {
    return null;
  }

  const handleSubmit = async () => {
    const trimmed = text.trim();
    if (!trimmed) {
      setError("Pega logs o explica que paso para poder ayudarte.");
      return;
    }
    setError(null);
    setStatusMessage(null);
    setIsSubmitting(true);
    try {
      const result = await supportApi.submitBugReport({
        category: "other",
        title: "Reporte rapido desde boton flotante",
        what_tried: trimmed.slice(0, 8000),
        expected_result: "Que la app funcione correctamente en el flujo esperado.",
        actual_result: trimmed.slice(0, 8000),
        error_text: trimmed.slice(0, 8000),
        browser: typeof navigator !== "undefined" ? navigator.userAgent : null,
        origin: typeof window !== "undefined" ? window.location.origin : null,
        app_version: APP_VERSION,
      });
      setStatusMessage(`Reporte enviado. ID #${result.bug_report.id}`);
      setText("");
    } catch (submitError) {
      if (submitError instanceof SupportApiError) {
        setError(`${submitError.code}: ${submitError.message}`);
      } else if (submitError instanceof Error) {
        setError(submitError.message);
      } else {
        setError("No se pudo enviar el reporte rapido.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <>
      <button
        type="button"
        className="support-floating-button"
        onClick={() => {
          setOpen((prev) => !prev);
          setError(null);
          setStatusMessage(null);
        }}
        aria-label="Reportar error o bug"
      >
        <AlertTriangle size={16} />
        Hubo un error? Reportalo
      </button>

      {open ? (
        <div className="support-floating-panel">
          <div className="support-floating-panel-head">
            <strong>Reporte rapido</strong>
            <button type="button" className="btn-secondary" onClick={() => setOpen(false)}>
              <X size={14} /> Cerrar
            </button>
          </div>
          <p className="help-text">
            Pega los logs que encuentres y toda la informacion que consideres necesaria. Nosotros nos encargamos de
            revisarlo.
          </p>
          <textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="Pega aqui logs, error exacto y que estabas haciendo."
          />
          {error ? <div className="support-error">{error}</div> : null}
          {statusMessage ? <div className="support-success">{statusMessage}</div> : null}
          <div className="support-floating-panel-actions">
            <button
              type="button"
              className="btn-primary support-inline-primary"
              onClick={() => void handleSubmit()}
              disabled={isSubmitting}
            >
              <Send size={14} /> {isSubmitting ? "Enviando..." : "Enviar reporte rapido"}
            </button>
            <a className="btn-secondary" href="/support">
              Formulario completo <ExternalLink size={14} />
            </a>
          </div>
        </div>
      ) : null}
    </>
  );
}

export default SupportFloatingButton;
