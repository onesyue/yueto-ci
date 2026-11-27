"""Named pins and collection limits for the Ops pytest shard policy."""
from __future__ import annotations

import re


SHA = re.compile(r"[0-9a-f]{40}")


EXPECTED_CONFIG = {
    "testpaths": "tests", "python_files": "test_*.py",
    "python_functions": "test_*", "asyncio_mode": "auto",
}


# Temp-dir retention keys only bound what pytest keeps on disk after a run;
# they never change which modules or tests are collected.
OPTIONAL_RETENTION_CONFIG = {
    "tmp_path_retention_policy": "failed", "tmp_path_retention_count": "1",
}


IDENTITY_FIELDS = ("policy_revision", "board_revision", "run_id", "run_attempt",
                   "runner_os", "runner_arch", "runner_image")


FILES = ("metadata.json", "events.jsonl", "pytest-exit-code.txt",
         "pytest-start-unix-ns.txt", "pytest-finish-unix-ns.txt", "selection.json")


SKIP_BASELINE = "ops-pytest-skip-baseline.json"


# The exact reviewed record is pinned independently of its baseline payload.
SSH_SKIP_TRANSITION_SHA256 = "df44974b4d4e883d73ffa6d3067a378441650456d3d1a64655f4d7ae73d1547f"


W85_INPUT_TRANSITION_SHA256 = "975897eb2f19379c17e81bb26ebbd6ea0d362563519174c27ceef000ff14223c"


W85_OBSERVABILITY_TRANSITION_SHA256 = "aa2582effcfb53d71b11abe0a60db1e9231c9236da6badc6cf49a1c128548c98"


AUDIT_DEPENDENCY_TRANSITION_SHA256 = "ff5a2514cd10c6c9cc81cb1e4e52afab20ba789b8a8af92ef4dcbd21cbbb1b6a"


ZOD_LOCK_TRANSITION_SHA256 = "691c045988e884f360dc6925bffea7798295970f2d62763ffec180ff2b20e842"


CURRENT_SKIP_TRANSITION_SHA256 = "302153cd755ac54d2346e0c3114fcfde776ba8ea79fbe2fd4d7de9d7cdae726d"


SCANNER_INPUT_TRANSITION_SHA256 = "5a639c8b455a5934d206af1f4e03d386d91b55a986f2e52ffc79cbedd2d1563c"


RELAY_SKIP_MODULE_TRANSITION_SHA256 = "afab000651dcbd556b14b27b27ecfc283f935f78be984293dbf2f1dcf971042b"


RELAY_METER_MODULE_TRANSITION_SHA256 = "99945322ac036c84b3a4a87e6f9378156e14e5cc1ec6d04680d69c54d44ad2df"


RELAY_PRESERVATION_MODULE_TRANSITION_SHA256 = "f5d43ba785159b00ab42f7034d29c77d78d8d9164f89b46b76d88a093c81407b"


RELAY_METRICS_MODULE_TRANSITION_SHA256 = "777214bee79eb25858c97781aaa065b53770693252185f3ee61e19c3c61efa07"


CASE_FILE_TRANSITION_SHA256 = "75190b489a8b271e693c52e78c183894f47e34e930183b9f433e538045afb9c7"


SKIP_BLOB_SUCCESSOR_TRANSITION_SHA256 = "befa7b3d2cb2c5d3bbeb6e225f908087b1cd42c0bedbe290033a73b3fffe799d"


I10_SKIP_BLOB_SUCCESSOR_TRANSITION_SHA256 = "f17408349a9f920c4712e112381a0b1ad40b00abc5d9357b6e423812b7e3ba20"


RELEASE_SKIP_BLOB_SUCCESSOR_TRANSITION_SHA256 = "efa7c2e8c9944feeccbcf0bf1111b3b4b67f8b15c94e1b6d41879654136d274b"


HANG_GUARD_INPUT_TRANSITION_SHA256 = "eb65c84d7ddab61a441c54d2f64a30e992f039b2c0c6ba709b570f5d3787fff0"


