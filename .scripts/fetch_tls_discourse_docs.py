"""Fetch TLS certificates interface docs from Discourse as JSON."""
import json
import time
import urllib.request
import pathlib
import sys

BASE = "https://discourse.charmhub.io/t"
OUT = pathlib.Path("interfaces/tls-certificates/docs/discourse-json")

# topic_id: (slug-for-filename, nav-title, category)
TOPICS = {
    11635: ("_navigation", "The TLS Certificate Interface Documentation", "nav"),
    15537: ("getting-started", "Getting Started (v4)", "tutorial"),
    15539: ("tls-certificates-interface", "TLS Certificates Interface", "explanation"),
    19118: ("common-name-and-sans-attributes", "Common Name and SANs Attributes", "explanation"),
    15542: ("certificate-renewal", "Automated Certificate Renewal (v4)", "explanation"),
    17225: ("library-differences-v3-to-v4", "TLS Certificates Library v3 vs v4", "explanation"),
    18245: ("security", "Security", "explanation"),
    15555: ("library-versions", "Library Versions", "reference-dev"),
    16764: ("private-key-label-change", "Change of private key labels in V4.8", "reference-dev"),
    15541: ("recommended-config-options", "Recommended Configuration Options", "reference-dev"),
    18382: ("securing-internal-communication", "Securing Internal Communication", "reference-user"),
    18385: ("securing-api-communication", "Securing API Communication", "reference-user"),
    18386: ("ca-trust-best-practices", "CA Trust Best Practices", "reference-user"),
}

DELAY = 2  # seconds between requests
MAX_RETRIES = 3


def fetch(topic_id: int) -> dict:
    url = f"{BASE}/{topic_id}.json?include_raw=true"
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "charmlibs-docs-migration/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except Exception as e:
            print(f"  attempt {attempt+1} failed: {e}", file=sys.stderr)
            if attempt < MAX_RETRIES - 1:
                time.sleep(DELAY * (attempt + 1))
    raise RuntimeError(f"Failed to fetch topic {topic_id} after {MAX_RETRIES} attempts")


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    for i, (topic_id, (slug, title, category)) in enumerate(TOPICS.items()):
        outfile = OUT / f"{slug}.json"
        if outfile.exists():
            print(f"[{i+1}/{len(TOPICS)}] SKIP {slug} (already exists)")
            continue
        print(f"[{i+1}/{len(TOPICS)}] Fetching {slug} (topic {topic_id})...", end=" ", flush=True)
        data = fetch(topic_id)
        outfile.write_text(json.dumps(data, indent=2))
        print(f"OK ({len(outfile.read_bytes())} bytes)")
        if i < len(TOPICS) - 1:
            time.sleep(DELAY)

    print("Done!")


if __name__ == "__main__":
    main()
