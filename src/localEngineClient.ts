export type EngineStatus =
  | "not_installed"
  | "stopped"
  | "downloading"
  | "ready"
  | "error";

export type DownloadState = {
  profile: string;
  status: "idle" | "downloading" | "completed" | "failed";
  progress: number;
  downloaded_bytes: number;
  total_bytes: number;
  error?: string;
};

export type EngineCapabilities = {
  platform: string;
  gpu_available: boolean;
  loaded_profile: string | null;
  profiles: string[];
  simulate_download: boolean;
  inference_backend?: "mock" | "chatterbox" | string;
  backend_mode?: "auto" | "mock" | "chatterbox" | string;
  real_backend_available?: boolean;
  real_backend_device?: string;
  real_backend_error?: string | null;
};

export type HealthPayload = {
  status: string;
  service: string;
  token_required: boolean;
};

export type SpeechRequest = {
  text: string;
  language: "es" | "en";
  quality_profile: string;
};

export type CloneRequest = SpeechRequest & {
  reference_audio: File;
};

type ErrorBody = {
  error?: {
    code?: string;
    message?: string;
  };
};

export class LocalEngineError extends Error {
  status: number;
  code: string;

  constructor(message: string, status: number, code = "UNKNOWN_ERROR") {
    super(message);
    this.status = status;
    this.code = code;
  }
}

const DEFAULT_URL = "http://127.0.0.1:57641";

const asBaseUrl = (baseUrl?: string): string => {
  let raw = (baseUrl ?? DEFAULT_URL).trim();
  if (!raw) raw = DEFAULT_URL;

  if (!/^[a-z]+:\/\//i.test(raw)) {
    raw = `http://${raw}`;
  }

  try {
    const parsed = new URL(raw);
    const host = parsed.hostname.toLowerCase();
    const isLoopback = host === "localhost" || host === "127.0.0.1" || host === "::1" || host === "[::1]";

    // Local engine MVP only serves HTTP on loopback. Auto-correct common HTTPS mistake.
    if (isLoopback && parsed.protocol === "https:") {
      parsed.protocol = "http:";
    }

    // Remove accidental path fragments like /health from the base URL field.
    parsed.pathname = "";
    parsed.search = "";
    parsed.hash = "";

    const normalized = parsed.toString();
    return normalized.endsWith("/") ? normalized.slice(0, -1) : normalized;
  } catch {
    return raw.endsWith("/") ? raw.slice(0, -1) : raw;
  }
};

const parseJsonSafe = async (response: Response): Promise<unknown> => {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
};

const toNetworkError = (error: unknown): LocalEngineError => {
  const detail = error instanceof Error && error.message ? ` (${error.message})` : "";
  return new LocalEngineError(
    `No se pudo conectar con el motor local.${detail} Verifica que este activo en http://127.0.0.1:57641 y que tu dominio HTTPS este permitido por el motor.`,
    0,
    "NETWORK_ERROR",
  );
};

const createHeaders = (token?: string, includeJson = true): Headers => {
  const headers = new Headers();
  if (includeJson) {
    headers.set("Content-Type", "application/json");
  }
  if (token?.trim()) {
    headers.set("Authorization", `Bearer ${token.trim()}`);
  }
  return headers;
};

const requestJson = async <T>(
  path: string,
  init: RequestInit = {},
  baseUrl?: string,
): Promise<T> => {
  let response: Response;
  try {
    response = await fetch(`${asBaseUrl(baseUrl)}${path}`, init);
  } catch (error) {
    throw toNetworkError(error);
  }
  const parsed = (await parseJsonSafe(response)) as ErrorBody | T | string | null;
  if (!response.ok) {
    const message =
      typeof parsed === "object" &&
      parsed &&
      "error" in parsed &&
      parsed.error?.message
        ? parsed.error.message
        : `Request failed with status ${response.status}`;
    const code =
      typeof parsed === "object" &&
      parsed &&
      "error" in parsed &&
      parsed.error?.code
        ? parsed.error.code
        : "UNKNOWN_ERROR";
    throw new LocalEngineError(message, response.status, code);
  }
  return parsed as T;
};

