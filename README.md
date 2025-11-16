# Your Own TV Channel 📺

Create your own always-on TV channel from a folder of videos. Stream your favorite shows, movies, or home videos 24/7—just like a real TV network, but completely yours. Perfect for running on a Raspberry Pi with Kodi, or watch it in any web browser.

## ✨ Features

- 🎬 **Automatic Playlist Generation** - Scans your media library and creates a seamless 24/7 stream
- 🎨 **Dynamic Bumpers** - "Up Next" cards, sassy intermissions, and network branding bumpers
- 🎮 **Web Admin Panel** - React-based control panel for managing channels, playlists, and settings
- 📱 **Multiple Playback Modes** - Sequential or weighted random playback with per-show configuration
- 🔄 **Watch Progress Tracking** - Automatically resumes from where you left off
- 🎯 **Real-time Playlist Management** - Reorder or skip episodes without restarting the stream
- 🏷️ **Smart Metadata** - Automatic season/episode detection from filenames
- 🎵 **Music Integration** - Background music for bumpers from your music library

## 📋 Table of Contents

- [Quick Start](#-quick-start)
- [Project Structure](#-project-structure)
- [Server Setup](#-server-setup)
- [Channel Admin](#-channel-admin)
- [Bumpers System](#-bumpers-system)
- [Playlist Management](#-playlist-management)
- [Client Setup](#-client-setup)
- [Configuration](#-configuration)
- [API Reference](#-api-reference)
- [Troubleshooting](#-troubleshooting)

## 🚀 Quick Start

### Prerequisites

- Docker and Docker Compose (for server)
- Python 3.9+ (for local development)
- Node.js 18+ (for admin UI development)
- Video files in a supported format (MP4, MKV, AVI, etc.)

### 1. Prepare Your Media

Organize your videos in a folder structure like:

```
~/tv_media/
├── Show Name 1/
│   ├── Season 01/
│   │   ├── Episode 01.mp4
│   │   └── Episode 02.mp4
│   └── Season 02/
│       └── ...
└── Show Name 2/
    └── ...
```

### 2. Start the Server

```bash
# Build and run the Docker container
docker build -t tvchannel -f server/Dockerfile .
docker run -d \
  -p 8080:8080 \
  -v ~/tv_media:/media/tvchannel \
  -v "$(pwd)/assets:/app/assets" \
  -v "$(pwd)/server/config:/app/config" \
  --name tvchannel tvchannel
```

Your stream is now available at: `http://localhost:8080/channel/stream.m3u8`

### 3. Watch the Channel

**Web Browser:**
```bash
cd client/web_test
./serve_test_client.sh
# Open http://localhost:8081 in Chrome or Safari
```

**VLC:**
- Open VLC → Media → Open Network Stream
- URL: `http://localhost:8080/channel/stream.m3u8`

**Kodi (Raspberry Pi):**
```bash
cd client/pi_setup
bash install_kodi.sh
bash configure_kodi.sh <SERVER_IP>
sudo reboot
```

## 📁 Project Structure

```
channel/
├── server/                 # Dockerized streaming server
│   ├── api/               # FastAPI admin API
│   │   ├── app.py        # Main API endpoints
│   │   ├── media_control.py
│   │   └── settings_service.py
│   ├── config/           # Channel configuration
│   │   ├── channel_settings.json
│   │   └── sassy_messages.json
│   ├── hls/              # HLS stream files (generated)
│   ├── generate_playlist.py    # Playlist generator
│   ├── stream.py         # FFmpeg streaming loop
│   ├── playlist_service.py     # Playlist utilities
│   ├── Dockerfile
│   └── nginx.conf
├── ui/channel-admin/      # React admin panel
│   └── src/
│       ├── components/   # React components
│       └── api.ts        # API client
├── client/
│   ├── pi_setup/         # Kodi automation scripts
│   └── web_test/         # Browser HLS player
├── assets/
│   ├── branding/         # Network logos
│   ├── bumpers/          # Generated bumpers
│   └── music/            # Background music tracks
└── scripts/
    └── bumpers/          # Bumper generation utilities
```

## 🖥️ Server Setup

### Docker Deployment (Recommended)

The server runs in a Docker container with FFmpeg and Nginx for HLS streaming.

```bash
docker build -t tvchannel -f server/Dockerfile .
docker run -d \
  -p 8080:8080 \
  -v /path/to/videos:/media/tvchannel \
  -v "$(pwd)/assets:/app/assets" \
  -v "$(pwd)/server/config:/app/config" \
  --name tvchannel tvchannel
```

**Environment Variables:**
- `CHANNEL_CONFIG` - Path to channel settings JSON (default: `/app/config/channel_settings.json`)
- `HBN_BUMPERS_ROOT` - Base path for bumper storage (default: `/app/assets/bumpers`)
- `CHANNEL_PLAYLIST_PATH` - Playlist file path (default: `/app/hls/playlist.txt`)
- `CHANNEL_PLAYHEAD_PATH` - Playhead tracking file (default: `/app/hls/playhead.json`)
- `CHANNEL_WATCH_PROGRESS_PATH` - Watch progress file (default: `/app/hls/watch_progress.json`)
- `PLAYLIST_EPISODE_LIMIT` - Max episodes to generate (default: `500`)
- `PLAYLIST_SEED_LIMIT` - Episodes to write before bumper rendering (default: `50`)

### Local Development

For development without Docker:

```bash
# Install dependencies
pip install -r requirements.txt

# Run playlist generator
python server/generate_playlist.py

# Start streaming
python server/stream.py

# Start admin API (separate terminal)
cd server/api
uvicorn app:app --reload --port 8000
```

### Channel Settings

Edit `server/config/channel_settings.json` to configure your channel:

```json
{
  "channels": [
    {
      "id": "default",
      "name": "My TV Channel",
      "enabled": true,
      "media_root": "/media/tvchannel",
      "playback_mode": "sequential",
      "loop_entire_library": true,
      "shows": [
        {
          "id": "show-1",
          "label": "Show Name",
          "path": "Show Name",
          "include": true,
          "playback_mode": "inherit",
          "weight": 1.0
        }
      ]
    }
  ]
}
```

**Configuration Options:**
- `playback_mode` - `"sequential"` or `"random"` for channel-wide playback
- `loop_entire_library` - Whether to loop through all episodes
- `shows` - Array of show configurations with per-show playback mode and weight
- Each show can `"inherit"`, `"sequential"`, or `"random"` playback mode

### Network Branding

The channel automatically overlays a network "bug" (logo) in the top-right corner of all streams. Customize it by:

1. Replace `assets/branding/hbn_logo_bug.png` with your logo
2. Or set environment variables:
   - `HBN_BUG_PATH` - Path to logo file
   - `HBN_BUG_POSITION` - Position (default: `"topright"`)
   - `HBN_BUG_HEIGHT_FRACTION` - Size relative to video height (default: `0.12`)
   - `HBN_BUG_ALPHA` - Opacity 0-1 (default: `0.8`)

## 🎛️ Channel Admin

### Admin API Setup

The FastAPI admin service provides a REST API for managing channels:

```bash
# Install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn[standard] pydantic

# Run the API
cd server
uvicorn api.app:app --reload --port 8000
```

The API is available at `http://localhost:8000` with interactive docs at `http://localhost:8000/docs`.

### Admin UI Setup

The React admin panel provides a web interface for channel management:

```bash
cd ui/channel-admin
npm install
VITE_API_BASE=http://localhost:8000 npm run dev
```

Open `http://localhost:5173` to access the admin panel.

**For Production:**
```bash
npm run build
# Serve the dist/ folder with nginx or any static file server
```

### Admin UI Features

- **Channel Settings** - Update media root, playback mode, and discover shows
- **Show Management** - Toggle shows on/off, adjust weights, set playback modes
- **Playlist Management** - View and reorder upcoming episodes in real-time
- **Episode Skipping** - Skip unwanted episodes without restarting the stream

## 🎬 Bumpers System

### Up Next Bumpers

Automatically generated 6-second cards that appear before each episode, showing what's coming up next.

**Manual Generation:**
```bash
python -m scripts.bumpers.cli_up_next \
  --title "Show Name" \
  --out assets/bumpers/up_next/show_name.mp4
```

**Customization:**
- Season/episode metadata is automatically detected from filenames
- Supports patterns like `S02E05`, `2x05`, or `Season 02/Episode 05.mp4`
- Each bumper uses a randomized gradient and pattern treatment

### Sassy Cards

Short intermission cards that can appear between episodes (inspired by Adult Swim).

**Configuration** (`server/config/sassy_messages.json`):
```json
{
  "enabled": true,
  "probability_between_episodes": 0.3,
  "duration_seconds": 4,
  "style": "hbn-cozy",
  "messages": [
    "We'll be right back",
    "Stay tuned",
    "Don't go anywhere"
  ]
}
```

**Styles:**
- `hbn-cozy` - Gradient background with logo and background music
- `adult-swim-minimal` - Black and white minimal style

### Network Branding Bumpers

Full network identity bumpers featuring the complete logo, displayed approximately every 25-30 episodes (about once per hour).

- Automatically generated on first playlist build
- 8-second duration with fade-in/scale animations
- Background music randomly selected from `assets/music/`
- Stored at `assets/bumpers/network/network_brand.mp4`

## 📋 Playlist Management

### Playlist Structure

The playlist is a simple text file (`/app/hls/playlist.txt`) with one file path per line:

```
/media/tvchannel/Show 1/Season 01/Episode 01.mp4
/media/tvchannel/Show 1/Season 01/Episode 02.mp4
/assets/bumpers/up_next/show_1.mp4
/media/tvchannel/Show 2/Season 01/Episode 01.mp4
...
```

### Playback Modes

**Sequential Mode:**
- Episodes play in order
- Shows are round-robin (one episode per show before cycling)
- Ensures variety even with large seasons

**Random Mode:**
- Episodes selected randomly based on show weights
- Higher weight = more frequent playback
- Each show can have its own playback mode

### Watch Progress

The system tracks which episodes you've watched and automatically resumes from where you left off:

- Progress stored in `watch_progress.json`
- Updated automatically when episodes finish
- Resume position maintained across playlist regenerations
- Falls back to beginning if watched episode not found

### Real-time Playlist Editing

Use the admin UI or API to:

- **Reorder Episodes** - Move items up/down in the queue
- **Skip Episodes** - Remove items from upcoming window
- **Skip Current** - Jump to the next episode immediately

Changes take effect without restarting the stream—the playlist file is edited in-place.

## 🖥️ Client Setup

### Web Browser (Local Testing)

```bash
cd client/web_test
chmod +x serve_test_client.sh
./serve_test_client.sh
```

Open `http://localhost:8081` in Chrome or Safari. Chrome uses hls.js for playback; Safari has native HLS support.

### Kodi on Raspberry Pi

```bash
# SSH into your Raspberry Pi
cd channel/client/pi_setup

# Install Kodi and IPTV Simple Client
bash install_kodi.sh

# Configure to auto-start and play your channel
bash configure_kodi.sh <YOUR_SERVER_IP>

# Reboot to start Kodi
sudo reboot
```

After reboot, Kodi will automatically start and begin streaming your channel.

### VLC Media Player

1. Open VLC
2. Media → Open Network Stream
3. Enter URL: `http://YOUR_SERVER_IP:8080/channel/stream.m3u8`
4. Click Play

## ⚙️ Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CHANNEL_CONFIG` | `/app/config/channel_settings.json` | Channel settings file path |
| `HBN_BUMPERS_ROOT` | `/app/assets/bumpers` | Base directory for bumper storage |
| `CHANNEL_PLAYLIST_PATH` | `/app/hls/playlist.txt` | Playlist file location |
| `CHANNEL_PLAYHEAD_PATH` | `/app/hls/playhead.json` | Current playback position |
| `CHANNEL_WATCH_PROGRESS_PATH` | `/app/hls/watch_progress.json` | Watch history |
| `PLAYLIST_EPISODE_LIMIT` | `500` | Maximum episodes to generate |
| `PLAYLIST_SEED_LIMIT` | `50` | Episodes before bumper rendering starts |
| `CHANNEL_DOCKER_CONTAINER` | `tvchannel` | Docker container name for restarts |
| `CHANNEL_RESTART_COMMAND` | `docker restart tvchannel` | Command to restart media server |

### Configuration Files

**`channel_settings.json`** - Main channel configuration
- Channel list with media roots and playback modes
- Show configurations with inclusion flags and weights

**`sassy_messages.json`** - Sassy card configuration
- Enable/disable feature
- Probability and style settings
- Custom messages array

## 📡 API Reference

### Channel Management

**List All Channels**
```http
GET /api/channels
```

**Get Channel Details**
```http
GET /api/channels/{channel_id}
```

**Update Channel**
```http
PUT /api/channels/{channel_id}
Content-Type: application/json

{
  "id": "default",
  "name": "My Channel",
  "enabled": true,
  "media_root": "/media/tvchannel",
  "playback_mode": "sequential",
  "loop_entire_library": true,
  "shows": [...]
}
```

**Discover Shows**
```http
GET /api/channels/{channel_id}/shows/discover?media_root=/path/to/media
```

### Playlist Management

**Get Playlist Snapshot**
```http
GET /api/channels/{channel_id}/playlist/next?limit=25
```

Returns current episode and next N controllable items.

**Update Playlist**
```http
POST /api/channels/{channel_id}/playlist/next
Content-Type: application/json

{
  "version": 1234567890.123,
  "desired": ["/path/to/episode1.mp4", "/path/to/episode2.mp4"],
  "skipped": ["/path/to/episode3.mp4"]
}
```

**Skip Current Episode**
```http
POST /api/channels/{channel_id}/playlist/skip-current
```

### Health Check

```http
GET /api/healthz
```

Returns `{"status": "ok"}` if the API is running.

## 🔧 Troubleshooting

### Stream Not Playing

1. **Check container logs:**
   ```bash
   docker logs tvchannel
   ```

2. **Verify media files exist:**
   ```bash
   docker exec tvchannel ls -la /media/tvchannel
   ```

3. **Check playlist generation:**
   ```bash
   docker exec tvchannel cat /app/hls/playlist.txt | head -20
   ```

4. **Verify HLS files are being created:**
   ```bash
   docker exec tvchannel ls -la /app/hls/ | grep .ts
   ```

### Playlist Not Updating

- Ensure `server/config/channel_settings.json` is mounted as a volume
- Check file permissions on the config directory
- Restart the container after config changes:
  ```bash
  docker restart tvchannel
  ```

### Bumpers Not Generating

- Verify `assets/` directory is mounted
- Check disk space (bumpers require temporary storage)
- Look for errors in container logs related to FFmpeg

### Admin UI Not Connecting

- Verify the API is running: `curl http://localhost:8000/api/healthz`
- Check CORS settings if accessing from a different origin
- Verify `VITE_API_BASE` environment variable matches your API URL

### Watch Progress Issues

- Check `watch_progress.json` exists and is writable
- Verify file paths in progress file match actual file locations
- Reset watch progress by deleting `watch_progress.json` and regenerating playlist

### Performance Issues

- Reduce `PLAYLIST_EPISODE_LIMIT` for faster playlist generation
- Increase `PLAYLIST_SEED_LIMIT` to write episodes before bumper rendering
- Monitor disk space in `/app/hls/` (HLS segments accumulate)
- Consider limiting watch progress history

## 🎯 Architecture Overview

```
┌─────────────────┐
│  Media Library  │
│  (/media/tv)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ generate_       │
│ playlist.py     │─────► Playlist.txt
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   stream.py     │─────► FFmpeg ───► HLS Segments
│  (FFmpeg loop)  │                      │
└────────┬────────┘                      │
         │                               ▼
         │                        ┌──────────────┐
         │                        │   Nginx      │
         │                        │  (HTTP)      │
         └────────────────────────┼──────────────┘
                                  │
                                  ▼
                        ┌─────────────────┐
                        │  Clients        │
                        │  (Kodi/Web/VLC) │
                        └─────────────────┘

         ┌─────────────────┐
         │   FastAPI       │
         │   Admin API     │
         └────────┬────────┘
                  │
                  ▼
         ┌─────────────────┐
         │  React Admin UI │
         └─────────────────┘
```

## 📝 Development Notes

### Key Files

- **`server/generate_playlist.py`** - Scans media, generates playlist with bumpers
- **`server/stream.py`** - Main streaming loop, FFmpeg process management
- **`server/playlist_service.py`** - Playlist utilities, watch progress, segment building
- **`server/api/app.py`** - FastAPI REST endpoints for admin interface
- **`ui/channel-admin/src/App.tsx`** - React admin panel main component

### Adding New Features

1. **New Bumper Types:** Add renderer in `scripts/bumpers/`
2. **API Endpoints:** Add routes in `server/api/app.py`
3. **UI Components:** Add React components in `ui/channel-admin/src/components/`

### Testing

- Local Mac testing: See [Local Mac Testing](#-local-mac-testing-no-raspberry-pi-required) section
- Manual testing recommended (no automated tests currently)
- Check container logs for debugging

## 🧪 Local Mac Testing (no Raspberry Pi required)

1. **Prepare media directory:**
   ```bash
   mkdir -p ~/tv_media
   # Copy some .mp4 / .mkv files into ~/tv_media
   ```

2. **Build and run the server:**
   ```bash
   docker build -t tvchannel -f server/Dockerfile .
   docker run -d \
     -p 8080:8080 \
     -v ~/tv_media:/media/tvchannel \
     -v "$(pwd)/assets:/app/assets" \
     -v "$(pwd)/server/config:/app/config" \
     --name tvchannel tvchannel
   ```

3. **Start the web test client:**
   ```bash
   cd client/web_test
   chmod +x serve_test_client.sh
   ./serve_test_client.sh
   ```

4. **Open the browser player:**
   - Visit `http://localhost:8081` in Chrome (hls.js) or Safari (native HLS)

## 🚧 Future Ideas

- Multiple channels / schedules
- Live input integration
- Electronic Program Guide (EPG)
- Commercial break insertion
- User authentication for admin panel
- Mobile app support
- Chromecast integration

## 📄 License

[Add your license information here]

---

**Enjoy your personal TV channel!** 🎉

For issues, questions, or contributions, please check the `ISSUES.md` and `PROJECT_STATUS.md` files.