# Sealed to the signed Tornado successor and authentic review/qualification receipts.
TORNADO66_DEPENDENCY_TRANSITION_SHA256 = "bed6e74fdb1a4b40775bc6fc9c4c4c6857ee6de8a245910e91809e7672756876"


# Sealed to the signed yueops 65887947/22a82f65 four-input successor and its receipts.
OPS_PACKAGING_TRANSITION_SHA256 = "755b998311346730753ebc2c44dd8a3dcb4b3bb9216756b6f126125b07b8fb27"


SSH_SKIP_CASES = {
    "tests/test_host_service_contracts_20261013.py::test_node_producer_is_durable_and_idempotent",
    "tests/test_installed_checker_transport_20261014.py::"
    "test_real_pinned_sshd_json_transport_plan_apply_readback_and_old_n_negative",
}


HISTORICAL_NATIVE_INPUTS = {
    "tests/native_loadshed_installer_20261030.py": "a861b1d6b30b3ba59d5321051430c73c099d25c2",
}


NATIVE_INPUTS = {
    "tests/native_loadshed_installer_20261030.py": "441aa89516d7a8afa651486cb893090563efe9d9",
}


# Reviewed pins of the same installer, oldest admitted tip last excluded.
# The historical predecessor stays rejected. Unknown blobs stay rejected.
# Each entry was the signed after-blob of a loadshed row-count ratchet.
NATIVE_INPUT_CHAIN = {
    "tests/native_loadshed_installer_20261030.py": frozenset({
        "b4a70d6d7c6c1b3e20e7263d8f12c4a69143b385",
        "4fe2c7b40110f20fa496b0fdd85cfe8c75da8591",
        "441aa89516d7a8afa651486cb893090563efe9d9",
    }),
}


NATIVE_INPUT_SUCCESSOR_KEY = "reviewed_loadshed_native_input_successor"


# Filled only from the actual signed source/review/qualification record.
NATIVE_INPUT_SUCCESSOR_SHA256 = "1c6883845729d08bb3ff932f54630a4cb25420b95b97650e5ee468c83333891f"


NATIVE_TARGETS = {
    "tests/native_loadshed_installer_20261030.py": (14, 0),
    "tests/test_board139_schema_acl_native_20261018.py": (6, 1001),
    "tests/test_node_systemd_pilot_20261018.py": (38, 0),
    "tests/test_schema_contract_receipt_20261020.py": (30, 0),
    "tests/test_panel_subscribe_delivery_alert_20261012.py": (17, 0),
    "tests/test_frozen_manifest_reader_20261015.py": (4, 0),
    "tests/test_status_tls_installer_20261027.py": (7, 0),
}


ORDINARY_WEIGHTS_PREFIX = "ops-ordinary-weights-"


PASSIVE_TIMING_PREFIX = "yueops-pytest-timing-"


ESTATE_INPUT_PATHS = {
    "qa/package.json", "qa/package-lock.json", "telegram-bot/yue/pyproject.toml",
    "tests/node_resource_fixture.py", "tests/native/subscribe_template_baseline_cas_pg.py",
}


ESTATE_ADDED_INPUT = "tests/native/subscribe_template_baseline_cas_pg.py"


# Preserve the historical estate seal, but retire its source-copy writer probe
# only after the exact reviewed deletion. No historical execution is credited.
TEMPLATE_WRITER_RETIREMENT = "6f7a1f635c94c9c5a0aeeb993c7893d7efe48dfc"


TEMPLATE_WRITER_BEFORE_BLOB = "1933467673713272e85f47a5732692d1c285a858"


SITE_LOCK_INPUT = "site/pnpm-lock.yaml"


BOT_PACKAGING_INPUT = "telegram-bot/yue/pyproject.toml"


HANG_GUARD_INPUT = "tests/_subprocess.py"


AUDIT_LOCK_INPUT = "uv.lock"


