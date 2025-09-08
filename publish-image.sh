#!/usr/bin/env bash

# Usage: ./publish-ghcr.sh <version>
# Example: ./publish-ghcr.sh v1.2.3

set -e

# Configurations
OWNER="xyqyear"
REPO="mc-admin"
IMAGE="ghcr.io/$OWNER/$REPO"

# Check arguments
if [ -z "$1" ]; then
  echo "Usage: $0 <version>"
  exit 1
fi

RAW_VER="$1"

# Remove leading "v" if present
if [[ "$RAW_VER" == v* ]]; then
  VER="${RAW_VER:1}"
else
  VER="$RAW_VER"
fi

# Extract major, minor, patch
IFS='.' read -r MAJOR MINOR PATCH <<< "$VER"

if [[ -z "$MAJOR" || -z "$MINOR" || -z "$PATCH" ]]; then
  echo "Error: version must be in the format major.minor.patch (e.g., 1.2.3)"
  exit 1
fi

# Build image
docker build -t "$IMAGE:$VER" .

# Tag versions
docker tag "$IMAGE:$VER" "$IMAGE:$MAJOR"
docker tag "$IMAGE:$VER" "$IMAGE:$MAJOR.$MINOR"
docker tag "$IMAGE:$VER" "$IMAGE:latest"

# Login to GHCR (only needs to be done once per session)
echo "If not already logged in, run:"
echo "  echo <YOUR_GITHUB_TOKEN> | docker login ghcr.io -u $OWNER --password-stdin"

# Push all tags
docker push "$IMAGE:$VER"
docker push "$IMAGE:$MAJOR"
docker push "$IMAGE:$MAJOR.$MINOR"
docker push "$IMAGE:latest"

echo "Pushed: $IMAGE:$VER $IMAGE:$MAJOR $IMAGE:$MAJOR.$MINOR $IMAGE:latest"
