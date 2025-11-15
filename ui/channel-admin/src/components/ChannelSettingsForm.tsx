import { ChannelConfig } from "../api";

interface Props {
  channel: ChannelConfig;
  onChange: (field: keyof ChannelConfig, value: unknown) => void;
}

function ChannelSettingsForm({ channel, onChange }: Props) {
  return (
    <section className="card">
      <h2>Playback Settings</h2>
      <div className="field">
        <label htmlFor="playback-mode">Playback Mode</label>
        <select
          id="playback-mode"
          value={channel.playback_mode}
          onChange={(evt) =>
            onChange("playback_mode", evt.target.value as ChannelConfig["playback_mode"])
          }
        >
          <option value="sequential">Sequential (episode order)</option>
          <option value="random">Random (shuffle shows/episodes)</option>
        </select>
      </div>
      <div className="field">
        <label>
          <input
            type="checkbox"
            checked={channel.loop_entire_library}
            onChange={(evt) => onChange("loop_entire_library", evt.target.checked)}
          />
          &nbsp;Loop entire library
        </label>
        <small>Restart from the beginning when the playlist reaches the end.</small>
      </div>
    </section>
  );
}

export default ChannelSettingsForm;

