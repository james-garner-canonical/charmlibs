"""Rewrite upload:// shortcodes in TLS docs to real image URLs.

Reads the cooked HTML from each Discourse JSON response to resolve upload://
shortcodes to real S3 URLs, then rewrites the markdown files to use those URLs
directly (stripping the Discourse |NNNxNNN dimension syntax from alt text).

Usage:
    python .scripts/process_tls_discourse_images.py
"""
import json
import re
from pathlib import Path

DOCS_DIR = Path("interfaces/tls-certificates/docs")
JSON_DIR = DOCS_DIR / "discourse-json"

# JSON files that contain upload:// image refs, mapped to their markdown output.
# (Subset of the mapping in extract_tls_discourse_docs.py — only files with images.)
JSON_TO_MD = {
    "getting-started.json": "tutorial.md",
    "securing-api-communication.json": "reference/securing-api-communication.md",
    "securing-internal-communication.json": "reference/securing-internal-communication.md",
    "tls-certificates-interface.json": "explanation/tls-certificates-interface.md",
}


def extract_upload_refs(raw: str) -> list[str]:
    """Extract upload:// shortcodes from raw markdown, in order."""
    return re.findall(r"upload://[^\s)]+", raw)


def extract_img_urls(cooked: str) -> list[str]:
    """Extract <img> src URLs from cooked HTML, in order."""
    return re.findall(r"<img[^>]+src=[\"']([^\"'\s]+)", cooked)


def rewrite_markdown(md_path: Path, replacements: dict[str, str]) -> None:
    """Rewrite upload:// shortcodes and Discourse image syntax in a markdown file.

    Transforms: ![alt|NNNxNNN](upload://...) -> ![alt](https://real-url)
    """
    content = md_path.read_text()
    for upload_ref, real_url in replacements.items():
        # Match ![alt|NNNxNNN](upload://...) or ![alt](upload://...)
        # Strip the |dimensions from alt text, replace URL with real URL.
        pattern = re.compile(
            r"!\[([^\]]*?)(?:\|[^\]]+)?\]\(" + re.escape(upload_ref) + r"\)"
        )
        content = pattern.sub(rf"![\1]({real_url})", content)
    md_path.write_text(content)


def main() -> None:
    total_rewritten = 0

    for json_name, md_rel in JSON_TO_MD.items():
        json_path = JSON_DIR / json_name
        md_path = DOCS_DIR / md_rel

        if not json_path.exists():
            print(f"  skip {json_name} (not found)")
            continue

        with open(json_path) as f:
            data = json.load(f)

        post = data["post_stream"]["posts"][0]
        raw = post.get("raw", "")
        cooked = post.get("cooked", "")

        upload_refs = extract_upload_refs(raw)
        img_urls = extract_img_urls(cooked)

        if not upload_refs:
            continue

        if len(upload_refs) != len(img_urls):
            print(
                f"  WARNING: {json_name}: {len(upload_refs)} upload:// refs "
                f"but {len(img_urls)} <img> URLs — skipping"
            )
            continue

        print(f"{json_name} -> {md_rel}: {len(upload_refs)} images")

        replacements: dict[str, str] = {}
        for upload_ref, img_url in zip(upload_refs, img_urls):
            # Ensure URL has a scheme
            if not img_url.startswith("http"):
                img_url = "https:" + img_url
            replacements[upload_ref] = img_url

        rewrite_markdown(md_path, replacements)
        total_rewritten += len(replacements)
        print(f"  rewrote {len(replacements)} image refs in {md_rel}")

    print(f"\nDone: {total_rewritten} refs rewritten")


if __name__ == "__main__":
    main()
