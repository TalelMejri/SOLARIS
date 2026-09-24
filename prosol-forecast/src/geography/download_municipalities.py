from pathlib import Path
import json
import requests


ROOT = Path(__file__).resolve().parents[2]

OUTPUT_DIR = ROOT / "data" / "raw"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

URL = "https://tn-municipality-api.vercel.app/api/municipalities"


def main():

    print("Downloading Tunisian municipalities...")

    response = requests.get(
        URL,
        timeout=60
    )

    response.raise_for_status()

    data = response.json()

    output = OUTPUT_DIR / "municipalities.json"

    with open(
        output,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )

    print(f"[OK] Saved: {output}")

    if isinstance(data, list):
        print(f"Municipalities: {len(data)}")

    elif isinstance(data, dict):
        print(
            "Top-level keys:",
            list(data.keys())
        )


if __name__ == "__main__":
    main()