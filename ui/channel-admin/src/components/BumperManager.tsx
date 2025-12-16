import { useEffect, useState } from "react";
import {
  fetchSassyConfig,
  updateSassyConfig,
  type SassyConfig,
  fetchWeatherConfig,
  updateWeatherConfig,
  type WeatherConfig,
} from "../api";

export default function BumperManager() {
  const [config, setConfig] = useState<SassyConfig | null>(null);
  const [weatherConfig, setWeatherConfig] = useState<WeatherConfig | null>(null);
  const [loadingSassy, setLoadingSassy] = useState(true);
  const [loadingWeather, setLoadingWeather] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [newMessage, setNewMessage] = useState("");
  const [activeTab, setActiveTab] = useState<"sassy" | "weather">("sassy");

  useEffect(() => {
    loadConfig();
    loadWeatherConfig();
  }, []);

  const loadConfig = async () => {
    setLoadingSassy(true);
    setError(null);
    try {
      const data = await fetchSassyConfig();
      // Ensure messages is always an array
      setConfig({
        ...data,
        messages: Array.isArray(data.messages) ? data.messages : [],
      });
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : "Failed to load sassy config";
      setError(errorMsg);
      console.error("Failed to load sassy config:", err);
    } finally {
      setLoadingSassy(false);
    }
  };

  const loadWeatherConfig = async () => {
    setLoadingWeather(true);
    try {
      const data = await fetchWeatherConfig();
      setWeatherConfig(data);
    } catch (err) {
      // Weather config might not exist yet, that's okay - we'll show a message
      console.warn("Failed to load weather config:", err);
      // Don't set error here as weather config is optional
    } finally {
      setLoadingWeather(false);
    }
  };

  const handleSave = async () => {
    if (activeTab === "sassy") {
      if (!config) return;
      setSaving(true);
      setError(null);
      setStatus(null);
      try {
        const updated = await updateSassyConfig(config);
        setConfig(updated);
        setStatus("Sassy card configuration saved successfully");
        setTimeout(() => setStatus(null), 3000);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to save");
      } finally {
        setSaving(false);
      }
    } else if (activeTab === "weather") {
      if (!weatherConfig) return;
      setSaving(true);
      setError(null);
      setStatus(null);
      try {
        const updated = await updateWeatherConfig(weatherConfig);
        setWeatherConfig(updated);
        setStatus("Weather bumper configuration saved successfully");
        setTimeout(() => setStatus(null), 3000);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to save");
      } finally {
        setSaving(false);
      }
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

  const handleWeatherUpdateField = <K extends keyof WeatherConfig>(
    field: K,
    value: WeatherConfig[K]
  ) => {
    if (!weatherConfig) return;
    setWeatherConfig({ ...weatherConfig, [field]: value });
  };

  const handleWeatherLocationUpdate = (
    field: keyof WeatherConfig["location"],
    value: string | number
  ) => {
    if (!weatherConfig) return;
    setWeatherConfig({
      ...weatherConfig,
      location: { ...weatherConfig.location, [field]: value },
    });
  };

  const handleAddMessage = () => {
    if (!config || !config.messages || !newMessage.trim()) return;
    setConfig({
      ...config,
      messages: [...config.messages, newMessage.trim()]
    });
    setNewMessage("");
  };

  const handleEditMessage = (index: number, newText: string) => {
    if (!config || !config.messages) return;
    const updated = [...config.messages];
    updated[index] = newText;
    setConfig({ ...config, messages: updated });
    setEditingIndex(null);
  };

  const handleDeleteMessage = (index: number) => {
    if (!config || !config.messages) return;
    if (window.confirm("Delete this message?")) {
      const updated = config.messages.filter((_, i) => i !== index);
      setConfig({ ...config, messages: updated });
    }
  };

  const handleMoveMessage = (index: number, direction: "up" | "down") => {
    if (!config || !config.messages) return;
    const newIndex = direction === "up" ? index - 1 : index + 1;
    if (newIndex < 0 || newIndex >= config.messages.length) return;
    const updated = [...config.messages];
    [updated[index], updated[newIndex]] = [updated[newIndex], updated[index]];
    setConfig({ ...config, messages: updated });
  };

  const isLoading = activeTab === "sassy" ? loadingSassy : loadingWeather;

  return (
    <div className="bumper-manager">
      <div className="card">
        <h2>Bumper Management</h2>
        
        {/* Tab navigation */}
        <div className="bumper-tabs">
          <button
            className={`bumper-tab ${activeTab === "sassy" ? "active" : ""}`}
            onClick={() => setActiveTab("sassy")}
          >
            Sassy Cards
          </button>
          <button
            className={`bumper-tab ${activeTab === "weather" ? "active" : ""}`}
            onClick={() => setActiveTab("weather")}
          >
            Weather Bumpers
          </button>
        </div>

        {error && activeTab === "sassy" && (
          <div className="error-message" style={{ marginBottom: "1rem" }}>
            <strong>Error:</strong> {error}
          </div>
        )}

        {status && (
          <div className="success-message" style={{ marginBottom: "1rem" }}>
            {status}
          </div>
        )}

        {isLoading && (
          <div className="loading-message" style={{ marginBottom: "1rem" }}>
            <div className="loading-spinner"></div>
            <span>Loading {activeTab === "sassy" ? "sassy card" : "weather bumper"} configuration...</span>
          </div>
        )}

        {activeTab === "sassy" && !loadingSassy && !config && (
          <div className="error-message" style={{ marginBottom: "1rem" }}>
            <strong>Error:</strong> Failed to load sassy card configuration. Please try reloading.
            <button
              className="btn btn-secondary"
              onClick={loadConfig}
              style={{ marginTop: "0.5rem" }}
            >
              Reload
            </button>
          </div>
        )}

        {activeTab === "sassy" && config && (
          <>
            <p className="help-text">
              Manage sassy card messages that appear between episodes. These messages are randomly
              selected from your list.
            </p>

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
          <div className="field">
            <label htmlFor="sassy-duration">Duration (seconds)</label>
            <input
              id="sassy-duration"
              type="number"
              min="1"
              max="30"
              step="0.5"
              value={config.duration_seconds}
              onChange={(e) =>
                handleUpdateField("duration_seconds", parseFloat(e.target.value))
              }
            />
          </div>
        </div>

        <div className="form-section">
          <div className="field">
            <label htmlFor="sassy-music-volume">Music Volume (0.0 - 1.0)</label>
            <input
              id="sassy-music-volume"
              type="number"
              min="0"
              max="1"
              step="0.1"
              value={config.music_volume}
              onChange={(e) =>
                handleUpdateField("music_volume", parseFloat(e.target.value))
              }
            />
          </div>
        </div>

        <div className="form-section">
          <div className="field">
            <label htmlFor="sassy-probability">Probability Between Episodes (0.0 - 1.0)</label>
            <input
              id="sassy-probability"
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
          </div>
        </div>

        <div className="form-section">
          <div className="field">
            <label htmlFor="sassy-style">Style</label>
            <select
              id="sassy-style"
              value={config.style}
              onChange={(e) => handleUpdateField("style", e.target.value)}
            >
              <option value="hbn-cozy">HBN Cozy</option>
              <option value="adult-swim-minimal">Adult Swim Minimal</option>
            </select>
          </div>
        </div>

        <div className="form-section">
          <h3>Messages ({config.messages?.length || 0})</h3>
          <div className="message-list">
            {(config.messages || []).map((message, index) => (
              <div key={index} className="message-item">
                {editingIndex === index ? (
                  <div className="message-edit">
                    <textarea
                      value={message}
                      onChange={(e) => {
                        if (!config.messages) return;
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
                        disabled={!config.messages || index === config.messages.length - 1}
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
          </>
        )}
      </div>

      {/* Weather Settings Tab */}
      {activeTab === "weather" && !loadingWeather && !weatherConfig && (
        <div className="card">
          <h2>Weather Bumper Settings</h2>
          <div className="error-message" style={{ marginBottom: "1rem" }}>
            Weather configuration not found. The server may need to initialize it first.
            <button
              className="btn btn-secondary"
              onClick={loadWeatherConfig}
              style={{ marginTop: "0.5rem" }}
            >
              Retry
            </button>
          </div>
        </div>
      )}

      {activeTab === "weather" && !loadingWeather && weatherConfig && (
        <div className="card">
          <h2>Weather Bumper Settings</h2>
          <p className="help-text">
            Configure dynamic weather bumpers that show current weather information between episodes.
            Weather data is fetched fresh at playback time.
          </p>

          <div className="form-section">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={weatherConfig.enabled}
                onChange={(e) => handleWeatherUpdateField("enabled", e.target.checked)}
              />
              <span>Enable weather bumpers</span>
            </label>
          </div>

          <div className="form-section">
            <h3>Location</h3>
            <div className="form-grid form-grid-2">
              <div className="field">
                <label htmlFor="weather-city">City</label>
                <input
                  id="weather-city"
                  type="text"
                  value={weatherConfig.location.city}
                  onChange={(e) => handleWeatherLocationUpdate("city", e.target.value)}
                  placeholder="Newark"
                />
              </div>
              <div className="field">
                <label htmlFor="weather-region">Region/State</label>
                <input
                  id="weather-region"
                  type="text"
                  value={weatherConfig.location.region}
                  onChange={(e) => handleWeatherLocationUpdate("region", e.target.value)}
                  placeholder="NJ"
                />
              </div>
            </div>
            <div className="form-grid form-grid-3">
              <div className="field">
                <label htmlFor="weather-country">Country</label>
                <input
                  id="weather-country"
                  type="text"
                  value={weatherConfig.location.country}
                  onChange={(e) => handleWeatherLocationUpdate("country", e.target.value)}
                  placeholder="US"
                />
              </div>
              <div className="field">
                <label htmlFor="weather-lat">Latitude</label>
                <input
                  id="weather-lat"
                  type="number"
                  step="0.0001"
                  value={weatherConfig.location.lat}
                  onChange={(e) => handleWeatherLocationUpdate("lat", parseFloat(e.target.value) || 0)}
                  placeholder="40.7357"
                />
              </div>
              <div className="field">
                <label htmlFor="weather-lon">Longitude</label>
                <input
                  id="weather-lon"
                  type="number"
                  step="0.0001"
                  value={weatherConfig.location.lon}
                  onChange={(e) => handleWeatherLocationUpdate("lon", parseFloat(e.target.value) || 0)}
                  placeholder="-74.1724"
                />
              </div>
            </div>
            <small>Find coordinates at <a href="https://www.latlong.net/" target="_blank" rel="noreferrer">latlong.net</a></small>
          </div>

          <div className="form-section">
            <h3>API Configuration</h3>
            <div className="field">
              <label htmlFor="weather-api-key">OpenWeatherMap API Key</label>
              <input
                id="weather-api-key"
                type="password"
                value={weatherConfig.api_key || ""}
                onChange={(e) => handleWeatherUpdateField("api_key", e.target.value)}
                placeholder={weatherConfig.api_key_set ? "API key is set (enter new to change)" : "Enter your API key"}
              />
              <small>
                Get a free API key at{" "}
                <a href="https://openweathermap.org/api" target="_blank" rel="noreferrer">
                  openweathermap.org/api
                </a>
                . The key will be set as an environment variable.
              </small>
            </div>
          </div>

          <div className="form-section">
            <h3>Display Settings</h3>
            <div className="form-grid form-grid-2">
              <div className="field">
                <label htmlFor="weather-units">Units</label>
                <select
                  id="weather-units"
                  value={weatherConfig.units}
                  onChange={(e) => handleWeatherUpdateField("units", e.target.value as "imperial" | "metric")}
                >
                  <option value="imperial">Imperial (°F)</option>
                  <option value="metric">Metric (°C)</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="weather-duration">Duration (seconds)</label>
                <input
                  id="weather-duration"
                  type="number"
                  min="1"
                  max="30"
                  step="0.5"
                  value={weatherConfig.duration_seconds}
                  onChange={(e) => handleWeatherUpdateField("duration_seconds", parseFloat(e.target.value))}
                />
              </div>
            </div>
          </div>

          <div className="form-section">
            <h3>Behavior</h3>
            <div className="form-grid form-grid-2">
              <div className="field">
                <label htmlFor="weather-probability">Probability Between Episodes (0.0 - 1.0)</label>
                <input
                  id="weather-probability"
                  type="number"
                  min="0"
                  max="1"
                  step="0.05"
                  value={weatherConfig.probability_between_episodes}
                  onChange={(e) =>
                    handleWeatherUpdateField("probability_between_episodes", parseFloat(e.target.value))
                  }
                />
                <small>1.0 = always show, 0.0 = never show</small>
              </div>
              <div className="field">
                <label htmlFor="weather-cache-ttl">Cache TTL (minutes)</label>
                <input
                  id="weather-cache-ttl"
                  type="number"
                  min="1"
                  max="60"
                  step="1"
                  value={weatherConfig.cache_ttl_minutes}
                  onChange={(e) => handleWeatherUpdateField("cache_ttl_minutes", parseFloat(e.target.value))}
                />
                <small>How long to cache weather data</small>
              </div>
            </div>
            {weatherConfig.music_volume !== undefined && (
              <div className="field" style={{ marginTop: "1.5rem" }}>
                <label htmlFor="weather-music-volume">Music Volume (0.0 - 1.0)</label>
                <input
                  id="weather-music-volume"
                  type="number"
                  min="0"
                  max="1"
                  step="0.1"
                  value={weatherConfig.music_volume}
                  onChange={(e) => handleWeatherUpdateField("music_volume", parseFloat(e.target.value))}
                />
              </div>
            )}
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
              onClick={loadWeatherConfig}
              disabled={saving}
            >
              Reload
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

