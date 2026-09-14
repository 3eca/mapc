import { useCallback, useEffect, useRef, useState } from "react";
import {
  Camera as CameraIcon,
  Map as MapIcon,
  Radar,
  Upload,
  Search,
  RefreshCw,
  ChevronRight,
  Trash2,
  ChevronDown,
  ChevronUp,
  LogOut,
  Plus,
  X,
  ImagePlus,
  ArrowUpRight,
  Check,
  LoaderCircle,
  AlertCircle,
  Layers,
  Crosshair,
  Eye,
  ShieldCheck,
} from "lucide-react";
import { api, message } from "./api";
import type { Camera, SiteMap } from "./types";
import { MapCanvas } from "./MapCanvas";
import { ScanPanel } from "./ScanPanel";

function Login() {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  return (
    <div className="login-page">
      <div className="login-art">
        <div className="brand">
          <span className="brand-icon">
            <Layers size={22} />
          </span>
          MAPC<span className="brand-tag">WORKSPACE</span>
        </div>
        <div className="login-copy">
          <span className="eyebrow">A CLEARER PICTURE</span>
          <h1>
            Every camera.
            <br />
            In the right place.
          </h1>
          <p>
            A considered workspace for your cameras, coverage, and the spaces
            they protect.
          </p>
          <div className="login-feature">
            <Crosshair size={18} /> Precise placement <span>·</span>
            <Eye size={18} /> Live snapshots
          </div>
        </div>
        <div className="login-grid">
          <div className="decor-sector" />
          <span className="decor-camera">
            <CameraIcon size={25} />
          </span>
        </div>
        <small>MAPC / CAMERA MANAGEMENT</small>
      </div>
      <div className="login-side">
        <form
          className="login-form"
          onSubmit={async (e) => {
            e.preventDefault();
            const data = new FormData(e.currentTarget);
            setBusy(true);
            setError("");
            try {
              await api("/auth/login", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  username: data.get("username"),
                  password: data.get("password"),
                }),
              });
              location.assign("/");
            } catch (e) {
              setError(message(e));
              setBusy(false);
            }
          }}
        >
          <span className="login-lock">
            <ShieldCheck size={24} />
          </span>
          <h2>Welcome back</h2>
          <p>Sign in to your camera workspace.</p>
          <label>
            Username
            <input
              name="username"
              autoComplete="username"
              required
              autoFocus
              maxLength={128}
            />
          </label>
          <label>
            Password
            <input
              name="password"
              type="password"
              autoComplete="current-password"
              required
              maxLength={1024}
            />
          </label>
          {error && (
            <div className="alert" role="alert">
              {error}
            </div>
          )}
          <button className="primary" disabled={busy}>
            {busy ? <LoaderCircle className="spin" size={18} /> : null} Sign in{" "}
            <ArrowUpRight size={18} />
          </button>
          <small>Administrator access · Your session stays private</small>
        </form>
      </div>
    </div>
  );
}
function UploadMap({
  onClose,
  onUploaded,
}: {
  onClose: () => void;
  onUploaded: (map: SiteMap) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [file, setFile] = useState<File | null>(null),
    [name, setName] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  return (
    <dialog
      ref={dialog}
      className="upload-dialog"
      onCancel={(e) => {
        e.preventDefault();
        if (!busy) onClose();
      }}
    >
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          if (!file || !name.trim()) return;
          setBusy(true);
          setError("");
          try {
            const map = await api<SiteMap>(
              `/maps/?name=${encodeURIComponent(name.trim())}`,
              {
                method: "POST",
                headers: {
                  "Content-Type": file.type || "application/octet-stream",
                },
                body: file,
                signal: new AbortController().signal,
              },
            );
            onUploaded(map);
          } catch (e) {
            setError(
              `${message(e)} Refresh the map list before retrying if the connection was interrupted.`,
            );
            setBusy(false);
          }
        }}
      >
        <div className="dialog-header">
          <div>
            <span className="eyebrow">YOUR WORKSPACE</span>
            <h2>Add a map</h2>
          </div>
          <button
            type="button"
            className="icon-button"
            aria-label="Close upload"
            disabled={busy}
            onClick={onClose}
          >
            <X size={20} />
          </button>
        </div>
        <label>
          Map name
          <input
            autoFocus
            placeholder="e.g. Ground floor"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={200}
            required
          />
        </label>
        <label className="upload-zone">
          <ImagePlus size={32} />
          <strong>
            {file ? file.name : "Choose a floor plan or site image"}
          </strong>
          <span>PNG or JPEG · Original quality preserved</span>
          <input
            type="file"
            accept="image/png,image/jpeg"
            required
            onChange={(e) => {
              const next = e.target.files?.[0] || null;
              setFile(next);
              if (next && !name) setName(next.name.replace(/\.[^.]+$/, ""));
            }}
          />
        </label>
        {error && (
          <div className="alert" role="alert">
            {error}
          </div>
        )}
        <div className="dialog-actions">
          <button type="button" disabled={busy} onClick={onClose}>
            Cancel
          </button>
          <button className="primary" disabled={busy || !file || !name.trim()}>
            {busy ? (
              <LoaderCircle size={16} className="spin" />
            ) : (
              <Upload size={16} />
            )}{" "}
            {busy ? "Uploading…" : "Upload map"}
          </button>
        </div>
      </form>
    </dialog>
  );
}
function Workspace() {
  const [mapRevision, setMapRevision] = useState(0);
  const [mapCollapsed, setMapCollapsed] = useState(false);
  const [tab, setTab] = useState<"map" | "scan">("map");
  const [maps, setMaps] = useState<SiteMap[]>([]),
    [cameras, setCameras] = useState<Camera[]>([]);
  const [mapId, setMapId] = useState<number | null>(null),
    [selected, setSelected] = useState<number | null>(null),
    [placed, setPlaced] = useState<number[]>([]);
  const [search, setSearch] = useState(""),
    [upload, setUpload] = useState(false),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [refreshing, setRefreshing] = useState(false);
  const [filter, setFilter] = useState<"all" | "placed" | "unplaced">("all");
  const refreshCameras = useCallback(async () => {
    const list = await api<Camera[]>("/camera/");
    setCameras(list);
  }, []);
  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [list, cams] = await Promise.all([
        api<SiteMap[]>("/maps/"),
        api<Camera[]>("/camera/"),
      ]);
      setMaps(list);
      setCameras(cams);
      setMapId((id) =>
        list.some((m) => m.id === id) ? id : (list[0]?.id ?? null),
      );
    } catch (e) {
      setError(message(e));
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);
  const map = maps.find((m) => m.id === mapId),
    chosen = cameras.find((c) => c.id === selected);
  const filtered = cameras.filter(
    (c) =>
      `${c.ip} ${c.model} ${c.manufacturer}`
        .toLowerCase()
        .includes(search.toLowerCase()) &&
      (filter === "all" ||
        (filter === "placed" ? placed.includes(c.id) : !placed.includes(c.id))),
  );
  const changeMap = (id: number) => {
    setSelected(null);
    setPlaced([]);
    setMapId(id);
  };
  return (
    <div className="workspace">
      <header className="topbar">
        <a href="/" className="brand">
          <span className="brand-icon">
            <Layers size={21} />
          </span>
          MAPC<span className="brand-tag">WORKSPACE</span>
        </a>
        <nav aria-label="Main navigation">
          <button
            className={tab === "map" ? "active" : ""}
            disabled={busy}
            onClick={() => setTab("map")}
          >
            <MapIcon size={16} /> Map workspace
          </button>
          <button
            className={tab === "scan" ? "active" : ""}
            disabled={busy}
            onClick={() => setTab("scan")}
          >
            <Radar size={16} /> Discovery
          </button>
        </nav>
        <div className="account">
          <span className="connection">
            <i className="dot" /> Connected
          </span>
          <a className="icon-button" href="/docs" title="API documentation">
            <ArrowUpRight size={17} />
          </a>
          <button
            className="icon-button"
            title="Sign out"
            aria-label="Sign out"
            onClick={async () => {
              try {
                await api("/auth/logout", { method: "POST" });
                location.assign("/login");
              } catch (e) {
                setError(message(e));
              }
            }}
          >
            <LogOut size={17} />
          </button>
          <span className="avatar">A</span>
        </div>
      </header>
      {error && (
        <div className="global-error" role="alert">
          <AlertCircle size={17} />
          {error}
          <button onClick={() => void load()}>Retry</button>
        </div>
      )}
      {tab === "scan" ? (
        <ScanPanel cameras={cameras} onSaved={refreshCameras} />
      ) : (
        <div className="workspace-body">
          <aside className="sidebar">
            <div className="sidebar-section">
              <span className="eyebrow">SITE MAP</span>
              <div className="map-picker">
                <MapIcon size={18} />
                <select
                  aria-label="Select map"
                  value={mapId ?? ""}
                  disabled={busy || loading || !maps.length}
                  onChange={(e) => changeMap(Number(e.target.value))}
                >
                  {!maps.length && <option value="">No maps yet</option>}
                  {maps.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name}
                    </option>
                  ))}
                </select>
              </div>
              <button
                className="upload-map-button"
                disabled={busy}
                onClick={() => setUpload(true)}
              >
                <Plus size={15} /> Add map
              </button>
            </div>
            <div className="camera-list-header">
              <div>
                <h2>
                  Cameras <span>{cameras.length}</span>
                </h2>
                <p>Select a camera to place or edit.</p>
              </div>
              <button
                className="icon-button"
                aria-label="Refresh cameras"
                disabled={refreshing || busy}
                onClick={async () => {
                  setRefreshing(true);
                  try {
                    await refreshCameras();
                  } catch (e) {
                    setError(message(e));
                  } finally {
                    setRefreshing(false);
                  }
                }}
              >
                <RefreshCw size={15} className={refreshing ? "spin" : ""} />
              </button>
            </div>
            <div className="search">
              <Search size={15} />
              <input
                placeholder="Search cameras…"
                aria-label="Search cameras"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <div className="camera-filters">
              {(["all", "placed", "unplaced"] as const).map((f) => (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  className={filter === f ? "active" : ""}
                >
                  {f === "all"
                    ? "All cameras"
                    : f === "placed"
                      ? "Placed"
                      : "Unplaced"}
                </button>
              ))}
            </div>
            <div className="camera-list">
              {filtered.map((c) => (
                <button
                  key={c.id}
                  className={`camera-card ${selected === c.id ? "selected" : ""}`}
                  disabled={busy}
                  onClick={() => setSelected(c.id)}
                  data-testid={`camera-card-${c.id}`}
                >
                  <span className="camera-card-icon">
                    <CameraIcon size={18} />
                  </span>
                  <span className="camera-card-text">
                    <strong>{c.ip}</strong>
                    <small>{c.model || "ONVIF camera"}</small>
                    <span className="camera-card-meta">
                      {c.protocol.toUpperCase()}
                      <span>·</span>
                      {placed.includes(c.id) ? "On this map" : "Not placed"}
                    </span>
                  </span>
                  {placed.includes(c.id) ? (
                    <Check size={14} className="placed-icon" />
                  ) : (
                    <Plus size={14} className="unplaced-icon" />
                  )}
                </button>
              ))}
              {!filtered.length && (
                <div className="sidebar-empty">
                  {loading
                    ? "Loading cameras…"
                    : cameras.length
                      ? "No matching cameras."
                      : "No cameras yet. Discover devices to get started."}
                </div>
              )}
            </div>
            <button
              className="discover-shortcut"
              disabled={busy}
              onClick={() => setTab("scan")}
            >
              <Radar size={18} />
              <span>
                Discover cameras<small>Scan your network for devices</small>
              </span>
              <ChevronRight size={16} />
            </button>
          </aside>
          <main className="map-main">
            <div className="workspace-heading">
              <div>
                <div className="breadcrumb">
                  Workspace <ChevronRight size={12} /> {map?.name || "Maps"}
                </div>
                <h1>{map?.name || "Your camera workspace"}</h1>
              </div>
              <div className="workspace-stats">
                <span>
                  <CameraIcon size={15} />
                  {placed.length} placed
                </span>
                <button
                  disabled={busy || !map}
                  aria-expanded={!mapCollapsed}
                  aria-controls="map-content"
                  onClick={() => setMapCollapsed((value) => !value)}
                >
                  {mapCollapsed ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
                  {mapCollapsed ? "Expand map" : "Collapse map"}
                </button>
                <span className="badge">
                  {map ? "MAP VIEW" : "GET STARTED"}
                </span>
              </div>
            </div>
            <div id="map-content" className="map-content" hidden={mapCollapsed}>
            {loading ? (
              <div className="empty-panel">
                <LoaderCircle size={32} className="spin" />
                <h2>Opening your workspace…</h2>
              </div>
            ) : map ? (
              <MapCanvas
                key={`${map.id}-${mapRevision}`}
                map={map}
                cameras={cameras}
                selected={selected}
                onSelect={setSelected}
                onCount={setPlaced}
                onBusy={setBusy}
              />
            ) : (
              <div className="empty-panel first-map">
                <div className="empty-map-icon">
                  <MapIcon size={44} />
                </div>
                <span className="eyebrow">START WITH YOUR SPACE</span>
                <h2>A place for every camera.</h2>
                <p>
                  Upload a floor plan or site image, then position your cameras
                  <br />
                  and shape their coverage directly on the map.
                </p>
                <button className="primary" onClick={() => setUpload(true)}>
                  <Upload size={17} /> Add your first map
                </button>
                <span className="empty-footnote">
                  PNG and JPEG · Original resolution
                </span>
              </div>
            )}
            </div>
            {chosen && (
              <div className="selection-strip">
                <CameraIcon size={17} />
                <strong>{chosen.ip}</strong>
                <span>{chosen.model}</span>
                <span className="badge">{chosen.protocol.toUpperCase()}</span>
                {chosen.streams.length > 0 && (
                  <details>
                    <summary>{chosen.streams.length} streams</summary>
                    <div className="stream-popover">
                      {chosen.streams.map((s, i) => (
                        <div key={i}>
                          <strong>{s.profile}</strong>
                          <code>{s.uri}</code>
                        </div>
                      ))}
                    </div>
                  </details>
                )}
                <button
                  disabled={busy}
                  aria-label="Delete camera"
                  onClick={async () => {
                    if (!window.confirm(`Delete camera ${chosen.ip}:${chosen.port}? Its streams and placements on all maps will also be deleted. This cannot be undone.`)) return;
                    setBusy(true);
                    try {
                      await api(`/camera/${chosen.id}`, { method: "DELETE" });
                      setCameras((list) => list.filter((camera) => camera.id !== chosen.id));
                      setPlaced((list) => list.filter((id) => id !== chosen.id));
                      setSelected(null);
                      setMapRevision((value) => value + 1);
                    } catch (e) {
                      setError(message(e));
                    } finally {
                      setBusy(false);
                    }
                  }}
                >
                  <Trash2 size={16} /> Delete camera
                </button>
                <button
                  className="icon-button"
                  aria-label="Clear camera selection"
                  disabled={busy}
                  onClick={() => setSelected(null)}
                >
                  <X size={16} />
                </button>
              </div>
            )}
          </main>
        </div>
      )}
      {upload && (
        <UploadMap
          onClose={() => setUpload(false)}
          onUploaded={(m) => {
            setMaps((list) => [...list, m]);
            changeMap(m.id);
            setUpload(false);
            setTab("map");
          }}
        />
      )}
    </div>
  );
}
export default function App() {
  return location.pathname === "/login" ? <Login /> : <Workspace />;
}
