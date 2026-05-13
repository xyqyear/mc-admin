"""FTB Utilities / FTB Chunks claim extraction.

Wraps ``mcmap extract-ftb-claims``, resolves its dim ids against the backend's
world layout, and groups each team's claims into stable per-dimension clusters
for the world-restore overlay. The route handler in
``app.routers.servers.world_restore`` calls :func:`extract_claims_for_server`
on every request — there is no caching.
"""

from .cluster import build_clusters
from .extract import (
    FtbExtractError,
    NoFtbDataError,
    extract_claims_for_server,
)
from .models import (
    ClaimDimensionEntry,
    ClaimMember,
    ClaimsResponse,
    ClusterEntry,
    DetectedFormat,
    TeamEntry,
    TeamType,
)

__all__ = [
    "ClaimDimensionEntry",
    "ClaimMember",
    "ClaimsResponse",
    "ClusterEntry",
    "DetectedFormat",
    "FtbExtractError",
    "NoFtbDataError",
    "TeamEntry",
    "TeamType",
    "build_clusters",
    "extract_claims_for_server",
]
