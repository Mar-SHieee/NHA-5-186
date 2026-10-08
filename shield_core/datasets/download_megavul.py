"""Download MegaVul dataset if it does not already exist."""

from __future__ import annotations

from pathlib import Path
from urllib.request import Request, urlopen

SOURCE_URL = "https://1drv.ms/u/c/6CFE4123EACEEBDC/AdzrzuojQf4ggGxzcgAAAAA?e=oD9TTq"

OUTPUT_PATH = Path("data/raw/megavul_simplee.json")


def download_megavul() -> None:
    if OUTPUT_PATH.exists():
        print(f"MegaVul already exists: {OUTPUT_PATH}")
        return

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    print("Downloading MegaVul...")
    print(f"Destination: {OUTPUT_PATH}")

    download_url = f"{SOURCE_URL}&download=1"

    request = Request(
        download_url,
        headers={"User-Agent": "Mozilla/5.0"},
    )

    with urlopen(request) as response:
        with OUTPUT_PATH.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)

    print(f"MegaVul downloaded successfully: {OUTPUT_PATH}")


if __name__ == "__main__":
    download_megavul()
