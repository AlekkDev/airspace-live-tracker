"""Run inside the dagster-webserver container by infra/test-db.sh (not collected by pytest):
fails unless the webserver has loaded the `airspace` code location."""

import json
import sys
import urllib.request

QUERY = """{ workspaceOrError { __typename ... on Workspace { locationEntries {
  name loadStatus locationOrLoadError { __typename ... on PythonError { message } } } } } }"""

request = urllib.request.Request(
    "http://127.0.0.1:3000/graphql",
    data=json.dumps({"query": QUERY}).encode(),
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(request, timeout=30) as response:
    body = json.load(response)

entries = body["data"]["workspaceOrError"]["locationEntries"]
location = next((e for e in entries if e["name"] == "airspace"), None)
if location is None or location["locationOrLoadError"]["__typename"] != "RepositoryLocation":
    sys.exit(f"code location not loaded: {json.dumps(entries)}")
print("dagster smoke test passed")
