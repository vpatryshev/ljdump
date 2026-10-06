#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
upload_images.py - upload JPEG images to Dreamwidth's media hosting.

Usage:
    ./upload_images.py USER PASSWORD PATH [PATH ...]

Example:
    ./upload_images.py myname mypassword '/Users/me/Desktop/2026*'

Each PATH may be a single file or a glob. Quote a glob so this script expands
it (e.g. '2026*'); an unquoted glob is expanded by your shell into multiple
PATH arguments, which also works. Only JPEG files (.jpg / .jpeg, any case) are
uploaded; everything else is skipped. The Dreamwidth URL assigned to each
uploaded image is printed.

Note on the API: Dreamwidth has no documented, authenticated public upload
endpoint. This drives the same on-site endpoint the website's own uploader
uses - POST /file/new, a multipart/form-data upload. Authentication is a real
browser-style web login (the `ljmastersession`/`ljloggedin` cookies), because
the plain flat-API session cookie is not honored by that controller.
"""

import argparse
import glob
import json
import os
import re
import sys
import uuid
import urllib.request
import urllib.error
from http.cookiejar import CookieJar
from urllib.parse import urlencode

# Ensure the scripts directory is on the path so sibling imports resolve when
# the script is run from anywhere.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils import DREAMWIDTH, SOCKET_TIMEOUT, fail

ALLOWED_EXTENSIONS = (".jpg", ".jpeg")
# The JSON media-upload endpoint is the versioned API route (the router strips
# the /api/v1 prefix and dispatches by version). Plain /file/new is only the
# HTML upload UI page.
UPLOAD_PATH = "/api/v1/file/new"
LOGIN_PATH = "/login"
IMAGE_CONTENT_TYPE = "image/jpeg"
USER_AGENT = "ljdump upload_images/1.0"
# Session cookies that indicate a successful web login.
SESSION_COOKIE_NAMES = ("ljmastersession", "ljloggedin")


def select_image_files(paths):
    """Expand paths/globs and keep only existing JPEG files.

    Extensions are matched case-insensitively (.jpg/.jpeg/.JPG/.JPEG). The
    result is de-duplicated while preserving a stable (sorted-per-arg) order.
    """
    selected = []
    seen = set()
    for p in paths:
        matches = sorted(glob.glob(p)) if glob.has_magic(p) else [p]
        for m in matches:
            if (os.path.splitext(m)[1].lower() in ALLOWED_EXTENSIONS
                    and os.path.isfile(m) and m not in seen):
                seen.add(m)
                selected.append(m)
    return selected


def extract_form_auth(html):
    """Pull the lj_form_auth (CSRF) token out of a Dreamwidth page, or None."""
    m = re.search(
        r'name=["\']lj_form_auth["\'] value=["\']([^"\']+)["\']', html)
    return m.group(1) if m else None


def parse_login_form(html):
    """Locate Dreamwidth's web login form(s) and return (action_url, fields).

    The login page carries more than one lj_login_form (a compact navbar one
    and the full page one); their hidden fields differ (only the full form has
    returnto/type), so we merge inputs across every lj_login_form. Returns
    (None, {}) if no such form is found."""
    action = None
    fields = {}
    for m in re.finditer(
            r'<form\b([^>]*\bclass=["\'][^"\']*lj_login_form[^"\']*["\'][^>]*)>(.*?)</form>',
            html, re.I | re.S):
        attrs, inner = m.group(1), m.group(2)
        action_m = re.search(r'\baction=["\']([^"\']+)["\']', attrs, re.I)
        if action_m and not action:
            action = action_m.group(1)
        for tag in re.findall(r'<input\b[^>]*>', inner, re.I):
            name_m = re.search(r'\bname=["\']([^"\']+)["\']', tag, re.I)
            if not name_m:
                continue
            val_m = re.search(r'\bvalue=["\']([^"\']*)["\']', tag, re.I)
            fields.setdefault(name_m.group(1), val_m.group(1) if val_m else "")
    return action, fields


def extract_error_text(html):
    """Pull human-readable error text out of a re-rendered Dreamwidth page
    (elements whose class contains 'error'), or '' if none found."""
    chunks = []
    for m in re.finditer(
            r'<([a-z0-9]+)\b[^>]*\bclass=["\'][^"\']*error[^"\']*["\'][^>]*>(.*?)</\1>',
            html, re.I | re.S):
        text = re.sub(r"<[^>]+>", " ", m.group(2))
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            chunks.append(text)
    return " | ".join(chunks)[:400]


def describe_forms(html):
    """Return (list of <form ...> tags, sorted input/select/textarea names,
    <title> text) for an HTML page - used to diagnose a failed login."""
    forms = re.findall(r'<form\b[^>]*>', html, re.I)
    names = re.findall(
        r'<(?:input|select|textarea|button)\b[^>]*\bname=["\']([^"\']+)["\']',
        html, re.I)
    title = re.search(r'<title[^>]*>(.*?)</title>', html, re.I | re.S)
    return forms, sorted(set(names)), (title.group(1).strip() if title else "?")


def encode_multipart(field_name, filename, file_bytes, content_type,
                     boundary=None, fields=None):
    """Encode a file (plus optional text fields) as a multipart/form-data body.

    Returns (content_type_header, body_bytes). A boundary may be supplied for
    deterministic output (tests); otherwise a random one is generated.
    """
    boundary = boundary or uuid.uuid4().hex
    crlf = b"\r\n"
    bb = boundary.encode("ascii")
    parts = []
    for name, value in (fields or {}).items():
        parts += [
            b"--", bb, crlf,
            f'Content-Disposition: form-data; name="{name}"'.encode("utf-8"),
            crlf, crlf,
            str(value).encode("utf-8"), crlf,
        ]
    disposition = (
        'Content-Disposition: form-data; '
        f'name="{field_name}"; filename="{filename}"'
    )
    parts += [
        b"--", bb, crlf,
        disposition.encode("utf-8"), crlf,
        f"Content-Type: {content_type}".encode("ascii"), crlf, crlf,
        file_bytes, crlf,
        b"--", bb, b"--", crlf,
    ]
    return f"multipart/form-data; boundary={boundary}", b"".join(parts)


def build_logged_in_opener(server, user, password):
    """Perform a browser-style Dreamwidth web login.

    Returns (opener, form_auth): an opener whose cookie jar holds the login
    session, and an lj_form_auth token harvested from the post-login page (or
    None). Calls fail() if no session cookie is obtained.
    """
    jar = CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar))
    login_url = server + LOGIN_PATH
    headers = {"User-Agent": USER_AGENT}

    # Step 1: fetch the login page (sets the anonymous cookie the form-auth
    # token is bound to) and read the actual login form.
    with opener.open(urllib.request.Request(login_url, headers=headers),
                     timeout=SOCKET_TIMEOUT) as r:
        login_html = r.read().decode("utf-8", "replace")

    # Step 2: submit the real form - keep its hidden fields (lj_form_auth,
    # returnto, type, ...) verbatim and only fill in the credentials. This
    # mirrors a browser far more faithfully than a hand-built field set.
    action, data = parse_login_form(login_html)
    data["user"] = user
    data["password"] = password
    data["remember_me"] = data.get("remember_me") or "1"
    data["action:login"] = "Log in"
    if "lj_form_auth" not in data:
        token = extract_form_auth(login_html)
        if token:
            data["lj_form_auth"] = token
    post_headers = dict(headers, Referer=login_url)
    with opener.open(
            urllib.request.Request(action or login_url,
                                   data=urlencode(data).encode("utf-8"),
                                   headers=post_headers),
            timeout=SOCKET_TIMEOUT) as r2:
        landing_html = r2.read().decode("utf-8", "replace")

    if not any(c.name in SESSION_COOKIE_NAMES for c in jar):
        forms, login_inputs, _ = describe_forms(login_html)
        _, _, landing_title = describe_forms(landing_html)
        cookies = ", ".join(sorted(c.name for c in jar)) or "(none)"
        safe = {k: ("***" if k == "password" else v) for k, v in data.items()}
        server_error = extract_error_text(landing_html) or "(none found on page)"
        fail("Web login failed - no session cookie received.\n"
             f"  server error message:    {server_error}\n"
             f"  posted fields+values:    {safe}\n"
             f"  login-page input names:  {login_inputs}\n"
             f"  login-page form action:  {action!r}\n"
             f"  landing-page title:      {landing_title}\n"
             f"  cookies received:        {cookies}")

    return opener


def upload_image(opener, server, path, form_auth=None, field_name="file"):
    """Upload one image file through an authenticated opener; return the parsed
    JSON response (which includes the assigned image 'url'). Raises on error."""
    with open(path, "rb") as f:
        file_bytes = f.read()
    fields = {"lj_form_auth": form_auth} if form_auth else None
    content_type_header, body = encode_multipart(
        field_name, os.path.basename(path), file_bytes, IMAGE_CONTENT_TYPE,
        fields=fields)
    request = urllib.request.Request(
        server + UPLOAD_PATH, data=body, method="POST",
        headers={"Content-Type": content_type_header,
                 "Accept": "application/json",
                 "User-Agent": USER_AGENT})
    with opener.open(request, timeout=SOCKET_TIMEOUT) as response:
        raw = response.read()
        status = getattr(response, "status", None)
        ctype = response.headers.get("Content-Type", "")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        snippet = raw.decode("utf-8", "replace").strip()[:1000]
        raise RuntimeError(
            f"expected JSON but got HTTP {status} ({ctype}); "
            f"first 1000 chars of body:\n{snippet}")


def main():
    parser = argparse.ArgumentParser(
        description="Upload JPEG images to Dreamwidth media hosting.")
    parser.add_argument("user")
    parser.add_argument("password")
    parser.add_argument(
        "paths", nargs="+",
        help="image file(s) or glob(s); only .jpg/.jpeg are uploaded")
    parser.add_argument(
        "--server", default=DREAMWIDTH,
        help=f"server base URL (default: {DREAMWIDTH})")
    args = parser.parse_args()

    files = select_image_files(args.paths)
    if not files:
        fail("No JPEG files (.jpg/.jpeg/.JPG/.JPEG) matched the given path(s).")

    opener = build_logged_in_opener(args.server, args.user, args.password)

    print(f"Uploading {len(files)} image(s) to {args.server} ...")
    uploaded = 0
    for path in files:
        try:
            result = upload_image(opener, args.server, path)
            # api_ok may wrap the object; accept either a top-level or nested url.
            url = result.get("url") or (result.get("result") or {}).get("url")
            if url:
                print(f"  {path} -> {url}")
                uploaded += 1
            else:
                print(f"  {path} FAILED: unexpected response: "
                      f"{json.dumps(result)[:500]}", file=sys.stderr)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace").strip()[:1000]
            print(f"  {path} FAILED: HTTP {e.code} {e.reason}\n{detail}",
                  file=sys.stderr)
        except Exception as e:
            print(f"  {path} FAILED: {e}", file=sys.stderr)
    print(f"Done: {uploaded}/{len(files)} uploaded.")


if __name__ == "__main__":
    main()
