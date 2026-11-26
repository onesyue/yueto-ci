# YueBoard candidate facts and reviewed policy

A YueBoard commit identifies its contract revision. The highest numbered SQL
migration in that commit's `internal/platform/db/migrations` directory
identifies its migration head. YueBoard's `db.SchemaFloorVersion()` computes
the floor from the highest irreversible migration. Its command-line reader
is `cmd/schemafloor`. These facts belong to the selected Board commit.

The build planner also resolves the previously promoted Board revision. That
revision supplies the comparison baseline for Board promotion. The reviewed
pin below records a separate release decision.

## Reviewed fields in native-node-contract.json

| Field | Decision recorded |
| --- | --- |
| `version` | Identifies the central contract format and revision reported by the validator. |
| `yueboard_contract_pin` | Records the reviewed Board commit consumed by the root ship script. The central image build admits candidates using its computed release checks. |
| `deprecated_fields.yueboard_contract_pin` | Documents the root ship script dependency that governs retirement of the pin. |
| `layout.node-1`, `layout.node-2` | Define the two approved native node profiles. Each profile's `inventory_type`, `kernel` and `artifact` select the inventory classification, implementation and installed executable. |
| `control.credential_file` | Sets the control credential's mount path. |
| `control.deployment_probe_rpc`, `control.machine_status_rpc` | Select the RPCs used for the deployment probe and machine status reports, respectively. |
| `control.static_node_rpcs`, `control.retired_rpcs` | Record the RPCs that nodes must support and those removed from the interface. |
| `presence.required_capabilities`, `presence.release_a_rollout_capabilities` | Select the capabilities required for presence and those needed to prove rollout readiness. |
| `presence.report_rpc`, `presence.rollout_proof_endpoint` | Identify the device-presence report RPC and the endpoint that supplies rollout evidence. |
| `presence.process_lease_seconds`, `presence.rollout_order` | Set the process lease duration and the required deployment order for producers and consumers. |
| `device_identity.count_basis`, `device_identity.count_equation` | Define which observations identify devices and how they determine the online count. |
| `device_identity.legacy_shared_online_max`, `device_identity.diagnostic_only` | Specify the shared online allowance and the metadata reserved for diagnostics. |
| `device_identity.devices_endpoint`, `device_identity.overview_endpoint`, `device_identity.reset_endpoint`, `device_identity.reset_identity_field` | Define the device list, account overview and reset routes, plus the field identifying affected users. |
| `device_identity.account_subscription_api`, `device_identity.account_subscription_prefix`, `device_identity.third_party_import` | Specify the account subscription API, public URL prefix and subscription source for third-party clients. |
| `device_identity.portal_installation_authority`, `device_identity.synthetic_install_identity` | Record retirement of portal installation authority and synthetic installation identities. |
| `device_identity.presence_sources` | Select the approved sources of presence observations. |
