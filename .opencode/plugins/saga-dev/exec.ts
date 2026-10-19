import { spawn, type ChildProcess } from "node:child_process";
import path from "node:path";

export type ExecResult = {
  exitCode: number | null;
  stdout: string;
  stderr: string;
  durationMs: number;
  timedOut: boolean;
  command: string;
};

export type ExecOptions = {
  cwd: string;
  env?: Record<string, string>;
  timeoutMs?: number;
  signal?: AbortSignal;
  maxBytes?: number;
};

export function quoteArg(value: string): string {
  return /^[A-Za-z0-9_./:=@+-]+$/.test(value) ? value : JSON.stringify(value);
}

export function formatCommand(cmd: string, args: string[]): string {
  return [cmd, ...args].map(quoteArg).join(" ");
}

export async function exec(cmd: string, args: string[], options: ExecOptions): Promise<ExecResult> {
  const started = Date.now();
  const maxBytes = options.maxBytes ?? 5 * 1024 * 1024;
  const timeoutMs = options.timeoutMs ?? 120_000;

  return await new Promise<ExecResult>((resolve, reject) => {
    let child: ChildProcess;
    try {
      child = spawn(cmd, args, {
        cwd: options.cwd,
        env: { ...process.env, ...options.env },
        shell: false,
        detached: process.platform !== "win32",
        stdio: ["ignore", "pipe", "pipe"],
      });
    } catch (error) {
      reject(error);
      return;
    }

    let stdout = "";
    let stderr = "";
    let stdoutBytes = 0;
    let stderrBytes = 0;
    let truncated = false;
    let timedOut = false;
    let settled = false;

    const append = (stream: "stdout" | "stderr", chunk: Buffer): void => {
      const used = stream === "stdout" ? stdoutBytes : stderrBytes;
      if (used >= maxBytes) {
        truncated = true;
        return;
      }
      const slice = chunk.subarray(0, maxBytes - used);
      if (slice.length < chunk.length) truncated = true;
      const text = slice.toString("utf8");
      if (stream === "stdout") {
        stdout += text;
        stdoutBytes += slice.length;
      } else {
        stderr += text;
        stderrBytes += slice.length;
      }
    };

    child.stdout?.on("data", (chunk: Buffer) => append("stdout", chunk));
    child.stderr?.on("data", (chunk: Buffer) => append("stderr", chunk));

    const timer = setTimeout(() => {
      timedOut = true;
      killTree(child);
    }, timeoutMs);
    timer.unref?.();

    const onAbort = (): void => killTree(child);
    options.signal?.addEventListener("abort", onAbort, { once: true });

    const cleanup = (): void => {
      clearTimeout(timer);
      options.signal?.removeEventListener("abort", onAbort);
    };

    child.once("error", (error) => {
      if (settled) return;
      settled = true;
      cleanup();
      reject(error);
    });

    child.once("close", (code) => {
      if (settled) return;
      settled = true;
      cleanup();
      if (truncated) stderr += "\n[output truncated]";
      resolve({
        exitCode: code,
        stdout,
        stderr,
        durationMs: Date.now() - started,
        timedOut,
        command: formatCommand(cmd, args),
      });
    });
  });
}

export function frontendCommand(root: string, args: string[]): { cmd: string; args: string[] } {
  const script = path.join(root, "scripts", process.platform === "win32" ? "with_node.ps1" : "with_node.sh");
  if (process.platform === "win32") {
    return {
      cmd: "powershell.exe",
      args: ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script, ...args],
    };
  }
  return { cmd: "bash", args: [script, ...args] };
}

export function backendCommand(args: string[]): { cmd: string; args: string[] } {
  return { cmd: "uv", args: ["run", ...args] };
}

function killTree(child: ChildProcess): void {
  const pid = child.pid;
  if (!pid) return;
  if (process.platform === "win32") {
    spawn("taskkill", ["/pid", String(pid), "/T", "/F"], { stdio: "ignore" }).unref();
    return;
  }
  try {
    process.kill(-pid, "SIGTERM");
  } catch {
    child.kill("SIGTERM");
  }
  const killer = setTimeout(() => {
    try {
      process.kill(-pid, "SIGKILL");
    } catch {
      // Process already gone.
    }
  }, 2000);
  killer.unref?.();
}
