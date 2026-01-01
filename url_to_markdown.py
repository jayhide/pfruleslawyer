#!/usr/bin/env python3
"""Scrape a URL and convert its content to markdown."""

import argparse
import re
import sys
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
import html2text


def fetch_url(url: str) -> str:
    """Fetch HTML content from a URL."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()

    # Use apparent_encoding for better detection of actual encoding
    # requests often guesses wrong from HTTP headers alone
    if response.encoding is None or response.encoding.lower() == 'iso-8859-1':
        response.encoding = response.apparent_encoding

    return response.text


def html_to_markdown(html: str) -> str:
    """Convert HTML to markdown format."""
    soup = BeautifulSoup(html, "html.parser")

    # Remove script and style elements
    for element in soup(["script", "style", "nav", "footer", "header"]):
        element.decompose()

    # Try to find main content
    main_content = (
        soup.find("main")
        or soup.find("article")
        or soup.find("div", {"class": "content"})
        or soup.find("body")
    )

    if main_content is None:
        main_content = soup

    # Configure html2text
    converter = html2text.HTML2Text()
    converter.ignore_links = False
    converter.ignore_images = False
    converter.ignore_emphasis = False
    converter.body_width = 0  # No wrapping

    return converter.handle(str(main_content))


def remove_links(content: str) -> str:
    """Remove markdown links, keeping only the link text."""
    pattern = r'\[([^\]]+)\]\([^)]+\)'
    return re.sub(pattern, r'\1', content)


def truncate_at_copyright(content: str) -> str:
    """Remove everything after 'Section 15: Copyright Notice'."""
    marker = "Section 15: Copyright Notice"
    idx = content.find(marker)
    if idx != -1:
        return content[:idx].rstrip()
    return content


def skip_to_first_heading(content: str) -> str:
    """Remove everything before the first H1 heading."""
    match = re.search(r'^# ', content, re.MULTILINE)
    if match:
        return content[match.start():]
    return content


def save_markdown(content: str, output_path: str) -> None:
    """Save markdown content to a file."""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)


def main():
    parser = argparse.ArgumentParser(
        description="Scrape a URL and convert to markdown"
    )
    parser.add_argument("url", help="URL to scrape")
    parser.add_argument(
        "-o", "--output",
        default="output.md",
        help="Output file path (default: output.md)"
    )
    args = parser.parse_args()

    # Validate URL
    parsed = urlparse(args.url)
    if not parsed.scheme or not parsed.netloc:
        print(f"Error: Invalid URL: {args.url}", file=sys.stderr)
        sys.exit(1)

    try:
        print(f"Fetching {args.url}...")
        html = fetch_url(args.url)

        print("Converting to markdown...")
        markdown = html_to_markdown(html)
        markdown = skip_to_first_heading(markdown)
        markdown = remove_links(markdown)
        markdown = truncate_at_copyright(markdown)

        print(f"Saving to {args.output}...")
        save_markdown(markdown, args.output)

        print("Done!")
    except requests.RequestException as e:
        print(f"Error fetching URL: {e}", file=sys.stderr)
        sys.exit(1)
    except IOError as e:
        print(f"Error writing file: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
