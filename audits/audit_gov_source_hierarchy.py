import csv
import json
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


FLAT_URL = "https://ankamala.org/organogram/flat"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"

RESULTS_FILE = (
    OUTPUT_DIR
    / "gov_source_verified_parent_candidates.csv"
)

SUMMARY_FILE = (
    OUTPUT_DIR
    / "gov_source_verified_parent_summary.json"
)

TIMEOUT = 8
MAX_WORKERS = 10
MAX_LANGUAGE_PAGES = 2


FEDERAL_MARKERS = (
    "government of nepal",
    "नेपाल सरकार",
)


PROVINCE_MARKERS = {
    "koshi": (
        "koshi province",
        "government of koshi province",
        "koshi provincial government",
        "कोशी प्रदेश",
        "कोशी प्रदेश सरकार",
    ),
    "madhesh": (
        "madhesh province",
        "government of madhesh province",
        "madhesh provincial government",
        "मधेश प्रदेश",
        "मधेश प्रदेश सरकार",
    ),
    "bagamati": (
        "bagmati province",
        "bagmati provincial government",
        "government of bagmati province",
        "बागमती प्रदेश",
        "वाग्मती प्रदेश",
        "बागमती प्रदेश सरकार",
        "वाग्मती प्रदेश सरकार",
    ),
    "gandaki": (
        "gandaki province",
        "gandaki provincial government",
        "government of gandaki province",
        "गण्डकी प्रदेश",
        "गण्डकी प्रदेश सरकार",
    ),
    "lumbini": (
        "lumbini province",
        "lumbini provincial government",
        "government of lumbini province",
        "लुम्बिनी प्रदेश",
        "लुम्बिनी प्रदेश सरकार",
    ),
    "karnali": (
        "karnali province",
        "karnali provincial government",
        "government of karnali province",
        "कर्णाली प्रदेश",
        "कर्णाली प्रदेश सरकार",
    ),
    "sudurpashchim": (
        "sudurpashchim province",
        "sudurpashchim provincial government",
        "government of sudurpashchim province",
        "सुदूरपश्चिम प्रदेश",
        "सुदूरपश्चिम प्रदेश सरकार",
    ),
}


LOCAL_MARKERS = (
    "rural municipality",
    "municipality",
    "metropolitan city",
    "sub metropolitan city",
    "गाउँपालिका",
    "नगरपालिका",
    "महानगरपालिका",
    "उपमहानगरपालिका",
)


LANGUAGE_LABELS = (
    "english",
    "nepali",
    "नेपाली",
)


def create_session():
    session = requests.Session()

    retry = Retry(
        total=1,
        connect=1,
        read=1,
        backoff_factor=0.4,
        status_forcelist=(
            429,
            500,
            502,
            503,
            504,
        ),
        allowed_methods=("GET",),
    )

    adapter = HTTPAdapter(
        max_retries=retry
    )

    session.mount(
        "https://",
        adapter,
    )

    session.mount(
        "http://",
        adapter,
    )

    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 "
                "(compatible; "
                "AnkamalaHierarchyAudit/1.0)"
            )
        }
    )

    return session


SESSION = create_session()


def normalize_text(value):
    if value is None:
        return ""

    value = unicodedata.normalize(
        "NFKC",
        str(value),
    )

    value = (
        value
        .replace("\u200b", " ")
        .lower()
    )

    value = re.sub(
        r"[^\w\u0900-\u097f]+",
        " ",
        value,
    )

    return " ".join(
        value.split()
    )


def is_gov_np_url(url):
    try:
        host = (
            urlparse(url).hostname
            or ""
        ).lower()

    except ValueError:
        return False

    return (
        host == "gov.np"
        or host.endswith(".gov.np")
    )


def get_name(record):
    if not record:
        return ""

    name = record.get("name")

    if isinstance(name, dict):
        return (
            name.get("display")
            or name.get("en")
            or name.get("ne")
            or ""
        )

    return name or ""


