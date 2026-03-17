# Aromalink Integration for Home Assistant

This custom component integrates Aroma-Link WiFi diffusers with Home Assistant.

> **Note:** The integration appears in Home Assistant as `Aromalink Integration` with the domain `aromalink_ha_integration`.

> **1.9 upgrade note:** Version `1.9.0` rebrands the integration domain from `aromalink_integration_v1` to `aromalink_ha_integration`. Existing config entries from `aroma_link_integration`, `dalyem_aroma_link`, `ha_aromalink`, and `aromalink_integration_v1` are not migrated automatically.

![Aroma-Link logo](brand/logo.png)

## Features

- Control diffuser power state
- Set diffuser work and pause durations
- Save diffuser schedules
- Run a diffuser immediately
- Auto-discover all devices on your Aroma-Link account
- Configure the polling interval from Home Assistant

## Migration to 1.9.0

1. Update the repository in HACS or replace the manual install folder with `custom_components/aromalink_ha_integration`.
2. Restart Home Assistant.
3. Add the integration named `Aromalink Integration`.
4. Re-enter your Aroma-Link credentials and reapply any options such as the polling interval.
5. Update automations or scripts that call `aromalink_integration_v1.*` services to use `aromalink_ha_integration.*`.
6. Remove the old integration entry after the new one is working.

If HACS still points at the old folder path, remove and re-add the custom repository so it refreshes the package metadata.

## Installation

### HACS

1. Ensure HACS is installed in Home Assistant.
2. Open HACS.
3. Click the three-dot menu in the top right.
4. Click **Custom repositories**.
5. Paste `https://github.com/dalyem/ha_aromalink`.
6. Select **Integration** and add it.
7. Open the repository entry and click **Download**.
8. Restart Home Assistant.

### Manual Installation

1. Copy the `aromalink_ha_integration` directory to `<config>/custom_components/`.
2. Restart Home Assistant.

Example:

```bash
cp -r custom_components/aromalink_ha_integration <home_assistant_config>/custom_components/
```

## Configuration

1. In Home Assistant, go to **Settings** -> **Devices and Services**.
2. Click **Add Integration**.
3. Search for `Aromalink Integration`.
4. Enter your Aroma-Link username and password.
5. Home Assistant will discover all supported devices on the account.

## Services

### `aromalink_ha_integration.set_scheduler`

Set the diffuser scheduler.

Parameters:

- `work_duration`: Required work duration in seconds.
- `pause_duration`: Optional pause duration in seconds.
- `week_days`: Optional list of weekdays.
- `device_id`: Required when multiple devices exist.

### `aromalink_ha_integration.run_diffuser`

Run the diffuser immediately.

Parameters:

- `work_duration`: Optional work duration in seconds.
- `pause_duration`: Optional pause duration in seconds.
- `device_id`: Required when multiple devices exist.

## Entities

The integration creates:

- Switch entities for diffuser power
- Button entities for run/save actions
- Number entities for work duration, pause duration, and polling interval
- Sensor entities for runtime and device statistics

## Technical Notes

- The integration uses the Aroma-Link web and mobile endpoints.
- The package polls cloud state every 60 seconds by default.
- Authentication is maintained with both web-session and app-token flows.

## Troubleshooting

- Verify your Aroma-Link credentials if setup fails.
- Confirm the diffuser is online in the Aroma-Link app.
- If HACS reports `No content to download`, verify that `custom_components/aromalink_ha_integration/manifest.json` exists on the default branch, then remove and re-add the custom repository if needed.
- If you are upgrading from an older domain, install the new integration first and remove the old one after confirming the new entities.

## Local Probe Script

To inspect the Aroma-Link endpoints locally:

1. Create a `.env.aromalink` file in the repository root.
2. Add `AROMALINK_USERNAME` and `AROMALINK_PASSWORD`.
3. Optionally add `AROMALINK_USER_ID` and `AROMALINK_DEVICE_ID`.
4. Run:

```bash
python3 scripts/aromalink_probe.py
```

Useful options:

- `python3 scripts/aromalink_probe.py --switch on`
- `python3 scripts/aromalink_probe.py --switch off`
- `python3 scripts/aromalink_probe.py --set-scheduler`
- `python3 scripts/aromalink_probe.py --device-id 408555 --user-id 181605`
- `python3 scripts/aromalink_probe.py --skip-web`

## Version History

- `1.9.0`: Rebranded to the `aromalink_ha_integration` domain and `Aromalink Integration` name, added migration guidance, and removed secret-adjacent debug logging
- `1.5.8`: Changed the default work/pause values to `10 / 90`
- `1.5.7`: Added a user-configurable polling interval option and improved runtime consistency
- `1.5.6`: Switched runtime fallback to the working web device-list endpoints and added the local probe script
- `1.5.1`: Added broader app response parsing
- `1.5.0`: Renamed the fork to the `aromalink_integration_v1` domain and package folder
- `1.4.0`: Renamed the fork to the `ha_aromalink` domain and display name
- `1.3.0`: Renamed the fork to the `ha_aroma_link` domain
- `1.2.0`: Renamed the fork to its own Home Assistant domain
- `1.1.0`: Updated to support HACS integration
- `1.0.0`: Initial release with automatic device discovery

## Requirements

- A valid Aroma-Link account
- At least one registered diffuser
- Home Assistant 2023.3.0 or newer
- An active internet connection

## License

This integration is provided as-is with no warranties.

## Links

- [Repository](https://github.com/dalyem/ha_aromalink)
- [Documentation](https://github.com/dalyem/ha_aromalink#readme)
- [Issue Tracker](https://github.com/dalyem/ha_aromalink/issues)
