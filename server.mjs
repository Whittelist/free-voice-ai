import { createHmac, timingSafeEqual } from "node:crypto";
import { createReadStream, existsSync } from "node:fs";
import { stat } from "node:fs/promises";
import { createServer } from "node:http";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";
import { Pool } from "pg";

const __dirname = fileURLToPath(new URL(".", import.meta.url));
const DIST_DIR = join(__dirname, "dist");
const INDEX_FILE = join(DIST_DIR, "index.html");
const PORT = Number.parseInt(process.env.PORT || "3000", 10);
const HOST = "0.0.0.0";

const DATABASE_URL = (process.env.DATABASE_URL || "").trim();
const ADMIN_PASSWORD = (process.env.BUG_REPORTS_ADMIN_PASSWORD || "").trim();
const SESSION_SECRET = (process.env.BUG_REPORTS_SESSION_SECRET || "").trim();

const SESSION_COOKIE_NAME = "studio_voice_admin_session";
const SESSION_TTL_SECONDS = 60 * 60 * 24 * 7;
const MAX_JSON_BODY_BYTES = 12 * 1024 * 1024;
const CATEGORY_VALUES = new Set(["launcher", "web", "other"]);
const STATUS_VALUES = new Set(["new", "reviewing", "resolved"]);
const MAX_ATTACHMENTS = 5;
const MAX_ATTACHMENT_BYTES = 3 * 1024 * 1024;
const MAX_ATTACHMENTS_TOTAL_BYTES = 8 * 1024 * 1024;

const MIME_MAP = new Map([
  [".html", "text/html; charset=utf-8"],
  [".js", "application/javascript; charset=utf-8"],
  [".css", "text/css; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".svg", "image/svg+xml"],
  [".png", "image/png"],
  [".jpg", "image/jpeg"],
  [".jpeg", "image/jpeg"],
  [".webp", "image/webp"],
  [".ico", "image/x-icon"],
  [".map", "application/json; charset=utf-8"],
  [".wav", "audio/wav"],
]);

const maybeUseSsl = () => {
  if (!DATABASE_URL) return undefined;
  if (DATABASE_URL.includes("localhost") || DATABASE_URL.includes("127.0.0.1")) {
    return undefined;
  }
  return { rejectUnauthorized: false };
};

const db = DATABASE_URL ? new Pool({ connectionString: DATABASE_URL, ssl: maybeUseSsl() }) : null;
let databaseReady = false;
let databaseInitError = null;

const sendJson = (response, statusCode, payload, extraHeaders = {}) => {
  const body = JSON.stringify(payload);
  response.writeHead(statusCode, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(body),
    "Cache-Control": "no-store",
    ...extraHeaders,
  });
  response.end(body);
};

const normalizeText = (value, { required = false, maxLength = 4000 } = {}) => {
  if (value === undefined || value === null) {
    if (required) return { ok: false, value: null };
    return { ok: true, value: null };
  }
  const text = String(value).trim();
  if (!text) {
    if (required) return { ok: false, value: null };
    return { ok: true, value: null };
  }
  if (text.length > maxLength) {
    return { ok: false, value: null };
  }
  return { ok: true, value: text };
};

const parseSupportBundle = (value) => {
  if (value === undefined || value === null) return null;
  if (typeof value === "object") return value;
  const text = String(value).trim();
  if (!text) return null;
  if (text.length > 200_000) {
    return { parse_error: "too_large", raw_text: text.slice(0, 200_000) };
  }
  try {
    return JSON.parse(text);
  } catch {
    return { parse_error: "invalid_json", raw_text: text };
  }
};

const estimateBase64Bytes = (base64Payload) => {
  const normalized = base64Payload.replace(/\s+/g, "");
  const padding = normalized.endsWith("==") ? 2 : normalized.endsWith("=") ? 1 : 0;
  return Math.floor((normalized.length * 3) / 4) - padding;
};

