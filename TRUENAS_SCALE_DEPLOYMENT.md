# TrueNAS Scale Deployment Guide

This guide covers deploying the TV Channel application to TrueNAS Scale.

## Prerequisites

- TrueNAS Scale installed and running
- Access to TrueNAS web interface
- Media dataset/directory accessible
- At least 4GB RAM available
- Docker/Apps enabled in TrueNAS Scale

## Method 1: Using Docker Compose via Custom App (Recommended)

### Step 1: Prepare Your Media Dataset

1. **Create a dataset for your media** (if not already created):
   - Go to **Storage** → **Pools**
   - Create a dataset (e.g., `tank/media/tv`)
   - Set permissions as needed

2. **Create datasets for application data**:
   - `tank/apps/tvchannel/assets` - For bumper assets
   - `tank/apps/tvchannel/config` - For configuration files
   - `tank/apps/tvchannel/hls` - For HLS segments and state

### Step 2: Prepare Docker Compose File

The `docker-compose.yml` file in the repo is ready, but you'll need to adjust paths:

1. **Update volume paths** to match your TrueNAS datasets:
   ```yaml
   volumes:
     - /mnt/tank/media/tv:/media/tvchannel:ro
     - /mnt/tank/apps/tvchannel/assets:/app/assets
     - /mnt/tank/apps/tvchannel/config:/app/config
     - /mnt/tank/apps/tvchannel/hls:/app/hls
   ```

2. **Set environment variables**:
   ```yaml
   environment:
     - CORS_ORIGINS=http://your-truenas-ip:5174,https://your-domain.com
     - LOG_LEVEL=INFO
   ```

### Step 3: Deploy via TrueNAS Apps

1. **Access TrueNAS Web Interface**:
   - Navigate to your TrueNAS Scale IP address
   - Log in with admin credentials

2. **Install Custom App**:
   - Go to **Apps** → **Discover Apps**
   - Click the three dots (⋮) next to **Custom App**
   - Select **Install via YAML**

