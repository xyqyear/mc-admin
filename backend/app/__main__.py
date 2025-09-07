import uvicorn

from .config import settings
from .main import app

if __name__ == "__main__":
    uvicorn.run(app, host=settings.host, port=settings.port, reload=False)
