# Your Own TV Channel

Create your own always-on TV channel from a folder of videos. Stream your favorite shows, movies, or home videos 24/7—just like a real TV network, but completely yours. Perfect for running on a Raspberry Pi with Kodi, or watch it in any web browser.

## Structure

- `server/` – Dockerized FFmpeg + Nginx streaming pipeline
  - `config/channel_settings.json` – persistent playlist configuration
- `client/pi_setup/` – Kodi automation scripts for Raspberry Pi
- `client/web_test/` – Browser-based HLS player for local verification

## Server Setup

From the repo root (`channel/`), build and run:

```
docker build -t tvchannel -f server/Dockerfile .
docker run -d \
  -p 8080:8080 \
  -v /path/to/videos:/media/tvchannel \
  -v "$(pwd)/assets:/app/assets" \
  -v "$(pwd)/server/config:/app/config" \
  --name tvchannel tvchannel
```

Your stream becomes available at `http://SERVER_IP:8080/channel/stream.m3u8`.

### Channel Settings

- Edit `server/config/channel_settings.json` (e.g., tweak `include_shows`) and keep it under version control or customize copies per deployment.
- Mount the config directory (`-v "$(pwd)/server/config:/app/config"`) so changes take effect immediately without rebuilding.
- Config files (`channel_settings.json` and `sassy_messages.json`) are included in the Docker image by default, so they're available even without mounting the volume.
- Optional overrides:
  - `CHANNEL_CONFIG` – point to a different JSON path inside the container.
  - `INCLUDE_SHOWS="Show A,Show B"` – quick one-off filter that takes precedence over the JSON file.

### HBN Channel Bug

- Every stream includes a subtle HBN network “bug” rendered from `assets/branding/hbn_logo_bug.png`.
- FFmpeg overlays the PNG in the top-right corner (≈12 % of video height, 40 px margin, ~80 % opacity) so it scales with any resolution.
- To customize the logo, replace the PNG (or mount a different `assets` directory) and restart the container. Advanced overrides are available through env vars such as `HBN_BUG_PATH`, `HBN_BUG_POSITION`, `HBN_BUG_HEIGHT_FRACTION`, and `HBN_BUG_ALPHA`.

### Files of Interest

- `generate_playlist.py` – scans your media root and writes `/app/hls/playlist.txt` (round-robins shows in sequential mode so you always cycle through the library).
- `stream.py` – loops through the playlist and pipes each file into FFmpeg HLS output `/app/hls/stream.m3u8`.
- `playlist_service.py` – shared helpers for inspecting/updating the playlist file plus playhead tracking metadata used by the admin UI.
- `entrypoint.sh` – regenerates playlist, starts Nginx, launches the streamer.

### Channel Admin API & UI

Manage channel playback behavior with the new FastAPI admin service plus a small React dashboard.

#### FastAPI Admin API

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn[standard]
uvicorn server.api.app:app --reload
```

The API reads `server/config/channel_settings.json` by default; override with `CHANNEL_CONFIG=/path/to/custom.json`.

#### React Control Panel

```bash
cd ui/channel-admin
npm install
VITE_API_BASE=http://localhost:8000 npm run dev
```

For production builds, run `npm run build` and serve the output from `ui/channel-admin/dist/`.

The admin UI lets you:

- Update the channel media root (TV folder), adjust playback options, and run **Discover shows** to scan the folder for new series that can be toggled into the playlist.
- Manage the **Playlist Management** page, which shows the next 25 controllable items, lets you drag items forward/back or skip them entirely, and applies changes without restarting FFmpeg (it edits the playlist file in-place).

Saving channel settings triggers a media-server restart so the stream picks up new changes.

> **Auto restart:** By default the API runs `docker restart tvchannel` after every save (if Docker is installed). Override the container name with `CHANNEL_DOCKER_CONTAINER`, or supply a custom command via `CHANNEL_RESTART_COMMAND`. If neither works, the API falls back to regenerating the playlist so changes apply on the next playback loop.

### Playlist API & Overrides

- `GET /api/channels/{channel_id}/playlist/next?limit=25` – returns the current player state (now playing + next 25 controllable episode segments).
- `POST /api/channels/{channel_id}/playlist/next` – accepts a `{"version": <mtime>, "desired": [episodePaths...], "skipped": [episodePaths...]}` payload to reorder or drop upcoming episodes without restarting the stream.

Environment overrides:

- `CHANNEL_PLAYLIST_PATH` – point the API/playlist manager to a custom playlist file path (defaults to `/app/hls/playlist.txt`, falling back to `server/hls/playlist.txt` during local dev).
- `CHANNEL_PLAYHEAD_PATH` – where the streamer writes JSON metadata about the currently playing entry (defaults to `/app/hls/playhead.json`).

### HBN “Up Next” Dynamic Bumpers

The system can automatically create “Up Next” bumpers for each show in your playlist. On first run, when `generate_playlist.py` encounters a show it hasn’t seen before, it:

- Renders a 6-second bumper as `assets/bumpers/up_next/<show>.mp4` by default.
- Inserts that bumper before each episode for that show.

You can also manually generate a bumper:

```bash
python -m scripts.bumpers.cli_up_next \
  --title "Futurama" \
  --out assets/bumpers/up_next/futurama.mp4