def source_urls(record):
    urls = []

    source_url = record.get(
        "source_url"
    )

    if (
        isinstance(source_url, str)
        and source_url.strip()
    ):
        urls.append(
            source_url.strip()
        )

    host = record.get("host")

    if host:
        urls.extend(
            [
                f"https://{host}/",
                f"http://{host}/",
            ]
        )

    result = []
    seen = set()

    for url in urls:
        if not is_gov_np_url(url):
            continue

        key = url.rstrip("/")

        if key not in seen:
            seen.add(key)
            result.append(url)

    return result


def fetch_records():
    response = SESSION.get(
        FLAT_URL,
        timeout=20,
    )

    response.raise_for_status()

    records = response.json()

    if not isinstance(records, list):
        raise ValueError(
            "Expected /organogram/flat "
            "to return a list."
        )

    return records


def find_cross_government_candidates(
    records,
):
    records_by_host = {
        row.get("host"): row
        for row in records
        if row.get("host")
    }

    bodies = [
        row
        for row in records
        if row.get("node_class")
        == "body"
    ]

    candidates = []

    for child in bodies:
        parent_host = child.get(
            "parent"
        )

        if not parent_host:
            continue

        parent = records_by_host.get(
            parent_host
        )

        if parent is None:
            continue

        child_government = (
            child.get("government")
        )

        parent_government = (
            parent.get("government")
        )

        if (
            not child_government
            or not parent_government
        ):
            continue

        if (
            child_government
            == parent_government
        ):
            continue

        candidates.append(
            {
                "child": child,
                "parent": parent,
            }
        )

    return (
        bodies,
        records_by_host,
        candidates,
    )


def discover_language_links(
    soup,
    base_url,
):
    base_host = (
        urlparse(base_url).hostname
        or ""
    ).lower()

    found = []

    for tag in soup.find_all(
        ["a", "link"]
    ):
        href = tag.get("href")

        if not href:
            continue

        label = normalize_text(
            " ".join(
                [
                    tag.get_text(
                        " ",
                        strip=True,
                    ),
                    str(
                        tag.get(
                            "title",
                            "",
                        )
                    ),
                    str(
                        tag.get(
                            "aria-label",
                            "",
                        )
                    ),
                    str(
                        tag.get(
                            "hreflang",
                            "",
                        )
                    ),
                ]
            )
        )

        hreflang = normalize_text(
            tag.get(
                "hreflang",
                "",
            )
        )

        is_language_link = any(
            normalize_text(item)
            in label
            for item
            in LANGUAGE_LABELS
        )

        if hreflang in {
            "en",
            "ne",
            "np",
        }:
            is_language_link = True

        if not is_language_link:
            continue

        absolute = urljoin(
            base_url,
            href,
        )

        if not is_gov_np_url(
            absolute
        ):
            continue

        link_host = (
            urlparse(absolute).hostname
            or ""
        ).lower()

        if link_host != base_host:
            continue

        found.append(
            absolute
        )

    result = []
    seen = set()

    for url in found:
        key = url.rstrip("/")

        if key not in seen:
            seen.add(key)
            result.append(url)

    return result[
        :MAX_LANGUAGE_PAGES
    ]


