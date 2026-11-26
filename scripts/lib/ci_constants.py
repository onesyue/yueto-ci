"""CI budgets, endpoints and ports for yueto-ci scripts.

One name per meaning. Brand hosts stay in ``scripts/brand_literals.py``;
this module does not repeat them and does not read another repository.
Nothing here is deploy-specific, so there is no environment override.
Protocol values (the PostgreSQL port, statement/predicate URIs) are named
so call sites do not repeat them; they are not knobs.
"""

from __future__ import annotations

# --- Endpoints. Not brand hosts. ---

GITHUB_HTTPS_ORIGIN = "https://github.com"
GITHUB_API_ORIGIN = "https://api.github.com"
GITHUB_ONESYUE_PREFIX = "https://github.com/onesyue/"
GHCR_ORIGIN = "https://ghcr.io"
ACTIONS_OIDC_ISSUER = "https://token.actions.githubusercontent.com"
SLSA_PROVENANCE_PREDICATE = "https://slsa.dev/provenance/v1"
IN_TOTO_STATEMENT_V01 = "https://in-toto.io/Statement/v0.1"
CYCLONEDX_BOM_PREDICATE = "https://cyclonedx.org/bom"
SPDX_DOCUMENT_PREDICATE = "https://spdx.dev/Document"

# --- Timeouts and intervals, in seconds. ---

GITHUB_HTTP_TIMEOUT_SECONDS = 30
GH_API_TIMEOUT_SECONDS = 60
GH_ATTESTATION_TIMEOUT_SECONDS = 180
GIT_COMMAND_TIMEOUT_SECONDS = 20
GIT_REV_PARSE_SHORT_TIMEOUT_SECONDS = 15
GIT_REV_PARSE_TIMEOUT_SECONDS = 30
GIT_OBJECT_TIMEOUT_SECONDS = 60
GPGV_TIMEOUT_SECONDS = 30
DOCKER_INSPECT_TIMEOUT_SECONDS = 30
DOCKER_HOSTED_CLEANUP_TIMEOUT_SECONDS = 60
DOCKER_LIFECYCLE_TIMEOUT_SECONDS = 120
DOCKER_WAIT_TIMEOUT_SECONDS = 7200
NODE_SUBPROCESS_TIMEOUT_SECONDS = 10
PROCESS_WAIT_TIMEOUT_SECONDS = 10
PROCESS_GROUP_JOIN_SECONDS = 5
PROCESS_GROUP_SETTLE_SECONDS = 0.5
PROCESS_GROUP_POLL_SECONDS = 0.05
ARTIFACT_RETRY_DELAY_SECONDS = 2
RUN_DISCOVERY_POLL_SECONDS = 5
RUN_DISCOVERY_DEADLINE_SECONDS = 180
SCAN_COMMAND_TIMEOUT_SECONDS = 600
TRIVY_ACTION_TIMEOUT_MINUTES = 15
HEAD_SCAN_CHECKOUT_MINUTES = 15
COREPACK_ENABLE_TIMEOUT_SECONDS = 60
COREPACK_PREPARE_TIMEOUT_SECONDS = 180
RATE_LIMIT_BACKOFF_SECONDS = 60
RATE_LIMIT_RETRY_CEILING_SECONDS = 300

# --- Counts and read bounds. ---

LOG_HEADER_BYTE_LIMIT = 65536
VALIDATION_IMAGE_WORKERS = 5
CI_FAILURE_CLUSTER_WORKERS = 4
POSTGRES_HEALTH_ATTEMPTS = 60
MAX_VERSION_PAGES = 100

# Package-size floors for the native contract. Each value is that package's
# reviewed minimum, not a shared knob.
NODE_CONFIG_MIN_FILES = 5
NODE_CONTROLPLANE_MIN_FILES = 5
NODE_SERVICE_MIN_FILES = 8
NODE_SERVICE_TEST_MIN_FILES = 3
NODE_MODEL_MIN_FILES = 8
NODE_XRAY_MIN_FILES = 20
NODE_XRAY_TEST_MIN_FILES = 10
NODE_HYSTERIA_MIN_FILES = 8
NODE_HYSTERIA_TEST_MIN_FILES = 10
OPS_DEPLOY_MIN_FILES = 5
BOARD_NODESYNC_MIN_FILES = 30
BOARD_SUBSCRIBE_MIN_FILES = 10
BOARD_DEVICE_IDENTITY_MIN_FILES = 2
BOARD_MODULE_MIN_FILES = 100
BOARD_WEB_MIN_FILES = 50
DEADCODE_MIN_CONFIDENCE = 100
COMPLEXITY_CCN_LIMIT = 30
COMPLEXITY_NLOC_LIMIT = 200

# Needles matched against published image and generator source.
NODE_IMAGE_BIN_COPY = "COPY --from=builder /build/yue-node* /usr/local/bin/"
NODE_ENTRYPOINT_NEEDLE = 'entrypoint: ["{BIN_YUE_NODE_PREFIX}{role}"]'
NODE_EXPECTED_PATH_NEEDLE = 'expected_path = f"{BIN_YUE_NODE_PREFIX}{role}"'

# --- Ports. 5432 is the PostgreSQL assigned port, not an env override. ---

POSTGRES_PORT = 5432
BOARD_E2E_PUBLISHED_POSTGRES_PORT = 55434
