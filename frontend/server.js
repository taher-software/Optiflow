import express from "express";
import path from "node:path";
import { fileURLToPath } from "node:url";

/**
 * Static server for the built Vite bundle, used by App Engine.
 *
 * The bundle is built before deploying (`npm run build`) and uploaded as-is —
 * this process only serves `dist/`. Two rules matter:
 *
 *   1. Hashed assets are immutable, so they get a one-year cache. `index.html`
 *      must never be cached, or a browser keeps loading the previous build's
 *      asset URLs after a deploy.
 *   2. Unknown paths fall back to `index.html`, because /privacy, /terms and
 *      /app/... are client-side routes with no file behind them. Without the
 *      fallback, a deep link or a page reload would 404.
 */
const dist = path.join(path.dirname(fileURLToPath(import.meta.url)), "dist");
const app = express();

app.disable("x-powered-by");

app.use(
  express.static(dist, {
    index: false,
    setHeaders: (res, filePath) => {
      const immutable = filePath.includes(`${path.sep}assets${path.sep}`);
      res.setHeader(
        "Cache-Control",
        immutable
          ? "public, max-age=31536000, immutable"
          : "public, max-age=3600",
      );
    },
  }),
);

app.get("/{*path}", (_req, res) => {
  res.setHeader("Cache-Control", "no-cache");
  res.sendFile(path.join(dist, "index.html"));
});

const port = Number(process.env.PORT) || 8080;
app.listen(port, () => {
  process.stdout.write(`serving ${dist} on :${port}\n`);
});
