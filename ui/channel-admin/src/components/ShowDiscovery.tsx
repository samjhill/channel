import { useState } from "react";
import { ShowConfig, discoverShows } from "../api";

interface Props {
  channelId: string;
  mediaRoot: string;
  disabled?: boolean;
  onAddShows: (shows: ShowConfig[]) => { added: number; total: number };
}

function ShowDiscovery({ channelId, mediaRoot, disabled, onAddShows }: Props) {
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleDiscover = async () => {
    if (!channelId || !mediaRoot) {
      setError("Set a media folder before scanning.");
      return;
    }

    setLoading(true);
    setMessage(null);
    setError(null);
    try {
      const discovered = await discoverShows(channelId, mediaRoot);
      if (!discovered.length) {
        setMessage("No show folders found in that directory.");
        return;
      }
      const { added, total } = onAddShows(discovered);
      if (added > 0) {
        setMessage(`Added ${added} new ${added === 1 ? "show" : "shows"} from ${total} found.`);
      } else {
        setMessage("All discovered shows are already in the channel.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to discover shows.");
    } finally {
      setLoading(false);
      setTimeout(() => setMessage(null), 4000);
    }
  };

  return (
    <section className="card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h2 style={{ margin: 0 }}>Show Discovery</h2>
          <p style={{ margin: "0.25rem 0 0", color: "#475569" }}>
            Scan the media folder for show directories and add them to this channel.
          </p>
        </div>
        <button
          className="btn btn-primary"
          onClick={handleDiscover}
          disabled={disabled || loading}
        >
          {loading ? "Scanning…" : "Discover shows"}
        </button>
      </div>
      {(message || error) && (
        <p style={{ marginTop: "0.5rem", color: error ? "#dc2626" : "#0f172a" }}>
          {error || message}
        </p>
      )}
    </section>
  );
}

export default ShowDiscovery;