def extract_evidence(
    html,
    final_url,
):
    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    for tag in soup(
        [
            "script",
            "style",
            "noscript",
            "template",
        ]
    ):
        tag.decompose()

    parts = []
    gov_links = []

    if soup.title:
        parts.append(
            soup.title.get_text(
                " ",
                strip=True,
            )
        )

    for selector in (
        'meta[property="og:title"]',
        'meta[name="description"]',
        'meta[property="og:description"]',
    ):
        tag = soup.select_one(
            selector
        )

        if (
            tag
            and tag.get(
                "content"
            )
        ):
            parts.append(
                tag["content"]
            )

    # Header text + header logo metadata
    for header in soup.find_all(
        "header"
    )[:3]:

        parts.append(
            header.get_text(
                " ",
                strip=True,
            )
        )

        for image in header.find_all(
            "img"
        ):
            parts.extend(
                [
                    image.get(
                        "alt",
                        "",
                    ),
                    image.get(
                        "title",
                        "",
                    ),
                ]
            )

        # Government links appearing
        # directly in the header
        for link in header.find_all(
            "a",
            href=True,
        ):
            absolute = urljoin(
                final_url,
                link["href"],
            )

            if is_gov_np_url(
                absolute
            ):
                gov_links.append(
                    absolute
                )

    # Organisation/header headings
    for heading in soup.find_all(
        [
            "h1",
            "h2",
            "h3",
            "h4",
        ],
        limit=40,
    ):
        parts.append(
            heading.get_text(
                " ",
                strip=True,
            )
        )

    # Logo metadata outside <header>
    for image in soup.find_all(
        "img",
        limit=120,
    ):
        descriptor = " ".join(
            [
                str(
                    image.get(
                        "src",
                        "",
                    )
                ),
                " ".join(
                    image.get(
                        "class",
                        [],
                    )
                    or []
                ),
                str(
                    image.get(
                        "id",
                        "",
                    )
                ),
            ]
        ).lower()

        if any(
            token in descriptor
            for token in (
                "logo",
                "brand",
                "emblem",
                "header",
            )
        ):
            parts.extend(
                [
                    image.get(
                        "alt",
                        "",
                    ),
                    image.get(
                        "title",
                        "",
                    ),
                ]
            )

    clean_parts = []
    seen = set()

    for part in parts:
        cleaned = " ".join(
            str(part).split()
        )

        key = normalize_text(
            cleaned
        )

        if (
            not key
            or key in seen
        ):
            continue

        seen.add(key)
        clean_parts.append(
            cleaned
        )

    return {
        "text": (
            " | ".join(
                clean_parts
            )
        ),
        "language_links": (
            discover_language_links(
                soup,
                final_url,
            )
        ),
        "gov_links": gov_links,
    }


