#!/bin/sh
# Inject runtime API URL into the frontend
# This runs at container start so VITE_API_URL can be set via Cloud Run env vars
cat > /usr/share/nginx/html/config.js <<EOF
window.__VITE_API_URL__ = "${VITE_API_URL:-/api}";
EOF

exec nginx -g 'daemon off;'
