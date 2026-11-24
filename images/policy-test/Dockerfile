FROM golang:1.27.2-bookworm@sha256:5cf287a799e6b94384bad13d16b14904c531f51ba65792237e122ce42b392f61 AS go_toolchain
FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90

COPY --from=go_toolchain /usr/local/go /usr/local/go
ENV PATH="/usr/local/go/bin:/usr/local/bin:/usr/bin:/bin" GOTOOLCHAIN=local TZ=UTC
RUN apt-get update -qq \
    && apt-get install -y --no-install-recommends bash ca-certificates curl git gnupg gpgv jq nodejs shellcheck xz-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-policy.txt scripts/run-policy-tests.py scripts/lint-tool-versions.sh scripts/ci-retry.sh /tmp/policy/
RUN bash -euo pipefail -c '\
    cd /tmp/policy; \
    source lint-tool-versions.sh; \
    source ci-retry.sh; \
    ci_download 5 --fail --silent --show-error --location --proto "=https" --tlsv1.2 \
      "https://github.com/rhysd/actionlint/releases/download/v${ACTIONLINT_VERSION}/actionlint_${ACTIONLINT_VERSION}_linux_amd64.tar.gz" \
      --output actionlint.tar.gz; \
    printf "%s  %s\n" "$ACTIONLINT_ARCHIVE_SHA256" actionlint.tar.gz | sha256sum --check --strict; \
    tar -xzf actionlint.tar.gz -C /usr/local/bin actionlint; \
    actionlint -version; \
    shellcheck --version; \
    python -m pip install --no-cache-dir --require-hashes --only-binary=:all: -r requirements-policy.txt; \
    python run-policy-tests.py --check-toolchain' \
    && rm -rf /tmp/policy

RUN /usr/sbin/useradd --uid 1000 --user-group --create-home policy \
    && install -d -o policy -g policy /gate
ENV HOME=/home/policy
USER policy
RUN test "$(id -u)" -gt 0 && test -w /gate && test -w "$HOME"
