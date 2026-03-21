import { createReadStream, existsSync } from "node:fs";
import { stat } from "node:fs/promises";
import { createServer } from "node:http";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = fileURLToPath(new URL(".", import.meta.url));
const DIST_DIR = join(__dirname, "dist");
const INDEX_FILE = join(DIST_DIR, "index.html");
const PORT = Number.parseInt(process.env.PORT || "3000", 10);
const HOST = "0.0.0.0";

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

if (!existsSync(INDEX_FILE)) {
  console.error("Missing dist/index.html. Build the app first with `npm run build`.");
  process.exit(1);
}

const server = createServer(async (request, response) => {
  try {
    const requestUrl = new URL(request.url || "/", "http://localhost");
    let pathname = decodeURIComponent(requestUrl.pathname);

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

