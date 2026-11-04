export type Metrics = {
  cpu_percent: number; cpu_count: number; memory_percent: number; memory_total: number;
  memory_used: number; disk_percent: number; network_rx: number; network_tx: number;
  load: number[]; uptime: number; disks: { mount: string; total: number; used: number; percent: number }[];
};
export type Container = { id: string; name: string; image: string; state: string; status: string; ports: string; cpu: string; memory: string };
export type Service = { name: string; description: string; active: string; sub: string; load: string };
export type Repo = { path: string; name: string; branch: string; changes: number; dirty: boolean; commit: string; message: string; relative_time: string; error?: string };
export type Health = { name: string; url: string; status: string; code: number | null; latency_ms: number | null; error?: string };
export type Snapshot = {
  status: string; timestamp: number; demo: boolean; error?: {code: string; message: string} | null;
  hostname?: string; os?: string; kernel?: string; metrics?: Metrics | null;
  docker?: { available: boolean; error?: string; containers: Container[]; images: Record<string, string>[]; compose: Record<string, string>[] };
  systemd?: { available: boolean; error?: string; services: Service[] };
  git?: Repo[]; health?: Health[];
};
export type DeviceConfig = {
  name: string; host: string; port: number; username: string; mode: 'demo' | 'ssh' | 'agent';
  credential_ref: string; jump_device_id: string | null; kind: 'linux' | 'nas' | 'windows' | 'macos';
  git_paths: string[]; health_targets: { name: string; url: string }[];
};
export type Device = DeviceConfig & { id: string; snapshot?: Snapshot | null };
export type Sample = Metrics & { timestamp: number };
export type Audit = { id: number; timestamp: number; action: string; target: string; detail: string };
