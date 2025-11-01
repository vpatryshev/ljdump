#!/usr/bin/env python3
"""Convert JuanEnrique markdown files to a single PDF."""

import os
import glob
import subprocess
import re
import tempfile
import json
from ljdumpops import *

def clean_html_entities(content):
    """Convert HTML entities to their text equivalents."""
    # Replace &nbsp; with regular space
    content = content.replace('&nbsp;', ' ')
    # Replace other common HTML entities
    content = content.replace('&quot;', '"')
    content = content.replace('&amp;', '&')
    content = content.replace('&lt;', '<')
    content = content.replace('&gt;', '>')
    return content

def clean_entry_format(content):
    """Clean up entry formatting: remove unwanted headers, convert dates to section titles."""
    lines = content.split('\n')
    result = []

    for line in lines:
        # Remove ALL header lines (# anything) - we'll create our own from dates
        if re.match(r'^#+\s+', line):
            continue

        date_match = re.match(r'^\*\*Date:\*\*\s+(.... \d+, \d\d\d\d).*$', line)
        if date_match:
            date=date_match.group(1)
            result.append(f"## {date}")
            continue

        # Remove "**Original:** <url>" lines
        if re.match(r'^\*\*Original:\*\*\s+https?://', line):
            continue

        # Remove "**Tags:** <tags>" lines
        if re.match(r'^\*\*Tags:\*\*\s+', line):
            continue

        # Remove "**Next:** [link]" lines
        if re.match(r'^\*\*Next:\*\*\s+\[', line):
            continue

        # Remove "**Previous:** [link]" lines
        if re.match(r'^\*\*Previous:\*\*\s+\[', line):
            continue

        # Remove \pagebreak lines
        if line.strip() == r'\pagebreak':
            continue

        result.append(line)

    return '\n'.join(result)

def remove_navigation_links(content):
    """Remove the Previous/Next navigation links from markdown content."""
    # Remove the navigation section at the bottom
    content = re.sub(r'\n+---\n+\*\*Previous:.*$', '', content, flags=re.MULTILINE|re.DOTALL)
    content = re.sub(r'\n+---\n+\*\*Next:.*$', '', content, flags=re.MULTILINE|re.DOTALL)
    content = re.sub(r'\n+---\n+## This is the end.*$', '', content, flags=re.MULTILINE|re.DOTALL)
    return content.rstrip()

def combine_markdown_files(directory="JuanEnrique", output_file="combined.md", config=None):
    """Combine all markdown files in chronological order."""

    # Get all markdown files and sort them
    pattern = os.path.join(directory, "*.md")
    files = sorted(glob.glob(pattern))

    if not files:
        print(f"No markdown files found in {directory}")
        return False

    print(f"Found {len(files)} markdown files to combine")

    with open(output_file, 'w', encoding='utf-8') as outfile:
        # Add title page with proper pandoc metadata
        title = config.get("title", "No Name")
        author = config.get("author", "(anonymous)")

        outfile.write(f"% {title}\n")
        outfile.write(f"% {author}\n")
        outfile.write("% \n\n")  # Date (empty for now)

        for i, filepath in enumerate(files):
            print(f"Processing {i+1}/{len(files)}: {os.path.basename(filepath)}")

            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            # Clean HTML entities first
            content = clean_html_entities(content)

            # Clean entry format (remove unwanted headers, fix dates, etc.)
            content = clean_entry_format(content)

            # Remove navigation links
            content = remove_navigation_links(content)

            # Add page break before each entry (except first)
            if i > 0:
                outfile.write("\n\\newpage\n\n")

            outfile.write(content)
            outfile.write("\n\n")

    print(f"Combined markdown saved to {output_file}")
    return True

