import { useEffect, useState } from "react";
import { fetchSassyConfig, updateSassyConfig, type SassyConfig } from "../api";

export default function BumperManager() {
  const [config, setConfig] = useState<SassyConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [newMessage, setNewMessage] = useState("");

  useEffect(() => {
    loadConfig();
  }, []);

  const loadConfig = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchSassyConfig();
      setConfig(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load config");
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    if (!config) return;
    setSaving(true);
    setError(null);
    setStatus(null);
    try {
      const updated = await updateSassyConfig(config);
      setConfig(updated);
      setStatus("Configuration saved successfully");
      setTimeout(() => setStatus(null), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const handleToggleEnabled = () => {
    if (!config) return;
    setConfig({ ...config, enabled: !config.enabled });
  };

  const handleUpdateField = <K extends keyof SassyConfig>(
    field: K,
    value: SassyConfig[K]
  ) => {
    if (!config) return;
    setConfig({ ...config, [field]: value });
  };

  const handleAddMessage = () => {
    if (!config || !newMessage.trim()) return;
    setConfig({
      ...config,
      messages: [...config.messages, newMessage.trim()]
    });
    setNewMessage("");
  };

  const handleEditMessage = (index: number, newText: string) => {
    if (!config) return;
    const updated = [...config.messages];
    updated[index] = newText;
    setConfig({ ...config, messages: updated });
    setEditingIndex(null);
  };

  const handleDeleteMessage = (index: number) => {
    if (!config) return;
    if (window.confirm("Delete this message?")) {
      const updated = config.messages.filter((_, i) => i !== index);
      setConfig({ ...config, messages: updated });
    }
  };

  const handleMoveMessage = (index: number, direction: "up" | "down") => {
    if (!config) return;
    const newIndex = direction === "up" ? index - 1 : index + 1;
    if (newIndex < 0 || newIndex >= config.messages.length) return;
    const updated = [...config.messages];
    [updated[index], updated[newIndex]] = [updated[newIndex], updated[index]];
    setConfig({ ...config, messages: updated });
  };

  if (loading) {
    return <div className="card loading-message">Loading bumper configuration...</div>;
  }

  if (!config) {
    return <div className="card error-message">Failed to load configuration</div>;
  }

  return (
    <div className="bumper-manager">
      <div className="card">
        <h2>Bumper Management</h2>
        <p className="help-text">
          Manage sassy card messages that appear between episodes. These messages are randomly
          selected from your list.
        </p>

        {error && (
          <div className="error-message" style={{ marginBottom: "1rem" }}>
            <strong>Error:</strong> {error}
          </div>
        )}

        {status && (
          <div className="success-message" style={{ marginBottom: "1rem", color: "#4caf50" }}>
            {status}
          </div>
        )}

        <div className="form-section">
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={config.enabled}
              onChange={handleToggleEnabled}
            />
            <span>Enable sassy cards</span>
          </label>
        </div>

        <div className="form-section">
          <label>
            Duration (seconds)
            <input
              type="number"
              min="1"
              max="30"
              step="0.5"
              value={config.duration_seconds}
              onChange={(e) =>
                handleUpdateField("duration_seconds", parseFloat(e.target.value))
              }
            />
          </label>
        </div>

        <div className="form-section">
          <label>
            Music Volume (0.0 - 1.0)
            <input
              type="number"
              min="0"
              max="1"
              step="0.1"
              value={config.music_volume}
              onChange={(e) =>
                handleUpdateField("music_volume", parseFloat(e.target.value))
              }
            />
          </label>
        </div>

        <div className="form-section">
          <label>
            Probability Between Episodes (0.0 - 1.0)
            <input
              type="number"
              min="0"
              max="1"
              step="0.1"
              value={config.probability_between_episodes}
              onChange={(e) =>
                handleUpdateField(
                  "probability_between_episodes",
                  parseFloat(e.target.value)
                )
              }
            />
            <small>1.0 = always show, 0.0 = never show</small>
          </label>
        </div>

        <div className="form-section">
          <label>
            Style
            <select
              value={config.style}
              onChange={(e) => handleUpdateField("style", e.target.value)}
            >
              <option value="hbn-cozy">HBN Cozy</option>
              <option value="adult-swim-minimal">Adult Swim Minimal</option>
            </select>
          </label>
        </div>

        <div className="form-section">
          <h3>Messages ({config.messages.length})</h3>
          <div className="message-list">
            {config.messages.map((message, index) => (
              <div key={index} className="message-item">
                {editingIndex === index ? (
                  <div className="message-edit">
                    <textarea
                      value={message}
                      onChange={(e) => {
                        const updated = [...config.messages];
                        updated[index] = e.target.value;
                        setConfig({ ...config, messages: updated });
                      }}
                      onBlur={() => setEditingIndex(null)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && e.ctrlKey) {
                          setEditingIndex(null);
                        }
                        if (e.key === "Escape") {
                          loadConfig(); // Revert changes
                          setEditingIndex(null);
                        }
                      }}
                      rows={2}
                      autoFocus
                    />
                    <button
                      className="btn-small"
                      onClick={() => setEditingIndex(null)}
                    >
                      Done
                    </button>
                  </div>
                ) : (
                  <>
                    <div
                      className="message-text"
                      onClick={() => setEditingIndex(index)}
                      title="Click to edit"
                    >
                      {message}
                    </div>
                    <div className="message-actions">
                      <button
                        className="btn-small"
                        onClick={() => handleMoveMessage(index, "up")}
                        disabled={index === 0}
                        title="Move up"
                      >
                        ↑
                      </button>
                      <button
                        className="btn-small"
                        onClick={() => handleMoveMessage(index, "down")}
                        disabled={index === config.messages.length - 1}
                        title="Move down"
                      >
                        ↓
                      </button>
                      <button
                        className="btn-small"
                        onClick={() => setEditingIndex(index)}
                        title="Edit"
                      >
                        ✏️
                      </button>
                      <button
                        className="btn-small btn-danger"
                        onClick={() => handleDeleteMessage(index)}
                        title="Delete"
                      >
                        🗑️
                      </button>
                    </div>
                  </>
                )}
              </div>
            ))}
          </div>

          <div className="add-message">
            <textarea
              placeholder="Enter a new message..."
              value={newMessage}
              onChange={(e) => setNewMessage(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && e.ctrlKey) {
                  handleAddMessage();
                }
              }}
              rows={2}
            />
            <button
              className="btn-primary"
              onClick={handleAddMessage}
              disabled={!newMessage.trim()}
            >
              Add Message
            </button>
            <small>Press Ctrl+Enter to add</small>
          </div>
        </div>

        <div className="form-actions">
          <button
            className="btn-primary"
            onClick={handleSave}
            disabled={saving}
          >
            {saving ? "Saving..." : "Save Configuration"}
          </button>
          <button
            className="btn-secondary"
            onClick={loadConfig}
            disabled={saving}
          >
            Reload
          </button>
        </div>
      </div>
    </div>
  );
}

