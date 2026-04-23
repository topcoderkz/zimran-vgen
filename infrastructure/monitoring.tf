# ---------- Notification Channel ----------

resource "google_monitoring_notification_channel" "email" {
  display_name = "VGen Alerts Email"
  type         = "email"

  labels = {
    email_address = var.alert_email
  }

  depends_on = [google_project_service.apis]
}

# ---------- Uptime Checks ----------

resource "google_monitoring_uptime_check_config" "api_health" {
  display_name = "VGen API Health"
  timeout      = "10s"
  period       = "300s"

  http_check {
    path         = "/api/health"
    port         = 443
    use_ssl      = true
    validate_ssl = true
  }

  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = var.project_id
      host       = trimprefix(google_cloud_run_v2_service.api.uri, "https://")
    }
  }

  depends_on = [google_project_service.apis]
}

resource "google_monitoring_uptime_check_config" "frontend" {
  display_name = "VGen Frontend"
  timeout      = "10s"
  period       = "300s"

  http_check {
    path         = "/"
    port         = 443
    use_ssl      = true
    validate_ssl = true
  }

  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = var.project_id
      host       = trimprefix(google_cloud_run_v2_service.frontend.uri, "https://")
    }
  }

  depends_on = [google_project_service.apis]
}

# ---------- Alert Policies ----------

