# AutoControl headless host — Linux container with Xvfb for off-screen GUI work.
# Run the REST API + remote-desktop host inside a CI / Kubernetes / docker-compose
# environment with no physical display.
#
# Build:   docker build -f docker/Dockerfile -t autocontrol:latest .
# Run:     docker run --rm -p 9939:9939 -p 9940:9940 autocontrol:latest

FROM python:3.12-slim AS runtime

ARG DEBIAN_FRONTEND=noninteractive

# Minimum apt set:
# - xvfb + xauth: virtual X server so the host can capture a "screen".
# - x11-utils + xdotool: useful for diagnostics, optional.
# - libgl1: PySide6 hard-requires libGL.so.1 at import time.
# - libxkbcommon-x11-0 + libdbus-1-3 + libxcb-*: Qt platform plugins.
# - libusb-1.0-0: USB enumeration via pyusb / libusb.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        xvfb xauth x11-utils xdotool \
        libgl1 \
        libxkbcommon-x11-0 libdbus-1-3 \
        libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
        libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-sync1 \
        libxcb-xfixes0 libxcb-xinerama0 libxcb-xkb1 \
        libusb-1.0-0 \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Bring in the project source. Build context is the repo root, so the
# COPY paths are relative to that — not to docker/.
COPY pyproject.toml dev_requirements.txt ./
COPY je_auto_control ./je_auto_control
COPY autocontrol-lsp ./autocontrol-lsp
COPY README.md ./

# Install the package + the [webrtc] extra so the optional WebRTC host
# also works inside the container. Pin pip first to keep layer churn
# minimal across CI rebuilds.
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e .

ENV DISPLAY=:99 \
    PYTHONUNBUFFERED=1 \
    AUTOCONTROL_HEADLESS=1

# Default ports — operator can rebind via -p when running the container.
# 9939 = REST API, 9940 = Remote Desktop TCP host, 8765 = signaling.
EXPOSE 9939 9940 8765

# Entry script handles Xvfb startup + the host process.
COPY docker/entrypoint.sh /usr/local/bin/autocontrol-entrypoint

# One RUN layer: make the entrypoint executable, create the unprivileged
# ``autocontrol`` user (uid 1001), and hand /app over to it.
RUN chmod +x /usr/local/bin/autocontrol-entrypoint \
    && groupadd --system --gid 1001 autocontrol \
    && useradd --system --uid 1001 --gid autocontrol \
       --home-dir /app --shell /usr/sbin/nologin autocontrol \
    && chown -R autocontrol:autocontrol /app
USER autocontrol

ENTRYPOINT ["/usr/local/bin/autocontrol-entrypoint"]
CMD ["rest"]
