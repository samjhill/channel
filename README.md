# Always-On TV Channel

Self-hosted TV channel stack that streams a folder of videos through FFmpeg → HLS and plays it on a Raspberry Pi running Kodi.

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
- Optional overrides:
  - `CHANNEL_CONFIG` – point to a different JSON path inside the container.
  - `INCLUDE_SHOWS="Show A,Show B"` – quick one-off filter that takes precedence over the JSON file.

### HBN Channel Bug

- Every stream includes a subtle HBN network “bug” rendered from `assets/branding/hbn_logo_bug.png`.
- FFmpeg overlays the PNG in the top-right corner (≈12 % of video height, 40 px margin, ~80 % opacity) so it scales with any resolution.
- To customize the logo, replace the PNG (or mount a different `assets` directory) and restart the container. Advanced overrides are available through env vars such as `HBN_BUG_PATH`, `HBN_BUG_POSITION`, `HBN_BUG_HEIGHT_FRACTION`, and `HBN_BUG_ALPHA`.

### Files of Interest

- `generate_playlist.py` – scans `/media/tvchannel` and writes `/app/hls/playlist.txt`.
- `stream.py` – loops through the playlist and pipes each file into FFmpeg HLS output `/app/hls/stream.m3u8`.
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

The admin UI lets you update the channel media root (TV folder), adjust playback options, and run **Discover shows** to scan the folder for new series that can be toggled into the playlist.

### HBN “Up Next” Dynamic Bumpers

The system can automatically create “Up Next” bumpers for each show in your playlist. On first run, when `generate_playlist.py` encounters a show it hasn’t seen before, it:

- Renders a 6-second bumper as `assets/bumpers/up_next/<show>.mp4`.
- Inserts that bumper before each episode for that show.

You can also manually generate a bumper:

```bash
python -m scripts.bumpers.cli_up_next \
  --title "Futurama" \
  --out assets/bumpers/up_next/futurama.mp4
```

Add `--seed <int>` if you want to reproduce the exact randomized look; omitting it yields a fresh variation each render.

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

