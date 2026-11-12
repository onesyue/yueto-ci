# YueOps / YueBoard validation toolchain. Validate jobs run this image and do
# not apt. Rebuild with .github/workflows/ci-toolchain.yml and pin the digest
# in build.yml. Apt happens only while this image is built.
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PATH=/usr/lib/postgresql/18/bin:/usr/local/go/bin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    GOTOOLCHAIN=local \
    UV_PYTHON_INSTALL_DIR=/opt/uv-python

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates curl gnupg sudo git jq build-essential \
      locales xz-utils logrotate docker.io \
 && rm -rf /var/lib/apt/lists/*

# PGDG key fingerprint is the one the retired apt installer required.
RUN curl --fail --silent --show-error --location \
      --proto '=https' --proto-redir '=https' --tlsv1.2 \
      https://www.postgresql.org/media/keys/ACCC4CF8.asc --output /tmp/pgdg.asc \
 && fingerprint=$(gpg --batch --show-keys --with-colons /tmp/pgdg.asc \
      | awk -F: '$1 == "fpr" && !seen {print $10; seen=1}') \
 && test "$fingerprint" = B97B0AFCAA1A47F044F244A07FCC7D46ACCC4CF8 \
 && install -d -m 0755 /usr/share/keyrings \
 && gpg --dearmor --output /usr/share/keyrings/postgresql.gpg /tmp/pgdg.asc \
 && printf '%s\n' \
      'Types: deb' \
      'URIs: https://apt.postgresql.org/pub/repos/apt' \
      'Suites: noble-pgdg' \
      'Components: main' \
      'Signed-By: /usr/share/keyrings/postgresql.gpg' \
      > /etc/apt/sources.list.d/pgdg.sources \
 && apt-get update \
 && apt-get install -y --no-install-recommends postgresql-18 postgresql-client-18 libpq-dev \
 && test -e /usr/lib/postgresql/18/lib/plpgsql.so \
 && test -e /usr/lib/postgresql/18/lib/dict_snowball.so \
 && test -f "$(pg_config --includedir)/pg_config.h" \
 && postgres --version | grep -E '\(PostgreSQL\) 18[.]' \
 && rm -rf /var/lib/apt/lists/* /tmp/pgdg.asc

# Reviewed native-test NGINX (scripts/native-nginx-toolchain.json, amd64).
RUN curl --fail --silent --show-error --location \
      --proto '=https' --proto-redir '=https' --tlsv1.2 \
      https://nginx.org/packages/ubuntu/pool/nginx/n/nginx/nginx_1.30.5-1~noble_amd64.deb \
      --output /tmp/nginx.deb \
 && echo '2ed3c0c4c5e24fe6c2bb46a5fc255d7e0de718e5ff5d8d6c9e17c79a1313dc05  /tmp/nginx.deb' | sha256sum -c \
 && apt-get update \
 && apt-get install -y --no-install-recommends /tmp/nginx.deb \
 && rm -rf /var/lib/apt/lists/* /tmp/nginx.deb \
 && nginx -v 2>&1 | grep -F 'nginx/1.30.5'

RUN curl --fail --silent --show-error --location \
      --proto '=https' --proto-redir '=https' --tlsv1.2 \
      https://go.dev/dl/go1.27.4.linux-amd64.tar.gz --output /tmp/go.tgz \
 && echo '7226736c2339719cda28fbf3a54d71aa63bcefe376e98cef00034268dab24840  /tmp/go.tgz' | sha256sum -c \
 && rm -rf /usr/local/go \
 && tar -C /usr/local -xzf /tmp/go.tgz \
 && rm /tmp/go.tgz \
 && go version | grep -F 'go1.27.4'

RUN curl --fail --silent --show-error --location \
      --proto '=https' --proto-redir '=https' --tlsv1.2 \
      https://nodejs.org/dist/v24.22.3/node-v24.22.3-linux-x64.tar.xz --output /tmp/node.tar.xz \
 && echo '4f2b175a6d53a5c617a80dba2676238a0688cef28c6da4eba35c7d844e66fcfb  /tmp/node.tar.xz' | sha256sum -c \
 && tar -C /usr/local --strip-components=1 -xJf /tmp/node.tar.xz \
 && rm /tmp/node.tar.xz \
 && node --version | grep -F 'v24.22.3' \
 && corepack --version \
 && corepack enable

# uv 0.10.9 is the version build.yml setup-uv pins. UV_SHA256 is filled from
# the release tarball before the image is built; the workflow refuses a blank.
# UV_PYTHON_INSTALL_DIR must stay set for `uv python find`: install and find
# do not share a default directory.
ARG UV_SHA256
RUN test -n "$UV_SHA256" \
 && curl --fail --silent --show-error --location \
      --proto '=https' --proto-redir '=https' --tlsv1.2 \
      https://github.com/astral-sh/uv/releases/download/0.10.9/uv-x86_64-unknown-linux-gnu.tar.gz \
      --output /tmp/uv.tgz \
 && echo "$UV_SHA256  /tmp/uv.tgz" | sha256sum -c \
 && tar -C /tmp -xzf /tmp/uv.tgz \
 && install -m 0755 /tmp/uv-x86_64-unknown-linux-gnu/uv /usr/local/bin/uv \
 && rm -rf /tmp/uv.tgz /tmp/uv-x86_64-unknown-linux-gnu \
 && uv --version | grep -F '0.10.9' \
 && uv python install 3.13 \
 && py=$(uv python find 3.13) \
 && test -x "$py" \
 && ln -sfn "$py" /usr/local/bin/python3.13 \
 && ln -sfn python3.13 /usr/local/bin/python3 \
 && ln -sfn python3.13 /usr/local/bin/python \
 && python3 -c 'import sys; assert sys.version_info[:2] == (3, 13)' \
 && chmod -R a+rX /opt/uv-python

RUN curl --fail --silent --show-error --location \
      --proto '=https' --proto-redir '=https' --tlsv1.2 \
      https://github.com/bufbuild/buf/releases/download/v1.72.0/buf-Linux-x86_64 \
      --output /usr/local/bin/buf \
 && echo '8720830e26a733da55bb89bcd3cb44849c0965fc0c44fb5d691cccdc64dca5af  /usr/local/bin/buf' | sha256sum -c \
 && chmod 0755 /usr/local/bin/buf \
 && buf --version | grep -F '1.72.0'

RUN curl --fail --silent --show-error --location \
      --proto '=https' --proto-redir '=https' --tlsv1.2 \
      https://github.com/SagerNet/sing-box/releases/download/v1.14.4/sing-box-1.14.4-linux-amd64.tar.gz \
      --output /tmp/sing-box.tgz \
 && echo '699a1b510aa4396b2176d32d1181920399ebf1e267835da6f3b598d0f7c24968  /tmp/sing-box.tgz' | sha256sum -c \
 && tar -C /tmp -xzf /tmp/sing-box.tgz \
 && install -m 0755 /tmp/sing-box-1.14.4-linux-amd64/sing-box /usr/local/bin/sing-box-1.14 \
 && rm -rf /tmp/sing-box.tgz /tmp/sing-box-1.14.4-linux-amd64 \
 && sing-box-1.14 version | grep -E '^sing-box version 1\.14\.'

COPY selfcheck.sh /usr/local/bin/yueops-ci-toolchain-selfcheck
RUN chmod 0755 /usr/local/bin/yueops-ci-toolchain-selfcheck \
 && groupadd --gid 1001 runner \
 && useradd --uid 1001 --gid 1001 --create-home --shell /bin/bash runner \
 && printf '%s\n' 'runner ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/runner \
 && chmod 0440 /etc/sudoers.d/runner \
 && mkdir -p /opt/hostedtoolcache \
 && chown -R runner:runner /opt/hostedtoolcache

LABEL org.opencontainers.image.source=https://github.com/onesyue/yueto-ci
LABEL org.opencontainers.image.description="YueOps CI toolchain (PostgreSQL 18, sing-box 1.14, Python 3.13, Go 1.27.4)"

USER runner
WORKDIR /home/runner