def convert_to_pdf(input_file, output_file):
    """Convert markdown file to PDF using pandoc."""
    print(f"Converting {input_file} to {output_file}...")

    cmd_pdf = [
        "pandoc",
        "--from=markdown",
        "--pdf-engine=xelatex",
        "--data-dir", ".",
        "--template", "template.latex",
        "--toc",
#         "--toc-depth=3",
        "-s", input_file,
        "-o", output_file
    ]

    try:
        subprocess.run(cmd_pdf, check=True, capture_output=True, text=True)
        print(f"PDF successfully created: {output_file}")
    except subprocess.CalledProcessError as e:
        print(f"Error creating PDF: {e.stderr}")
        return False

def convert_to_pdf_old(input_file="combined.md", output_file="JuanEnrique.pdf"):
    """Convert markdown file to PDF using pandoc."""
    print(f"Converting {input_file} to HTML first...")

    # First convert to HTML with TOC
    html_file = input_file.replace('.md', '.html')
    output_html = output_file.replace('.pdf', '.html')

    cmd_html = [
        "pandoc",
        input_file,
        "-o", output_html,
        "--standalone",
        "--toc",
        "--toc-depth=2"
    ]

    try:
        subprocess.run(cmd_html, check=True, capture_output=True, text=True)
        print(f"HTML successfully created: {output_html}")
    except subprocess.CalledProcessError as e:
        print(f"Error creating HTML: {e.stderr}")
        return False

    try:
        subprocess.run(cmd_html, check=True, capture_output=True, text=True)
        print(f"HTML successfully created: {output_html}")
    except subprocess.CalledProcessError as e:
        print(f"Error creating HTML: {e.stderr}")
        return False

    # Now try to convert HTML to PDF
    print(f"Converting HTML to PDF...")

    # Try Chrome/Chromium headless first (most reliable)
    chrome_paths = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "google-chrome",
        "chromium",
        "chrome"
    ]

    for chrome_path in chrome_paths:
        try:
            cmd_pdf = [
                chrome_path,
                "--headless",
                "--disable-gpu",
                "--print-to-pdf=" + output_file,
                "file://" + os.path.abspath(output_html)
            ]
            subprocess.run(cmd_pdf, check=True, capture_output=True, text=True, timeout=60)
            if os.path.exists(output_file):
                print(f"PDF successfully created with Chrome: {output_file}")
                return True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            continue

    # Try wkhtmltopdf
    try:
        cmd_pdf = [
            "wkhtmltopdf",
            "--enable-local-file-access",
            "--margin-top", "20mm",
            "--margin-bottom", "20mm",
            "--margin-left", "20mm",
            "--margin-right", "20mm",
            output_html,
            output_file
        ]

        subprocess.run(cmd_pdf, check=True, capture_output=True, text=True)
        print(f"PDF successfully created with wkhtmltopdf: {output_file}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # Try weasyprint
    try:
        cmd_pdf = ["weasyprint", output_html, output_file]
        subprocess.run(cmd_pdf, check=True, capture_output=True, text=True)
        print(f"PDF successfully created with weasyprint: {output_file}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    print(f"No PDF converter available.")
    print(f"HTML file is available at: {output_html}")
    print("You can open it in a browser and use Print > Save as PDF.")
    return False

def main():

    # Load configuration
    config = load_config("confessions.json")
    print(f"Loaded config: Title='{config['title']}', Author='{config['author']}'")
    # Create temporary combined markdown file
    temp_md = "combined_temp.md"

    try:
        # Combine all markdown files
        if not combine_markdown_files(output_file=temp_md, config=config):
            return

        # Convert to PDF
        output_pdf = config.get("output_pdf")
        if convert_to_pdf(input_file=temp_md, output_file=output_pdf):
            print(f"\n✓ Success! PDF created: {output_pdf}")
        else:
            print("\n✗ Failed to create PDF")

    finally:
        # Clean up temporary file       
        #        if os.path.exists(temp_md):
        #            os.remove(temp_md)
        #            print(f"Cleaned up temporary file: {temp_md}")
        print("Done with PDF.")

if __name__ == "__main__":
    main()