const parseAttachments = (value) => {
  if (value === undefined || value === null) return null;
  if (!Array.isArray(value)) {
    throw new Error("attachments_json must be an array.");
  }
  if (value.length > MAX_ATTACHMENTS) {
    throw new Error(`attachments_json allows up to ${MAX_ATTACHMENTS} files.`);
  }

  const attachments = [];
  let totalBytes = 0;

  for (const item of value) {
    if (!item || typeof item !== "object") {
      throw new Error("Invalid attachment object.");
    }
    const name = normalizeText(item.name, { required: true, maxLength: 180 });
    const contentType = normalizeText(item.content_type, { maxLength: 120 });
    const dataUrlRaw = typeof item.data_url === "string" ? item.data_url.trim() : "";
    if (!name.ok || !dataUrlRaw) {
      throw new Error("Attachment must include name and data_url.");
    }
    const match = dataUrlRaw.match(/^data:([^;,]+);base64,([a-zA-Z0-9+/=\s]+)$/);
    if (!match) {
      throw new Error("Attachment data_url must be a base64 data URL.");
    }

    const detectedMime = match[1].trim().toLowerCase();
    const base64Payload = match[2];
    const decodedBytes = estimateBase64Bytes(base64Payload);
    if (!Number.isFinite(decodedBytes) || decodedBytes <= 0) {
      throw new Error("Attachment payload is invalid.");
    }
    if (decodedBytes > MAX_ATTACHMENT_BYTES) {
      throw new Error(`Attachment '${name.value}' exceeds ${MAX_ATTACHMENT_BYTES} bytes.`);
    }
    totalBytes += decodedBytes;
    if (totalBytes > MAX_ATTACHMENTS_TOTAL_BYTES) {
      throw new Error(`Total attachments exceed ${MAX_ATTACHMENTS_TOTAL_BYTES} bytes.`);
    }

    attachments.push({
      name: name.value,
      content_type: contentType.value || detectedMime,
      size_bytes: decodedBytes,
      data_url: `data:${detectedMime};base64,${base64Payload.replace(/\s+/g, "")}`,
    });
  }

  return attachments.length > 0 ? attachments : null;
};

const parseCookies = (cookieHeader) => {
  const cookies = new Map();
  if (!cookieHeader) return cookies;
  for (const segment of cookieHeader.split(";")) {
    const [rawKey, ...rest] = segment.split("=");
    const key = rawKey?.trim();
    if (!key) continue;
    cookies.set(key, rest.join("=").trim());
  }
  return cookies;
};

const signSession = (encodedPayload) =>
  createHmac("sha256", SESSION_SECRET).update(encodedPayload).digest("base64url");

const createSessionToken = () => {
  const payload = { exp: Date.now() + SESSION_TTL_SECONDS * 1000, role: "admin" };
  const encoded = Buffer.from(JSON.stringify(payload)).toString("base64url");
  const signature = signSession(encoded);
  return `${encoded}.${signature}`;
};

const verifySessionToken = (token) => {
  if (!SESSION_SECRET || !token) return false;
  const [encoded, signature] = token.split(".");
  if (!encoded || !signature) return false;
  const expectedSignature = signSession(encoded);
  const a = Buffer.from(signature);
  const b = Buffer.from(expectedSignature);
  if (a.length !== b.length || !timingSafeEqual(a, b)) return false;
  try {
    const payload = JSON.parse(Buffer.from(encoded, "base64url").toString("utf-8"));
    return Boolean(payload?.role === "admin" && typeof payload.exp === "number" && payload.exp > Date.now());
  } catch {
    return false;
  }
};

const makeSessionCookie = (request, token) => {
  const forwardedProto = String(request.headers["x-forwarded-proto"] || "");
  const isSecure = process.env.NODE_ENV === "production" || forwardedProto.includes("https");
  const parts = [
    `${SESSION_COOKIE_NAME}=${token}`,
    "Path=/",
    "HttpOnly",
    "SameSite=Lax",
    `Max-Age=${SESSION_TTL_SECONDS}`,
  ];
  if (isSecure) parts.push("Secure");
  return parts.join("; ");
};

const makeLogoutCookie = (request) => {
  const forwardedProto = String(request.headers["x-forwarded-proto"] || "");
  const isSecure = process.env.NODE_ENV === "production" || forwardedProto.includes("https");
  const parts = [`${SESSION_COOKIE_NAME}=`, "Path=/", "HttpOnly", "SameSite=Lax", "Max-Age=0"];
  if (isSecure) parts.push("Secure");
  return parts.join("; ");
};

const readJsonBody = async (request) => {
  const chunks = [];
  let size = 0;
  for await (const chunk of request) {
    size += chunk.length;
    if (size > MAX_JSON_BODY_BYTES) {
      throw new Error("JSON payload too large");
    }
    chunks.push(chunk);
  }
  if (chunks.length === 0) return {};
  const raw = Buffer.concat(chunks).toString("utf-8").trim();
  if (!raw) return {};
  return JSON.parse(raw);
};