# Each runtime dependency input is bound to the exact after-blob of the seal that
# last reviewed it; nothing outside these three paths may move.
RUNTIME_DEPENDENCY_INPUTS = {
    "pyproject.toml": "reviewed_audit_dependency_transition",
    "telegram-bot/yue/requirements.txt": "reviewed_python_input_transition",
    "uv.lock": "reviewed_audit_lock_transition",
}


RETIRED_HOST_KEY = "reviewed_retired_host_transition"


RETIRED_HOST_MODULE = "tests/test_miniapp_existing_app_nginx_native_20261013.py"


RETIRED_HOST_PRIOR_SHA256 = "927f711ddbdd4aa14012ccb687183e969610922e0c9b17b55eef06545ec86e91"


RETIRED_HOST_BEFORE_BLOB = "812e3509c7213cf16f507271f5a1d4f8c0cefe29"


RETIRED_HOST_AFTER_BLOB = "ba19e043309d0805710e0a2d3fc9cc76ea6ce55f"


RETIRED_HOST_TRANSITION_SHA256 = "961fa6fd314c9d292e766e1cea5b8571f0d97b489adbebb63d4f35d16af6d7b0"


# 2026-11-10 (owner t836u, yueops fdf97f87e / 3ed500a0f): the sibling Mini host
# brand_literals.RETIRED_MINI_ALTERNATE_HOST was retired too and the fixture
# certificate moved to brand_literals.PANEL_HOST. This is a code-reviewed
# successor on top of the sealed transition above; it changes no baseline
# bytes. With exactly this module blob, the three alternate-mirror Mini
# cases must be absent and every other survivor keeps its sealed outcome
# and reason. Any other blob still has to equal the sealed case.
RETIRED_HOST_SECOND_AFTER_BLOB = "6c3e8eca2a185a9b89aedbc3abec63c7cc2eb2fd"


# 2026-11-27 (owner t1528u, yueops #1240): the 靠谱云.com panel mirror
# brand_literals.PANEL_MIRROR_ALTERNATE_HOST was retired and its nginx vhost
# deleted, so the module dropped that host and the apex probe in
# test_native_unchanged_panel_site_url_bearer_and_default444 now covers only
# the remaining mirror. Code-reviewed successor on top of the second one; it
# changes no baseline bytes. With exactly this module blob, the second
# transition's absences hold, the three alternate-panel cases must be absent
# too, and every other survivor keeps its sealed outcome and reason.
RETIRED_HOST_THIRD_AFTER_BLOB = "2e7ad9e66349f16a144e43082d9cdcc9f2190cfc"


NEZHA_RETIREMENT_KEY = "owner_nezha_retirement_20261103"


NEZHA_RETIRED_MODULE = "tests/test_nezha_retirement_20261013.py"


NEZHA_PRIOR_BASELINE_SHA256 = "190f2ad9a50a78d0d8bfac1eb383f350e36586688510aa025e74435e6c28332d"


SECURITY_INPUT_KEY = "reviewed_npm_security_transition"


SECURITY_INPUT_PATHS = frozenset({"frontend/package.json", "frontend/package-lock.json",
    "telegram-bot/yue/miniapp/package.json", "telegram-bot/yue/miniapp/package-lock.json"})


SECURITY_INPUT_TRANSITION_SHA256 = "92aae6604a0d8a027c667313be6fbaf9dc1f87ee260cf7baed00d57f2f767bb2"


COLLECTION_SHUFFLE_KEY = "reviewed_collection_shuffle_transition"


COLLECTION_SHUFFLE_INPUT = "conftest.py"


# Exact independently reviewed record and actual same-source collection receipt.
COLLECTION_SHUFFLE_TRANSITION_SHA256 = "2140ecb94164f962036d2cd6353285042d5d955ffecc0817c753fed0fe2fa139"


OPS_PACKAGING_KEY = "reviewed_ops_packaging_transition"


OPS_PACKAGING_INPUT = "pyproject.toml"


OPS_PACKAGING_ADDED_INPUT = "tests/_runtime_module_patch.py"


OPS_PACKAGING_INPUTS = frozenset({
    OPS_PACKAGING_INPUT, OPS_PACKAGING_ADDED_INPUT,
    "tests/_bot_real_modules.py", "tests/_yueboard_internal_source.py",
})


