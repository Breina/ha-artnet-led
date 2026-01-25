import shutil
import time
import webbrowser

from requests import get, post, Response

STAGING_FOLDER = "\\\\hesp-staging.frituur\\config\\custom_components\\dmx"

SUPERVISOR_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJkZTljYWIyYjE3YzE0MTU4YThhNTE1OTk0Nzg1YWE2MiIsImlhdCI6MTc2NTY0MjEzNCwiZXhwIjoyMDgxMDAyMTM0fQ.4LMTZfAqpnUHRbma4GSGmt-ZVjj-fkWeq0oBURI7wlM"
HEADERS = {
    "Authorization": ("Bearer %s" % SUPERVISOR_TOKEN),
    "content-type": "application/json",
}


def copy_repo():
    print("Copying repo...")
    # Requires Samba share and it being configured as network location in Windows
    shutil.rmtree(STAGING_FOLDER)
    shutil.copytree("custom_components/dmx", STAGING_FOLDER, dirs_exist_ok=True)


def restart_ha() -> Response:
    """Requires Remote API proxy Addon"""

    print("Restarting HA...")
    response = post("http://hesp-staging.frituur:8123/api/services/homeassistant/restart", headers=HEADERS)
    print(response.text)
    return response


def open_browser():
    print("Opening browser...")
    webbrowser.open("http://hesp-staging.frituur:8123/config/integrations/dashboard")


def follow_logs():
    print("Following logs...")
    lastTs = time.gmtime()
    while True:
        newLog = get("http://hesp-staging.frituur/core/logs", headers=HEADERS).text
        for logLine in newLog.split("\n"):
            if not logLine:
                continue

            logTs = time.strptime(logLine[5:28], "%Y-%m-%d %H:%M:%S.%f")
            if logTs <= lastTs:
                continue

            print(logLine)
            lastTs = logTs

        time.sleep(0.1)


copy_repo()
response = restart_ha()
# if response.status_code == 200:
#     open_browser()
# follow_logs()
