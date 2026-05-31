from ingestion_service.infrastructure.normalizers import datadog, pagerduty, prometheus

NORMALIZERS = {
    "prometheus": prometheus.normalize,
    "datadog": datadog.normalize,
    "pagerduty": pagerduty.normalize,
}
