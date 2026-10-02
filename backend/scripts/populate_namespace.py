#!/usr/bin/env python3
"""Populate an OptiFlow namespace with realistic demo data, straight in Firestore.

Writes directly to Firestore (not through the HTTP API) because the API always
stamps a ticket with the current time — backdated and future-dated downtime
history can only be seeded this way. Document shapes mirror what the API
services write, so every endpoint reads the result as if it were real data.

The namespace and its owner must already exist: they are only checked, never
created or modified, and no existing data is deleted. Everything below is
ADDED to the namespace (running the script twice adds a second set).

What it does, in order:
  1. Checks the namespace exists and the owner (by email) belongs to it.
  2. Plant settings: three shifts per day (06-14, 14-22, 22-06), each with a
     30-minute break (the settings document is overwritten).
  3. Supervisors and agents for every process.
  4. UAPs -> production lines -> workstations (standard / critical / bottleneck).
  5. Downtime tickets from `--days` days before today to `--days` days after,
     with random scope, type, location and lifecycle times, handled by random
     agents of the ticket's own process.

Usage (from `backend/`):
    .venv/bin/python scripts/populate_namespace.py --seed 42

Firestore credentials come from the usual backend configuration
(`GOOGLE_APPLICATION_CREDENTIALS` / project settings).
"""

import argparse
import random
import sys
import uuid
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.app.async_jobs.add_down_time import _resolve_shift  # noqa: E402
from src.app.core.firestore import (  # noqa: E402
    NAMESPACE_COLLECTION,
    NAMESPACE_SETTINGS_COLLECTION,
    PRODUCTION_LINE_COLLECTION,
    SETTINGS_SUBCOLLECTION,
    UAP_COLLECTION,
    USERS_COLLECTION,
    WORKSTATION_COLLECTION,
)
from src.app.core.security import hash_password  # noqa: E402
from src.app.core.security_code import generate_security_code  # noqa: E402
from src.app.gcp import get_firestore_client  # noqa: E402
from src.app.gcp.firestore import FirestoreClient  # noqa: E402
from src.app.globals.enum import (  # noqa: E402
    DownTimeStatus,
    DownTimeType,
    Process,
    ProductionScope,
    Role,
    WorkstationType,
)
from src.app.globals.enum.process import (  # noqa: E402
    CLOSE_ONLY_DOWNTIME_TYPES,
    DOWNTIME_TYPE_PROCESS,
)

DOWN_TIME_COLLECTION = "down_time"
ISSUES_SUBCOLLECTION = "issues"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_NAMESPACE_ID = "d7d6135e-e0b7-41aa-8ece-9a50e1362687"
DEFAULT_OWNER_EMAIL = "ttaherhagui@gmail.com"
DEFAULT_TIMEZONE = "Africa/Tunis"
DEFAULT_DAYS = 30

# Password given to every created user (agents pair by security code anyway).
STAFF_PASSWORD = "Operio-Demo-2026!"

SHIFTS = {
    "shift_1": {
        "start_time": "06:00",
        "end_time": "14:00",
        "break_start_time": "10:00",
        "break_end_time": "10:30",
    },
    "shift_2": {
        "start_time": "14:00",
        "end_time": "22:00",
        "break_start_time": "18:00",
        "break_end_time": "18:30",
    },
    "shift_3": {
        "start_time": "22:00",
        "end_time": "06:00",
        "break_start_time": "02:00",
        "break_end_time": "02:30",
    },
}