def request_one_page(url):
    try:
        response = SESSION.get(
            url,
            timeout=TIMEOUT,
            allow_redirects=True,
        )

        response.raise_for_status()

    except requests.RequestException as exc:
        return {
            "ok": False,
            "url": "",
            "text": "",
            "gov_links": [],
            "language_links": [],
            "method": "requests",
            "error": (
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
        }

    if not is_gov_np_url(
        response.url
    ):
        return {
            "ok": False,
            "url": response.url,
            "text": "",
            "gov_links": [],
            "language_links": [],
            "method": "requests",
            "error": (
                "redirected outside "
                ".gov.np"
            ),
        }

    evidence = extract_evidence(
        response.text,
        response.url,
    )

    return {
        "ok": True,
        "url": response.url,
        "text": evidence["text"],
        "gov_links": (
            evidence["gov_links"]
        ),
        "language_links": (
            evidence[
                "language_links"
            ]
        ),
        "method": "requests",
        "error": "",
    }


def merge_pages(pages):
    texts = []
    urls = []
    gov_links = []
    methods = []

    seen_text = set()
    seen_url = set()
    seen_gov_link = set()

    for page in pages:
        text = page.get(
            "text",
            "",
        )

        key = normalize_text(
            text
        )

        if (
            key
            and key not in seen_text
        ):
            seen_text.add(key)
            texts.append(text)

        url = page.get(
            "url",
            "",
        )

        if (
            url
            and url not in seen_url
        ):
            seen_url.add(url)
            urls.append(url)

        for link in page.get(
            "gov_links",
            [],
        ):
            if (
                link
                not in seen_gov_link
            ):
                seen_gov_link.add(
                    link
                )

                gov_links.append(
                    link
                )

        method = page.get(
            "method"
        )

        if (
            method
            and method not in methods
        ):
            methods.append(
                method
            )

    return {
        "ok": bool(pages),
        "urls": urls,
        "text": (
            " | ".join(texts)
        ),
        "gov_links": gov_links,
        "methods": methods,
        "error": "",
    }


def fetch_site_requests(record):
    last_error = ""

    for start_url in source_urls(
        record
    ):
        first = request_one_page(
            start_url
        )

        if not first["ok"]:
            last_error = (
                first["error"]
            )
            continue

        pages = [first]

        seen = {
            first["url"].rstrip("/")
        }

        for language_url in (
            first[
                "language_links"
            ]
        ):
            key = (
                language_url
                .rstrip("/")
            )

            if key in seen:
                continue

            extra = request_one_page(
                language_url
            )

            if extra["ok"]:
                pages.append(
                    extra
                )

                seen.add(
                    extra[
                        "url"
                    ].rstrip("/")
                )

            if (
                len(pages)
                >= 1
                + MAX_LANGUAGE_PAGES
            ):
                break

        return merge_pages(
            pages
        )

    return {
        "ok": False,
        "urls": [],
        "text": "",
        "gov_links": [],
        "methods": [],
        "error": (
            last_error
            or
            "no usable .gov.np source"
        ),
    }


def evidence_is_weak(site):
    if not site.get(
        "ok"
    ):
        return True

    return (
        len(
            normalize_text(
                site.get(
                    "text",
                    "",
                )
            )
        )
        < 50
    )


def playwright_fallback(
    record,
    existing,
):
    """
    Browser fallback for failed or weak
    candidate sites.

    It renders JavaScript and attempts
    common English/Nepali toggles.
    """

    try:
        from playwright.sync_api import (
            sync_playwright,
        )

    except ImportError:
        return existing

    start_urls = source_urls(
        record
    )

    if not start_urls:
        return existing

    try:
        with sync_playwright() as playwright:

            browser = (
                playwright
                .chromium
                .launch(
                    headless=True
                )
            )

            context = (
                browser.new_context(
                    ignore_https_errors=True
                )
            )

            pages = []
            base_url = ""

            for start_url in start_urls:
                page = (
                    context.new_page()
                )

                try:
                    page.goto(
                        start_url,
                        wait_until=(
                            "domcontentloaded"
                        ),
                        timeout=(
                            TIMEOUT
                            * 1000
                        ),
                    )

                    page.wait_for_timeout(
                        500
                    )

                    if not is_gov_np_url(
                        page.url
                    ):
                        continue

                    evidence = (
                        extract_evidence(
                            page.content(),
                            page.url,
                        )
                    )

                    pages.append(
                        {
                            "ok": True,
                            "url": page.url,
                            "text": (
                                evidence[
                                    "text"
                                ]
                            ),
                            "gov_links": (
                                evidence[
                                    "gov_links"
                                ]
                            ),
                            "method": (
                                "playwright"
                            ),
                            "error": "",
                        }
                    )

                    base_url = page.url
                    break

                except Exception:
                    continue

                finally:
                    page.close()

            if not pages:
                context.close()
                browser.close()
                return existing

            # JS language toggles
            for label in (
                "English",
                "नेपाली",
                "Nepali",
            ):
                page = (
                    context.new_page()
                )

                try:
                    page.goto(
                        base_url,
                        wait_until=(
                            "domcontentloaded"
                        ),
                        timeout=(
                            TIMEOUT
                            * 1000
                        ),
                    )

                    page.wait_for_timeout(
                        300
                    )

                    locator = (
                        page.get_by_text(
                            label,
                            exact=True,
                        )
                    )

                    if (
                        locator.count()
                        == 0
                    ):
                        continue

                    locator.first.click(
                        timeout=2000
                    )

                    page.wait_for_timeout(
                        500
                    )

                    if not is_gov_np_url(
                        page.url
                    ):
                        continue

                    evidence = (
                        extract_evidence(
                            page.content(),
                            page.url,
                        )
                    )

                    pages.append(
                        {
                            "ok": True,
                            "url": page.url,
                            "text": (
                                evidence[
                                    "text"
                                ]
                            ),
                            "gov_links": (
                                evidence[
                                    "gov_links"
                                ]
                            ),
                            "method": (
                                "playwright-toggle"
                            ),
                            "error": "",
                        }
                    )

                except Exception:
                    pass

                finally:
                    page.close()

            context.close()
            browser.close()

            merged = merge_pages(
                pages
            )

            # Keep existing requests evidence
            # if it contains more useful text.
            if (
                existing.get("ok")
                and len(
                    normalize_text(
                        existing.get(
                            "text",
                            "",
                        )
                    )
                )
                > len(
                    normalize_text(
                        merged.get(
                            "text",
                            "",
                        )
                    )
                )
            ):
                return existing

            return merged

    except Exception:
        return existing


def infer_official_jurisdiction(
    text,
):
    normalized = normalize_text(
        text
    )

    if not normalized:
        return (
            "unknown",
            "none",
        )

    federal_hit = any(
        normalize_text(marker)
        in normalized
        for marker
        in FEDERAL_MARKERS
    )

    province_hits = [
        province
        for province, markers
        in PROVINCE_MARKERS.items()
        if any(
            normalize_text(marker)
            in normalized
            for marker
            in markers
        )
    ]

    local_hit = any(
        normalize_text(marker)
        in normalized
        for marker
        in LOCAL_MARKERS
    )

    if (
        federal_hit
        and not province_hits
    ):
        return (
            "federal",
            "strong",
        )

    if (
        len(province_hits) == 1
        and not federal_hit
    ):
        return (
            province_hits[0],
            "strong",
        )

    if (
        local_hit
        and not federal_hit
        and not province_hits
    ):
        return (
            "local",
            "medium",
        )

    if (
        federal_hit
        or province_hits
        or local_hit
    ):
        return (
            "mixed",
            "ambiguous",
        )

    return (
        "unknown",
        "none",
    )


def ankamala_jurisdiction(
    record,
):
    level = record.get(
        "level"
    )

    government = record.get(
        "government"
    )

    if (
        level == "federal"
        and government
        == "federal"
    ):
        return "federal"

    if (
        level == "provincial"
        and government
        in PROVINCE_MARKERS
    ):
        return government

    if (
        level == "local"
        or government == "local"
    ):
        return "local"

    return (
        government
        or level
        or "unknown"
    )


def get_named_parent(record):
    evidence = record.get(
        "evidence"
    )

    if not isinstance(
        evidence,
        dict,
    ):
        return ""

    named = evidence.get(
        "named"
    )

    if isinstance(
        named,
        str,
    ):
        return named.strip()

    return ""


def get_evidence_chain(record):
    evidence = record.get(
        "evidence"
    )

    if not isinstance(
        evidence,
        dict,
    ):
        return ""

    chain = (
        evidence.get("chain")
        or []
    )

    if not isinstance(
        chain,
        list,
    ):
        return ""

    return " -> ".join(
        str(item)
        for item in chain
    )


def audit_candidate(
    item,
    site_by_host,
):
    child = item["child"]
    parent = item["parent"]

    child_host = child.get(
        "host",
        "",
    )

    parent_host = parent.get(
        "host",
        "",
    )

    child_site = (
        site_by_host.get(
            child_host,
            {},
        )
    )

    parent_site = (
        site_by_host.get(
            parent_host,
            {},
        )
    )

    (
        child_official,
        child_confidence,
    ) = infer_official_jurisdiction(
        child_site.get(
            "text",
            "",
        )
    )

    (
        parent_official,
        parent_confidence,
    ) = infer_official_jurisdiction(
        parent_site.get(
            "text",
            "",
        )
    )

    child_ankamala = (
        ankamala_jurisdiction(
            child
        )
    )

    parent_ankamala = (
        ankamala_jurisdiction(
            parent
        )
    )

    status = "review"
    reasons = []

    # Strong source-supported case:
    #
    # official child site says jurisdiction X,
    # Ankamala also classifies child as X,
    # but assigned parent belongs to another
    # government/jurisdiction.
    if (
        child_confidence
        == "strong"
        and child_official
        == child_ankamala
        and child_official
        != parent_ankamala
    ):
        status = (
            "source_supported_conflict"
        )

        reasons.append(
            "child official header/logo "
            "jurisdiction agrees with "
            "child classification but "
            "conflicts with assigned parent"
        )

    # Stronger again if BOTH official
    # government sites independently identify
    # themselves as different jurisdictions.
    if (
        child_confidence
        == "strong"
        and parent_confidence
        == "strong"
        and child_official
        != parent_official
    ):
        status = (
            "source_supported_conflict"
        )

        reasons.append(
            "child and assigned-parent "
            "official websites show "
            "different jurisdictions"
        )

    if not child_site.get(
        "ok"
    ):
        status = (
            "source_unreachable"
        )

        reasons.append(
            "child official source "
            "could not be fetched"
        )

    elif child_official in {
        "unknown",
        "mixed",
    }:
        reasons.append(
            "child header/logo evidence "
            "does not give one clear "
            "jurisdiction"
        )

    if not parent_site.get(
        "ok"
    ):
        reasons.append(
            "assigned-parent official "
            "source could not be fetched"
        )

    elif parent_official in {
        "unknown",
        "mixed",
    }:
        reasons.append(
            "assigned-parent header/logo "
            "evidence does not give one "
            "clear jurisdiction"
        )

    # Check whether the exact assigned
    # parent host is actually linked from
    # the child site's header.
    parent_host_in_child_header = False

    for link in child_site.get(
        "gov_links",
        [],
    ):
        link_host = (
            urlparse(link).hostname
            or ""
        ).lower()

        if (
            link_host
            == parent_host.lower()
        ):
            parent_host_in_child_header = (
                True
            )

            break

    return {
        "child_host": child_host,
        "child_name": get_name(
            child
        ),
        "child_level": child.get(
            "level",
            "",
        ),
        "child_government": child.get(
            "government",
            "",
        ),
        "child_ankamala_jurisdiction": (
            child_ankamala
        ),

        "assigned_parent_host": (
            parent_host
        ),
        "assigned_parent_name": (
            get_name(parent)
        ),
        "parent_level": parent.get(
            "level",
            "",
        ),
        "parent_government": (
            parent.get(
                "government",
                "",
            )
        ),
        "parent_ankamala_jurisdiction": (
            parent_ankamala
        ),

        "placement_rule": child.get(
            "rule",
            "",
        ),
        "support_n": child.get(
            "support_n",
            "",
        ),

        "ankamala_named_parent": (
            get_named_parent(
                child
            )
        ),
        "ankamala_evidence_chain": (
            get_evidence_chain(
                child
            )
        ),

        "child_source_ok": (
            child_site.get(
                "ok",
                False,
            )
        ),
        "child_source_urls": (
            " | ".join(
                child_site.get(
                    "urls",
                    [],
                )
            )
        ),
        "child_source_methods": (
            ",".join(
                child_site.get(
                    "methods",
                    [],
                )
            )
        ),
        "child_official_jurisdiction": (
            child_official
        ),
        "child_official_confidence": (
            child_confidence
        ),

        "parent_source_ok": (
            parent_site.get(
                "ok",
                False,
            )
        ),
        "parent_source_urls": (
            " | ".join(
                parent_site.get(
                    "urls",
                    [],
                )
            )
        ),
        "parent_source_methods": (
            ",".join(
                parent_site.get(
                    "methods",
                    [],
                )
            )
        ),
        "parent_official_jurisdiction": (
            parent_official
        ),
        "parent_official_confidence": (
            parent_confidence
        ),

        "assigned_parent_host_linked_in_child_header": (
            parent_host_in_child_header
        ),

        "status": status,
        "reason": (
            " | ".join(
                reasons
            )
        ),

        "child_header_logo_excerpt": (
            " ".join(
                child_site.get(
                    "text",
                    "",
                ).split()
            )[:600]
        ),

        "parent_header_logo_excerpt": (
            " ".join(
                parent_site.get(
                    "text",
                    "",
                ).split()
            )[:600]
        ),
    }


def save_csv(rows):
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not rows:
        RESULTS_FILE.write_text(
            "",
            encoding="utf-8",
        )
        return

    with RESULTS_FILE.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=list(
                rows[0].keys()
            ),
        )

        writer.writeheader()
        writer.writerows(
            rows
        )


