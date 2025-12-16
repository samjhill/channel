FROM ubuntu:22.04

# Install Node.js for building admin UI
RUN apt update && apt install -y \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt install -y \
    ffmpeg \
    nginx \
    python3 \
    python3-pip \
    nodejs \
    fonts-dejavu-core && \
    rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir watchdog pillow numpy fastapi uvicorn[standard] requests psutil

# Remove default nginx sites to prevent conflicts
RUN rm -rf /etc/nginx/sites-enabled/* /etc/nginx/sites-available/* || true

WORKDIR /app

# Copy core server files to consistent locations
COPY server/stream.py /app/server/stream.py
COPY server/generate_playlist.py /app/server/generate_playlist.py
COPY server/playlist_service.py /app/server/playlist_service.py
COPY server/bumper_block.py /app/server/bumper_block.py
COPY server/__init__.py /app/server/__init__.py
COPY server/entrypoint.sh /app/entrypoint.sh
COPY server/process_monitor.py /app/process_monitor.py
COPY server/api /app/server/api
COPY server/services /app/server/services
COPY server/nginx.conf /etc/nginx/nginx.conf
# Copy config files (channel_settings.json, sassy_messages.json)
# Note: If a volume is mounted at /app/config, it will override these files
COPY server/config /app/config
COPY assets /app/assets
COPY scripts /app/scripts
COPY client/web_test /app/client/web_test

# Build admin UI
COPY ui/channel-admin /app/ui/channel-admin
WORKDIR /app/ui/channel-admin
RUN npm install && npm run build
WORKDIR /app

RUN chmod +x /app/entrypoint.sh /app/process_monitor.py && mkdir -p /app/hls

EXPOSE 8080 8000 8081

CMD ["/app/entrypoint.sh"]