const requireAdminSession = (request, response) => {
  if (!ADMIN_PASSWORD || !SESSION_SECRET) {
    sendJson(response, 503, {
      error: {
        code: "ADMIN_NOT_CONFIGURED",
        message: "Admin panel is not configured in this environment.",
      },
    });
    return false;
  }
  const cookies = parseCookies(request.headers.cookie);
  const token = cookies.get(SESSION_COOKIE_NAME);
  if (!verifySessionToken(token)) {
    sendJson(response, 401, {
      error: { code: "UNAUTHORIZED", message: "Admin session required." },
    });
    return false;
  }
  return true;
};

const requireDatabase = (response) => {
  if (!db) {
    sendJson(response, 503, {
      error: { code: "DATABASE_NOT_CONFIGURED", message: "DATABASE_URL is missing in this environment." },
    });
    return false;
  }
  if (!databaseReady) {
    const detail = databaseInitError instanceof Error ? databaseInitError.message : "Database initialization pending";
    sendJson(response, 503, {
      error: { code: "DATABASE_NOT_READY", message: detail },
    });
    return false;
  }
  return true;
};

const validateBugReportPayload = (payload, requestUrl, request) => {
  const category = typeof payload.category === "string" ? payload.category.trim().toLowerCase() : "";
  if (!CATEGORY_VALUES.has(category)) {
    throw new Error("category must be launcher, web or other.");
  }

  const title = normalizeText(payload.title, { required: true, maxLength: 180 });
  const whatTried = normalizeText(payload.what_tried, { required: true, maxLength: 8000 });
  const expectedResult = normalizeText(payload.expected_result, { required: true, maxLength: 8000 });
  const actualResult = normalizeText(payload.actual_result, { required: true, maxLength: 8000 });
  const errorText = normalizeText(payload.error_text, { maxLength: 8000 });
  const browser = normalizeText(payload.browser, { maxLength: 120 });
  const windowsVersion = normalizeText(payload.windows_version, { maxLength: 120 });
  const gpu = normalizeText(payload.gpu, { maxLength: 250 });
  const contactEmail = normalizeText(payload.contact_email, { maxLength: 320 });
  const appVersion = normalizeText(payload.app_version, { maxLength: 120 });
  const declaredOrigin = normalizeText(payload.origin, { maxLength: 250 });

  if (!title.ok || !whatTried.ok || !expectedResult.ok || !actualResult.ok || !errorText.ok) {
    throw new Error("One or more fields are missing or exceed max length.");
  }

  const headerOrigin = normalizeText(request.headers.origin, { maxLength: 250 }).value;
  const supportBundle = parseSupportBundle(payload.support_bundle_json);
  const attachments = parseAttachments(payload.attachments_json);

  return {
    category,
    title: title.value,
    what_tried: whatTried.value,
    expected_result: expectedResult.value,
    actual_result: actualResult.value,
    error_text: errorText.value,
    browser: browser.value,
    windows_version: windowsVersion.value,
    gpu: gpu.value,
    contact_email: contactEmail.value,
    support_bundle_json: supportBundle,
    attachments_json: attachments,
    origin: declaredOrigin.value || headerOrigin || requestUrl.origin,
    app_version: appVersion.value,
  };
};

const sendFile = async (filePath, response) => {
  const fileInfo = await stat(filePath);
  const ext = extname(filePath).toLowerCase();
  const contentType = MIME_MAP.get(ext) || "application/octet-stream";

  response.writeHead(200, {
    "Content-Type": contentType,
    "Content-Length": fileInfo.size,
    "Cache-Control": ext === ".html" ? "no-cache" : "public, max-age=3600",
  });
  createReadStream(filePath).pipe(response);
};

const isPathInsideDist = (candidatePath) => {
  const normalized = normalize(candidatePath);
  const normalizedDist = normalize(DIST_DIR);
  return normalized.startsWith(normalizedDist);
};

