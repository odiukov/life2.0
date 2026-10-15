"""Construct the public service from validated environment settings."""

from fastapi import FastAPI
from gateway.settings import GatewaySettings

from orchestrator.composition import build_app
from orchestrator.settings import OrchestratorSettings


def create_app() -> FastAPI:
    return build_app(OrchestratorSettings(), GatewaySettings())
