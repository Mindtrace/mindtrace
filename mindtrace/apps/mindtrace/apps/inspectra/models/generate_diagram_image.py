#!/usr/bin/env python3
"""
Script to generate a visual diagram image from the Mermaid schema diagram.

This script provides multiple methods to generate diagram images:
1. Using mermaid-cli (mmdc) if installed
2. Using Playwright/Selenium to render the HTML file
3. Instructions for manual export
"""

import subprocess
import sys
from pathlib import Path


def check_mermaid_cli():
    """Check if mermaid-cli is installed."""
    try:
        result = subprocess.run(["mmdc", "--version"], capture_output=True, text=True, timeout=5)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def generate_with_mermaid_cli(mermaid_file, output_file):
    """Generate image using mermaid-cli."""
    try:
        subprocess.run(
            ["mmdc", "-i", mermaid_file, "-o", output_file, "-t", "default", "-b", "white"],
            check=True,
            capture_output=True,
        )
        print(f"✓ Successfully generated {output_file} using mermaid-cli")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Error generating with mermaid-cli: {e}")
        return False
    except FileNotFoundError:
        return False


def extract_mermaid_code(markdown_file):
    """Extract Mermaid code from markdown file."""
    with open(markdown_file, "r") as f:
        content = f.read()

    # Find the mermaid code block
    start = content.find("```mermaid")
    if start == -1:
        return None

    start += len("```mermaid")
    end = content.find("```", start)

    if end == -1:
        return None

    return content[start:end].strip()


def create_mermaid_file(mermaid_code, output_file):
    """Create a standalone .mmd file with Mermaid code."""
    with open(output_file, "w") as f:
        f.write(mermaid_code)
    print(f"✓ Created Mermaid file: {output_file}")


def main():
    """Main function to generate diagram image."""
    script_dir = Path(__file__).parent
    markdown_file = script_dir / "SCHEMA_DIAGRAM.md"
    html_file = script_dir / "schema_diagram.html"
    mermaid_file = script_dir / "schema_diagram.mmd"

    print("Inspectra Database Schema Diagram Generator")
    print("=" * 50)

    # Extract Mermaid code from markdown
    print("\n1. Extracting Mermaid code from markdown...")
    mermaid_code = extract_mermaid_code(markdown_file)

    if not mermaid_code:
        print("✗ Could not extract Mermaid code from markdown file")
        sys.exit(1)

    # Create standalone .mmd file
    create_mermaid_file(mermaid_code, mermaid_file)

    # Try to generate with mermaid-cli
    print("\n2. Checking for mermaid-cli (mmdc)...")
    if check_mermaid_cli():
        print("✓ mermaid-cli found!")

        # Generate PNG
        png_file = script_dir / "schema_diagram.png"
        if generate_with_mermaid_cli(str(mermaid_file), str(png_file)):
            print(f"\n✓ Diagram saved as: {png_file}")

        # Generate SVG
        svg_file = script_dir / "schema_diagram.svg"
        if generate_with_mermaid_cli(str(mermaid_file), str(svg_file)):
            print(f"✓ Diagram saved as: {svg_file}")
    else:
        print("✗ mermaid-cli not found")
        print("\n3. Alternative methods:")
        print("   a) Install mermaid-cli:")
        print("      npm install -g @mermaid-js/mermaid-cli")
        print("\n   b) Open the HTML file in a browser:")
        print(f"      {html_file}")
        print("      Then right-click the diagram and save as image")
        print("\n   c) Use online Mermaid editor:")
        print("      https://mermaid.live/")
        print("      Copy the content from schema_diagram.mmd")

    print("\n" + "=" * 50)
    print("Files created:")
    print(f"  - {mermaid_file} (Mermaid source)")
    print(f"  - {html_file} (HTML viewer)")


if __name__ == "__main__":
    main()
