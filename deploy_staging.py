#!/usr/bin/env python3
"""
Deployment script for ha-artnet-led to staging environment.

Copies the custom_components/dmx directory to staging server and restarts Home Assistant.
"""

import argparse
import os
import shutil
import sys
import time

import requests
import urllib3

# Disable SSL warnings since we're not validating certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configuration
STAGING_SERVER = "192.168.1.98"
STAGING_SHARE = f"\\\\{STAGING_SERVER}\\config"
STAGING_HA_URL = f"https://{STAGING_SERVER}:8123"
SOURCE_DIR = "custom_components\\dmx"
DEST_DIR = f"{STAGING_SHARE}\\custom_components"


def copy_files():
    """Copy the custom_components/dmx directory to staging server."""
    print(f"Copying {SOURCE_DIR} to {DEST_DIR}...")

    # Check if source directory exists
    if not os.path.exists(SOURCE_DIR):
        print(f"Error: Source directory {SOURCE_DIR} does not exist!")
        return False

    # Create destination directory if it doesn't exist
    dest_dmx_dir = os.path.join(DEST_DIR, "dmx")

    try:
        # Remove existing directory if it exists
        if os.path.exists(dest_dmx_dir):
            print(f"Removing existing {dest_dmx_dir}...")
            shutil.rmtree(dest_dmx_dir)

        # Create parent directory if needed
        os.makedirs(DEST_DIR, exist_ok=True)

        # Copy the directory
        shutil.copytree(SOURCE_DIR, dest_dmx_dir)
        print(f"✓ Successfully copied files to {dest_dmx_dir}")
        return True

    except Exception as e:
        print(f"Error copying files: {e}")
        return False


def restart_homeassistant(api_token=None):
    """Restart Home Assistant via API."""
    print("Restarting Home Assistant...")

    headers = {}
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"

    try:
        response = requests.post(
            f"{STAGING_HA_URL}/api/services/homeassistant/restart",
            headers=headers,
            verify=False,
            timeout=5,
        )

        if response.status_code == 200:
            print("✓ Home Assistant restart initiated")
            return True
        else:
            print(f"Error restarting HA: HTTP {response.status_code}")
            print(f"Response: {response.text}")
            return False

    except requests.exceptions.ReadTimeout:
        # This is expected - HA kills the process during restart
        print("✓ Home Assistant restart initiated (connection closed as expected)")
        return True
    except Exception as e:
        # Check if it's a connection error that might indicate restart started
        if "Connection" in str(e) or "timeout" in str(e).lower():
            print("✓ Home Assistant restart likely initiated (connection interrupted)")
            return True
        print(f"Error calling HA API: {e}")
        return False


def wait_for_homeassistant(timeout=60):
    """Wait for Home Assistant to come back online."""
    print("Waiting for Home Assistant to come back online...")

    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get(f"{STAGING_HA_URL}/api/", verify=False, timeout=5)
            if response.status_code == 200:
                print("✓ Home Assistant is back online")
                return True
        except Exception:
            # Expected during HA startup - connection failures are normal
            pass

        print(".", end="", flush=True)
        time.sleep(2)

    print(f"\nTimeout waiting for Home Assistant to restart ({timeout}s)")
    return False


def main():
    parser = argparse.ArgumentParser(description="Deploy ha-artnet-led to staging environment")
    parser.add_argument("--token", help="Home Assistant API token")
    parser.add_argument("--skip-restart", action="store_true", help="Skip Home Assistant restart")

    args = parser.parse_args()

    print("=== Deploying ha-artnet-led to staging ===")

    # Step 1: Copy files
    if not copy_files():
        sys.exit(1)

    # Step 2: Restart Home Assistant
    if not args.skip_restart:
        if not restart_homeassistant(args.token):
            print("Warning: Failed to restart Home Assistant")
        else:
            # Wait for HA to come back online
            wait_for_homeassistant()

    print("\n✓ Deployment complete!")


if __name__ == "__main__":
    main()
