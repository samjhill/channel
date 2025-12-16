# Production Deployment Guide

This guide covers deploying the TV Channel application to dedicated hardware.

## Prerequisites

- Docker and Docker Compose installed
- At least 2GB RAM available
- At least 10GB free disk space (for HLS segments)
- Media directory accessible (mounted or network share)

## Quick Start

1. **Set environment variables**:
   ```bash
   export MEDIA_DIR=/path/to/your/media
   export CORS_ORIGINS=http://your-domain.com,https://your-domain.com
   export LOG_LEVEL=INFO
   ```

2. **Start with Docker Compose**:
   ```bash
   docker-compose up -d
   ```

3. **Check health**:
   ```bash
   curl http://localhost:8000/api/healthz
   ```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MEDIA_DIR` | `/Volumes/media/tv` | Path to media directory on host |
| `CORS_ORIGINS` | `http://localhost:5173,...` | Comma-separated list of allowed CORS origins |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |

### Resource Limits

The `docker-compose.yml` includes resource limits:
- **Memory**: 4GB limit, 1GB reserved
- **CPU**: 4.0 cores limit, 1.0 core reserved

These limits provide good headroom for:
- Multiple concurrent FFmpeg processes
- Bumper block generation
- Playlist processing
- API requests

Adjust these based on your hardware:
```yaml
deploy:
  resources:
    limits:
      memory: 8G      # Increase for very large playlists or many concurrent operations
      cpus: '8.0'      # Increase for maximum performance
```

### Log Rotation

Logs are automatically rotated:
- Max size: 10MB per log file
- Max files: 3 (keeps ~30MB of logs total)

To view logs:
```bash
docker-compose logs -f tvchannel
```

## Monitoring

### Health Check Endpoint

The `/api/healthz` endpoint provides:
- Process status
- Resource usage (memory, CPU, disk)
- Playlist and playhead status
- HLS segment count

Example response:
```json
{
  "status": "ok",
  "timestamp": 1234567890,
  "resources": {
    "memory_mb": 512.5,
    "memory_percent": 25.6,
    "cpu_percent": 15.2,
    "disk": {
      "total_gb": 100.0,
      "used_gb": 45.2,
      "free_gb": 54.8,
      "percent": 45.2
    },
    "hls_segments": 50
  },
  "checks": {
    "playlist": {"status": "ok", "entries": 150},
    "playhead": {"status": "ok"}
  }
}
```

### Monitoring Recommendations

1. **Set up alerts** for:
   - Health check failures
   - Disk usage > 90%
   - Memory usage > 90%
   - Process crashes

2. **Monitor disk space**:
   - HLS segments auto-cleanup runs hourly
   - Old segments (>2 hours) are automatically removed
   - Monitor `/app/hls` directory size

3. **Check logs regularly**:
   ```bash
   docker-compose logs --tail=100 tvchannel
   ```

## Backup Strategy

### Critical Files to Backup

1. **Configuration**:
   - `server/config/channel_settings.json`
   - `server/config/sassy_messages.json`
   - `server/config/weather_config.json`

2. **State Files**:
   - `server/hls/watch_progress.json` (watch history)
   - `server/hls/playhead.json` (current position)

### Backup Script Example

```bash
#!/bin/bash
BACKUP_DIR="/backups/tvchannel"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

# Backup config files
docker exec tvchannel tar czf - -C /app/config . | \
  gzip > "$BACKUP_DIR/config_$DATE.tar.gz"

# Backup state files
docker exec tvchannel tar czf - -C /app/hls watch_progress.json playhead.json | \
  gzip > "$BACKUP_DIR/state_$DATE.tar.gz"

# Keep only last 7 days of backups
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +7 -delete
```

## Troubleshooting

### Container Won't Start

1. Check logs:
   ```bash
   docker-compose logs tvchannel
   ```

2. Verify media directory is accessible:
   ```bash
   docker exec tvchannel ls -la /media/tvchannel
   ```

3. Check resource limits:
   ```bash
   docker stats tvchannel
   ```

### High Disk Usage

1. Check HLS segment count:
   ```bash
   docker exec tvchannel ls -1 /app/hls/stream*.ts | wc -l
   ```

2. Manual cleanup (if needed):
   ```bash
   docker exec tvchannel python3 -c "
   import sys
   sys.path.insert(0, '/app')
   from server.stream import cleanup_old_hls_segments
   cleanup_old_hls_segments(max_age_hours=1.0, max_segments=50)
   "
   ```

### Process Crashes

The process monitor automatically restarts crashed processes. Check logs for crash reasons:
```bash
docker-compose logs tvchannel | grep -i error
```

### Performance Issues

1. **Increase resource limits** in `docker-compose.yml`
2. **Check FFmpeg processes**:
   ```bash
   docker exec tvchannel ps aux | grep ffmpeg
   ```
3. **Monitor resource usage**:
   ```bash
   docker stats tvchannel
   ```

## Security Considerations

1. **CORS Configuration**: Set `CORS_ORIGINS` to your actual domain(s)
2. **Network**: Consider using a reverse proxy (nginx/traefik) for SSL/TLS
3. **Firewall**: Only expose necessary ports (8080 for stream, 8000 for API)
4. **Authentication**: Currently no auth - add if exposing to public internet

## Maintenance

### Regular Tasks

1. **Weekly**: Check disk usage and logs
2. **Monthly**: Review and rotate backups
3. **As needed**: Update Docker image when new versions are available

### Updates

To update the application:
```bash
# Pull latest code
git pull

# Rebuild and restart
docker-compose build
docker-compose up -d
```

## Support

For issues or questions:
1. Check logs: `docker-compose logs tvchannel`
2. Check health: `curl http://localhost:8000/api/healthz`
3. Review this guide and README.md

