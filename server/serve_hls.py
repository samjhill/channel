#!/usr/bin/env python3
"""
Simple HTTP server to serve HLS files in baremetal mode.
Mimics nginx configuration for /channel/ path.
"""

import http.server
import socketserver
import os
from pathlib import Path

# Determine HLS directory
if Path("/app/hls").exists():
    HLS_DIR = Path("/app/hls")
else:
    HLS_DIR = Path(__file__).parent / "hls"

class HLSHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(HLS_DIR), **kwargs)
    
    def do_GET(self):
        # Handle /channel/ prefix - modify self.path before processing
        original_path = self.path
        if self.path.startswith('/channel/'):
            self.path = self.path.replace('/channel/', '/', 1)
        elif self.path == '/channel':
            self.path = '/'
        elif self.path == '/channel/':
            self.path = '/'
        
        # Debug logging
        if original_path != self.path:
            print(f"Path rewrite: {original_path} -> {self.path}")
        
        return super().do_GET()
    
    def end_headers(self):
        # Add CORS headers (matching nginx config)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, HEAD, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Origin, Accept, Range, Content-Type')
        self.send_header('Access-Control-Expose-Headers', 'Content-Length, Content-Range')
        self.send_header('Cache-Control', 'no-cache')
        
        # Set correct MIME types
        if self.path.endswith('.m3u8'):
            self.send_header('Content-Type', 'application/vnd.apple.mpegurl')
        elif self.path.endswith('.ts'):
            self.send_header('Content-Type', 'video/mp2t')
        
        super().end_headers()
    
    def do_OPTIONS(self):
        # Handle CORS preflight
        self.send_response(204)
        self.end_headers()

if __name__ == '__main__':
    PORT = 8080
    
    print(f"Serving HLS files from {HLS_DIR} on port {PORT}")
    print(f"Access stream at: http://localhost:{PORT}/channel/stream.m3u8")
    
    with socketserver.TCPServer(('', PORT), HLSHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down HLS server...")

