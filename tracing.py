"""
Shared OpenTelemetry tracing setup for Western Health Foundry agent.

Exports traces to Azure Monitor Application Insights so they appear in
the Foundry portal under Observability > Traces.

Set APPLICATION_INSIGHTS_CONNECTION_STRING in your .env file. If unset,
traces are printed to the console (useful for local debugging).

Usage:
    from tracing import tracer, configure_tracing
    configure_tracing()          # call once at startup
    with tracer.start_as_current_span("my_operation"):
        ...
"""

import os

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

SERVICE_NAME = "wh-patient-helper"

# Module-level tracer — import this wherever you need to create spans.
tracer = trace.get_tracer(__name__, tracer_provider=None)

_configured = False


def configure_tracing() -> TracerProvider | None:
    """
    Initialise the global TracerProvider and wire up the exporter.

    Safe to call multiple times; only the first call takes effect.
    Set TRACING_ENABLED=false in .env to disable tracing entirely.
    """
    global _configured, tracer
    if _configured:
        return trace.get_tracer_provider()

    enabled = os.getenv("TRACING_ENABLED", "true").lower() not in ("false", "0", "no")
    if not enabled:
        print("[tracing] Tracing is disabled (TRACING_ENABLED=false)")
        _configured = True
        return None

    resource = Resource.create({"service.name": SERVICE_NAME})
    provider = TracerProvider(resource=resource)

    conn_str = os.getenv("APPLICATION_INSIGHTS_CONNECTION_STRING")
    if conn_str:
        from azure.monitor.opentelemetry.exporter import AzureMonitorTraceExporter

        exporter = AzureMonitorTraceExporter.from_connection_string(conn_str)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        print(f"[tracing] Exporting traces to Application Insights")
    else:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        print("[tracing] APPLICATION_INSIGHTS_CONNECTION_STRING not set — traces go to console")

    trace.set_tracer_provider(provider)
    tracer = trace.get_tracer(__name__)

    # Enable azure-sdk tracing (azure-core-tracing-opentelemetry)
    from azure.core.settings import settings as azure_settings
    azure_settings.tracing_implementation = "opentelemetry"

    _configured = True
    return provider
