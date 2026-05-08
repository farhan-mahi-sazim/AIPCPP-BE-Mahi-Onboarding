from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class EHealthStatus(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class TDependencyCheck(BaseModel):
    status: EHealthStatus
    component_type: str = "datastore"
    observed_value: float | None = None
    observed_unit: str | None = None
    time: datetime
    output: str | None = None


class THealthCheckResponse(BaseModel):
    status: EHealthStatus
    version: str
    description: str
    timestamp: datetime
    uptime_seconds: float
    environment: str
    checks: dict[str, TDependencyCheck]
    output: str | None = None


class TLivenessResponse(BaseModel):
    status: EHealthStatus
    timestamp: datetime