STAFF = [
    ("Leila", "Manager", Role.MANAGER),
    ("Sami", "Supervisor-Prod", Role.PRODUCTION_SUPERVISOR),
    ("Nadia", "Supervisor-Maint", Role.MAINTENANCE_SUPERVISOR),
    ("Karim", "Supervisor-Quality", Role.QUALITY_SUPERVISOR),
    ("Salma", "Supervisor-Logistic", Role.LOGISTIC_SUPERVISOR),
    ("Youssef", "Agent-Prod-1", Role.PRODUCTION_AGENT),
    ("Amira", "Agent-Prod-2", Role.PRODUCTION_AGENT),
    ("Walid", "Agent-Prod-3", Role.PRODUCTION_AGENT),
    ("Mohamed", "Agent-Maint-1", Role.MAINTENANCE_AGENT),
    ("Hana", "Agent-Maint-2", Role.MAINTENANCE_AGENT),
    ("Bilel", "Agent-Maint-3", Role.MAINTENANCE_AGENT),
    ("Omar", "Agent-Quality-1", Role.QUALITY_AGENT),
    ("Ines", "Agent-Quality-2", Role.QUALITY_AGENT),
    ("Rami", "Agent-Logistic-1", Role.LOGISTIC_AGENT),
    ("Nour", "Agent-Logistic-2", Role.LOGISTIC_AGENT),
]

STRUCTURE = [
    (
        "UAP Assemblage",
        "Unité de production - assemblage mécanique",
        [
            ("Ligne Assemblage A1", "Ligne principale d'assemblage"),
            ("Ligne Assemblage A2", "Ligne secondaire d'assemblage"),
        ],
    ),
    (
        "UAP Peinture",
        "Unité de production - peinture et finitions",
        [
            ("Ligne Peinture P1", "Ligne peinture primaire"),
            ("Ligne Peinture P2", "Ligne peinture de finition"),
            ("Ligne Séchage S1", "Ligne séchage et contrôle"),
        ],
    ),
    (
        "UAP Injection",
        "Unité de production - injection plastique",
        [
            ("Ligne Injection I1", "Ligne injection grande capacité"),
            ("Ligne Injection I2", "Ligne injection pièces fines"),
        ],
    ),
]

WORKSTATION_TEMPLATES = [
    [
        ("Poste Soudure", WorkstationType.CRITICAL, "Poste de soudure robotisée"),
        ("Poste Montage", WorkstationType.STANDARD, "Poste de montage manuel"),
        ("Poste Vissage", WorkstationType.BOTTLENECK, "Vissage automatique (goulot)"),
        ("Poste Contrôle", WorkstationType.STANDARD, "Contrôle qualité en ligne"),
    ],
    [
        ("Poste Presse", WorkstationType.BOTTLENECK, "Presse hydraulique (goulot)"),
        ("Poste Découpe", WorkstationType.CRITICAL, "Machine de découpe laser"),
        ("Poste Ébavurage", WorkstationType.STANDARD, "Ébavurage et finition"),
    ],
    [
        ("Poste Injection", WorkstationType.CRITICAL, "Presse d'injection 800T"),
        ("Poste Refroidissement", WorkstationType.STANDARD, "Tunnel de refroidissement"),
        ("Poste Emballage", WorkstationType.STANDARD, "Emballage et palettisation"),
    ],
]

# UAP id-list field -> role whose users are assigned to every UAP.
UAP_ROLE_FIELDS = {
    "maintenance_agent_ids": Role.MAINTENANCE_AGENT,
    "production_agent_ids": Role.PRODUCTION_AGENT,
    "quality_agent_ids": Role.QUALITY_AGENT,
    "logistic_agent_ids": Role.LOGISTIC_AGENT,
    "logistic_supervisor_ids": Role.LOGISTIC_SUPERVISOR,
    "maintenance_supervisor_ids": Role.MAINTENANCE_SUPERVISOR,
    "quality_supervisor_ids": Role.QUALITY_SUPERVISOR,
    "production_supervisor_ids": Role.PRODUCTION_SUPERVISOR,
}