const handleApi = async (request, response, requestUrl) => {
  const { pathname, searchParams } = requestUrl;

  if (pathname === "/api/health" && request.method === "GET") {
    sendJson(response, 200, {
      status: "ok",
      database_ready: databaseReady,
      has_database: Boolean(db),
    });
    return;
  }

  if (pathname === "/api/bug-reports" && request.method === "POST") {
    if (!requireDatabase(response)) return;
    try {
      const payload = await readJsonBody(request);
      const normalized = validateBugReportPayload(payload, requestUrl, request);
      const query = `
        INSERT INTO bug_reports (
          category, status, title, what_tried, expected_result, actual_result, error_text,
          browser, windows_version, gpu, contact_email, support_bundle_json, attachments_json, origin, app_version
        ) VALUES (
          $1, 'new', $2, $3, $4, $5, $6,
          $7, $8, $9, $10, $11::jsonb, $12::jsonb, $13, $14
        )
        RETURNING id, created_at, status
      `;
      const values = [
        normalized.category,
        normalized.title,
        normalized.what_tried,
        normalized.expected_result,
        normalized.actual_result,
        normalized.error_text,
        normalized.browser,
        normalized.windows_version,
        normalized.gpu,
        normalized.contact_email,
        normalized.support_bundle_json ? JSON.stringify(normalized.support_bundle_json) : null,
        normalized.attachments_json ? JSON.stringify(normalized.attachments_json) : null,
        normalized.origin,
        normalized.app_version,
      ];
      const result = await db.query(query, values);
      sendJson(response, 201, { bug_report: result.rows[0] });
    } catch (error) {
      sendJson(response, 400, {
        error: {
          code: "INVALID_PAYLOAD",
          message: error instanceof Error ? error.message : "Invalid payload",
        },
      });
    }
    return;
  }

  if (pathname === "/api/admin/login" && request.method === "POST") {
    if (!ADMIN_PASSWORD || !SESSION_SECRET) {
      sendJson(response, 503, {
        error: { code: "ADMIN_NOT_CONFIGURED", message: "Admin login is disabled in this environment." },
      });
      return;
    }
    try {
      const payload = await readJsonBody(request);
      const password = typeof payload.password === "string" ? payload.password : "";
      if (!password || password !== ADMIN_PASSWORD) {
        sendJson(response, 401, {
          error: { code: "INVALID_CREDENTIALS", message: "Invalid admin password." },
        });
        return;
      }

      const token = createSessionToken();
      sendJson(
        response,
        200,
        { status: "ok" },
        {
          "Set-Cookie": makeSessionCookie(request, token),
        },
      );
    } catch (error) {
      sendJson(response, 400, {
        error: {
          code: "INVALID_PAYLOAD",
          message: error instanceof Error ? error.message : "Invalid payload",
        },
      });
    }
    return;
  }

  if (pathname === "/api/admin/logout" && request.method === "POST") {
    sendJson(
      response,
      200,
      { status: "ok" },
      {
        "Set-Cookie": makeLogoutCookie(request),
      },
    );
    return;
  }

  if (pathname === "/api/admin/session" && request.method === "GET") {
    if (!requireAdminSession(request, response)) return;
    sendJson(response, 200, { authenticated: true });
    return;
  }

  if (pathname === "/api/admin/bug-reports" && request.method === "GET") {
    if (!requireAdminSession(request, response)) return;
    if (!requireDatabase(response)) return;
    const category = (searchParams.get("category") || "").trim().toLowerCase();
    const status = (searchParams.get("status") || "").trim().toLowerCase();
    const limitRaw = Number.parseInt(searchParams.get("limit") || "50", 10);
    const offsetRaw = Number.parseInt(searchParams.get("offset") || "0", 10);
    const limit = Number.isFinite(limitRaw) ? Math.min(Math.max(limitRaw, 1), 200) : 50;
    const offset = Number.isFinite(offsetRaw) ? Math.max(offsetRaw, 0) : 0;

    const where = [];
    const values = [];
    if (CATEGORY_VALUES.has(category)) {
      values.push(category);
      where.push(`category = $${values.length}`);
    }
    if (STATUS_VALUES.has(status)) {
      values.push(status);
      where.push(`status = $${values.length}`);
    }
    values.push(limit);
    const limitIndex = values.length;
    values.push(offset);
    const offsetIndex = values.length;

    const whereClause = where.length > 0 ? `WHERE ${where.join(" AND ")}` : "";
    const listSql = `
      SELECT
        id, created_at, category, status, title, browser, windows_version, gpu, origin, app_version,
        COALESCE(jsonb_array_length(attachments_json), 0) AS attachments_count
      FROM bug_reports
      ${whereClause}
      ORDER BY created_at DESC
      LIMIT $${limitIndex} OFFSET $${offsetIndex}
    `;
    const result = await db.query(listSql, values);
    sendJson(response, 200, { bug_reports: result.rows });
    return;
  }

  const detailMatch = pathname.match(/^\/api\/admin\/bug-reports\/(\d+)$/);
  if (detailMatch && request.method === "GET") {
    if (!requireAdminSession(request, response)) return;
    if (!requireDatabase(response)) return;
    const id = Number.parseInt(detailMatch[1], 10);
    const result = await db.query(
      `
        SELECT
          id, created_at, category, status, title, what_tried, expected_result, actual_result,
          error_text, browser, windows_version, gpu, contact_email, support_bundle_json, attachments_json, origin, app_version
        FROM bug_reports
        WHERE id = $1
      `,
      [id],
    );
    if (result.rows.length === 0) {
      sendJson(response, 404, { error: { code: "NOT_FOUND", message: "Bug report not found." } });
      return;
    }
    sendJson(response, 200, { bug_report: result.rows[0] });
    return;
  }

  const statusMatch = pathname.match(/^\/api\/admin\/bug-reports\/(\d+)\/status$/);
  if (statusMatch && request.method === "POST") {
    if (!requireAdminSession(request, response)) return;
    if (!requireDatabase(response)) return;
    const id = Number.parseInt(statusMatch[1], 10);
    try {
      const payload = await readJsonBody(request);
      const nextStatus = typeof payload.status === "string" ? payload.status.trim().toLowerCase() : "";
      if (!STATUS_VALUES.has(nextStatus)) {
        sendJson(response, 400, {
          error: { code: "INVALID_STATUS", message: "status must be new, reviewing or resolved." },
        });
        return;
      }
      const result = await db.query(
        `
          UPDATE bug_reports
          SET status = $2, updated_at = NOW()
          WHERE id = $1
          RETURNING id, status, updated_at
        `,
        [id, nextStatus],
      );
      if (result.rows.length === 0) {
        sendJson(response, 404, { error: { code: "NOT_FOUND", message: "Bug report not found." } });
        return;
      }
      sendJson(response, 200, { bug_report: result.rows[0] });
    } catch (error) {
      sendJson(response, 400, {
        error: {
          code: "INVALID_PAYLOAD",
          message: error instanceof Error ? error.message : "Invalid payload",
        },
      });
    }
    return;
  }

  sendJson(response, 404, { error: { code: "NOT_FOUND", message: "Unknown API route." } });
};