# Outermost first; historical seals remain unchanged.
PR_SHARED_INPUT_SEALS = (
    (256, "894176392f12701905ae38034d84fbb1ed922a9a76266e5ec08f23abd1db3636",
     frozenset({"pyproject.toml", "uv.lock"})),
    (122, "c2d8f9c57343ec12fcbaecda2bd3ef2e4fcf68c0fba3c4b86dd2f4c4bbdd7a46",
     frozenset({"checkin-api/requirements.txt", "pyproject.toml",
                "telegram-bot/yue/requirements.txt", "uv.lock"})),
)


# Activate only for these exact after-blobs; historical policy fixtures need no new evidence.
PR_SHARED_INPUT_AFTER_BLOBS = frozenset({
    ('pyproject.toml', '1d861dc9e1da3fbe876ded02f454a3fd26f2cd27'),
    ('uv.lock', 'a432bb987a9b6f8f7871647680e9078c6a56b6a3'),

    ('checkin-api/requirements.txt', 'a5bd445e3f132c2fd090490ab07bb8ee79de6a2f'),
    ('pyproject.toml', 'ba32ad966dc0d67280ba04c03c1f911c8839780a'),
    ('telegram-bot/yue/requirements.txt', '6d87484afee325a2c00630c6eb1c9ed411b130f1'),
    ('uv.lock', '18d0dc71583fcd55ae726dd6c533e0f2111539f2'),
})


PR_SHARED_INPUT_SOURCE_REVISIONS = (
    "4b64bf9a9b26a24aecdc551bbe7eaa7a840558cd",
    "56a7e0412e9bd1d297ba4a5dd3d363147fac463c",
)


MINIAPP_MEMBERSHIP_TRANSITION_SHA256 = "ca92f22e6699afa5e9dd48457b79968d8cfb540a43c6e2f7d715158423703638"


MINIAPP_MEMBERSHIP_INPUT = "tests/_miniapp_source.py"


# New shared-input seals are outermost, as with the MiniApp membership seal.
# Keep the historical baseline and every prior_baseline_sha256 byte-identical.
REVIEWED_PR_INPUTS = {
    "ruff_retired_video": ("7c952fe87ad22cce6bcadd7408c727afe31075d5a11650e9a714fa2cb0d6f88e", frozenset({"pyproject.toml"})),
    "deploy_ai_exit": (
        "e2c2ccc85646e12c1172fc83b1da76efa9e8c4e30884ddfc4abe7ce006ec6f81",
        frozenset({"tests/_deploy_source.py"}),
    ),
    "site_devdeps": (
        "b9fc088633186556e350eee3c090748d7dc18655e3aea6bbd83bd5bd92fe9de0",
        frozenset({"site/package.json", "site/pnpm-lock.yaml"}),
    ),
    # yueops #411 (short PG socket dir) + #415 (pytest tmp retention), pin 3beb7b8c.
    "test_inputs_1105": (
        "2113cfed645784355f1cbd250def65e000076f5b71f6a4d9e65772a3003d3510",
        frozenset({"pytest.ini", "tests/_native_postgres.py"}),
    ),
    # yueops 00f1063f0 (t823u): drop site npm script refresh-plans; lockfile unchanged.
    "site_refresh_plans": (
        "9e2912667e20acb474d995fffe67bbfae47a79d3e2842207fa900e49b80f3568",
        frozenset({"site/package.json"}),
    ),
    # yueops a8bdd4684 + 5c4cc83a7 (ship 9): tests/conftest.py empty retired-entry
    # quarantine fixture and direct-gfw domestic probe off in tests.
    "conftest_quarantine_1111": (
        "f0d8ba5b5660dadf4caf8690384a30ca99f540d47b519bd04d1736a1b608ccf5",
        frozenset({"tests/conftest.py"}),
    ),
}


