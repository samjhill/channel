#!/bin/bash
set -euo pipefail

sudo apt update
sudo apt install -y kodi
sudo systemctl enable kodi