const initDatabase = async () => {
  if (!db) return;
  await db.query(`
    CREATE TABLE IF NOT EXISTS bug_reports (
      id BIGSERIAL PRIMARY KEY,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      category TEXT NOT NULL CHECK (category IN ('launcher', 'web', 'other')),
      status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'reviewing', 'resolved')),
      title TEXT NOT NULL,
      what_tried TEXT NOT NULL,
      expected_result TEXT NOT NULL,
      actual_result TEXT NOT NULL,
      error_text TEXT,
      browser TEXT,
      windows_version TEXT,
      gpu TEXT,
      contact_email TEXT,
      support_bundle_json JSONB,
      attachments_json JSONB,
      origin TEXT,
      app_version TEXT
    );
  `);
  await db.query(`
    ALTER TABLE bug_reports
    ADD COLUMN IF NOT EXISTS attachments_json JSONB;
  `);
  await db.query(`
    CREATE INDEX IF NOT EXISTS bug_reports_created_at_idx
    ON bug_reports (created_at DESC);
  `);
  await db.query(`
    CREATE INDEX IF NOT EXISTS bug_reports_category_status_idx
    ON bug_reports (category, status);
  `);
  databaseReady = true;
};

if (!existsSync(INDEX_FILE)) {
  console.error("Missing dist/index.html. Build the app first with `npm run build`.");
  process.exit(1);
}

if (db) {
  try {
    await initDatabase();
    console.log("Bug reports database initialized.");
  } catch (error) {
    databaseInitError = error;
    console.error("Failed to initialize bug reports database:", error);
  }
}

const server = createServer(async (request, response) => {
  try {
    const requestUrl = new URL(request.url || "/", "http://localhost");
    let pathname = decodeURIComponent(requestUrl.pathname);

    if (pathname.startsWith("/api/")) {
      await handleApi(request, response, requestUrl);
      return;
    }

    if (pathname === "/") pathname = "/index.html";

    const candidate = join(DIST_DIR, pathname);
    if (isPathInsideDist(candidate) && existsSync(candidate)) {
      await sendFile(candidate, response);
      return;
    }

    await sendFile(INDEX_FILE, response);
  } catch (error) {
    response.writeHead(500, { "Content-Type": "text/plain; charset=utf-8" });
    response.end(`Internal Server Error: ${error instanceof Error ? error.message : "unknown"}`);
  }
});

server.listen(PORT, HOST, () => {
  console.log(`Studio Voice AI listening on http://${HOST}:${PORT}`);
});