# Relative frequency of each downtime type / scope in the generated history.
TYPE_WEIGHTS = {
    DownTimeType.BREAKDOWN: 35,
    DownTimeType.QUALITY_ISSUE: 18,
    DownTimeType.MATERIAL_SHORTAGE: 12,
    DownTimeType.SETUP_CHANGEOVER: 10,
    DownTimeType.WIP_SHORTAGE: 10,
    DownTimeType.ABSENTEEISM: 7,
    DownTimeType.OTHERS: 8,
}
SCOPE_WEIGHTS = {
    ProductionScope.WORK_STATION: 70,
    ProductionScope.PRODUCTION_LINE: 18,
    ProductionScope.UAP: 9,
    ProductionScope.PLANT: 3,
}

AGENT_ROLE = {
    Process.PRODUCTION: Role.PRODUCTION_AGENT,
    Process.MAINTENANCE: Role.MAINTENANCE_AGENT,
    Process.QUALITY: Role.QUALITY_AGENT,
    Process.LOGISTIC: Role.LOGISTIC_AGENT,
}


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------


def check_namespace_and_owner(
    client: FirestoreClient, namespace_id: str, owner_email: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return the existing namespace and owner docs; exit if either is missing."""
    namespace = client.get_document(NAMESPACE_COLLECTION, namespace_id)
    if not namespace:
        sys.exit(f"✗ Namespace {namespace_id} does not exist.")
    owner = client.find_document(USERS_COLLECTION, {"email": owner_email})
    if not owner or owner.get("namespace_id") != namespace_id:
        sys.exit(f"✗ No user {owner_email} in namespace {namespace_id}.")
    print(f"  ✓ Namespace {namespace.get('company_name') or namespace_id} "
          f"(tz={namespace.get('timezone') or DEFAULT_TIMEZONE})")
    print(f"  ✓ Owner {owner_email} ({owner.get('role')}) → id={owner['id']}")
    return namespace, owner


def create_settings(client: FirestoreClient, namespace_id: str) -> dict[str, Any]:
    settings = {
        "namespace_id": namespace_id,
        "shift_number": 3,
        "time_to_escalate": 1800,
        **SHIFTS,
    }
    client.create_subdocument(
        NAMESPACE_SETTINGS_COLLECTION,
        namespace_id,
        SETTINGS_SUBCOLLECTION,
        settings,
        document_id=namespace_id,
    )
    for key, shift in SHIFTS.items():
        print(
            f"  ✓ {key}: {shift['start_time']}-{shift['end_time']} "
            f"(break {shift['break_start_time']}-{shift['break_end_time']})"
        )
    return settings


def _create_user(
    client: FirestoreClient,
    namespace_id: str,
    first_name: str,
    last_name: str,
    role: Role,
    password: str,
    email: Optional[str] = None,
) -> dict[str, Any]:
    user_id = str(uuid.uuid4())
    doc = {
        "id": user_id,
        "first_name": first_name,
        "last_name": last_name,
        "role": role.value,
        "email": email,
        "password": hash_password(password),
        "security_code": generate_security_code(client, namespace_id),
        "namespace_id": namespace_id,
        "online": True,
    }
    client.create_document(USERS_COLLECTION, doc, document_id=user_id)
    return doc


def create_users(
    client: FirestoreClient, namespace_id: str, owner: dict[str, Any]
) -> dict[Role, list[dict[str, Any]]]:
    by_role: dict[Role, list[dict[str, Any]]] = {Role.OWNER: [owner]}
    for first_name, last_name, role in STAFF:
        user = _create_user(client, namespace_id, first_name, last_name, role, STAFF_PASSWORD)
        by_role.setdefault(role, []).append(user)
        print(f"  ✓ {first_name} {last_name} ({role.value}) → code={user['security_code']}")
    return by_role


def create_structure(
    client: FirestoreClient, namespace_id: str, users: dict[Role, list[dict[str, Any]]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    uaps: list[dict[str, Any]] = []
    lines: list[dict[str, Any]] = []
    stations: list[dict[str, Any]] = []
    role_ids = {
        field: [u["id"] for u in users.get(role, [])] for field, role in UAP_ROLE_FIELDS.items()
    }

    line_number = 0
    for uap_name, uap_description, line_defs in STRUCTURE:
        uap = {
            "id": str(uuid.uuid4()),
            "name": uap_name,
            "description": uap_description,
            "namespace_id": namespace_id,
            **role_ids,
        }
        client.create_document(UAP_COLLECTION, uap, document_id=uap["id"])
        uaps.append(uap)
        print(f"  ✓ {uap_name}")

        for line_name, line_description in line_defs:
            line = {
                "id": str(uuid.uuid4()),
                "name": line_name,
                "description": line_description,
                "uap_id": uap["id"],
                "namespace_id": namespace_id,
            }
            client.create_document(PRODUCTION_LINE_COLLECTION, line, document_id=line["id"])
            lines.append(line)
            line_number += 1

            template = WORKSTATION_TEMPLATES[(line_number - 1) % len(WORKSTATION_TEMPLATES)]
            for position, (name, ws_type, description) in enumerate(template, start=1):
                station = {
                    "id": str(uuid.uuid4()),
                    "name": f"{name} WS-{line_number}{position:02d}",
                    "description": description,
                    "production_line_id": line["id"],
                    "type": ws_type.value,
                    "namespace_id": namespace_id,
                }
                client.create_document(WORKSTATION_COLLECTION, station, document_id=station["id"])
                stations.append({**station, "uap_id": uap["id"]})
            print(f"      ✓ {line_name} ({len(template)} workstations)")
    return uaps, lines, stations


def _pick_location(
    rng: random.Random,
    uaps: list[dict[str, Any]],
    lines: list[dict[str, Any]],
    stations: list[dict[str, Any]],
) -> tuple[ProductionScope, Optional[str], Optional[str], Optional[str]]:
    scope = rng.choices(list(SCOPE_WEIGHTS), weights=list(SCOPE_WEIGHTS.values()))[0]
    if scope == ProductionScope.WORK_STATION:
        station = rng.choice(stations)
        return scope, station["uap_id"], station["production_line_id"], station["id"]
    if scope == ProductionScope.PRODUCTION_LINE:
        line = rng.choice(lines)
        return scope, line["uap_id"], line["id"], None
    if scope == ProductionScope.UAP:
        return scope, rng.choice(uaps)["id"], None, None
    return scope, None, None, None


def _build_issue(
    rng: random.Random,
    namespace_id: str,
    created_local: datetime,
    settings: dict[str, Any],
    users: dict[Role, list[dict[str, Any]]],
    uaps: list[dict[str, Any]],
    lines: list[dict[str, Any]],
    stations: list[dict[str, Any]],
) -> dict[str, Any]:
    dt_type = rng.choices(list(TYPE_WEIGHTS), weights=list(TYPE_WEIGHTS.values()))[0]
    department: Optional[str] = None
    if dt_type == DownTimeType.SETUP_CHANGEOVER:
        process = rng.choice([Process.PRODUCTION, Process.MAINTENANCE])
        department = process.value
    else:
        process = DOWNTIME_TYPE_PROCESS[dt_type]

    scope, uap_id, line_id, station_id = _pick_location(rng, uaps, lines, stations)
    agents = users[AGENT_ROLE[process]]
    creator = rng.choice(users[Role.PRODUCTION_AGENT])
    closer = rng.choice(users[Role.PRODUCTION_AGENT] + users[Role.PRODUCTION_SUPERVISOR])

    issue: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "namespace_id": namespace_id,
        "created_at": created_local.isoformat(),
        "down_time_scope": scope.value,
        "uap_id": uap_id,
        "production_line_id": line_id,
        "workstation_id": station_id,
        "down_time_type": dt_type.value,
        "department": department,
        "process": process.value,
        "created_by": creator["id"],
        "shift": _resolve_shift(settings, created_local),
        "acknowledged_at": None,
        "acknowledged_by": None,
        "resolved_at": None,
        "resolved_by": None,
        "status": DownTimeStatus.CLOSED.value,
        "escalation_task_id": None,
    }

    if dt_type in CLOSE_ONLY_DOWNTIME_TYPES:
        # pending -> closed directly: production confirms it has resumed.
        closed_at = created_local + timedelta(minutes=rng.randint(5, 90))
    else:
        acknowledged_at = created_local + timedelta(minutes=rng.randint(1, 25))
        # Mostly short stops, with a long tail of heavy breakdowns.
        repair_minutes = min(int(rng.expovariate(1 / 55)) + 8, 8 * 60)
        resolved_at = acknowledged_at + timedelta(minutes=repair_minutes)
        closed_at = resolved_at + timedelta(minutes=rng.randint(3, 45))
        responder = rng.choice(agents)
        issue.update(
            {
                "acknowledged_at": acknowledged_at.isoformat(),
                "acknowledged_by": responder["id"],
                "resolved_at": resolved_at.isoformat(),
                # Another agent of the same process sometimes finishes the repair.
                "resolved_by": rng.choice([responder, responder, rng.choice(agents)])["id"],
            }
        )

    issue["closed_at"] = closed_at.isoformat()
    issue["closed_by"] = closer["id"]
    issue["updated_at"] = closed_at.isoformat()
    return issue


def create_issues(
    client: FirestoreClient,
    rng: random.Random,
    namespace_id: str,
    tz: ZoneInfo,
    today: date,
    days: int,
    settings: dict[str, Any],
    users: dict[Role, list[dict[str, Any]]],
    uaps: list[dict[str, Any]],
    lines: list[dict[str, Any]],
    stations: list[dict[str, Any]],
) -> int:
    total = 0
    for offset in range(-days, days + 1):
        day = today + timedelta(days=offset)
        count = rng.randint(3, 9)
        for _ in range(count):
            seconds = rng.randint(0, 24 * 3600 - 1)
            created_local = datetime.combine(day, time.min, tzinfo=tz) + timedelta(
                seconds=seconds
            )
            issue = _build_issue(
                rng, namespace_id, created_local, settings, users, uaps, lines, stations
            )
            client.create_subdocument(
                DOWN_TIME_COLLECTION,
                namespace_id,
                ISSUES_SUBCOLLECTION,
                issue,
                document_id=issue["id"],
            )
        total += count
        print(f"  ✓ {day.isoformat()}: {count} tickets")
    return total


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--namespace-id", default=DEFAULT_NAMESPACE_ID)
    parser.add_argument("--owner-email", default=DEFAULT_OWNER_EMAIL)
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_DAYS,
        help="Days of tickets before AND after today (default: 30).",
    )
    parser.add_argument("--seed", type=int, default=None, help="Random seed (reproducible data).")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    rng = random.Random(args.seed)
    client = get_firestore_client()

    print("\n1. Namespace and owner")
    namespace, owner = check_namespace_and_owner(client, args.namespace_id, args.owner_email)
    tz = ZoneInfo(namespace.get("timezone") or DEFAULT_TIMEZONE)
    today = datetime.now(tz).date()

    print("\n2. Settings (3 shifts per day)")
    settings = create_settings(client, args.namespace_id)

    print("\n3. Users")
    users = create_users(client, args.namespace_id, owner)

    print("\n4. UAPs / production lines / workstations")
    uaps, lines, stations = create_structure(client, args.namespace_id, users)

    print(f"\n5. Downtime tickets ({today - timedelta(days=args.days)} → "
          f"{today + timedelta(days=args.days)})")
    total = create_issues(
        client, rng, args.namespace_id, tz, today, args.days, settings, users, uaps, lines, stations
    )

    print("\n" + "=" * 60)
    print(f"Namespace {args.namespace_id} populated (added):")
    print(f"  users={len(STAFF)}  uaps={len(uaps)}  lines={len(lines)}  "
          f"workstations={len(stations)}  tickets={total}")
    print(f"  Created users' password: {STAFF_PASSWORD} (agents pair with their security code).")


if __name__ == "__main__":
    main()
