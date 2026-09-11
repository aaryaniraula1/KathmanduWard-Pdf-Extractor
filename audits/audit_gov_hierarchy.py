import json
from collections import Counter
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


FLAT_URL = "https://ankamala.org/organogram/flat"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
SUMMARY_FILE = OUTPUT_DIR / "gov_hierarchy_summary.json"

TIMEOUT = 30


def create_session():
    session = requests.Session()

    retries = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[
            429,
            500,
            502,
            503,
            504,
        ],
        allowed_methods=["GET"],
    )

    session.mount(
        "https://",
        HTTPAdapter(max_retries=retries),
    )

    session.headers.update(
        {
            "User-Agent": "AnkamalaGovAudit/1.0"
        }
    )

    return session


SESSION = create_session()


def fetch_records():
    response = SESSION.get(
        FLAT_URL,
        timeout=TIMEOUT,
    )

    response.raise_for_status()

    records = response.json()

    if not isinstance(records, list):
        raise ValueError(
            "Expected /organogram/flat to return a list."
        )

    return records


def find_duplicate_hosts(records):
    host_counts = Counter(
        record.get("host")
        for record in records
        if record.get("host")
    )

    return {
        host: count
        for host, count in host_counts.items()
        if count > 1
    }


def contains_cycle(start_host, records_by_host):
    visited = set()
    current_host = start_host

    while current_host:
        if current_host in visited:
            return True

        visited.add(current_host)

        current_record = records_by_host.get(
            current_host
        )

        if current_record is None:
            return False

        current_host = current_record.get(
            "parent"
        )

    return False


def audit_hierarchy(records):
    records_by_host = {
        record["host"]: record
        for record in records
        if record.get("host")
    }

    bodies = [
        record
        for record in records
        if record.get("node_class") == "body"
    ]

    systems = [
        record
        for record in records
        if record.get("node_class") == "system"
    ]

    unclassified = [
        record
        for record in records
        if record.get("node_class")
        == "unclassified"
    ]

    level_counts = Counter(
        record.get("level")
        for record in bodies
    )

    duplicate_hosts = find_duplicate_hosts(
        records
    )

    parented_bodies = 0
    parentless_bodies = 0

    invalid_parent_refs = 0
    parent_refs_to_non_body = 0

    depth_mismatches = 0
    parent_lineage_mismatches = 0
    missing_ancestor_refs = 0
    hierarchy_cycles = 0

    support_count_mismatches = 0

    support_zero = 0
    support_one = 0
    support_two_plus = 0

    for record in bodies:
        host = record.get("host")
        parent = record.get("parent")
        lineage = record.get("lineage") or []
        depth = record.get("depth")

        support = record.get("support") or []
        support_n = record.get("support_n")

        # Objective check:
        # depth should equal number of ancestors.
        if depth != len(lineage):
            depth_mismatches += 1

        if parent:
            parented_bodies += 1

            parent_record = records_by_host.get(
                parent
            )

            # Parent host should exist in the graph.
            if parent_record is None:
                invalid_parent_refs += 1

            elif (
                parent_record.get("node_class")
                != "body"
            ):
                # This is recorded for review.
                # It is not automatically treated
                # as a confirmed hierarchy error.
                parent_refs_to_non_body += 1

            # Immediate parent should be the final
            # entry in the root-first lineage.
            if (
                not lineage
                or lineage[-1] != parent
            ):
                parent_lineage_mismatches += 1

            if support_n == 0:
                support_zero += 1

            elif support_n == 1:
                support_one += 1

            elif (
                isinstance(support_n, int)
                and support_n >= 2
            ):
                support_two_plus += 1

        else:
            parentless_bodies += 1

        # All lineage hosts should exist.
        for ancestor in lineage:
            if ancestor not in records_by_host:
                missing_ancestor_refs += 1

        # support_n should agree with the number
        # of support entries when available.
        if (
            isinstance(support_n, int)
            and support_n != len(support)
        ):
            support_count_mismatches += 1

        # Following parent links should never
        # lead back to the same record.
        if host and contains_cycle(
            host,
            records_by_host,
        ):
            hierarchy_cycles += 1

    summary = {
        "source": FLAT_URL,
        "total_graph_records": len(records),
        "bodies": len(bodies),
        "systems": len(systems),
        "unclassified": len(unclassified),
        "body_levels": {
            "federal": level_counts["federal"],
            "provincial": level_counts[
                "provincial"
            ],
            "local": level_counts["local"],
        },
        "duplicate_hosts": len(
            duplicate_hosts
        ),
        "parented_bodies": parented_bodies,
        "parentless_bodies": (
            parentless_bodies
        ),
        "invalid_parent_refs": (
            invalid_parent_refs
        ),
        "parent_refs_to_non_body": (
            parent_refs_to_non_body
        ),
        "depth_mismatches": (
            depth_mismatches
        ),
        "parent_lineage_mismatches": (
            parent_lineage_mismatches
        ),
        "missing_ancestor_refs": (
            missing_ancestor_refs
        ),
        "hierarchy_cycles": (
            hierarchy_cycles
        ),
        "support_count_mismatches": (
            support_count_mismatches
        ),
        "parent_edges_support_0": (
            support_zero
        ),
        "parent_edges_support_1": (
            support_one
        ),
        "parent_edges_support_2_plus": (
            support_two_plus
        ),
    }

    return summary