```

Add `--seed <int>` if you want to reproduce the exact randomized look; omitting it yields a fresh variation each render.

Episode filenames that contain tokens like `S02E05`, `2x05`, or live inside folders such as `Season 02` automatically add a subtitle line to the bumper so viewers see the exact season and episode numbers with every “Up Next” card. Each render also picks a randomized on-brand gradient + pattern treatment, so the bumpers feel lively without clashing with channel colors.

When you run `python server/generate_playlist.py`, the generator immediately writes a short “seed” chunk of upcoming episodes (default 50) straight to the playlist so the stream can start without waiting for bumper renders. The script then keeps running, rendering bumpers in the background and appending the fully-produced entries after the seed chunk.

### Sassy Cards

Between episodes the playlist can optionally splice in short “sassy card” bumpers (think Adult Swim vibes). Configure them via `server/config/sassy_messages.json`:

- `enabled` – master switch for the feature.
- `probability_between_episodes` – chance (0–1) to insert a card after any given episode.
- `duration_seconds`, `style` (either `hbn-cozy` gradient with logo/music or `adult-swim-minimal` black & white), and `messages` – customize cadence, look, and text.

On playlist generation the renderer creates one MP4 per message under `assets/bumpers/sassy/` by default (only rerendering when a file is missing) and then deals them out from a shuffled deck so every phrase appears once before repeating. Tweak the JSON and rerun `generate_playlist.py` (or hit the Admin API “Save” button) to apply changes immediately.

### Network Branding Bumpers

Full network branding bumpers featuring the complete HBN logo are automatically inserted periodically (approximately once per hour, or roughly every 25-30 episodes). These 8-second bumpers display the full logo with "HILLSIDE BROADCASTING NETWORK" and station info, animated with subtle fade-ins and scale effects. Each bumper is mixed with a randomly selected track from your music library for a polished, professional feel.

The network bumper is generated once on first playlist build and stored at `assets/bumpers/network/network_brand.mp4` by default. It uses the full logo SVG (or PNG fallback) from `assets/branding/hbn_logo_bug.svg`.

To move all rendered bumpers out of the Docker image and onto your media volume (for example, under `/media/tvchannel/bumpers` which might be backed by `/Volumes/media/tv/bumpers` on the host), set:

```bash
# Inside the container (or via docker run -e / compose env)
HBN_BUMPERS_ROOT=/media/tvchannel/bumpers
```

With this set, all new “Up Next”, sassy, and network bumpers are written under:

- `/media/tvchannel/bumpers/up_next`
- `/media/tvchannel/bumpers/sassy`
- `/media/tvchannel/bumpers/network`

### Playlist Generation Details

- **Sequential mode**: shows are round-robined so each pass through the playlist includes one episode per included show before looping back (keeps the stream varied even with large seasons).
- **Random mode**: still uses the existing weighted random logic based on per-show `weight`.
- Playlist + playhead files live under `/app/hls/` when running in Docker. During local development (outside the container) the generator/streamer fall back to `server/hls/`.
- For faster test iterations, playlist generation stops after the first 500 episodes by default. Override with `PLAYLIST_EPISODE_LIMIT=<int>` if you need longer queues.
- Control how many bumper-free "seed" episodes get written immediately with `PLAYLIST_SEED_LIMIT=<int>` (defaults to 50). Set it to `0` if you'd rather block until every bumper is rendered.

### Watch Progress Tracking

The system automatically tracks which episodes have been watched and resumes playback from where you left off when the playlist is regenerated:

- **Automatic tracking**: Episodes are marked as watched when they finish playing
- **Resume on regeneration**: When the playlist is regenerated, it automatically starts from the next episode after the last watched one
- **Progress storage**: Watch progress is stored in `/app/hls/watch_progress.json` (or `server/hls/watch_progress.json` during local development)
- **Override path**: Set `CHANNEL_WATCH_PROGRESS_PATH` environment variable to use a custom location
- If the last watched episode isn't found in the new playlist (e.g., show was removed), playback starts from the beginning

## 🧪 Local Mac Testing (no Raspberry Pi required)

1. **Prepare media directory** on your Mac:

   ```bash
   mkdir -p ~/tv_media
   # copy some .mp4 / .mkv files into ~/tv_media
   ```

2. **Build and run the server container**:

   ```bash
   docker build -t tvchannel -f server/Dockerfile .
   docker run -d \
     -p 8080:8080 \
     -v ~/tv_media:/media/tvchannel \
     -v "$(pwd)/assets:/app/assets" \
     -v "$(pwd)/server/config:/app/config" \
     --name tvchannel tvchannel
   ```

   The stream is served at `http://localhost:8080/channel/stream.m3u8`.

3. **Start the web test client**:

   ```bash
   cd ../client/web_test
   chmod +x serve_test_client.sh
   ./serve_test_client.sh
   ```

4. **Open the browser player**:

   Visit `http://localhost:8081` in Chrome (hls.js) or Safari (native HLS) to watch the channel.

5. **Alternative: test with VLC**:

   - VLC → “Open Network…”
   - URL: `http://localhost:8080/channel/stream.m3u8`
   - Click Play

## Raspberry Pi Client

On the Pi (Raspberry Pi OS):

```
cd channel/client/pi_setup
bash install_kodi.sh
bash configure_kodi.sh <SERVER_IP>
sudo reboot
```

Kodi auto-starts (systemd service enabled) and IPTV Simple Client plays the channel.

## Next Ideas

- Multiple channels / schedules
- Bumpers, overlays, live inputs
- Web content manager & EPG

