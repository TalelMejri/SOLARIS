from pathlib import Path
import json


PROJECT_ROOT = Path(__file__).resolve().parents[3]

JSON_FILE = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "nwp"
    / "historical_forecast_test"
    / "tunis_ville_2023-06-01_2023-06-04.json"
)


print()
print("=" * 72)
print("PROSOL FORECAST — PHASE 5.2")
print("STEP 3 — HISTORICAL FORECAST METADATA INSPECTION")
print("=" * 72)

print()
print(f"File:")
print(f"  {JSON_FILE}")


if not JSON_FILE.exists():
    print()
    print("[ERROR] JSON file not found.")
    raise SystemExit(1)


with open(JSON_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)


print()
print("TOP-LEVEL RESPONSE KEYS")
print("-" * 72)

for key in data.keys():
    value = data[key]

    if isinstance(value, dict):
        print(f"{key}: dict")
        print(f"  keys: {list(value.keys())}")

    elif isinstance(value, list):
        print(f"{key}: list[{len(value)}]")

    else:
        print(f"{key}: {type(value).__name__} = {value}")


print()
print("=" * 72)
print("FORECAST-ORIGIN SEARCH")
print("=" * 72)


keywords = [
    "run",
    "issue",
    "initial",
    "init",
    "reference",
    "lead",
    "forecast",
    "model",
    "generation",
]


def recursive_search(obj, path="root"):
    found = []

    if isinstance(obj, dict):

        for key, value in obj.items():

            key_lower = str(key).lower()

            if any(k in key_lower for k in keywords):
                found.append(
                    (
                        f"{path}.{key}",
                        value,
                    )
                )

            found.extend(
                recursive_search(
                    value,
                    f"{path}.{key}",
                )
            )

    elif isinstance(obj, list):

        for i, value in enumerate(obj[:10]):

            found.extend(
                recursive_search(
                    value,
                    f"{path}[{i}]",
                )
            )

    return found


matches = recursive_search(data)


if matches:

    print()

    for path, value in matches:

        if isinstance(value, (dict, list)):
            preview = str(value)[:500]
        else:
            preview = repr(value)

        print(f"{path}")
        print(f"  {preview}")

else:

    print()
    print("[PASS] No explicit forecast issue/run field found.")


print()
print("=" * 72)
print("HOURLY TIME STRUCTURE")
print("=" * 72)


hourly = data.get("hourly", {})

times = hourly.get("time", [])

print()
print(f"Hourly timestamps: {len(times)}")

if times:

    print(f"First: {times[0]}")
    print(f"Last:  {times[-1]}")


print()
print("=" * 72)
print("CONCLUSION")
print("=" * 72)

print()
print(
    "The Historical Forecast API response is inspected for "
    "explicit initialization/run/lead-time metadata."
)

print()
print(
    "If no issue-time field exists, we must NOT infer "
    "forecast lead time from valid_time alone."
)

print()
print("=" * 72)