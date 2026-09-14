import { useEffect, useState } from "react";
import { Camera, LoaderCircle, AlertCircle } from "lucide-react";
import { message, request } from "./api";
export function Snapshot({
  cameraId,
  label,
  x,
  y,
}: {
  cameraId: number;
  label: string;
  x: number;
  y: number;
}) {
  const [state, setState] = useState<{
    url?: string;
    error?: string;
    time?: string;
  }>({});
  useEffect(() => {
    const controller = new AbortController();
    let url: string | undefined;
    let active = true;
    const timer = setTimeout(async () => {
      try {
        const response = await request(`/camera/${cameraId}/snapshot`, {
          signal: controller.signal,
          cache: "no-store",
        });
        const blob = await response.blob();
        if (!active) return;
        url = URL.createObjectURL(blob);
        setState({ url, time: new Date().toLocaleTimeString("en-GB") });
      } catch (e) {
        if (active)
          setState({
            error: controller.signal.aborted
              ? "Snapshot request timed out."
              : message(e),
          });
      }
    }, 350);
    const timeout = setTimeout(() => controller.abort(), 45000);
    return () => {
      active = false;
      clearTimeout(timer);
      clearTimeout(timeout);
      controller.abort();
      if (url) URL.revokeObjectURL(url);
    };
  }, [cameraId]);
  const width = Math.min(340, window.innerWidth - 24);
  const left = Math.max(
    12,
    Math.min(
      window.innerWidth - width - 12,
      x + 22 + width < window.innerWidth ? x + 22 : x - width - 22,
    ),
  );
  return (
    <div
      className="snapshot"
      role="status"
      style={{
        left,
        top: Math.max(12, Math.min(window.innerHeight - 290, y - 50)),
        width,
      }}
    >
      <div className="snapshot-heading">
        <Camera size={15} />
        <strong>{label}</strong>
        <span>SNAPSHOT</span>
      </div>
      {state.url ? (
        <img
          src={state.url}
          alt={`Current view from ${label}`}
          onError={() => setState({ error: "Could not display the snapshot." })}
        />
      ) : (
        <div className="snapshot-placeholder">
          {state.error ? <AlertCircle /> : <LoaderCircle className="spin" />}
          <p>{state.error || "Requesting a fresh frame…"}</p>
        </div>
      )}
      {state.time && (
        <div className="snapshot-time">
          <i className="dot" /> Captured at {state.time}
        </div>
      )}
    </div>
  );
}