def save_summary(summary):
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


def print_summary(summary):
    print("\n--- GOV STRUCTURAL AUDIT ---")

    print(
        f"Total graph records: "
        f"{summary['total_graph_records']:,}"
    )

    print(
        f"Government bodies checked: "
        f"{summary['bodies']:,}"
    )

    print(
        f"Systems: "
        f"{summary['systems']:,}"
    )

    print(
        f"Unclassified: "
        f"{summary['unclassified']:,}"
    )

    print("\nBodies by level:")

    print(
        f"  Federal: "
        f"{summary['body_levels']['federal']:,}"
    )

    print(
        f"  Provincial: "
        f"{summary['body_levels']['provincial']:,}"
    )

    print(
        f"  Local: "
        f"{summary['body_levels']['local']:,}"
    )

    print("\nObjective graph checks:")

    print(
        f"  Duplicate hosts: "
        f"{summary['duplicate_hosts']}"
    )

    print(
        f"  Invalid parent references: "
        f"{summary['invalid_parent_refs']}"
    )

    print(
        f"  Parent references to non-body records: "
        f"{summary['parent_refs_to_non_body']}"
    )

    print(
        f"  Depth mismatches: "
        f"{summary['depth_mismatches']}"
    )

    print(
        f"  Parent/lineage mismatches: "
        f"{summary['parent_lineage_mismatches']}"
    )

    print(
        f"  Missing ancestor references: "
        f"{summary['missing_ancestor_refs']}"
    )

    print(
        f"  Hierarchy cycles: "
        f"{summary['hierarchy_cycles']}"
    )

    print(
        f"  Support-count mismatches: "
        f"{summary['support_count_mismatches']}"
    )

    print("\nParent-edge evidence:")

    print(
        f"  0 signals: "
        f"{summary['parent_edges_support_0']}"
    )

    print(
        f"  1 signal: "
        f"{summary['parent_edges_support_1']}"
    )

    print(
        f"  2+ signals: "
        f"{summary['parent_edges_support_2_plus']}"
    )

    print(
        "\nNote: this script checks internal graph "
        "consistency only. It does not measure "
        "factual government-hierarchy accuracy."
    )

    print(
        f"\nSaved summary: {SUMMARY_FILE}"
    )


def main():
    print(
        "Fetching live /gov organogram data..."
    )

    records = fetch_records()

    summary = audit_hierarchy(records)

    save_summary(summary)

    print_summary(summary)


if __name__ == "__main__":
    main()