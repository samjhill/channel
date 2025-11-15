import { useEffect, useMemo, useState } from "react";
import {
  ChannelConfig,
  PlaybackMode,
  ShowConfig,
  fetchChannel,
  fetchChannels,
  saveChannel
} from "./api";
import ChannelSelector from "./components/ChannelSelector";
import ChannelSettingsForm from "./components/ChannelSettingsForm";
import ShowDiscovery from "./components/ShowDiscovery";
import ShowTable from "./components/ShowTable";
import SaveBar from "./components/SaveBar";

function cloneChannel(channel: ChannelConfig | null): ChannelConfig | null {
  return channel ? JSON.parse(JSON.stringify(channel)) : null;
}

function App() {
  const [channels, setChannels] = useState<ChannelConfig[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [currentChannel, setCurrentChannel] = useState<ChannelConfig | null>(null);
  const [initialChannel, setInitialChannel] = useState<ChannelConfig | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchChannels()
      .then((list) => {
        setChannels(list);
        if (list.length > 0) {
          setSelectedId(list[0].id);
        }
      })
      .catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    if (!selectedId) {
      return;
    }
    setLoading(true);
    fetchChannel(selectedId)
      .then((channel) => {
        setCurrentChannel(channel);
        setInitialChannel(cloneChannel(channel));
        setError(null);
      })
      .catch((err) => {
        setError(err.message);
        setCurrentChannel(null);
        setInitialChannel(null);
      })
      .finally(() => setLoading(false));
  }, [selectedId]);

  const isDirty = useMemo(() => {
    if (!currentChannel || !initialChannel) {
      return false;
    }
    return JSON.stringify(currentChannel) !== JSON.stringify(initialChannel);
  }, [currentChannel, initialChannel]);

  const handleChannelChange = (field: keyof ChannelConfig, value: unknown) => {
    if (!currentChannel) {
      return;
    }
    setCurrentChannel({ ...currentChannel, [field]: value });
  };

  const handleShowChange = (index: number, updated: Partial<ShowConfig>) => {
    if (!currentChannel) {
      return;
    }
    const shows = currentChannel.shows.map((show, idx) =>
      idx === index ? { ...show, ...updated } : show
    );
    setCurrentChannel({ ...currentChannel, shows });
  };

  const handleBulkAction = (action: "selectAll" | "deselectAll" | "normalizeWeights") => {
    if (!currentChannel) {
      return;
    }
    let shows: ShowConfig[] = currentChannel.shows;
    if (action === "selectAll") {
      shows = shows.map((show) => ({ ...show, include: true }));
    } else if (action === "deselectAll") {
      shows = shows.map((show) => ({ ...show, include: false }));
    } else if (action === "normalizeWeights") {
      shows = shows.map((show) => ({ ...show, weight: 1 }));
    }
    setCurrentChannel({ ...currentChannel, shows });
  };

  const handleDiscoveredShows = (discovered: ShowConfig[]) => {
    if (!currentChannel) {
      return { added: 0, total: discovered.length };
    }
    const existingIndex = new Map(currentChannel.shows.map((show, idx) => [show.id, idx]));
    const merged = [...currentChannel.shows];
    let added = 0;

    discovered.forEach((show) => {
      const idx = existingIndex.get(show.id);
      if (idx === undefined) {
        merged.push(show);
        existingIndex.set(show.id, merged.length - 1);
        added += 1;
      } else {
        merged[idx] = { ...merged[idx], ...show };
      }
    });

    setCurrentChannel({ ...currentChannel, shows: merged });
    return { added, total: discovered.length };
  };

  const handleSave = async () => {
    if (!currentChannel) {
      return;
    }
    setSaving(true);
    setStatus(null);
    try {
      await saveChannel(currentChannel);
      setInitialChannel(cloneChannel(currentChannel));
      setStatus("Changes saved");
      setError(null);
      setChannels((prev) =>
        prev.map((ch) => (ch.id === currentChannel.id ? currentChannel : ch))
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
      setTimeout(() => setStatus(null), 3000);
    }
  };

  const handleDiscard = () => {
    setCurrentChannel(cloneChannel(initialChannel));
  };

  return (
    <div className="app-shell">
      <header className="card">
        <h1>Channel Admin</h1>
        <ChannelSelector
          channels={channels}
          selectedId={selectedId}
          onSelect={setSelectedId}
          disabled={loading}
        />
      </header>
      <main className="app-content">
        {error && <div className="card" style={{ color: "#dc2626" }}>{error}</div>}
        {!error && loading && <div className="card">Loading channel…</div>}
        {!loading && currentChannel && (
          <>
            <ChannelSettingsForm
              channel={currentChannel}
              onChange={handleChannelChange}
            />
            <ShowDiscovery
              channelId={currentChannel.id}
              mediaRoot={currentChannel.media_root}
              disabled={!currentChannel.media_root}
              onAddShows={handleDiscoveredShows}
            />
            <ShowTable
              shows={currentChannel.shows}
              channelMode={currentChannel.playback_mode as PlaybackMode}
              onChange={handleShowChange}
              onBulkAction={handleBulkAction}
            />
          </>
        )}
      </main>
      <SaveBar
        dirty={isDirty}
        saving={saving}
        disabled={!currentChannel || !isDirty}
        status={status}
        onSave={handleSave}
        onDiscard={handleDiscard}
      />
    </div>
  );
}

export default App;

