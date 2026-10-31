# A disposable test toolchain, never a production service image.
FROM debian:13-slim@sha256:1e1a22175fbf1b32157ddaf0219e1db4e5401fab2b94ed285add64d18587cd2d
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates git gnupg python3 python3-venv \
    && python3 -m venv /opt/native-venv \
    && /opt/native-venv/bin/pip install --no-cache-dir pytest==9.1.1 \
    && rm -rf /var/lib/apt/lists/*
ENV PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 TZ=UTC
WORKDIR /source
ENTRYPOINT ["/opt/native-venv/bin/python"]
