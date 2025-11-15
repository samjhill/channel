import { PlaybackMode, ShowConfig } from "../api";

interface Props {
  shows: ShowConfig[];
  channelMode: PlaybackMode;
  onChange: (index: number, updated: Partial<ShowConfig>) => void;
  onBulkAction: (action: "selectAll" | "deselectAll" | "normalizeWeights") => void;
}

const playbackOptions: { label: string; value: PlaybackMode }[] = [
  { label: "Inherit channel setting", value: "inherit" },
  { label: "Sequential", value: "sequential" },
  { label: "Random", value: "random" }
];

function ShowTable({ shows, channelMode, onChange, onBulkAction }: Props) {
  if (!shows.length) {
    return (
      <section className="card">
        <h2>Shows</h2>
        <p>No shows found for this channel.</p>
      </section>
    );
  }

  return (
    <section className="card">
      <div className="shows-header">
        <h2>Shows ({shows.length})</h2>
        <div className="shows-actions">
          <button className="btn btn-light" onClick={() => onBulkAction("selectAll")}>
            Select all
          </button>
          <button className="btn btn-light" onClick={() => onBulkAction("deselectAll")}>
            Deselect all
          </button>
          <button className="btn btn-light" onClick={() => onBulkAction("normalizeWeights")}>
            Normalize weights
          </button>
        </div>
      </div>
      <table className="shows-table">
        <thead>
          <tr>
            <th>Include</th>
            <th>Show Name</th>
            <th>Path</th>
            <th>Playback Mode</th>
            <th>Weight</th>
          </tr>
        </thead>
        <tbody>
          {shows.map((show, idx) => (
            <tr key={show.id}>
              <td>
                <input
                  type="checkbox"
                  checked={show.include}
                  onChange={(evt) => onChange(idx, { include: evt.target.checked })}
                />
              </td>
              <td>
                <input
                  type="text"
                  value={show.label}
                  onChange={(evt) => onChange(idx, { label: evt.target.value })}
                />
              </td>
              <td>{show.path}</td>
              <td>
                <select
                  value={show.playback_mode}
                  onChange={(evt) =>
                    onChange(idx, { playback_mode: evt.target.value as PlaybackMode })
                  }
                >
                  {playbackOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                      {option.value === "inherit" ? ` (${channelMode})` : ""}
                    </option>
                  ))}
                </select>
              </td>
              <td>
                <input
                  type="number"
                  min={0.1}
                  max={5}
                  step={0.1}
                  value={show.weight}
                  onChange={(evt) => {
                    const next = Math.max(0.1, Math.min(5, Number(evt.target.value)));
                    onChange(idx, { weight: next });
                  }}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

export default ShowTable;

