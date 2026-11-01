from enum import Enum


class MCServerStatus(str, Enum):
    REMOVED = "REMOVED"
    EXISTS = "EXISTS"
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    STARTING = "STARTING"
    HEALTHY = "HEALTHY"
