"""CRAIC team knowledge store API."""

import uvicorn
from fastapi import FastAPI

app = FastAPI(title="CRAIC Team API", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


def main() -> None:
    """Start the CRAIC team API server."""
    uvicorn.run(app, host="0.0.0.0", port=8742)