# Later sidecars live in their own file so earlier outer seals' hashes stay exact.
REVIEWED_PR_INPUT_FILES = {"ruff_retired_video": "ops-shared-input-successors-1106.json", "test_inputs_1105": "ops-shared-input-successors-1105.json", "site_refresh_plans": "ops-shared-input-successors-1110.json", "conftest_quarantine_1111": "ops-shared-input-successors-1111.json"}


# Activate these sidecars only for their exact after-blobs (historical trees need no evidence).
REVIEWED_PR_INPUT_ACTIVATION = {"ruff_retired_video": frozenset({
    ("pyproject.toml", "fbedf7789a78aaa402835eb3747e8be2e24772d2"),
}), "test_inputs_1105": frozenset({
    ("pytest.ini", "9599c104c7dcfcfa3718c9be2335362731d4758f"),
    ("tests/_native_postgres.py", "5ac0ed066b88979b123bb0dab037ca497e41e23c"),
}), "site_devdeps": frozenset({
    # Activate only on the reviewed after package.json. The lockfile after-blob
    # is unchanged by later site_refresh_plans, so using it here would keep
    # this bundle live and reject the new package.json successor.
    ("site/package.json", "09ceb094c9286134cce8e770196ce70159a5bec6"),
}), "site_refresh_plans": frozenset({
    ("site/package.json", "2ee14b2010387075336100cd89318730b23c5c06"),
}), "conftest_quarantine_1111": frozenset({
    ("tests/conftest.py", "3776755a872e2919f9ca3360fb9a4c630b5b2ec8"),
})}


LOG_LINE_LIMIT = 400


OPS_SKIP_EVIDENCE = "tests/admission/ordinary-skip-evidence.json"


CASE_SCOPE_DEPTH = 32


_BINDING_KEYS = ("successors", "relay_successors", "metrics_successors", "meter_successors",
                 "preservation_successors", "case_successors", "blob_successors",
                 "release_blob_successors", "i10_blob_successors", "ordinary_skips")


_SKIP_UNKNOWN = object()


ORDINARY_BINDING_KEYS = (
    "successors", "relay_successors", "metrics_successors", "meter_successors",
    "preservation_successors", "case_successors", "blob_successors",
    "release_blob_successors", "i10_blob_successors", "ordinary_skips",
)


# Reviewed module blobs and case seals. One name per reviewed meaning.
CANCELED_BACKUP_AFTER_BLOB = "a609746c0f11d0965861bbecd25044c659c5eabe"
CANCELED_BACKUP_CASES_SHA256 = "8f23edcedaac436947b770f5d028c0deb4d2889201fa4bbdf63a68bec2b37ddf"
RESTORE_DRILL_BEFORE_BLOB = "2f57ec05cab6f9af631f66650feaaf76a7770222"
RESTORE_DRILL_AFTER_BLOB = "3cca4792fbd3319411901ad3588a879e7b52193f"
RESTORE_DRILL_CASES_SHA256 = "3fa2693d80385d2531d1d10e17cf6f529be968c2be53d503b0cb432d8a8de32e"
BOARD139_BEFORE_BLOB = "7031c88d7b25d3b61ff40429cc8e54f3e7248466"
BOARD139_AFTER_BLOB = "2d510c6a2e765ae7eb0379ab7671ba64d6770ef4"
BOARD139_RENEWAL_BLOB = "0509528f81cd39c6e308e130650670a874b1b3df"
NEZHA_RETIRED_CASE_BLOB = "f378f0ec5098b6f2664e97b266efd4031df0165c"
NATIVE_PROTOCOL_HELPER_POLICY_SHA256 = "1ee4183d8f902df6839936adfc6ec8bfcb995892352cf2fcdf44d51f993383ee"
P015_HELPER_POLICY_SHA256 = "cb32a56317731b0e57429ac7ca333c24bb527a7e3bc778af518e3ebc95c918a5"

_POLICY_HELPERS = (
    "_invoke_native_successor", "synthetic_native_obligations",
    "apply_ops_reviewed_skip_blobs", "apply_reviewed_skip_blob_successors",
    "prepare_skip_bindings",
)