resource "google_monitoring_alert_policy" "api_down" {
  display_name = "VGen API Down"
  combiner     = "OR"

  conditions {
    display_name = "API uptime check failing"
    condition_threshold {
      filter          = "resource.type=\"uptime_url\" AND metric.type=\"monitoring.googleapis.com/uptime_check/check_passed\" AND metric.labels.check_id=\"${google_monitoring_uptime_check_config.api_health.uptime_check_id}\""
      comparison      = "COMPARISON_GT"
      threshold_value = 1
      duration        = "600s"

      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_NEXT_OLDER"
        cross_series_reducer = "REDUCE_COUNT_FALSE"
        group_by_fields      = ["resource.label.project_id"]
      }

      trigger {
        count = 1
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.id]

  alert_strategy {
    auto_close = "1800s"
  }

  documentation {
    content   = "The VGen API health endpoint is not responding. Check Cloud Run logs: `gcloud logging read 'resource.labels.service_name=\"vgen-api\"' --limit 50`"
    mime_type = "text/markdown"
  }

  depends_on = [google_project_service.apis]
}

resource "google_monitoring_alert_policy" "frontend_down" {
  display_name = "VGen Frontend Down"
  combiner     = "OR"

  conditions {
    display_name = "Frontend uptime check failing"
    condition_threshold {
      filter          = "resource.type=\"uptime_url\" AND metric.type=\"monitoring.googleapis.com/uptime_check/check_passed\" AND metric.labels.check_id=\"${google_monitoring_uptime_check_config.frontend.uptime_check_id}\""
      comparison      = "COMPARISON_GT"
      threshold_value = 1
      duration        = "600s"

      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_NEXT_OLDER"
        cross_series_reducer = "REDUCE_COUNT_FALSE"
        group_by_fields      = ["resource.label.project_id"]
      }

      trigger {
        count = 1
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.id]

  alert_strategy {
    auto_close = "1800s"
  }

  documentation {
    content   = "The VGen frontend is not responding. Check Cloud Run logs: `gcloud logging read 'resource.labels.service_name=\"vgen-frontend\"' --limit 50`"
    mime_type = "text/markdown"
  }

  depends_on = [google_project_service.apis]
}

resource "google_monitoring_alert_policy" "high_error_rate" {
  display_name = "VGen High Error Rate"
  combiner     = "OR"

  conditions {
    display_name = "Video processing errors > 5 in 5 min"
    condition_threshold {
      filter          = "metric.type=\"custom.googleapis.com/video_merger/errors\" resource.type=\"global\""
      comparison      = "COMPARISON_GT"
      threshold_value = 5
      duration        = "0s"

      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_SUM"
      }

      trigger {
        count = 1
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.id]

  alert_strategy {
    auto_close = "1800s"
  }

  documentation {
    content   = "More than 5 video processing errors in 5 minutes. Check worker logs: `gcloud logging read 'resource.labels.service_name=\"vgen-worker\" AND jsonPayload.event=\"pipeline_failed\"' --limit 20`"
    mime_type = "text/markdown"
  }

  depends_on = [google_project_service.apis]
}

resource "google_monitoring_alert_policy" "dlq_accumulating" {
  display_name = "VGen DLQ Messages Accumulating"
  combiner     = "OR"

  conditions {
    display_name = "Dead-letter queue has undelivered messages"
    condition_threshold {
      filter          = "metric.type=\"pubsub.googleapis.com/subscription/num_undelivered_messages\" resource.type=\"pubsub_subscription\" resource.labels.subscription_id=\"${google_pubsub_subscription.dlq_consumer.name}\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "300s"

      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_MEAN"
      }

      trigger {
        count = 1
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.id]

  alert_strategy {
    auto_close = "86400s"
  }

  documentation {
    content   = "Messages are landing in the dead-letter queue. These are merge tasks that failed after 5 retries. Inspect via: `curl https://vgen-api-kuvjowj3aq-uc.a.run.app/api/dlq/messages` or `gcloud pubsub subscriptions pull merge-tasks-dlq-sub --project sandbox-456317 --limit 5`"
    mime_type = "text/markdown"
  }

  depends_on = [google_project_service.apis]
}

resource "google_monitoring_alert_policy" "worker_backlog" {
  display_name = "VGen Worker Backlog Growing"
  combiner     = "OR"

  conditions {
    display_name = "Main subscription backlog > 50 for 15 min"
    condition_threshold {
      filter          = "metric.type=\"pubsub.googleapis.com/subscription/num_undelivered_messages\" resource.type=\"pubsub_subscription\" resource.labels.subscription_id=\"${google_pubsub_subscription.worker.name}\""
      comparison      = "COMPARISON_GT"
      threshold_value = 50
      duration        = "900s"

      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_MEAN"
      }

      trigger {
        count = 1
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.id]

  alert_strategy {
    auto_close = "3600s"
  }

  documentation {
    content   = "The worker subscription has more than 50 unacked messages for over 15 minutes. Workers may be stuck or scaled down. Check: `gcloud run services describe vgen-worker --region us-central1` and worker logs."
    mime_type = "text/markdown"
  }

  depends_on = [google_project_service.apis]
}

# ---------- DLQ Subscription ----------

resource "google_pubsub_subscription" "dlq_consumer" {
  name  = "merge-tasks-dlq-sub"
  topic = google_pubsub_topic.dlq.id

  ack_deadline_seconds       = 60
  message_retention_duration = "604800s"

  expiration_policy {
    ttl = ""
  }
}

# ---------- Monitoring Dashboard ----------

resource "google_monitoring_dashboard" "vgen" {
  dashboard_json = jsonencode({
    displayName = "VGen"
    gridLayout = {
      columns = 2
      widgets = [
        {
          title = "Videos Processed"
          xyChart = {
            dataSets = [{
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"custom.googleapis.com/video_merger/videos_processed\""
                }
              }
            }]
          }
        },
        {
          title = "Processing Time (ms)"
          xyChart = {
            dataSets = [{
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"custom.googleapis.com/video_merger/processing_time_ms\""
                }
              }
            }]
          }
        },
        {
          title = "Errors"
          xyChart = {
            dataSets = [{
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"custom.googleapis.com/video_merger/errors\""
                }
              }
            }]
          }
        },
        {
          title = "Worker Subscription Backlog"
          xyChart = {
            dataSets = [{
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"pubsub.googleapis.com/subscription/num_undelivered_messages\" resource.type=\"pubsub_subscription\" resource.labels.subscription_id=\"${google_pubsub_subscription.worker.name}\""
                }
              }
            }]
          }
        },
        {
          title = "DLQ Message Count"
          xyChart = {
            dataSets = [{
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"pubsub.googleapis.com/subscription/num_undelivered_messages\" resource.type=\"pubsub_subscription\" resource.labels.subscription_id=\"${google_pubsub_subscription.dlq_consumer.name}\""
                }
              }
            }]
          }
        },
        {
          title = "API Request Count"
          xyChart = {
            dataSets = [{
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"run.googleapis.com/request_count\" resource.type=\"cloud_run_revision\" resource.labels.service_name=\"vgen-api\""
                }
              }
            }]
          }
        },
        {
          title = "API Request Latency (ms)"
          xyChart = {
            dataSets = [{
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"run.googleapis.com/request_latencies\" resource.type=\"cloud_run_revision\" resource.labels.service_name=\"vgen-api\""
                }
              }
            }]
          }
        },
        {
          title = "Worker Instance Count"
          xyChart = {
            dataSets = [{
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"run.googleapis.com/container/instance_count\" resource.type=\"cloud_run_revision\" resource.labels.service_name=\"vgen-worker\""
                }
              }
            }]
          }
        },
      ]
    }
  })
}
