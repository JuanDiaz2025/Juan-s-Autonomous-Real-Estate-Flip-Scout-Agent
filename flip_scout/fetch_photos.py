#!/usr/bin/env python3
"""
Download a listing's Redfin photos for visual condition review.

Part of the standing lead-verification step (see SOP.md): before any new
qualified lead reaches the sheet feed or a notification, its actual listing
photos are downloaded and visually reviewed (homescout rubric - distress /
deferred maintenance / already-clean signals) so a "fixer" that's actually
a finished home never slips through on description keywords alone.

Usage:
    python3 flip_scout/fetch_photos.py <redfin_url> <out_dir> [max_photos]

Prints one line per saved photo, then "SAVED <n> photos to <out_dir>".
Exits 2 if the page had no extractable photos (itself a signal - MLS-light
listings often have none).
"""

import os
import re
import sys

import requests

UA = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) "
                     "Chrome/120.0 Safari/537.36")}


def extract_photo_urls(html):
    """Return the SUBJECT listing's photo URLs, deduped, in order.

    The page also embeds photos for the 'similar homes' carousel - those are
    other properties and must not be reviewed as if they were this one. All
    photos of one listing share the same MLS-number filename stem
    (.../bigphoto/463/OC25123456.jpg, OC25123456_1.jpg, ...), so group by
    stem and keep only the first photo's group.
    """
    urls = re.findall(
        r'https://ssl\.cdn-redfin\.com/photo/\d+/(?:bigphoto|mbphoto|islphoto)[^"\\\s]+\.jpg',
        html)
    seen, ordered = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            ordered.append(u)
    if not ordered:
        return []

    def stem(url):
        name = url.rsplit('/', 1)[-1]          # OC25123456_2.jpg
        base = name.rsplit('.', 1)[0]          # OC25123456_2
        return re.sub(r'_\d+$', '', base)      # OC25123456

    subject_stem = stem(ordered[0])
    return [u for u in ordered if stem(u) == subject_stem]


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    listing_url, out_dir = sys.argv[1], sys.argv[2]
    max_photos = int(sys.argv[3]) if len(sys.argv) > 3 else 6

    os.makedirs(out_dir, exist_ok=True)
    r = requests.get(listing_url, headers=UA, timeout=20)
    if r.status_code != 200:
        print(f"page fetch failed: HTTP {r.status_code}")
        sys.exit(2)

    photo_urls = extract_photo_urls(r.text)
    if not photo_urls:
        print("NO PHOTOS extractable from page (MLS-light listing?)")
        sys.exit(2)

    saved = 0
    for i, u in enumerate(photo_urls[:max_photos]):
        try:
            pr = requests.get(u, headers=UA, timeout=20)
            if pr.status_code == 200 and pr.content[:2] == b"\xff\xd8":  # JPEG magic
                path = os.path.join(out_dir, f"photo_{i:02d}.jpg")
                with open(path, "wb") as f:
                    f.write(pr.content)
                print(path)
                saved += 1
        except requests.RequestException:
            continue

    print(f"SAVED {saved} photos to {out_dir}")
    sys.exit(0 if saved else 2)


if __name__ == "__main__":
    main()
