# AutoControl headless host — Linux container with Xvfb for off-screen GUI work.
# Run the REST API + remote-desktop host inside a CI / Kubernetes / docker-compose
# environment with no physical display.
#
# Build:   docker build -f docker/Dockerfile -t autocontrol:latest .
# Run:     docker run --rm -p 9939:9939 -p 9940:9940 autocontrol:latest

# Build every wheel — the project and its dependencies — in a throwaway
# stage. The runtime image then installs binaries only, so no dependency
# gets to execute a setup script there and the resolved set is fixed at
# build time instead of being re-resolved against PyPI.
FROM python:3.12-slim AS builder

WORKDIR /src
COPY pyproject.toml README.md ./
COPY je_auto_control ./je_auto_control
COPY autocontrol-lsp ./autocontrol-lsp
RUN pip install --no-cache-dir --only-binary :all: --upgrade "pip==26.0.1" \
    && pip wheel --no-cache-dir --wheel-dir /wheels .


FROM python:3.12-slim AS runtime

ARG DEBIAN_FRONTEND=noninteractive

# Minimum apt set:
# - xvfb + xauth: virtual X server so the host can capture a "screen".
# - x11-utils + xdotool: useful for diagnostics, optional.
# - libgl1: PySide6 + opencv-python hard-require libGL.so.1 at import.
# - libglib2.0-0: opencv-python needs libgthread-2.0.so.0 from glib.
# - libxkbcommon-x11-0 + libdbus-1-3 + libxcb-*: Qt platform plugins.
# - libusb-1.0-0: USB enumeration via pyusb / libusb.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        xvfb xauth x11-utils xdotool \
        libgl1 libglib2.0-0 \
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

# Install from the wheels built above: pinned pip, wheels only, and no
# index lookup, so the runtime layer cannot pull anything new from PyPI.
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --only-binary :all: --upgrade "pip==26.0.1" \
    && pip install --no-cache-dir --only-binary :all: --no-index \
       --find-links=/wheels /wheels/je_auto_control-*.whl \
    && rm -rf /wheels

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
