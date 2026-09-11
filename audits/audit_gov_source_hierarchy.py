import asyncio
import csv
import json
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup


FLAT_URL = "https://ankamala.org/organogram/flat"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"

RESULTS_FILE = (
    OUTPUT_DIR / "gov_source_hierarchy_audit.csv"
)

SUMMARY_FILE = (
    OUTPUT_DIR / "gov_source_hierarchy_summary.json"
)

FINDINGS_FILE = (
    OUTPUT_DIR / "gov_source_hierarchy_findings.csv"
)

MAX_CONCURRENT = 25
REQUEST_TIMEOUT = 7.0
MAX_LANGUAGE_PAGES = 1


FEDERAL_MARKERS = (
    "government of nepal",
    "नेपाल सरकार",
)


PROVINCE_MARKERS = {
    "koshi": (
        "koshi province government",
        "government of koshi province",
        "कोशी प्रदेश सरकार",
        "कोशी प्रदेश",
    ),
    "madhesh": (
        "madhesh province government",
        "government of madhesh province",
        "मधेश प्रदेश सरकार",
        "मधेश प्रदेश",
    ),
    "bagamati": (
        "bagmati province government",
        "government of bagmati province",
        "बागमती प्रदेश सरकार",
        "वाग्मती प्रदेश सरकार",
        "बागमती प्रदेश",
        "वाग्मती प्रदेश",
    ),
    "gandaki": (
        "gandaki province government",
        "government of gandaki province",
        "गण्डकी प्रदेश सरकार",
        "गण्डकी प्रदेश",
    ),
    "lumbini": (
        "lumbini province government",
        "government of lumbini province",
        "लुम्बिनी प्रदेश सरकार",
        "लुम्बिनी प्रदेश",
    ),
    "karnali": (
        "karnali province government",
        "government of karnali province",
        "कर्णाली प्रदेश सरकार",
        "कर्णाली प्रदेश",
    ),
    "sudurpashchim": (
        "sudurpashchim province government",
        "government of sudurpashchim province",
        "सुदूरपश्चिम प्रदेश सरकार",
        "सुदूरपश्चिम प्रदेश",
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


LANGUAGE_MARKERS = (
    "english",
    "nepali",
    "नेपाली",
    "eng",
)


NAME_STOP_WORDS = {
    "the",
    "of",
    "and",
    "government",
    "nepal",
    "ministry",
    "department",
    "office",
}


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


def get_record_names(record):
    if not record:
        return []

    name = record.get("name")
    names = []

    if isinstance(name, dict):
        names.extend(
            [
                name.get("display"),
                name.get("en"),
                name.get("ne"),
            ]
        )

    elif isinstance(name, str):
        names.append(name)

    result = []
    seen = set()

    for value in names:
        if not value:
            continue

        clean = " ".join(
            str(value).split()
        )

        key = normalize_text(clean)

        if key and key not in seen:
            seen.add(key)
            result.append(clean)

    return result


def get_named_parent(record):
    evidence = record.get("evidence")

    if not isinstance(evidence, dict):
        return ""

    named = evidence.get("named")

    if isinstance(named, str):
        return named.strip()

    return ""


def get_evidence_chain(record):
    evidence = record.get("evidence")

    if not isinstance(evidence, dict):
        return ""

    chain = evidence.get("chain") or []

    if not isinstance(chain, list):
        return ""

    return " -> ".join(
        str(item)
        for item in chain
    )


def get_start_urls(record):
    urls = []

    source_url = record.get("source_url")

    if (
        isinstance(source_url, str)
        and source_url.strip()
    ):
        urls.append(
            source_url.strip()
        )

    host = record.get("host")

    if host:
        urls.append(
            f"https://{host}/"
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


def dedupe(values):
    result = []
    seen = set()

    for value in values:
        if not value:
            continue

        key = normalize_text(value)

        if key and key not in seen:
            seen.add(key)
            result.append(value)

    return result


def extract_evidence(html, final_url):
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

    evidence_parts = []
    header_links = []

    if soup.title:
        evidence_parts.append(
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
        tag = soup.select_one(selector)

        if tag and tag.get("content"):
            evidence_parts.append(
                tag["content"]
            )

    blocks = []

    for selector in (
        "header",
        ".header",
        "#header",
        ".site-header",
        ".site-branding",
        ".navbar-brand",
        ".breadcrumb",
        ".breadcrumbs",
    ):
        blocks.extend(
            soup.select(selector)[:4]
        )

    for block in blocks:
        evidence_parts.append(
            block.get_text(
                " ",
                strip=True,
            )
        )

        for image in block.find_all(
            "img"
        ):
            evidence_parts.extend(
                [
                    image.get("alt", ""),
                    image.get("title", ""),
                ]
            )

        for link in block.find_all(
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
                header_links.append(
                    absolute
                )

    for heading in soup.find_all(
        [
            "h1",
            "h2",
            "h3",
            "h4",
        ],
        limit=40,
    ):
        evidence_parts.append(
            heading.get_text(
                " ",
                strip=True,
            )
        )

    # Catch logos/emblems outside <header>.
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
            evidence_parts.extend(
                [
                    image.get("alt", ""),
                    image.get("title", ""),
                ]
            )

    language_links = []

    base_host = (
        urlparse(final_url).hostname
        or ""
    ).lower()

    for tag in soup.find_all(
        [
            "a",
            "link",
        ]
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

        language_link = (
            any(
                marker in label
                for marker
                in LANGUAGE_MARKERS
            )
            or hreflang
            in {
                "en",
                "ne",
                "np",
            }
        )

        if not language_link:
            continue

        absolute = urljoin(
            final_url,
            href,
        )

        linked_host = (
            urlparse(absolute).hostname
            or ""
        ).lower()

        if (
            is_gov_np_url(absolute)
            and linked_host
            == base_host
        ):
            language_links.append(
                absolute
            )

    return {
        "text": " | ".join(
            dedupe(
                evidence_parts
            )
        ),
        "header_links": (
            dedupe(
                header_links
            )
        ),
        "language_links": (
            dedupe(
                language_links
            )[
                :MAX_LANGUAGE_PAGES
            ]
        ),
    }


async def fetch_url(
    client,
    semaphore,
    url,
):
    try:
        async with semaphore:
            response = await client.get(
                url
            )

        response.raise_for_status()

        final_url = str(
            response.url
        )

        if not is_gov_np_url(
            final_url
        ):
            return {
                "ok": False,
                "url": final_url,
                "text": "",
                "header_links": [],
                "language_links": [],
                "error": (
                    "redirected outside "
                    ".gov.np"
                ),
            }

        evidence = extract_evidence(
            response.text,
            final_url,
        )

        return {
            "ok": True,
            "url": final_url,
            "text": (
                evidence["text"]
            ),
            "header_links": (
                evidence[
                    "header_links"
                ]
            ),
            "language_links": (
                evidence[
                    "language_links"
                ]
            ),
            "error": "",
        }

    except Exception as exc:
        return {
            "ok": False,
            "url": "",
            "text": "",
            "header_links": [],
            "language_links": [],
            "error": (
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
        }


async def fetch_site(
    record,
    client,
    semaphore,
):
    last_error = ""

    for start_url in get_start_urls(
        record
    ):
        first = await fetch_url(
            client,
            semaphore,
            start_url,
        )

        if not first["ok"]:
            last_error = (
                first["error"]
            )
            continue

        pages = [first]

        # Follow at most one English/Nepali
        # variant if the site exposes one.
        for language_url in (
            first[
                "language_links"
            ]
        ):
            extra = await fetch_url(
                client,
                semaphore,
                language_url,
            )

            if extra["ok"]:
                pages.append(
                    extra
                )

        texts = []
        links = []
        urls = []

        for page in pages:
            urls.append(
                page["url"]
            )

            texts.append(
                page["text"]
            )

            links.extend(
                page[
                    "header_links"
                ]
            )

        return {
            "ok": True,
            "urls": dedupe(urls),
            "text": " | ".join(
                dedupe(texts)
            ),
            "header_links": (
                dedupe(links)
            ),
            "error": "",
        }

    return {
        "ok": False,
        "urls": [],
        "text": "",
        "header_links": [],
        "error": (
            last_error
            or
            "no usable .gov.np URL"
        ),
    }


def infer_source_jurisdiction(
    text,
):
    text = normalize_text(text)

    if not text:
        return (
            "unknown",
            "none",
        )

    federal = any(
        normalize_text(marker)
        in text
        for marker
        in FEDERAL_MARKERS
    )

    provinces = [
        province
        for province, markers
        in PROVINCE_MARKERS.items()
        if any(
            normalize_text(marker)
            in text
            for marker
            in markers
        )
    ]

    local = any(
        normalize_text(marker)
        in text
        for marker
        in LOCAL_MARKERS
    )

    if (
        federal
        and not provinces
    ):
        return (
            "federal",
            "strong",
        )

    if (
        len(provinces) == 1
        and not federal
    ):
        return (
            provinces[0],
            "strong",
        )

    if (
        local
        and not federal
        and not provinces
    ):
        return (
            "local",
            "strong",
        )

    if (
        federal
        or provinces
        or local
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
    if not record:
        return "unknown"

    government = record.get(
        "government"
    )

    level = record.get(
        "level"
    )

    if government == "federal":
        return "federal"

    if government in PROVINCE_MARKERS:
        return government

    if government == "local":
        return "local"

    if level == "federal":
        return "federal"

    if level == "local":
        return "local"

    return (
        government
        or level
        or "unknown"
    )


def name_tokens(value):
    return {
        token
        for token
        in normalize_text(
            value
        ).split()
        if (
            len(token) > 1
            and token
            not in NAME_STOP_WORDS
        )
    }


def name_similarity(a, b):
    a_norm = normalize_text(a)
    b_norm = normalize_text(b)

    if not a_norm or not b_norm:
        return 0.0

    if (
        a_norm in b_norm
        or b_norm in a_norm
    ):
        return 1.0

    sequence = (
        SequenceMatcher(
            None,
            a_norm,
            b_norm,
        ).ratio()
    )

    a_tokens = name_tokens(a)
    b_tokens = name_tokens(b)

    if a_tokens and b_tokens:
        union = (
            a_tokens
            | b_tokens
        )

        token_score = (
            len(
                a_tokens
                & b_tokens
            )
            / len(union)
        )

    else:
        token_score = 0.0

    return max(
        sequence,
        token_score,
    )


def resolve_linked_parent(
    child,
    child_site,
    records_by_host,
):
    """
    If the official child header links to
    another Ankamala body whose name matches
    the named parent, return that host.

    Nothing is hardcoded.
    """

    named_parent = (
        get_named_parent(
            child
        )
    )

    if (
        not named_parent
        or not child_site.get(
            "ok"
        )
    ):
        return (
            "",
            0.0,
        )

    child_host = (
        child.get(
            "host",
            ""
        ).lower()
    )

    candidates = []

    for link in child_site.get(
        "header_links",
        [],
    ):
        linked_host = (
            urlparse(link).hostname
            or ""
        ).lower()

        if (
            not linked_host
            or linked_host
            == child_host
        ):
            continue

        candidate = (
            records_by_host.get(
                linked_host
            )
        )

        if not candidate:
            continue

        score = max(
            (
                name_similarity(
                    named_parent,
                    candidate_name,
                )
                for candidate_name
                in get_record_names(
                    candidate
                )
            ),
            default=0.0,
        )

        candidates.append(
            (
                linked_host,
                score,
            )
        )

    if not candidates:
        return (
            "",
            0.0,
        )

    candidates.sort(
        key=lambda item: item[1],
        reverse=True,
    )

    best_host, best_score = (
        candidates[0]
    )

    if best_score < 0.65:
        return (
            "",
            best_score,
        )

    return (
        best_host,
        best_score,
    )


def compare_edge(
    child,
    parent,
    child_site,
    parent_site,
    records_by_host,
):
    child_ank = (
        ankamala_jurisdiction(
            child
        )
    )

    parent_ank = (
        ankamala_jurisdiction(
            parent
        )
    )

    (
        child_source,
        child_confidence,
    ) = infer_source_jurisdiction(
        child_site.get(
            "text",
            "",
        )
    )

    (
        parent_source,
        parent_confidence,
    ) = infer_source_jurisdiction(
        parent_site.get(
            "text",
            "",
        )
    )

    assigned_parent = (
        child.get("parent")
        or ""
    )

    assigned_parent_linked = False

    for link in child_site.get(
        "header_links",
        [],
    ):
        linked_host = (
            urlparse(link).hostname
            or ""
        ).lower()

        if (
            linked_host
            == assigned_parent.lower()
        ):
            assigned_parent_linked = True
            break

    (
        linked_parent_candidate,
        linked_parent_score,
    ) = resolve_linked_parent(
        child,
        child_site,
        records_by_host,
    )

    status = "review"
    reasons = []

    if not child_site.get("ok"):
        status = (
            "source_unreachable"
        )

        reasons.append(
            "child official source "
            "could not be fetched"
        )

    elif (
        child_confidence
        == "strong"
        and child_source
        != child_ank
    ):
        status = (
            "classification_mismatch"
        )

        reasons.append(
            "child official source "
            "disagrees with "
            "Ankamala classification"
        )

    elif (
        parent
        and parent_confidence
        == "strong"
        and parent_source
        != parent_ank
    ):
        status = (
            "parent_classification_mismatch"
        )

        reasons.append(
            "parent official source "
            "disagrees with "
            "Ankamala classification"
        )

    elif (
        parent
        and child_confidence
        == "strong"
        and parent_confidence
        == "strong"
        and child_source
        == child_ank
        and parent_source
        == parent_ank
        and child_source
        != parent_source
    ):
        status = (
            "source_supported_mismatch"
        )

        reasons.append(
            "child and assigned parent "
            "are confirmed by their "
            "official sites as different "
            "government jurisdictions"
        )

    elif child_ank == parent_ank:
        status = (
            "no_mismatch_detected"
        )

        reasons.append(
            "child and parent are in "
            "the same Ankamala jurisdiction"
        )

    else:
        status = "review"

        reasons.append(
            "cross-government edge "
            "needs stronger source evidence"
        )

    if (
        linked_parent_candidate
        and linked_parent_candidate
        != assigned_parent
    ):
        reasons.append(
            "child official header links "
            "to another Ankamala body "
            "matching the named parent"
        )

    return {
        "child_host": (
            child.get(
                "host",
                "",
            )
        ),

        "child_name": (
            get_name(child)
        ),

        "child_level": (
            child.get(
                "level",
                "",
            )
        ),

        "child_government": (
            child.get(
                "government",
                "",
            )
        ),

        "child_source_jurisdiction": (
            child_source
        ),

        "child_source_confidence": (
            child_confidence
        ),

        "assigned_parent_host": (
            assigned_parent
        ),

        "assigned_parent_name": (
            get_name(parent)
        ),

        "parent_level": (
            parent.get(
                "level",
                "",
            )
            if parent
            else ""
        ),

        "parent_government": (
            parent.get(
                "government",
                "",
            )
            if parent
            else ""
        ),

        "parent_source_jurisdiction": (
            parent_source
        ),

        "parent_source_confidence": (
            parent_confidence
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

        "assigned_parent_linked_in_child_header": (
            assigned_parent_linked
        ),

        "linked_parent_candidate": (
            linked_parent_candidate
        ),

        "linked_parent_candidate_score": (
            round(
                linked_parent_score,
                3,
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

        "parent_source_urls": (
            " | ".join(
                parent_site.get(
                    "urls",
                    [],
                )
            )
        ),

        "status": status,

        "reason": (
            " | ".join(
                reasons
            )
        ),

        "child_header_logo_evidence": (
            " ".join(
                child_site.get(
                    "text",
                    "",
                ).split()
            )[:700]
        ),

        "parent_header_logo_evidence": (
            " ".join(
                parent_site.get(
                    "text",
                    "",
                ).split()
            )[:500]
        ),
    }


def save_csv(path, rows):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not rows:
        path.write_text(
            "",
            encoding="utf-8",
        )
        return

    with path.open(
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
        writer.writerows(rows)


async def main():
    print(
        "Fetching live "
        "Ankamala organogram..."
    )

    timeout = httpx.Timeout(
        REQUEST_TIMEOUT,
    )

    limits = httpx.Limits(
        max_connections=(
            MAX_CONCURRENT
        ),
        max_keepalive_connections=(
            MAX_CONCURRENT
        ),
    )

    async with httpx.AsyncClient(
        timeout=timeout,
        limits=limits,
        follow_redirects=True,

        # Some government sites have
        # problematic TLS configurations.
        # We are only reading public data.
        verify=False,

        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(compatible; "
                "AnkamalaHierarchyAudit/2.0)"
            )
        },
    ) as client:

        response = await client.get(
            FLAT_URL
        )

        response.raise_for_status()

        records = response.json()

        if not isinstance(
            records,
            list,
        ):
            raise ValueError(
                "Expected /organogram/flat "
                "to return a list."
            )

        bodies = [
            record
            for record
            in records
            if (
                record.get(
                    "node_class"
                )
                == "body"
                and record.get(
                    "host"
                )
            )
        ]

        records_by_host = {
            record.get(
                "host",
                "",
            ).lower(): record

            for record
            in records

            if record.get(
                "host"
            )
        }

        # All government bodies.
        records_to_fetch = {
            record.get(
                "host",
                "",
            ).lower(): record

            for record
            in bodies
        }

        # Include any parent hosts that
        # are referenced but are not bodies.
        for child in bodies:
            parent_host = (
                child.get(
                    "parent"
                )
                or ""
            ).lower()

            if (
                parent_host
                and parent_host
                in records_by_host
            ):
                records_to_fetch[
                    parent_host
                ] = (
                    records_by_host[
                        parent_host
                    ]
                )

        print(
            f"Government bodies: "
            f"{len(bodies):,}"
        )

        print(
            "Official hosts to inspect: "
            f"{len(records_to_fetch):,}"
        )

        print(
            "Async concurrency: "
            f"{MAX_CONCURRENT}"
        )

        semaphore = (
            asyncio.Semaphore(
                MAX_CONCURRENT
            )
        )

        async def fetch_one(
            host,
            record,
        ):
            site = await fetch_site(
                record,
                client,
                semaphore,
            )

            return (
                host,
                site,
            )

        tasks = [
            asyncio.create_task(
                fetch_one(
                    host,
                    record,
                )
            )

            for host, record
            in records_to_fetch.items()
        ]

        site_by_host = {}

        completed = 0
        successful = 0

        for task in asyncio.as_completed(
            tasks
        ):
            host, site = await task

            site_by_host[
                host
            ] = site

            completed += 1

            if site.get("ok"):
                successful += 1

            if (
                completed % 100 == 0
                or completed
                == len(tasks)
            ):
                print(
                    f"[{completed:,}/"
                    f"{len(tasks):,}] "
                    f"OK={successful:,} "
                    f"FAILED="
                    f"{completed-successful:,}"
                )

    print(
        "\nComparing "
        "parent-child hierarchy..."
    )

    rows = []

    for child in bodies:
        parent_host = (
            child.get(
                "parent"
            )
            or ""
        ).lower()

        if not parent_host:
            continue

        parent = (
            records_by_host.get(
                parent_host
            )
        )

        child_host = (
            child.get(
                "host",
                ""
            ).lower()
        )

        child_site = (
            site_by_host.get(
                child_host,
                {
                    "ok": False,
                    "urls": [],
                    "text": "",
                    "header_links": [],
                },
            )
        )

        parent_site = (
            site_by_host.get(
                parent_host,
                {
                    "ok": False,
                    "urls": [],
                    "text": "",
                    "header_links": [],
                },
            )
        )

        rows.append(
            compare_edge(
                child,
                parent,
                child_site,
                parent_site,
                records_by_host,
            )
        )

    priority = {
        "source_supported_mismatch": 0,
        "classification_mismatch": 1,
        "parent_classification_mismatch": 2,
        "review": 3,
        "source_unreachable": 4,
        "no_mismatch_detected": 5,
    }

    rows.sort(
        key=lambda row: (
            priority.get(
                row["status"],
                99,
            ),
            row["child_host"],
        )
    )

    findings = [
        row
        for row in rows
        if row["status"]
        in {
            "source_supported_mismatch",
            "classification_mismatch",
            "parent_classification_mismatch",
        }
    ]

    save_csv(
        RESULTS_FILE,
        rows,
    )

    save_csv(
        FINDINGS_FILE,
        findings,
    )

    counts = {}

    for row in rows:
        counts[row["status"]] = (
            counts.get(
                row["status"],
                0,
            )
            + 1
        )

    summary = {
        "source": FLAT_URL,

        "total_graph_records": (
            len(records)
        ),

        "government_bodies": (
            len(bodies)
        ),

        "official_hosts_attempted": (
            len(
                records_to_fetch
            )
        ),

        "official_hosts_fetched": (
            successful
        ),

        "official_hosts_failed": (
            len(
                records_to_fetch
            )
            - successful
        ),

        "parent_child_edges_compared": (
            len(rows)
        ),

        "findings": (
            len(findings)
        ),

        "status_counts": counts,
    }

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

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
        "HIERARCHY AUDIT ---"
    )

    print(
        f"Government bodies: "
        f"{len(bodies):,}"
    )

    print(
        f"Official hosts fetched: "
        f"{successful:,}/"
        f"{len(records_to_fetch):,}"
    )

    print(
        "Parent-child edges compared: "
        f"{len(rows):,}"
    )

    print(
        f"Strong findings: "
        f"{len(findings):,}"
    )

    print()

    for status, count in sorted(
        counts.items(),
        key=lambda item: (
            priority.get(
                item[0],
                99,
            )
        ),
    ):
        print(
            f"{status}: "
            f"{count:,}"
        )

    print(
        f"\nAll edges: "
        f"{RESULTS_FILE}"
    )

    print(
        f"Strong findings: "
        f"{FINDINGS_FILE}"
    )

    print(
        f"Summary: "
        f"{SUMMARY_FILE}"
    )

    print(
        "\nNo organisation/domain "
        "is hardcoded."
    )


if __name__ == "__main__":
    asyncio.run(main())