export interface Video {
  object_id: string;
  author: string;
  title: string;
  duration_ms: number;
  cover_url: string;
  file_size: number;
  specs_json?: string;
  formats?: string[];
  last_capture?: number;
  played?: boolean;
  last_played_at?: number;
  focused?: boolean;
  target?: boolean;
}

export interface RuntimeState {
  api_port: number;
  proxy_port: number;
  proxy_running: boolean;
  proxy: { enabled: boolean; points_to_us: boolean; armed_journal: boolean };
  cert: { exists: boolean; installed: boolean; thumbprint?: string };
  download_dir: string;
  count: number;
}

const base = location.origin;

async function get<T>(path: string): Promise<T> {
  const r = await fetch(base + path);
  return (await r.json()) as T;
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(base + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? "{}" : JSON.stringify(body),
  });
  return (await r.json()) as T;
}

export const api = {
  state: () => get<RuntimeState>("/api/state"),
  videos: (opts: { played?: boolean } = {}) =>
    get<{ videos: Video[] }>("/api/videos" + (opts.played ? "?played=1" : "")).then(
      (r) => r.videos
    ),
  download: (object_id: string, fmt?: string) =>
    post("/api/download", { object_id, fmt }),
  target: (link: string) => post<{ ok: boolean; short_id: string }>("/api/target", { link }),
  startProxy: () => post("/api/proxy/start"),
  stopProxy: () => post("/api/proxy/stop"),
};

export function connectWS(onEvent: (e: any) => void): WebSocket {
  const ws = new WebSocket(base.replace(/^http/, "ws") + "/ws");
  ws.onmessage = (m) => {
    try {
      onEvent(JSON.parse(m.data));
    } catch {
      /* ignore */
    }
  };
  return ws;
}