const requestBlob = async (
  path: string,
  init: RequestInit = {},
  baseUrl?: string,
): Promise<Blob> => {
  let response: Response;
  try {
    response = await fetch(`${asBaseUrl(baseUrl)}${path}`, init);
  } catch (error) {
    throw toNetworkError(error);
  }
  if (!response.ok) {
    const parsed = (await parseJsonSafe(response)) as ErrorBody | string | null;
    const message =
      typeof parsed === "object" &&
      parsed &&
      "error" in parsed &&
      parsed.error?.message
        ? parsed.error.message
        : `Request failed with status ${response.status}`;
    const code =
      typeof parsed === "object" &&
      parsed &&
      "error" in parsed &&
      parsed.error?.code
        ? parsed.error.code
        : "UNKNOWN_ERROR";
    throw new LocalEngineError(message, response.status, code);
  }
  return response.blob();
};

export const getDefaultLocalEngineUrl = (): string => {
  const envUrl = import.meta.env.VITE_LOCAL_ENGINE_URL as string | undefined;
  return asBaseUrl(envUrl || DEFAULT_URL);
};

export const localEngineClient = {
  async health(baseUrl?: string): Promise<HealthPayload> {
    return requestJson<HealthPayload>("/health", { method: "GET" }, baseUrl);
  },

  async version(baseUrl?: string): Promise<{ version: string }> {
    return requestJson<{ version: string }>("/version", { method: "GET" }, baseUrl);
  },

  async capabilities(baseUrl: string, token: string): Promise<EngineCapabilities> {
    return requestJson<EngineCapabilities>(
      "/capabilities",
      {
        method: "GET",
        headers: createHeaders(token, false),
      },
      baseUrl,
    );
  },

  async downloadModel(baseUrl: string, token: string, profile: string): Promise<DownloadState> {
    return requestJson<DownloadState>(
      "/models/download",
      {
        method: "POST",
        headers: createHeaders(token),
        body: JSON.stringify({ profile }),
      },
      baseUrl,
    );
  },

  async downloadStatus(baseUrl: string, token: string, profile: string): Promise<DownloadState> {
    const query = encodeURIComponent(profile);
    return requestJson<DownloadState>(
      `/models/download/status?profile=${query}`,
      {
        method: "GET",
        headers: createHeaders(token, false),
      },
      baseUrl,
    );
  },

  async loadModel(baseUrl: string, token: string, profile: string): Promise<{ status: string }> {
    return requestJson<{ status: string }>(
      "/models/load",
      {
        method: "POST",
        headers: createHeaders(token),
        body: JSON.stringify({ profile }),
      },
      baseUrl,
    );
  },

  async unloadModel(baseUrl: string, token: string, profile: string): Promise<{ status: string }> {
    return requestJson<{ status: string }>(
      "/models/unload",
      {
        method: "POST",
        headers: createHeaders(token),
        body: JSON.stringify({ profile }),
      },
      baseUrl,
    );
  },

  async synthesize(baseUrl: string, token: string, payload: SpeechRequest): Promise<Blob> {
    return requestBlob(
      "/tts",
      {
        method: "POST",
        headers: createHeaders(token),
        body: JSON.stringify(payload),
      },
      baseUrl,
    );
  },

  async clone(baseUrl: string, token: string, payload: CloneRequest): Promise<Blob> {
    const body = new FormData();
    body.append("text", payload.text);
    body.append("language", payload.language);
    body.append("quality_profile", payload.quality_profile);
    body.append("reference_audio", payload.reference_audio);

    return requestBlob(
      "/clone",
      {
        method: "POST",
        headers: createHeaders(token, false),
        body,
      },
      baseUrl,
    );
  },
};
