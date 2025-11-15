import { ChannelConfig } from "../api";

interface Props {
  channels: ChannelConfig[];
  selectedId: string;
  disabled?: boolean;
  onSelect: (id: string) => void;
}

function ChannelSelector({ channels, selectedId, disabled, onSelect }: Props) {
  return (
    <div className="field">
      <label htmlFor="channel-select">Channel</label>
      <select
        id="channel-select"
        value={selectedId}
        disabled={disabled || channels.length === 0}
        onChange={(evt) => onSelect(evt.target.value)}
      >
        {channels.length === 0 && <option value="">No channels configured</option>}
        {channels.map((channel) => (
          <option key={channel.id} value={channel.id}>
            {channel.name}
          </option>
        ))}
      </select>
    </div>
  );
}

export default ChannelSelector;

