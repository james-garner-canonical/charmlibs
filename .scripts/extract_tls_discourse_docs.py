"""Extract raw markdown from downloaded Discourse JSON into the docs directory structure.

Reads JSON files from interfaces/tls-certificates/docs/discourse-json/
and writes markdown files to interfaces/tls-certificates/docs/ following
the diataxis category layout defined in PLAN.md.

The category assignments below are based on the Charmhub navigation table
and editorial judgement about what fits each diataxis category in the
charmlibs docs context.
"""
import json
import pathlib

JSON_DIR = pathlib.Path("interfaces/tls-certificates/docs/discourse-json")
DOCS_DIR = pathlib.Path("interfaces/tls-certificates/docs")

# Map from JSON filename (without .json) to output path relative to DOCS_DIR.
# Category assignments:
#   tutorial   - hands-on getting started
#   explanation - conceptual/background discussion
#   reference  - for pages that are reference-like on Charmhub
#                (placed under explanation/ or reference/ as appropriate;
#                 most "reference" pages from Charmhub are actually explanations
#                 or how-tos in diataxis terms -- we place them as-is and
#                 recategorise later during review)
FILE_MAP = {
    # Tutorial
    "getting-started": "tutorial.md",
    # Explanation
    "tls-certificates-interface": "explanation/tls-certificates-interface.md",
    "common-name-and-sans-attributes": "explanation/common-name-and-sans-attributes.md",
    "certificate-renewal": "explanation/certificate-renewal.md",
    "library-differences-v3-to-v4": "explanation/library-differences-v3-to-v4.md",
    "security": "explanation/security.md",
    # Reference (for charm developers) — placed under reference/ for now
    "library-versions": "reference/library-versions.md",
    "private-key-label-change": "reference/private-key-label-change.md",
    "recommended-config-options": "reference/recommended-config-options.md",
    # Reference (for charm users) — placed under reference/ for now
    "securing-internal-communication": "reference/securing-internal-communication.md",
    "securing-api-communication": "reference/securing-api-communication.md",
    "ca-trust-best-practices": "reference/ca-trust-best-practices.md",
}


def main():
    for json_slug, rel_path in FILE_MAP.items():
        json_file = JSON_DIR / f"{json_slug}.json"
        if not json_file.exists():
            print(f"SKIP {json_slug} (JSON not found)")
            continue

        data = json.loads(json_file.read_text())
        raw = data["post_stream"]["posts"][0]["raw"]

        out_path = DOCS_DIR / rel_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(raw)
        print(f"  {rel_path} ({len(raw)} chars)")

    print("Done!")


if __name__ == "__main__":
    main()
