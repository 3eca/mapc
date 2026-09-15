export interface Stream {
  profile: string;
  token: string;
  uri: string;
}
export interface Camera {
  id: number;
  ip: string;
  port: number;
  protocol: string;
  manufacturer: string;
  model: string;
  firmware: string;
  serial_number: string;
  mac_address: string;
  is_active: boolean;
  streams: Stream[];
  error?: string;
  already_exists?: boolean;
  username?: string;
  password?: string;
}
export interface SiteMap {
  id: number;
  name: string;
  width: number;
  height: number;
  mime_type: string;
}
export interface Placement {
  camera_id: number;
  x: number;
  y: number;
  direction: number;
  view_angle: number;
  view_distance: number;
  id?: number;
  map_id?: number;
}
export interface ScanJob {
  id: string;
  status: "running" | "completed" | "failed" | "cancelled";
  error: string | null;
  result: Record<string, Record<string, Camera[]>> | null;
}
export type Point = { x: number; y: number };
export type View = Point & { scale: number };
