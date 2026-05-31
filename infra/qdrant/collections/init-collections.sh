#!/usr/bin/env bash
set -euo pipefail

QDRANT_URL="${QDRANT_URL:-http://qdrant:6333}"

create_collection() {
  local name="$1"
  curl -sf -X PUT "${QDRANT_URL}/collections/${name}" \
    -H "Content-Type: application/json" \
    -d '{
      "vectors": {
        "size": 1536,
        "distance": "Cosine"
      }
    }' || true
}

create_collection historical_incidents
create_collection runbooks

echo "Qdrant collections initialized."
