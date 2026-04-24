from typing import Annotated

from pydantic import Field

from ..schemas import BaseConfigSchema


class MCMapConfig(BaseConfigSchema):
    """Server map (mcmap) rendering configuration."""

    stale_timeout_seconds: Annotated[
        int,
        Field(
            description="Serve cached PNG when (mca.mtime - png.mtime) is below this; otherwise re-render",
            ge=0,
            le=3600,
        ),
    ] = 60
    batch_size: Annotated[
        int,
        Field(
            description="Maximum regions rendered in a single mcmap invocation",
            ge=1,
            le=256,
        ),
    ] = 16
    thread_count: Annotated[
        int,
        Field(
            description="Worker thread count passed to mcmap as -j",
            ge=1,
            le=64,
        ),
    ] = 4
    request_timeout_seconds: Annotated[
        int,
        Field(
            description="Maximum seconds a tile HTTP request waits on a render to complete",
            ge=1,
            le=600,
        ),
    ] = 30
