import assert from "node:assert/strict";
import { execFile } from "node:child_process";
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
import process from "node:process";
import { after, before, test } from "node:test";
import { promisify } from "node:util";
import { runInNewContext } from "node:vm";
import { ESLint } from "eslint";
import tseslint from "typescript-eslint";
import { createServer, type ViteDevServer } from "vite";

let root: string;
let server: ViteDevServer;
let origin: string;
const secret = "saga-security-regression-secret";
const fromParser = createRequire(
  createRequire(import.meta.url).resolve("@typescript-eslint/typescript-estree"),
);

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

test("the parser's matcher rejects hostile glob amplification within a hard limit", async () => {
  assert.equal(
    (fromParser("minimatch/package.json") as { version: string }).version,
    "11.0.5",
    "Revalidate the parser's minimatch override before changing its version",
  );
  const entry = fromParser.resolve("minimatch");
  const script = `
    const assert = require('node:assert/strict');
    const { Minimatch } = require(${JSON.stringify(entry)});
    const pattern = Array.from({ length: 18 }, (_, i) => '**/../a' + i + '/b' + i)
      .join('/') + '/target.ts';
    assert.throws(() => new Minimatch(pattern, { optimizationLevel: 2, dot: true }), {
      name: 'RangeError',
      message: "optimizationLevel 2: too many patterns from '**/..'",
    });
    process.stdout.write('rejected');
  `;
  const { stdout } = await promisify(execFile)(
    process.execPath,
    ["--max-old-space-size=128", "--input-type=commonjs", "-e", script],
    { timeout: 5_000, maxBuffer: 4_096 },
  );

  assert.equal(stdout, "rejected");
});

test("ESLint still resolves allowDefaultProject globs for typed rules", async () => {
  await writeFile(join(root, "included.ts"), "export const included = 1;");
  await writeFile(
    join(root, "tsconfig.json"),
    JSON.stringify({ compilerOptions: { target: "ES2020" }, include: ["included.ts"] }),
  );
  const eslint = new ESLint({
    cwd: root,
    overrideConfigFile: true,
    overrideConfig: [
      {
        files: ["**/*.ts"],
        languageOptions: {
          parser: tseslint.parser,
          parserOptions: {
            tsconfigRootDir: root,
            projectService: { allowDefaultProject: ["probe.ts"] },
          },
        },
        plugins: { "@typescript-eslint": tseslint.plugin },
        rules: { "@typescript-eslint/no-floating-promises": "error" },
      },
    ],
  });

  const results = await eslint.lintText("Promise.resolve(42);", {
    filePath: join(root, "probe.ts"),
  });

  assert.equal(results.length, 1);
  assert.equal(results[0].fatalErrorCount, 0);
  assert.deepEqual(
    results[0].messages.map((message) => message.ruleId),
    ["@typescript-eslint/no-floating-promises"],
  );

  const blocked = await eslint.lintText("Promise.resolve(42);", {
    filePath: join(root, "other.ts"),
  });
  assert.equal(blocked[0].fatalErrorCount, 1);
  assert.match(blocked[0].messages[0].message, /not found by the project service/);
});

test("the parser's matcher preserves dot, brace, extglob and path matching", () => {
  const { minimatch } = fromParser("minimatch") as {
    minimatch: (path: string, pattern: string, options: { dot: boolean }) => boolean;
  };
  const cases: ReadonlyArray<readonly [string, string, boolean]> = [
    ["eslint.config.js", "*.config.{js,ts}", true],
    ["vite.config.ts", "@(eslint|vite).config.*", true],
    ["other.config.ts", "@(eslint|vite).config.*", false],
    [".config.ts", "*.ts", true],
    ["src/.hidden/file.ts", "src/**/*.ts", true],
    ["src/file.tsx", "src/**/*.ts", false],
    ["C:/saga/vite.config.ts", "C:/saga/*.ts", true],
    ["/saga/vite.config.ts", "/saga/*.ts", true],
    ["src/game/view.tsx", "src/**/view.?sx", true],
    ["src/game/view.tsx", "src/*/view.tsx", true],
    ["src/game/deep/view.tsx", "src/*/view.tsx", false],
    ["readme.md", "!*.ts", true],
    ["index.ts", "!*.ts", false],
  ];

  for (const [path, pattern, expected] of cases) {
    assert.equal(minimatch(path, pattern, { dot: true }), expected, `${path}: ${pattern}`);
  }
});
