import assert from "node:assert/strict";
import { once } from "node:events";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import {
  createServer as createHttpServer,
  type ClientRequest,
  type IncomingMessage,
  type Server,
} from "node:http";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, before, test } from "node:test";
import { runInNewContext } from "node:vm";
import { createServer, type ViteDevServer } from "vite";

let root: string;
let server: ViteDevServer;
let origin: string;
const secret = "saga-security-regression-secret";

before(async () => {
  root = await mkdtemp(join(tmpdir(), "saga-vite-security-"));
  await writeFile(join(root, "index.html"), "<html><body>SAGA</body></html>");
  await writeFile(join(root, ".env"), `SECRET=${secret}`);
  server = await createServer({
    configFile: false,
    root,
    server: { host: "127.0.0.1", port: 0 },
    logLevel: "silent",
  });
  await server.listen();
  const address = server.httpServer?.address();
  if (!address || typeof address === "string") throw new Error("Missing Vite address");
  origin = `http://127.0.0.1:${address.port}`;
});

after(async () => {
  await server?.close();
  if (root) await rm(root, { recursive: true, force: true });
});

test("Vite serves the app without exposing denied files through queries", async () => {
  assert.equal((await fetch(origin)).status, 200);
  for (const query of ["", "?raw", "?import&raw", "?import&url&inline"]) {
    const response = await fetch(`${origin}/.env${query}`);
    assert.equal(response.status, 403, query);
    assert.ok(!(await response.text()).includes(secret), query);
  }
});

interface RedirectClient {
  get(
    url: string,
    options: { headers: Record<string, string>; sensitiveHeaders: string[] },
    callback: (response: IncomingMessage) => void,
  ): ClientRequest;
}

async function listen(server: Server): Promise<string> {
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  if (!address || typeof address === "string") throw new Error("Missing HTTP address");
  return `http://127.0.0.1:${address.port}`;
}

async function close(server: Server): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    server.close((error) => (error ? reject(error) : resolve()));
  });
}

test("redirects strip custom credentials declared in another JS realm", async (context) => {
  let credential: string | string[] | undefined;
  let harmless: string | string[] | undefined;
  const destination = createHttpServer((request, response) => {
    credential = request.headers["x-api-key"];
    harmless = request.headers["x-harmless"];
    response.end("ok");
  });
  const destinationUrl = await listen(destination);
  context.after(() => close(destination));
  const redirect = createHttpServer((_request, response) => {
    response.writeHead(302, { Location: destinationUrl });
    response.end();
  });
  const redirectUrl = await listen(redirect);
  context.after(() => close(redirect));
  const headers: unknown = runInNewContext("['X-API-Key']");
  assert.ok(Array.isArray(headers) && headers.every((header) => typeof header === "string"));
  const { http } = createRequire(import.meta.url)("follow-redirects") as {
    http: RedirectClient;
  };

  await new Promise<void>((resolve, reject) => {
    http
      .get(
        redirectUrl,
        { headers: { "X-API-Key": secret, "X-Harmless": "kept" }, sensitiveHeaders: headers },
        (response) => {
          response.resume();
          response.once("end", resolve);
          response.once("error", reject);
        },
      )
      .once("error", reject);
  });

  assert.equal(credential, undefined);
  assert.equal(harmless, "kept");
});
