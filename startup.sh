#!/bin/sh
set -eu

exec python -m streamlit run BDACC_proj_1.py \
  --server.address=0.0.0.0 \
  --server.port=8000 \
  --server.headless=true \
  --server.fileWatcherType=none \
  --browser.gatherUsageStats=false