3. **Configure the App**:
   - **Application Name**: `tvchannel`
   - **Version**: `latest`
   - **Image Repository**: Leave blank (we'll use docker-compose)
   - **Custom Config**: Paste your modified `docker-compose.yml` content
   - **Resource Limits**: 
     - CPU: 4 cores
     - Memory: 4GB

4. **Configure Storage**:
   - Map your datasets to the container paths:
     - `/mnt/tank/media/tv` → `/media/tvchannel` (read-only)
     - `/mnt/tank/apps/tvchannel/assets` → `/app/assets`
     - `/mnt/tank/apps/tvchannel/config` → `/app/config`
     - `/mnt/tank/apps/tvchannel/hls` → `/app/hls`

5. **Configure Networking**:
   - **Port**: `8080` (for HLS stream)
   - **Type**: `NodePort` or `LoadBalancer` (depending on your setup)

6. **Deploy**:
   - Click **Save**
   - Monitor deployment in **Installed Applications**

## Method 2: Using Docker Compose via Shell (Alternative)

If you prefer command-line deployment:

### Step 1: SSH into TrueNAS Scale

```bash
ssh root@your-truenas-ip
```

### Step 2: Clone Repository

```bash
cd /mnt/tank/apps
git clone https://github.com/your-username/channel.git tvchannel
cd tvchannel
```

### Step 3: Update docker-compose.yml

Edit `docker-compose.yml` to use TrueNAS paths:

```yaml
volumes:
  - /mnt/tank/media/tv:/media/tvchannel:ro
  - /mnt/tank/apps/tvchannel/assets:/app/assets
  - /mnt/tank/apps/tvchannel/config:/app/config
  - /mnt/tank/apps/tvchannel/hls:/app/hls
```

### Step 4: Deploy

```bash
docker-compose up -d
```

### Step 5: Verify

```bash
docker-compose ps
docker-compose logs -f tvchannel
```

## Method 3: Using TrueNAS Scale Kubernetes (Advanced)

For production deployments, you can create a Kubernetes manifest:

### Create `k8s-deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: tvchannel
  namespace: default
spec:
  replicas: 1
  selector:
    matchLabels:
      app: tvchannel
  template:
    metadata:
      labels:
        app: tvchannel
    spec:
      containers:
      - name: tvchannel
        image: tvchannel:latest
        ports:
        - containerPort: 8080
        env:
        - name: CORS_ORIGINS
          value: "http://your-truenas-ip:5174"
        - name: LOG_LEVEL
          value: "INFO"
        resources:
          limits:
            memory: "4Gi"
            cpu: "4"
          requests:
            memory: "1Gi"
            cpu: "1"
        volumeMounts:
        - name: media
          mountPath: /media/tvchannel
          readOnly: true
        - name: assets
          mountPath: /app/assets
        - name: config
          mountPath: /app/config
        - name: hls
          mountPath: /app/hls
      volumes:
      - name: media
        persistentVolumeClaim:
          claimName: tvchannel-media
      - name: assets
        persistentVolumeClaim:
          claimName: tvchannel-assets
      - name: config
        persistentVolumeClaim:
          claimName: tvchannel-config
      - name: hls
        persistentVolumeClaim:
          claimName: tvchannel-hls
---
apiVersion: v1
kind: Service
metadata:
  name: tvchannel-service
spec:
  selector:
    app: tvchannel
  ports:
  - port: 8080
    targetPort: 8080
  type: LoadBalancer
```

## Configuration

### Environment Variables

Set these in TrueNAS Apps interface or docker-compose.yml:

| Variable | Example | Description |
|----------|---------|-------------|
| `CORS_ORIGINS` | `http://192.168.1.100:5174` | Comma-separated allowed origins |
| `LOG_LEVEL` | `INFO` | Logging level |
| `MEDIA_DIR` | `/mnt/tank/media/tv` | Media directory path (host) |

### Storage Paths

TrueNAS Scale uses `/mnt/pool-name/dataset-name` format:

- **Media**: `/mnt/tank/media/tv` (or your pool/dataset)
- **Assets**: `/mnt/tank/apps/tvchannel/assets`
- **Config**: `/mnt/tank/apps/tvchannel/config`
- **HLS**: `/mnt/tank/apps/tvchannel/hls`

### Network Configuration

- **HLS Stream Port**: `8080` (internal)
- **API Port**: `8000` (if running separately)
- **Admin UI Port**: `5174` (if running separately)

For external access, configure:
- **NodePort**: Exposes on host IP
- **LoadBalancer**: If you have a load balancer configured
- **Ingress**: For domain-based access

## Initial Setup

### 1. Copy Configuration Files

After first deployment, copy default configs:

```bash
# SSH into TrueNAS or use shell in Apps
docker exec tvchannel cp -r /app/config/* /mnt/tank/apps/tvchannel/config/
```

### 2. Configure Channel Settings

Edit `/mnt/tank/apps/tvchannel/config/channel_settings.json`:

```json
{
  "channels": [
    {
      "id": "main",
      "label": "Main Channel",
      "media_root": "/media/tvchannel"
    }
  ]
}
```

### 3. Add Media Files

Place your video files in the media dataset:
```
/mnt/tank/media/tv/
├── Show Name/
│   ├── Season 01/
│   │   └── Episode 01.mp4
│   └── Season 02/
│       └── ...
```

## Accessing the Application

### HLS Stream
```
http://your-truenas-ip:8080/channel/stream.m3u8
```

### Admin UI (if running separately)
```
http://your-truenas-ip:5174
```

### API
```
http://your-truenas-ip:8000
http://your-truenas-ip:8000/docs  # API documentation
```

## Monitoring

### Check Application Status

1. **Via TrueNAS UI**:
   - Go to **Apps** → **Installed Applications**
   - Click on `tvchannel`
   - View logs and status

2. **Via Command Line**:
   ```bash
   docker ps | grep tvchannel
   docker logs tvchannel
   ```

### Health Check

```bash
curl http://your-truenas-ip:8000/api/healthz
```

## Troubleshooting

### Application Won't Start

1. **Check logs**:
   ```bash
   docker logs tvchannel
   ```

2. **Verify storage mounts**:
   ```bash
   docker exec tvchannel ls -la /media/tvchannel
   docker exec tvchannel ls -la /app/config
   ```

3. **Check resource usage**:
   ```bash
   docker stats tvchannel
   ```

### Can't Access Stream

1. **Verify port is exposed**:
   ```bash
   netstat -tuln | grep 8080
   ```

2. **Check firewall**:
   - Ensure port 8080 is open in TrueNAS firewall settings

3. **Test from container**:
   ```bash
   docker exec tvchannel curl http://localhost:8080/channel/stream.m3u8
   ```

### Storage Issues

1. **Check dataset permissions**:
   ```bash
   ls -la /mnt/tank/apps/tvchannel/
   ```

2. **Verify mount points**:
   ```bash
   docker exec tvchannel df -h
   ```

### Performance Issues

1. **Monitor resources**:
   - Check CPU and memory usage in TrueNAS dashboard
   - Adjust resource limits if needed

2. **Check HLS segment count**:
   ```bash
   docker exec tvchannel ls -1 /app/hls/stream*.ts | wc -l
   ```

## Backup Strategy

### Critical Files to Backup

1. **Configuration**:
   - `/mnt/tank/apps/tvchannel/config/channel_settings.json`
   - `/mnt/tank/apps/tvchannel/config/sassy_messages.json`
   - `/mnt/tank/apps/tvchannel/config/weather_config.json`

2. **State Files**:
   - `/mnt/tank/apps/tvchannel/hls/watch_progress.json`
   - `/mnt/tank/apps/tvchannel/hls/playhead.json`

### Automated Backup

Create a TrueNAS scheduled task:

1. Go to **Tasks** → **Cron Jobs**
2. Add new task:
   - **Command**: `/usr/local/bin/backup-tvchannel.sh`
   - **Schedule**: Daily at 2 AM

Create backup script at `/usr/local/bin/backup-tvchannel.sh`:
```bash
#!/bin/bash
BACKUP_DIR="/mnt/tank/backups/tvchannel"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"
tar czf "$BACKUP_DIR/config_$DATE.tar.gz" -C /mnt/tank/apps/tvchannel/config .
tar czf "$BACKUP_DIR/state_$DATE.tar.gz" -C /mnt/tank/apps/tvchannel/hls watch_progress.json playhead.json
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +7 -delete
```

## Updates

To update the application:

1. **Pull latest code**:
   ```bash
   cd /mnt/tank/apps/tvchannel
   git pull
   ```

2. **Rebuild and restart**:
   ```bash
   docker-compose build
   docker-compose up -d
   ```

Or via TrueNAS UI:
- Go to **Apps** → **Installed Applications**
- Click **Update** on tvchannel app

## Security Considerations

1. **Firewall**: Configure TrueNAS firewall to only allow necessary ports
2. **CORS**: Set `CORS_ORIGINS` to your actual domain/IP
3. **Network**: Consider using TrueNAS internal network for services
4. **Authentication**: Currently no auth - add reverse proxy with auth if exposing publicly

## Support

For issues:
1. Check logs: `docker logs tvchannel`
2. Check health: `curl http://your-truenas-ip:8000/api/healthz`
3. Review this guide and PRODUCTION_DEPLOYMENT.md

