================================
Running AutoControl in CI / Cloud
================================

AutoControl is a GUI automation framework, so by default it expects a
real display server. The provided Docker images let you run the same
code in CI pipelines, Kubernetes, or any container runtime with no
physical screen attached.

Two container variants ship with the project:

* ``docker/Dockerfile`` (default) — ``python:3.12-slim`` plus **Xvfb**.
  Headless. ~750 MB. Use for CI runs, REST-only deployments, and
  remote-desktop hosts that talk to API clients (no operator looking
  at the desktop).
* ``docker/Dockerfile.xfce`` — same base image plus **XFCE4** and
  **x11vnc**. ~1.5 GB. Use when you need a real desktop session that
  an operator can attach to with a VNC viewer, or when tests need a
  window manager (drag/drop targets, taskbar, …).

----

Quick start
===========

Build the slim image once, then run any of the entry-point modes:

.. code-block:: bash

   # Build (from the repo root, not docker/):
   docker build -f docker/Dockerfile -t autocontrol:latest .

   # Run the REST API on :9939
   docker run --rm -p 9939:9939 -e AC_TOKEN=mytoken autocontrol:latest

   # Or the Remote-Desktop TCP host on :9940
   docker run --rm -p 9940:9940 -e AC_TOKEN=mytoken \
       autocontrol:latest remote-host

   # Or the WebRTC signaling server on :8765
   docker run --rm -p 8765:8765 autocontrol:latest signaling

   # Or a debug shell (Xvfb still runs in the background)
   docker run --rm -it autocontrol:latest shell

Set ``XVFB_GEOMETRY`` (default ``1280x800x24``) to change the virtual
screen resolution. ``DISPLAY`` defaults to ``:99``.

----

GitHub Actions
==============

A ready-to-use workflow lives in
``.github/workflows/docker.yml``. It builds the slim image on every
push touching ``docker/``, ``je_auto_control/`` or
``pyproject.toml``, runs the **headless pytest suite** inside the
container under ``xvfb-run``, then smoke-tests the REST entrypoint
with ``curl /health``.

Reuse from any branch by adding this job to your own workflow:

.. code-block:: yaml

   jobs:
     headless-pytest:
       runs-on: ubuntu-22.04
       steps:
         - uses: actions/checkout@v4
         - uses: docker/setup-buildx-action@v3
         - uses: docker/build-push-action@v5
           with:
             context: .
             file: docker/Dockerfile
             tags: autocontrol:ci
             load: true
         - run: |
             docker run --rm --user root \
               -v "$PWD:/work" -w /work \
               --entrypoint /bin/sh autocontrol:ci -c "
                 pip install --no-cache-dir -r dev_requirements.txt &&
                 xvfb-run -a -s '-screen 0 1280x800x24' \
                   python -m pytest test/unit_test/headless -q
               "

----

GitLab CI
=========

Copy ``ci_templates/.gitlab-ci.yml`` to the repo root. It uses
Docker-in-Docker (``docker:24-dind``) and mirrors the GitHub flow:
build → headless pytest → REST smoke. The template also includes a
commented-out ``publish:`` job for pushing tagged builds to the
GitLab Container Registry.

The runner needs the ``docker`` executor or a privileged shell
executor — both the SaaS shared runners and most self-hosted setups
work out of the box.

----

Kubernetes
==========

The slim image is a self-contained server. Run it as a Deployment +
Service:

.. code-block:: yaml

   apiVersion: apps/v1
   kind: Deployment
   metadata:
     name: autocontrol
   spec:
     replicas: 1
     selector:
       matchLabels: { app: autocontrol }
     template:
       metadata:
         labels: { app: autocontrol }
       spec:
         containers:
           - name: rest
             image: autocontrol:latest
             args: ["rest"]
             env:
               - name: AC_TOKEN
                 valueFrom:
                   secretKeyRef:
                     name: autocontrol-token
                     key: token
             ports:
               - containerPort: 9939
             readinessProbe:
               httpGet:
                 path: /health
                 port: 9939
                 httpHeaders:
                   - name: Authorization
                     value: Bearer $(AC_TOKEN)

A Helm chart with sane defaults lives under ``helm/autocontrol/``
(see the ``Phase 9.x`` notes in the repo for the full chart layout
including PodSecurityContext, the ``ydotoold`` sidecar pattern for
``/dev/uinput`` workloads, and the optional ``coturn`` companion).

----

Limitations
===========

* The slim Xvfb image has **no window manager**. Tests that need
  taskbar / WM behaviour (window placement, drag-drop targets,
  decorations) should use the XFCE variant instead.
* ``/dev/uinput`` (the Linux Interception-style backend) requires
  ``--device /dev/uinput`` on ``docker run`` *and* a host kernel
  module — most managed CI runners do not expose it.
* Wayland is detected at import time. Set
  ``JE_AUTOCONTROL_LINUX_DISPLAY_SERVER=x11`` inside the container if
  the runner injects ``XDG_SESSION_TYPE=wayland`` from the host.
* The REST and Remote-Desktop hosts default to binding on ``0.0.0.0``
  inside the container — front them with a network policy or
  reverse-proxy when exposing them beyond ``localhost``.
