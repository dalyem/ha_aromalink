# HA Aromalink Integration for Home Assistant

This custom component provides integration with Aroma-Link WiFi diffusers in Home Assistant.

> **Note:** The integration appears in Home Assistant as "HA Aromalink" with the domain `ha_aromalink`

> **Upgrade note:** Because this fork now uses its own Home Assistant domain, existing `aroma_link_integration`, `dalyem_aroma_link`, and `ha_aroma_link` config entries will not be reused automatically. Add `HA Aromalink` as a new integration after updating. If HACS was tracking an older folder/domain name, remove and re-add the custom repository so HACS refreshes the repository content path.

![Aroma-Link logo](brand/logo.png)

## Features

- Control diffuser power state (on/off)
- Set diffuser work duration
- Set diffuser schedules
- Run diffuser for specific durations
- Automatic device discovery
- Auto-detection of devices in your Aroma-Link account

## Installation

### HACS

1. Ensure HACS is installed in Home Assistant.

2. Open the HACS tab.

3. Click the **three dots** in the top right.

4. Click **Custom repositories**

5. Paste the GitHub repository URL `https://github.com/dalyem/ha_aromalink`

6. Select **integration** as the type then click **ADD**

7. Click on the freshly added repository in HACS.

8. Click **Download**

9. Restart Home Assistant

> **Repository note:** HACS installs from the repository's default branch or published release. If you rename the integration folder or domain, those changes must be present on the default branch before HACS can download them.

### Manual Installation

1. Copy the `ha_aromalink` directory to your Home Assistant `custom_components` directory

   - The directory is typically located at `<config>/custom_components/`
   - If the `custom_components` directory doesn't exist, create it

   For example:

   ```bash
   cp -r custom_components/ha_aromalink <home_assistant_config>/custom_components/
   ```

2. Restart Home Assistant

### Configuration

1. In Home Assistant, go to **Settings** → **Devices and Services**
2. Click the **+ ADD INTEGRATION** button
3. Search for "HA Aromalink" and select it
4. Enter your Aroma-Link username and password
5. The integration will automatically discover and add all devices in your account

## Services

The integration provides the following services:

### `ha_aromalink.set_scheduler`

Set the scheduler for the diffuser.

Parameters:

- `work_duration`: Duration in seconds for the diffuser to work (required)
- `week_days`: Days of the week to apply the schedule (optional, defaults to all days)
- `device_id`: The ID of the device to control (optional, required if you have multiple devices)

### `ha_aromalink.run_diffuser`

Run the diffuser for a specific time.

Parameters:

- `work_duration`: Work duration in seconds for the diffuser (required)
- `diffuse_time`: Total time in seconds for the diffuser to run (required)
- `device_id`: The ID of the device to control (optional, required if you have multiple devices)

## Entities

The integration adds the following entities:

- **Switch**: Control the power state of the diffuser
- **Button**: Send immediate commands to the diffuser
- **Number**: Set work duration values

## How It Works

The integration works by:

1. Connecting to the Aroma-Link account using your credentials
2. Automatically discovering all devices in your account
3. Setting up all devices as separate entities in Home Assistant
4. Maintaining a shared authentication session for all devices

### Auto-Discovery Feature

The new auto-discovery feature eliminates the need to manually find your device ID. When setting up:

1. The integration authenticates with the Aroma-Link server
2. It requests a list of all devices registered to your account
3. All devices are automatically added to Home Assistant
4. Each device gets its own set of entities (switch, button, number controls)

### Technical Details

- The integration uses the same API as the official Aroma-Link website
- All communication is done securely over HTTPS
- Session management is handled with cookies and automatic re-login when needed
- The integration checks device status every minute by default

## Troubleshooting

- If you have issues connecting, verify that your Aroma-Link credentials are correct
- Check the Home Assistant logs for debugging information
- Make sure your diffuser is connected to your WiFi network and accessible from the internet
- If automatic device discovery fails, you can still manually specify your device ID
- If HACS reports `No content to download`, verify that the default branch contains `custom_components/ha_aromalink/manifest.json` and the latest integration files. If you renamed the integration folder/domain, remove and re-add the custom repository in HACS so it refreshes the cached content path

## FAQ

**Q: Can I control multiple diffusers?**  
A: Yes! The integration now automatically discovers and adds all diffusers in your Aroma-Link account. Each diffuser gets its own set of entities in Home Assistant. When using service calls, you can specify which device to control using the `device_id` parameter, or leave it blank to use the first device if you only have one.

**Q: Why is my diffuser showing as offline?**  
A: Make sure your diffuser is connected to WiFi and properly set up in the Aroma-Link app.

**Q: How do I find my device ID?**  
A: You don't need to! The integration automatically discovers your devices and lets you select which one to use from a list.

## Version History

- 1.4.0: Renamed the fork to the `ha_aromalink` domain and `HA Aromalink` display name
- 1.3.0: Renamed the fork to the `ha_aroma_link` domain with a neutral HA-specific identity
- 1.2.0: Renamed the fork to its own Home Assistant domain so it installs as a separate integration
- 1.1.0: Updated to support HACS integration
- 1.0.0: Initial release with automatic device discovery

## Requirements

- A valid Aroma-Link account
- At least one registered diffuser device
- Home Assistant 2023.3.0 or newer
- An active internet connection

## License

This integration is provided as-is with no warranties.

## Links

- [Repository](https://github.com/dalyem/ha_aromalink)
- [Documentation](https://github.com/dalyem/ha_aromalink#readme)
- [Issue Tracker](https://github.com/dalyem/ha_aromalink/issues)
