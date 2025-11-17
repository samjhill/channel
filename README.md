# Your Own TV Channel 📺

Ever wanted your own 24/7 TV channel? This project lets you turn a folder full of videos into a continuous stream that runs all day, every day. It's like having your own personal TV network—perfect for running on a Raspberry Pi with Kodi, or just watching in your browser.

I built this because I wanted to watch my collection of shows and movies in a more TV-like way, with bumpers and everything. It's been a fun project and I hope you find it useful too.

## What It Does

The basic idea is simple: you point it at a folder of videos, and it creates a never-ending playlist that streams 24/7. But there's a lot of nice touches:

- **Automatic playlist generation** - Just drop your videos in folders and it figures out the rest
- **"Up Next" bumpers** - Little cards that show what's coming up, just like real TV
- **Sassy intermissions** - Short cards between episodes (inspired by Adult Swim's style)
- **Weather bumpers** - Optional dynamic "Current Weather" cards with fresh weather data
- **Web admin panel** - A nice React interface for managing everything
- **Watch progress tracking** - Remembers where you left off
- **Real-time playlist control** - Skip episodes or reorder the queue without restarting
- **Smart metadata** - Automatically detects season/episode numbers from filenames
- **Network branding** - Overlays your logo on the stream (the "bug" in the corner)

## Quick Start

### What You'll Need

- Docker (for running the server)
- Some video files (MP4, MKV, AVI, etc.)
- Python 3.9+ if you want to develop locally
- Node.js 18+ if you want to work on the admin UI

### Step 1: Organize Your Videos

Put your videos in folders like this:

```
~/tv_media/
├── Your Show Name/
│   ├── Season 01/
│   │   ├── Episode 01.mp4
│   │   └── Episode 02.mp4
│   └── Season 02/
│       └── ...
└── Another Show/
    └── ...
```

The system is pretty flexible with naming—it can figure out seasons and episodes from patterns like `S02E05`, `2x05`, or even `Season 02/Episode 05.mp4`.

### Step 2: Start the Server

Build and run the Docker container:

```bash
docker build -t tvchannel -f server/Dockerfile .
docker run -d \
  -p 8080:8080 \
  -v ~/tv_media:/media/tvchannel \
  -v "$(pwd)/assets:/app/assets" \
  -v "$(pwd)/server/config:/app/config" \
  --name tvchannel tvchannel
```

That's it! Your stream should now be available at `http://localhost:8080/channel/stream.m3u8`

### Step 3: Watch It

You've got a few options:

**In a web browser:**
```bash
cd client/web_test
./serve_test_client.sh
# Then open http://localhost:8081 in Chrome or Safari
```

**In VLC:**
- Open VLC → Media → Open Network Stream
- Paste: `http://localhost:8080/channel/stream.m3u8`

**On a Raspberry Pi with Kodi:**
```bash
cd client/pi_setup
bash install_kodi.sh
bash configure_kodi.sh <YOUR_SERVER_IP>
sudo reboot
```

After reboot, Kodi will automatically start and play your channel. It's pretty cool to see it boot up and start streaming.

## How It Works

Here's the basic flow:

1. **Playlist generation** - `generate_playlist.py` scans your media folder and creates a playlist file. It also generates bumpers (those "Up Next" cards and intermissions) and mixes them in.

2. **Streaming** - `stream.py` reads the playlist and uses FFmpeg to stream each video to HLS format. It runs in a loop, so when it reaches the end, it starts over.

3. **Serving** - Nginx serves the HLS stream files so clients can watch.

4. **Admin interface** - A FastAPI backend and React frontend let you manage channels, reorder playlists, skip episodes, etc.

The playlist is just a text file with one file path per line. Episodes, bumpers, and intermissions are all mixed together. When you want to skip something or reorder, the system edits this file in place—no need to restart the stream.

## Configuration

### Channel Settings

Edit `server/config/channel_settings.json` to set up your channel. Here's a basic example:

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

**Playback modes:**
- `sequential` - Episodes play in order, shows rotate round-robin style
- `random` - Episodes are picked randomly based on show weights

Each show can have its own playback mode, or it can inherit from the channel. Shows also have weights (1.0 is default, higher = plays more often in random mode).

### Network Branding

The system automatically overlays a logo "bug" in the top-right corner of all streams. To customize it:

1. Replace `assets/branding/hbn_logo_bug.png` with your own logo
2. Or set these environment variables:
   - `HBN_BUG_PATH` - Path to your logo file
   - `HBN_BUG_POSITION` - Where to put it (default: `"topright"`)
   - `HBN_BUG_HEIGHT_FRACTION` - Size relative to video (default: `0.12`)
   - `HBN_BUG_ALPHA` - Opacity 0-1 (default: `0.8`)

### Environment Variables

There are a bunch of environment variables you can set if you need to customize things:

- `CHANNEL_CONFIG` - Path to channel settings (default: `/app/config/channel_settings.json`)
- `HBN_BUMPERS_ROOT` - Where to store bumpers (default: `/app/assets/bumpers`)
- `CHANNEL_PLAYLIST_PATH` - Playlist file location (default: `/app/hls/playlist.txt`)
- `CHANNEL_PLAYHEAD_PATH` - Current playback position (default: `/app/hls/playhead.json`)
- `CHANNEL_WATCH_PROGRESS_PATH` - Watch history (default: `/app/hls/watch_progress.json`)
- `PLAYLIST_EPISODE_LIMIT` - Max episodes to generate (default: `500`)
- `PLAYLIST_SEED_LIMIT` - Episodes to write before bumper rendering (default: `50`)

Most of these you probably won't need to change, but they're there if you do.

## The Admin Panel

There's a web-based admin interface for managing everything. It's built with React and connects to a FastAPI backend.

### Running the Admin API

```bash
# Set up a virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Start the API
cd server
uvicorn api.app:app --reload --port 8000
```

The API will be at `http://localhost:8000`, and there are interactive docs at `http://localhost:8000/docs` (FastAPI's auto-generated Swagger UI).

### Running the Admin UI

```bash
cd ui/channel-admin
npm install
VITE_API_BASE=http://localhost:8000 npm run dev
```

Then open `http://localhost:5173` in your browser.

The admin panel lets you:
- Update channel settings (media root, playback mode, etc.)
- Discover shows in your media folder
- Toggle shows on/off, adjust weights, set playback modes
- View and reorder the upcoming playlist in real-time
- Skip episodes without restarting the stream

For production, just build it and serve the `dist/` folder with nginx or any static file server.

## Bumpers

Bumpers are those short video clips that play between content. There are three types:

### Up Next Bumpers

These are 6-second cards that show what's coming up next. They're automatically generated when the playlist is built. The system extracts the show name and episode info from the filename and creates a nice-looking card with a random gradient background.

You can also generate them manually:
```bash
python -m scripts.bumpers.cli_up_next \
  --title "Show Name" \
  --out assets/bumpers/up_next/show_name.mp4
```

### Sassy Cards

These are short intermission cards inspired by Adult Swim's style. They show random messages like "We'll be right back" or "Stay tuned" between episodes.

Configure them in `server/config/sassy_messages.json`:

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

The `probability_between_episodes` setting controls how often they appear (0.3 = 30% chance). There are two styles: `hbn-cozy` (gradient with logo and music) and `adult-swim-minimal` (black and white).

### Network Branding Bumpers

These are full network identity bumpers with the complete logo. They play about once per hour (every 25-30 episodes). They're automatically generated on the first playlist build and include fade-in/scale animations with background music randomly selected from your `assets/music/` folder.

## Playlist Management

The playlist is just a text file (`/app/hls/playlist.txt`) with one file path per line. Episodes, bumpers, and intermissions are all mixed together:

```
/media/tvchannel/Show 1/Season 01/Episode 01.mp4
/media/tvchannel/Show 1/Season 01/Episode 02.mp4
/assets/bumpers/up_next/show_1.mp4
/media/tvchannel/Show 2/Season 01/Episode 01.mp4
...
```

### Watch Progress

The system tracks which episodes you've watched in `watch_progress.json`. When you restart or regenerate the playlist, it automatically resumes from where you left off. If it can't find the last watched episode (maybe you deleted it), it just starts from the beginning.

### Real-time Editing

One of my favorite features is that you can edit the playlist while it's playing. The admin UI lets you:
- Reorder episodes in the upcoming queue
- Skip episodes (removes them from the queue)
- Skip the current episode (jumps to the next one immediately)

All of this happens by editing the playlist file in place—the streamer picks up the changes automatically. No restart needed.

### Weather Bumpers

HBN supports optional "Current Weather" bumpers between episodes. These are short (≈5 seconds) cards that show current weather for a configured location.

Configure them in:

```text
server/config/weather_bumpers.json
```

and set an OpenWeather API key in the `HBN_WEATHER_API_KEY` environment variable.

The system:
- Inserts logical weather slots between episodes according to `probability_between_episodes` (default: 25%)
- Just before each slot, fetches (cached) current weather and renders a short bumper on the fly
- This keeps weather info reasonably fresh even for long playlists (500+ episodes)
- Weather data is cached for 7 minutes by default to avoid over-calling the API

Example configuration:

```json
{
  "enabled": true,
  "provider": "openweathermap",
  "api_key_env_var": "HBN_WEATHER_API_KEY",
  "location": {
    "city": "Newark",
    "region": "NJ",
    "country": "US",
    "lat": 40.7357,
    "lon": -74.1724
  },
  "units": "imperial",
  "duration_seconds": 5,
  "cache_ttl_minutes": 7,
  "probability_between_episodes": 0.25
}
```

When running in Docker, pass the API key via environment variable:

```bash
docker run -d \
  -e HBN_WEATHER_API_KEY=your_api_key_here \
  ...
```

Get a free OpenWeatherMap API key at: https://openweathermap.org/api

## Development

### Local Setup (Without Docker)

If you want to develop locally:

```bash
# Install dependencies
pip install -r requirements.txt

# Generate the playlist
python server/generate_playlist.py

# Start streaming
python server/stream.py

# In another terminal, start the admin API
cd server/api
uvicorn app:app --reload --port 8000
```

### Project Structure

```
channel/
├── server/                 # The streaming server
│   ├── api/               # FastAPI admin API
│   ├── config/           # Configuration files
│   ├── hls/              # Generated HLS stream files
│   ├── generate_playlist.py
│   ├── stream.py         # Main streaming loop
│   └── playlist_service.py
├── ui/channel-admin/      # React admin panel
├── client/               # Client setup scripts
│   ├── pi_setup/         # Kodi automation
│   └── web_test/         # Browser player
├── assets/               # Logos, bumpers, music
└── scripts/              # Bumper generation utilities
```

### Testing

There's a test suite! Run it with:

```bash
# Python tests
pytest tests/ -v

# TypeScript/React tests
cd ui/channel-admin
npm test
```

The GitHub Actions workflow runs these automatically on push.

## Troubleshooting

### Stream Not Playing

First, check the container logs:
```bash
docker logs tvchannel
```

Make sure your media files are actually there:
```bash
docker exec tvchannel ls -la /media/tvchannel
```

Check if the playlist was generated:
```bash
docker exec tvchannel cat /app/hls/playlist.txt | head -20
```

And verify HLS segments are being created:
```bash
docker exec tvchannel ls -la /app/hls/ | grep .ts
```

### Playlist Not Updating

Make sure `server/config/channel_settings.json` is mounted as a volume. If you change the config, restart the container:
```bash
docker restart tvchannel
```

### Bumpers Not Generating

Check that the `assets/` directory is mounted. Bumpers need disk space for temporary files during generation. If something's wrong, check the container logs for FFmpeg errors.

### Admin UI Not Connecting

Make sure the API is running:
```bash
curl http://localhost:8000/api/healthz
```

If you're accessing from a different origin, check CORS settings. Also verify that `VITE_API_BASE` matches your API URL.

### Watch Progress Issues

If watch progress isn't working, check that `watch_progress.json` exists and is writable. The file paths in there need to match your actual file locations. If things get messed up, just delete `watch_progress.json` and regenerate the playlist.

### Performance Issues

If playlist generation is slow, try reducing `PLAYLIST_EPISODE_LIMIT`. If you want bumpers to start appearing sooner, increase `PLAYLIST_SEED_LIMIT`. Also keep an eye on disk space in `/app/hls/`—HLS segments can accumulate over time.

## API Reference

The admin API is pretty straightforward. Here are the main endpoints:

**List channels:**
```
GET /api/channels
```

**Get a specific channel:**
```
GET /api/channels/{channel_id}
```

**Update a channel:**
```
PUT /api/channels/{channel_id}
Content-Type: application/json

{
  "id": "default",
  "name": "My Channel",
  ...
}
```

**Discover shows in a folder:**
```
GET /api/channels/{channel_id}/shows/discover?media_root=/path/to/media
```

**Get playlist snapshot:**
```
GET /api/channels/{channel_id}/playlist/next?limit=25
```

**Update playlist order:**
```
POST /api/channels/{channel_id}/playlist/next
Content-Type: application/json

{
  "version": 1234567890.123,
  "desired": ["/path/to/episode1.mp4", ...],
  "skipped": ["/path/to/episode3.mp4"]
}
```

**Skip current episode:**
```
POST /api/channels/{channel_id}/playlist/skip-current
```

**Health check:**
```
GET /api/healthz
```

The interactive docs at `/docs` are probably easier to use than reading this, but there you go.

## Future Ideas

Some things I've been thinking about adding:
- Multiple channels with different schedules
- Live input integration (stream from a camera or capture card)
- Electronic Program Guide (EPG)
- Commercial break insertion
- User authentication for the admin panel
- Mobile app
- Chromecast support

If you have ideas or want to contribute, feel free to open an issue or PR!

## License

[Add your license information here]

---

**Enjoy your personal TV channel!** 🎉

If you run into issues or have questions, check out `ISSUES.md` and `PROJECT_STATUS.md`. Or just open an issue on GitHub.