def main():
    print(
        "Fetching live "
        "Ankamala /gov data..."
    )

    records = fetch_records()

    (
        bodies,
        _,
        candidates,
    ) = (
        find_cross_government_candidates(
            records
        )
    )

    print(
        "Government bodies checked: "
        f"{len(bodies):,}"
    )

    print(
        "Cross-government parent "
        f"candidates: "
        f"{len(candidates):,}"
    )

    # Crawl only sites involved in
    # automatically detected candidates.
    records_to_fetch = {}

    for item in candidates:
        for record in (
            item["child"],
            item["parent"],
        ):
            host = record.get(
                "host"
            )

            if host:
                records_to_fetch[
                    host
                ] = record

    print(
        "Official candidate-related "
        "sites to inspect: "
        f"{len(records_to_fetch):,}"
    )

    site_by_host = {}

    with ThreadPoolExecutor(
        max_workers=MAX_WORKERS
    ) as executor:

        future_to_host = {
            executor.submit(
                fetch_site_requests,
                record,
            ): host

            for host, record
            in records_to_fetch.items()
        }

        completed = 0
        total = len(
            future_to_host
        )

        for future in as_completed(
            future_to_host
        ):
            host = (
                future_to_host[
                    future
                ]
            )

            try:
                site_by_host[
                    host
                ] = future.result()

            except Exception as exc:
                site_by_host[
                    host
                ] = {
                    "ok": False,
                    "urls": [],
                    "text": "",
                    "gov_links": [],
                    "methods": [],
                    "error": (
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    ),
                }

            completed += 1

            state = (
                "OK"
                if site_by_host[
                    host
                ].get("ok")
                else "FAILED"
            )

            print(
                f"[{completed}/{total}] "
                f"{host}: {state}"
            )

    # Browser only for sites where normal
    # requests could not get enough evidence.
    weak_hosts = [
        host
        for host, site
        in site_by_host.items()
        if evidence_is_weak(
            site
        )
    ]

    if weak_hosts:
        print(
            "\nPlaywright fallback for "
            f"{len(weak_hosts):,} "
            "failed/weak sites..."
        )

    for number, host in enumerate(
        weak_hosts,
        start=1,
    ):
        print(
            f"[browser "
            f"{number}/"
            f"{len(weak_hosts)}] "
            f"{host}"
        )

        site_by_host[
            host
        ] = playwright_fallback(
            records_to_fetch[
                host
            ],
            site_by_host[
                host
            ],
        )

    rows = [
        audit_candidate(
            item,
            site_by_host,
        )
        for item in candidates
    ]

    rows.sort(
        key=lambda row: (
            row["status"]
            != "source_supported_conflict",
            row["child_host"],
        )
    )

    save_csv(
        rows
    )

    counts = {
        "source_supported_conflict": sum(
            row["status"]
            == "source_supported_conflict"
            for row in rows
        ),

        "review": sum(
            row["status"]
            == "review"
            for row in rows
        ),

        "source_unreachable": sum(
            row["status"]
            == "source_unreachable"
            for row in rows
        ),
    }

    summary = {
        "source": FLAT_URL,
        "total_graph_records": (
            len(records)
        ),
        "government_bodies_checked": (
            len(bodies)
        ),
        "cross_government_parent_candidates": (
            len(candidates)
        ),
        "candidate_related_official_sites": (
            len(records_to_fetch)
        ),
        **counts,
    }

    with SUMMARY_FILE.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            summary,
            file,
            indent=2,
            ensure_ascii=False,
        )

    print(
        "\n--- GOV SOURCE "
        "PARENT AUDIT ---"
    )

    print(
        "Government bodies checked: "
        f"{len(bodies):,}"
    )

    print(
        "Cross-government parent "
        f"candidates: "
        f"{len(candidates):,}"
    )

    print(
        "Source-supported conflicts: "
        f"{counts['source_supported_conflict']:,}"
    )

    print(
        "Review candidates: "
        f"{counts['review']:,}"
    )

    print(
        "Source unreachable: "
        f"{counts['source_unreachable']:,}"
    )

    print(
        f"\nResults: "
        f"{RESULTS_FILE}"
    )

    print(
        f"Summary: "
        f"{SUMMARY_FILE}"
    )

    print(
        "\nNote: "
        "source_supported_conflict is "
        "automated source evidence, "
        "not a legal/administrative "
        "determination. It means the "
        "official header/logo "
        "jurisdiction conflicts with "
        "the assigned Ankamala parent."
    )


if __name__ == "__main__":
    main()