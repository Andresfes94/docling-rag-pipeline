from __future__ import annotations

import logging
import os

_log = logging.getLogger(__name__)


def setup_tracing(service_name: str = "rag-pipeline") -> None:
    """Initialize OpenTelemetry tracing.

    Disabled by default. Set OTEL_EXPORTER_OTLP_ENDPOINT to enable.
    """
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        _log.info("OpenTelemetry tracing disabled (set OTEL_EXPORTER_OTLP_ENDPOINT to enable)")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource(attributes={SERVICE_NAME: service_name})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _log.info("OpenTelemetry tracing enabled (endpoint=%s)", endpoint)
    except ImportError as exc:
        _log.warning(
            "OpenTelemetry tracing not available (install opentelemetry-api, "
            "opentelemetry-sdk, opentelemetry-exporter-otlp-proto-http, "
            "opentelemetry-instrumentation-fastapi): %s", exc,
        )
