import argparse
import logging
import os
import signal
import threading
from collections.abc import Callable
from concurrent import futures
from typing import Any

import grpc
from google.protobuf import empty_pb2
from google.protobuf.timestamp_pb2 import Timestamp

from . import __version__
from .cli.client import (
    _build_entry,
    _client_build_entry,
    _format_timestamp,
    _format_timestamp_ms,
    _parse_datetime,
    _run_client_module,
    _timestamp_from_datetime,
    _timestamp_from_milliseconds,
    _timestamp_to_milliseconds,
    build_parser,
)
from .config import GRPC_HOST, GRPC_PORT
from .generated import timeseries_pb2, timeseries_pb2_grpc
from .service.timeseries_store import APP_VERSION, TimeSeriesServicer, Point, TimeSeriesStore
from .store.redis_time_series_store import PointConflictError, RedisStoreDriftError, RedisTimeSeriesStore

OutFn = Callable[[str], Any]
DEFAULT_MAX_WORKERS = 10
DEFAULT_SHUTDOWN_GRACE_SECONDS = 5.0

logger = logging.getLogger(__name__)

_SHUTDOWN_SIGNALS = (signal.SIGINT, signal.SIGTERM)


def _default_grpc_server_factory() -> grpc.Server:
    return grpc.server(futures.ThreadPoolExecutor(max_workers=DEFAULT_MAX_WORKERS))


def _register_health_service(grpc_server: grpc.Server) -> Any | None:
    """Register the standard gRPC health-checking service, if available.

    Returns the HealthServicer instance (so callers can flip it to
    NOT_SERVING on shutdown), or None if the optional dependency is missing.
    """
    try:
        from grpc_health.v1 import health, health_pb2, health_pb2_grpc
    except ImportError:
        logger.warning("grpcio-health-checking not installed; skipping health service registration")
        return None

    health_servicer = health.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, grpc_server)

    service_name = timeseries_pb2.DESCRIPTOR.services_by_name["TimeSeries"].full_name
    health_servicer.set(service_name, health_pb2.HealthCheckResponse.SERVING)
    health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)
    return health_servicer


def _mark_health_not_serving(health_servicer: Any | None) -> None:
    if health_servicer is None:
        return
    health_servicer.enter_graceful_shutdown()


def _install_signal_handlers(
    grpc_server: grpc.Server,
    shutdown_grace_seconds: float,
    health_servicer: Any | None,
) -> None:
    def _handle_shutdown_signal(signum: int, frame: Any) -> None:
        logger.info(
            "Received signal %s, shutting down gRPC server (grace=%ss)",
            signal.Signals(signum).name,
            shutdown_grace_seconds,
        )
        _mark_health_not_serving(health_servicer)
        grpc_server.stop(shutdown_grace_seconds)

    if threading.current_thread() is not threading.main_thread():
        logger.warning("Not running in the main thread; skipping signal handler registration")
        return

    for sig in _SHUTDOWN_SIGNALS:
        try:
            signal.signal(sig, _handle_shutdown_signal)
        except ValueError:
            logger.warning("Unable to register handler for %s outside the main thread", sig.name)


def serve(
    args: argparse.Namespace | None = None,
    grpc_server_factory: Callable[[], grpc.Server] | None = None,
    register_servicer: Callable[[TimeSeriesServicer, grpc.Server], None] | None = None,
    servicer_factory: Callable[[], TimeSeriesServicer] | None = None,
    host: str | None = None,
    port: int | None = None,
    register_health_service: bool = True,
    shutdown_grace_seconds: float | None = None,
    out: OutFn = print,
) -> int:
    args = args or build_parser().parse_args()
    grpc_server_factory = grpc_server_factory or _default_grpc_server_factory
    register_servicer = register_servicer or timeseries_pb2_grpc.add_TimeSeriesServicer_to_server
    servicer_factory = servicer_factory or TimeSeriesServicer
    host = host if host is not None else GRPC_HOST
    port = port if port is not None else GRPC_PORT
    shutdown_grace_seconds = (
        shutdown_grace_seconds
        if shutdown_grace_seconds is not None
        else float(os.getenv("GRPC_SHUTDOWN_GRACE_SECONDS", str(DEFAULT_SHUTDOWN_GRACE_SECONDS)))
    )

    if getattr(args, "version", False):
        out(APP_VERSION)
        return 0

    module = getattr(args, "module", "serve")
    if module in {"get", "set", "update", "delete", "query", "version"}:
        return _run_client_module(args, out=out)

    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=os.getenv("LOG_LEVEL", "INFO"),
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )

    grpc_server = grpc_server_factory()
    servicer = servicer_factory()
    register_servicer(servicer, grpc_server)

    health_servicer = _register_health_service(grpc_server) if register_health_service else None

    address = f"{host}:{port}"
    bound_port = grpc_server.add_insecure_port(address)
    if not bound_port:
        logger.error("Failed to bind gRPC server to %s (port already in use?)", address)
        return 1

    try:
        grpc_server.start()
    except OSError:
        logger.exception("Failed to start gRPC server on %s", address)
        return 1

    logger.info("gRPC TimeSeries running on %s:%s", host, bound_port)
    _install_signal_handlers(grpc_server, shutdown_grace_seconds, health_servicer)
    grpc_server.wait_for_termination()
    return 0


__all__ = [
    "APP_VERSION",
    "DEFAULT_MAX_WORKERS",
    "DEFAULT_SHUTDOWN_GRACE_SECONDS",
    "TimeSeriesServicer",
    "OutFn",
    "Point",
    "PointConflictError",
    "RedisStoreDriftError",
    "RedisTimeSeriesStore",
    "TimeSeriesStore",
    "Timestamp",
    "__version__",
    "_build_entry",
    "_client_build_entry",
    "_default_grpc_server_factory",
    "_format_timestamp",
    "_format_timestamp_ms",
    "_parse_datetime",
    "_run_client_module",
    "_timestamp_from_datetime",
    "_timestamp_from_milliseconds",
    "_timestamp_to_milliseconds",
    "build_parser",
    "empty_pb2",
    "timeseries_pb2",
    "timeseries_pb2_grpc",
    "grpc",
    "serve",
]

