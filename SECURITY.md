# Security Guide

## Write Permissions

This application is designed to **only write to container-local paths**. All write operations are restricted to:

### Writable Paths (Inside Container)

1. **`/app/hls/`** - HLS streaming files
   - `playlist.txt` - Generated playlist
   - `playhead.json` - Playhead state
   - `watch_progress.json` - Watch progress tracking
   - `stream.m3u8` - HLS playlist file
   - `stream*.ts` - HLS video segments
   - `preview_block_*.mp4` - Preview files
   - `blocks/` - Pre-generated bumper blocks
   - `weather_temp/` - Temporary weather bumper files
   - `up_next_temp/` - Temporary up-next bumper files
   - `streamer.lock` - Lock file
   - `streamer.pid` - PID file

2. **`/app/config/`** - Configuration files
   - `channel_settings.json` - Channel configuration
   - `weather_bumpers.json` - Weather bumper configuration
   - `.weather_api_key` - Weather API key (secret)

### Read-Only Paths (Mounted from Host)

- **`/media/tvchannel`** - Media files (TV shows, movies)
  - Mounted as **read-only** (`:ro` flag)
  - Application **never writes** to this path
  - Only reads media files for streaming

### Volume Mounts

In `docker-compose.truenas.yml`:

```yaml
volumes:
  # Media - READ-ONLY (application never writes here)
  - /mnt/blackhole/media/tv:/media/tvchannel:ro
  
  # Application data - WRITABLE (all writes go here)
  - /mnt/blackhole/apps/tvchannel/assets:/app/assets
  - /mnt/blackhole/apps/tvchannel/config:/app/config
  - /mnt/blackhole/apps/tvchannel/hls:/app/hls
```

### Security Guarantees

1. **Media files are read-only** - The application cannot modify or delete your media files
2. **All writes are container-local** - Application state, logs, and temporary files are written to `/app/hls` and `/app/config`
3. **No host filesystem writes** - The application never writes outside the mounted volumes
4. **Isolated configuration** - Config files are in `/app/config`, separate from media

### Verification

To verify the application is not writing to media:

```bash
# Check that media mount is read-only
docker inspect tvchannel | grep -A 5 "Mounts" | grep media

# Should show: "Mode": "ro" (read-only)

# Monitor writes (should only see /app/hls and /app/config)
docker exec tvchannel find /app -type f -newer /tmp/timestamp 2>/dev/null
```

### Best Practices

1. **Always mount media as read-only** - Use `:ro` flag in volume mounts
2. **Separate volumes** - Keep media, config, and HLS data in separate volumes
3. **Regular backups** - Backup `/app/config` if you want to preserve settings
4. **Monitor disk usage** - HLS segments can grow; cleanup is automatic but monitor `/app/hls`

