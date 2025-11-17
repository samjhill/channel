FROM ubuntu:22.04

RUN apt update && apt install -y \
    ffmpeg \
    nginx \
    python3 \
    python3-pip \
    fonts-dejavu-core && \
    rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir watchdog pillow numpy fastapi uvicorn[standard]

WORKDIR /app

COPY server/generate_playlist.py server/stream.py server/entrypoint.sh server/process_monitor.py ./
COPY server/playlist_service.py /app/playlist_service.py
COPY server/__init__.py /app/server/__init__.py
COPY server/playlist_service.py /app/server/playlist_service.py
COPY server/api /app/server/api
COPY server/nginx.conf /etc/nginx/nginx.conf
# Copy config files (channel_settings.json, sassy_messages.json)
# Note: If a volume is mounted at /app/config, it will override these files
COPY server/config /app/config
COPY assets /app/assets
COPY scripts /app/scripts

RUN chmod +x entrypoint.sh process_monitor.py && mkdir -p /app/hls

EXPOSE 8080

CMD ["/app/entrypoint.sh"]
