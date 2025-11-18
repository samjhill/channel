import { useEffect, useState } from "react";
import {
  API_BASE,
  fetchBumperPreview,
  type BumperPreviewResponse,
} from "../api";

export default function BumperPreview() {
  const [preview, setPreview] = useState<BumperPreviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadPreview = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchBumperPreview();
      setPreview(data);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to load bumper preview";
      setError(message);
      setPreview(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadPreview();
  }, []);

  const handleRefresh = () => {
    loadPreview();
  };

  const musicLabel =
    preview?.music_track?.split(/[\\/]/).pop() || "Random track";
  const videoSrc = preview ? `${API_BASE}${preview.video_url}` : undefined;

  return (
    <div className="bumper-preview card">
      <div className="preview-header">
        <h2>Bumper Preview</h2>
        <button
          className="btn btn-secondary"
          onClick={handleRefresh}
          disabled={loading}
        >
          {loading ? "Refreshing…" : "Refresh Preview"}
        </button>
      </div>

      <p className="help-text">
        Generates the next bumper block (sassy + optional weather + up-next +
        network) with its shared music bed so you can review it before it airs.
      </p>

      {error && (
        <div className="error-message" style={{ marginBottom: "1rem" }}>
          {error}
        </div>
      )}

      {loading && (
        <div className="loading-message" style={{ marginBottom: "1rem" }}>
          <div className="loading-spinner" />
          <span>Loading preview…</span>
        </div>
      )}

      {!loading && preview && (
        <>
          <video
            key={preview.video_url}
            controls
            style={{
              width: "100%",
              maxHeight: "420px",
              borderRadius: "8px",
              background: "#000",
              marginBottom: "1rem",
            }}
            src={videoSrc}
          />

          <div className="preview-meta">
            <p>
              <strong>Promoted Episode:</strong> {preview.episode_filename}
            </p>
            <p>
              <strong>Music Track:</strong> {musicLabel}
            </p>
            <p>
              <strong>Block ID:</strong> {preview.block_id}
            </p>
          </div>

          <div className="form-section">
            <h3>Included Bumpers ({preview.bumpers.length})</h3>
            <ul className="bumper-list">
              {preview.bumpers.map((item, idx) => (
                <li key={`${item.path}-${idx}`}>
                  <strong>{item.type.toUpperCase()}</strong>: {item.filename}
                </li>
              ))}
            </ul>
          </div>
        </>
      )}

      {!loading && !preview && !error && (
        <div className="card">
          Unable to locate an upcoming bumper block. Try refreshing again in a
          moment.
        </div>
      )}
    </div>
  );
}

