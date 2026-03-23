export type EngineStatus =
  | "not_installed"
  | "stopped"
  | "downloading"
  | "ready"
  | "error";

export type DownloadState = {
  profile: string;
  status: "idle" | "downloading" | "completed" | "failed";
  stage?: string;
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
  request_id?: string;
  cfg_weight?: number;
  exaggeration?: number;
  temperature?: number;
  seed?: number;
};

export type CloneRequest = SpeechRequest & {
  reference_audio: File;
};

export type EngineEvent = {
  id: number;
  timestamp: number;
  request_id: string;
  phase: string;
  level: "info" | "error" | string;
  message: string;
  progress?: number;
};

export type EventPollResponse = {
  events: EngineEvent[];
  next_cursor: number;
};

type ErrorBody = {
  error?: {
    code?: string;
    message?: string;
  };
  detail?: string;
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

const isLoopbackUrl = (candidateUrl: string): boolean => {
  try {
    const parsed = new URL(candidateUrl);
    const host = parsed.hostname.toLowerCase();
    return host === "localhost" || host === "127.0.0.1" || host === "::1" || host === "[::1]";
  } catch {
    return false;
  }
};

const canRequestLnaPrompt = (candidateUrl: string): boolean => {
  if (typeof window === "undefined") return false;
  if (!window.isSecureContext) return false;
  return isLoopbackUrl(candidateUrl);
};

type LocalNetworkRequestInit = RequestInit & {
  targetAddressSpace?: "local" | "private" | "loopback";
};

const warmupLoopbackPermission = async (baseUrl: string): Promise<void> => {
  if (!canRequestLnaPrompt(baseUrl)) return;
  try {
    const init: LocalNetworkRequestInit = {
      method: "GET",
      mode: "cors" as const,
      cache: "no-store" as const,
      // Experimental option used by Chromium-based browsers for local-network prompts.
      targetAddressSpace: "loopback",
    };
    await fetch(`${baseUrl}/health`, init);
  } catch {
    // Best-effort warm-up. We reattempt the original request immediately after this.
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
  const normalizedBaseUrl = asBaseUrl(baseUrl);
  const requestUrl = `${normalizedBaseUrl}${path}`;
  let response: Response;
  try {
    response = await fetch(requestUrl, init);
  } catch (error) {
    if (canRequestLnaPrompt(normalizedBaseUrl)) {
      try {
        await warmupLoopbackPermission(normalizedBaseUrl);
        response = await fetch(requestUrl, init);
      } catch (retryError) {
        throw toNetworkError(retryError);
      }
    } else {
      throw toNetworkError(error);
    }
  }
  const parsed = (await parseJsonSafe(response)) as ErrorBody | T | string | null;
  if (!response.ok) {
    const message =
      typeof parsed === "object" &&
      parsed &&
      "error" in parsed &&
      parsed.error?.message
        ? parsed.error.message
        : typeof parsed === "object" &&
            parsed &&
            "detail" in parsed &&
            typeof parsed.detail === "string"
          ? parsed.detail
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
  const normalizedBaseUrl = asBaseUrl(baseUrl);
  const requestUrl = `${normalizedBaseUrl}${path}`;
  let response: Response;
  try {
    response = await fetch(requestUrl, init);
  } catch (error) {
    if (canRequestLnaPrompt(normalizedBaseUrl)) {
      try {
        await warmupLoopbackPermission(normalizedBaseUrl);
        response = await fetch(requestUrl, init);
      } catch (retryError) {
        throw toNetworkError(retryError);
      }
    } else {
      throw toNetworkError(error);
    }
  }
  if (!response.ok) {
    const parsed = (await parseJsonSafe(response)) as ErrorBody | string | null;
    const message =
      typeof parsed === "object" &&
      parsed &&
      "error" in parsed &&
      parsed.error?.message
        ? parsed.error.message
        : typeof parsed === "object" &&
            parsed &&
            "detail" in parsed &&
            typeof parsed.detail === "string"
          ? parsed.detail
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

export const getLocalNetworkPermissionState = async (): Promise<"granted" | "prompt" | "denied" | "unsupported"> => {
  if (typeof window === "undefined" || !("permissions" in navigator) || !navigator.permissions?.query) {
    return "unsupported";
  }
  try {
    const permissionName = "local-network-access" as PermissionName;
    const result = await navigator.permissions.query({ name: permissionName });
    if (result.state === "granted" || result.state === "prompt" || result.state === "denied") {
      return result.state;
    }
    return "unsupported";
  } catch {
    return "unsupported";
  }
};

export const localEngineClient = {
  async health(baseUrl?: string): Promise<HealthPayload> {
    const retryDelaysMs = [0, 350, 900];
    let lastError: unknown;

    for (const delayMs of retryDelaysMs) {
      if (delayMs > 0) {
        await new Promise((resolve) => {
          globalThis.setTimeout(resolve, delayMs);
        });
      }
      try {
        return await requestJson<HealthPayload>("/health", { method: "GET" }, baseUrl);
      } catch (error) {
        lastError = error;
      }
    }

    throw lastError instanceof Error ? lastError : new LocalEngineError("No se pudo comprobar /health", 0);
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

  async pollEvents(
    baseUrl: string,
    token: string,
    options: {
      cursor?: number;
      request_id?: string;
      limit?: number;
    } = {},
  ): Promise<EventPollResponse> {
    const cursor = Math.max(0, Math.floor(options.cursor ?? 0));
    const limit = Math.max(1, Math.min(500, Math.floor(options.limit ?? 200)));
    const params = new URLSearchParams();
    params.set("cursor", String(cursor));
    params.set("limit", String(limit));
    if (options.request_id?.trim()) {
      params.set("request_id", options.request_id.trim());
    }
    return requestJson<EventPollResponse>(
      `/events/poll?${params.toString()}`,
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
    if (payload.request_id?.trim()) {
      body.append("request_id", payload.request_id.trim());
    }
    if (payload.cfg_weight !== undefined) {
      body.append("cfg_weight", String(payload.cfg_weight));
    }
    if (payload.exaggeration !== undefined) {
      body.append("exaggeration", String(payload.exaggeration));
    }
    if (payload.temperature !== undefined) {
      body.append("temperature", String(payload.temperature));
    }
    if (payload.seed !== undefined) {
      body.append("seed", String(payload.seed));
    }
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
