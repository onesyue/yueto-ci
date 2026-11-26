"""YueLink native contract validator."""

from __future__ import annotations

from pathlib import Path

from .fragments import forbid, read, require


def validate_yuelink(root: Path, contract: dict) -> None:
    identity = contract["device_identity"]
    device_summary = read(root / "lib/domain/account/device_summary.dart")
    device_summary_test = read(root / "test/domain/account/device_summary_test.dart")
    subscription_reset = read(
        root / "lib/domain/account/subscription_reset_outcome.dart"
    )
    subscription_reset_test = read(
        root / "test/domain/account/subscription_reset_outcome_test.dart"
    )
    panel_api = read(root / "lib/infrastructure/datasources/panel/api.dart")
    repository = read(
        root / "lib/infrastructure/account/account_center_repository.dart"
    )
    provider = read(
        root / "lib/modules/account/providers/account_center_providers.dart"
    )

    # The panel takes the max of observed identities and network lines rather
    # than their sum: the same device is usually visible to both, so adding
    # them is the inflation this projection exists to prevent. The client must
    # accept that shape, and must still refuse a count below what it already
    # knows to be online.
    require(
        device_summary,
        [
            "final floor = onlineIdentities > (sharedOnline ? 1 : 0)",
            "if (!pending && count < floor) {",
            "Never infer devices from IP cardinality",
            "shared_online",
            "presence_source",
            "database_projection",
        ],
        "YueLink strict device identity projection",
    )
    forbid(
        device_summary,
        ["onlineDevices + (sharedOnline ? 1 : 0)"],
        "YueLink retired additive device count",
    )
    require(
        device_summary_test,
        [
            "five IP observations still represent only one identity",
            "unattributed presence is explicit even when IPs are empty",
            "an identity and a network line are one device, not two",
        ],
        "YueLink IP-inflation regression tests",
    )
    require(
        subscription_reset + subscription_reset_test,
        [
            identity["reset_identity_field"],
            "rawUserIds.length != 1",
            "jsonToInt(rawUserIds.single) != expectedUserId",
            "device reset response disclosed a secret",
            "no account or device authority is accepted on this boundary",
            "the account-wide reset parser remains the sole public outcome",
        ],
        "YueLink account subscription reset binding",
    )
    # The panel registers this route as GET. v1.2.111 shipped it as POST, which
    # fell through to the anti-GFW decoy (non-JSON) and broke every
    # subscription sync with "数据格式化异常". Pin the verb, not just the path.
    require(
        panel_api,
        [
            "getRawData(\n      '/api/v1/user/getSubscribe'",
        ],
        "YueLink account subscription verb",
    )
    forbid(
        panel_api,
        ["postRawData(\n      '/api/v1/user/getSubscribe'"],
        "YueLink retired account subscription verb",
    )
    require(
        panel_api,
        [
            identity["overview_endpoint"],
            "It deliberately never returns account `token`, `uuid`, or subscription",
            "The account subscription is fetched only at the import boundary",
        ],
        "YueLink credential-free account overview",
    )
    require(
        repository + provider,
        [
            "AccountCenterRepository(this._api, this._token, this._accountId)",
            "expectedUserId: _accountId",
            "accountId == null || accountId <= 0",
        ],
        "YueLink immutable account binding",
    )

