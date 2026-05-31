#!/usr/bin/env bash
set -euo pipefail

BOOTSTRAP_SERVER="${KAFKA_BOOTSTRAP_SERVER:-kafka:9092}"

create_topic() {
  local name="$1"
  local partitions="$2"
  local retention_ms="$3"
  local cleanup_policy="${4:-delete}"

  kafka-topics.sh \
    --bootstrap-server "${BOOTSTRAP_SERVER}" \
    --create \
    --if-not-exists \
    --topic "${name}" \
    --partitions "${partitions}" \
    --replication-factor 1 \
    --config "retention.ms=${retention_ms}" \
    --config "cleanup.policy=${cleanup_policy}"
}

create_topic alerts-topic 4 2592000000 delete
create_topic logs-topic 6 604800000 delete
create_topic metrics-topic 6 604800000 delete
create_topic incident-topic 3 31536000000 compact,delete
create_topic rca-topic 3 7776000000 delete

echo "Kafka topics provisioned."
