import { useEffect, useRef, useState } from "react";
import {
  Radar,
  RefreshCw,
  Plus,
  Check,
  AlertCircle,
  LoaderCircle,
  Network,
} from "lucide-react";
import { api, message } from "./api";
import type { Camera, ScanJob } from "./types";
export function ScanPanel({
  onSaved,
  cameras,
}: {
  onSaved: () => Promise<void>;
  cameras: Camera[];
}) {
  const [job, setJob] = useState<ScanJob | null>(null),
    [scanId, setScanId] = useState(
      () => sessionStorage.getItem("mapc.scan") || "",
    );
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [adding, setAdding] = useState<number | null>(null);
  const [added, setAdded] = useState<Set<number>>(new Set());
  const generation = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const stop = () => {
    ++generation.current;
    if (timer.current) clearTimeout(timer.current);
  };
  useEffect(() => () => stop(), []);
  const poll = async (id: string, version: number) => {
    try {
      const next = await api<ScanJob>(`/scans/${encodeURIComponent(id)}`);
      if (version !== generation.current) return;
      setJob(next);
      setBusy(false);
      if (next.status === "running")
        timer.current = setTimeout(() => void poll(id, version), 2000);
    } catch (e) {
      if (version === generation.current) {
        setError(`${message(e)} Polling stopped; use Get status to retry.`);
        setBusy(false);
      }
    }
  };
  const start = async () => {
    stop();
    const v = generation.current;
    setBusy(true);
    setError("");
    setAdded(new Set());
    try {
      const next = await api<ScanJob>("/scans/", { method: "POST" });
      if (v !== generation.current) return;
      setJob(next);
      setScanId(next.id);
      sessionStorage.setItem("mapc.scan", next.id);
      void poll(next.id, v);
    } catch (e) {
      setError(
        `${message(e)} If the connection failed, the scan may still have started.`,
      );
      setBusy(false);
    }
  };
  const rows = job?.result
    ? Object.values(job.result).flatMap((groups) =>
        Object.values(groups).flat(),
      )
    : [];
  const add = async (index: number) => {
    if (!job) return;
    setAdding(index);
    setError("");
    try {
      await api(`/scans/${encodeURIComponent(job.id)}/cameras/${index}`, {
        method: "POST",
      });
      setAdded((s) => new Set([...s, index]));
      await onSaved();
    } catch (e) {
      setError(message(e));
    } finally {
      setAdding(null);
    }
  };
  return (
    <div className="scan-page">
      <div className="page-heading">
        <div>
          <div className="eyebrow">DEVICE DISCOVERY</div>
          <h1>Network scan</h1>
          <p>Find ONVIF cameras and bring them into your workspace.</p>
        </div>
        <button
          className="primary"
          disabled={busy || job?.status === "running"}
          onClick={() => void start()}
        >
          {busy || job?.status === "running" ? (
            <LoaderCircle className="spin" size={17} />
          ) : (
            <Radar size={17} />
          )}{" "}
          Start scan
        </button>
      </div>
      <div className="scan-summary">
        <div className="summary-icon">
          <Network size={25} />
        </div>
        <div>
          <strong>
            {job
              ? {
                  running: "Scanning your network",
                  completed: "Scan completed",
                  failed: "Scan failed",
                  cancelled: "Scan cancelled",
                }[job.status]
              : "Ready to discover"}
          </strong>
          <p>
            Uses the subnets, ports, and exclusions configured on your server.
          </p>
        </div>
        <span className="badge">{rows.length} devices</span>
      </div>
      <form
        className="scan-lookup"
        onSubmit={(e) => {
          e.preventDefault();
          stop();
          setAdded(new Set());
          setError("");
          setBusy(true);
          void poll(scanId.trim(), generation.current);
        }}
      >
        <input
          aria-label="Scan ID"
          placeholder="Scan ID"
          value={scanId}
          onChange={(e) => setScanId(e.target.value)}
          required
        />
        <button disabled={busy || !scanId.trim()}>
          <RefreshCw size={15} /> Get status
        </button>
      </form>
      {(error || job?.error) && (
        <div className="alert" role="alert">
          <AlertCircle size={18} />
          {error || job?.error}
        </div>
      )}
      {rows.length ? (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Device</th>
                <th>Protocol</th>
                <th>Model / manufacturer</th>
                <th>Details</th>
                <th>Result</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((c, index) => {
                const exists =
                  c.already_exists ||
                  added.has(index) ||
                  cameras.some(
                    (saved) =>
                      saved.ip === c.ip &&
                      saved.port === c.port &&
                      saved.protocol === c.protocol,
                  );
                return (
                  <tr key={`${c.ip}-${c.port}-${index}`}>
                    <td>
                      <strong className="mono">{c.ip}</strong>
                      <small>Port {c.port}</small>
                    </td>
                    <td>
                      <span className="badge">{c.protocol.toUpperCase()}</span>
                    </td>
                    <td>
                      {c.model || "Unknown device"}
                      <small>{c.manufacturer || "Not available"}</small>
                    </td>
                    <td>
                      <small>{c.mac_address || "No MAC address"}</small>
                      {c.serial_number && <small>{c.serial_number}</small>}
                      {c.streams?.length > 0 && (
                        <details>
                          <summary>{c.streams.length} streams</summary>
                          {c.streams.map((s, i) => (
                            <p key={i}>
                              <strong>{s.profile}</strong>
                              <code>{s.uri}</code>
                            </p>
                          ))}
                        </details>
                      )}
                    </td>
                    <td>
                      {c.error ? (
                        <span className="error-text">{c.error}</span>
                      ) : (
                        <span className="success-text">ONVIF verified</span>
                      )}
                    </td>
                    <td>
                      <button
                        disabled={!!exists || !!c.error || adding !== null}
                        onClick={() => void add(index)}
                      >
                        {exists ? (
                          <Check size={15} />
                        ) : adding === index ? (
                          <LoaderCircle size={15} className="spin" />
                        ) : (
                          <Plus size={15} />
                        )}{" "}
                        {exists ? "Saved" : "Add"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="empty-panel">
          <Radar size={38} />
          <h2>
            {job?.status === "running"
              ? "Looking for cameras…"
              : "Your devices will appear here"}
          </h2>
          <p>
            {job?.status === "running"
              ? "You can return to the map while the server scans."
              : "Start a network scan or retrieve an earlier scan by its ID."}
          </p>
        </div>
      )}
    </div>
  );
}
