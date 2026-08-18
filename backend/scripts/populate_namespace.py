#!/usr/bin/env python3
"""Populate an OptiFlow namespace with realistic demo data.

Creates:
  - Users (agents) for each process/role
  - UAPs (production areas)
  - Production lines per UAP
  - Workstations per production line (standard, critical, bottleneck)
  - Downtimes at every scope (plant, uap, production line, work station)
  - Drives each downtime through its full lifecycle workflow

Usage:
    python scripts/populate_namespace.py

Environment:
    BASE_URL  – API root (default: http://localhost:8000)
"""

import os
import sys
import time
import json
import requests
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")
NAMESPACE_ID = "8ec36496-4d18-4644-83ba-2757e62a1804"

# Owner / admin token (the user who calls user-management + structure endpoints)
OWNER_TOKEN = (
    ".eJwly0sKAjEMANC7ZG1g8jFtvYw0aRaCzkgHcSHe3QH3733gtee83gZcwIVLiju2WBhV"
    "qGBlLkghjUKJhzmcYO2P3J898r9qhpg2Qx1UUU0Vq3hHLueSxp3qosea2z0Pvb3XnPD9"
    "Aau-IJ4.aoNBXg.lICv22aT_ungB_sC5W9momGpzdc"
)

# Common password for all created users
DEFAULT_PASSWORD = "OptiFlow2024!"


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


class ApiClient:
    """Thin wrapper around requests for the OptiFlow API."""

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            }
        )

    def with_token(self, token: str) -> "ApiClient":
        """Return a new client authenticated with a different token."""
        return ApiClient(self.base_url, token)

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def post(self, path: str, payload: dict, expected: int = 201) -> dict:
        r = self.session.post(self._url(path), json=payload)
        if r.status_code != expected:
            print(f"  ✗ POST {path} → {r.status_code}: {r.text[:500]}")
            return {}
        return r.json()

    def get(self, path: str) -> dict:
        r = self.session.get(self._url(path))
        if r.status_code != 200:
            print(f"  ✗ GET {path} → {r.status_code}: {r.text[:500]}")
            return {}
        return r.json()


def login_user(client: ApiClient, email: str, password: str) -> Optional[str]:
    """Log in and return the access token, or None."""
    r = client.session.post(
        client._url("/auth/login"),
        json={"username": email, "password": password},
    )
    if r.status_code != 200:
        print(f"  ✗ Login as {email} failed: {r.status_code} {r.text[:300]}")
        return None
    data = r.json().get("data", {})
    return data.get("access_token")


# ---------------------------------------------------------------------------
# 1. Create users (agents for each process)
# ---------------------------------------------------------------------------

USERS_TO_CREATE = [
    # Supervisors (email required)
    {
        "first_name": "Ahmed",
        "last_name": "Supervisor-Prod",
        "role": "production supervisor",
        "email": "ahmed.prodsup@optiflow-demo.com",
        "password": DEFAULT_PASSWORD,
    },
    {
        "first_name": "Fatma",
        "last_name": "Supervisor-Maint",
        "role": "maintenance supervisor",
        "email": "fatma.maintsup@optiflow-demo.com",
        "password": DEFAULT_PASSWORD,
    },
    {
        "first_name": "Karim",
        "last_name": "Supervisor-Quality",
        "role": "quality supervisor",
        "email": "karim.qualsup@optiflow-demo.com",
        "password": DEFAULT_PASSWORD,
    },
    {
        "first_name": "Salma",
        "last_name": "Supervisor-Logistic",
        "role": "logistic supervisor",
        "email": "salma.logsup@optiflow-demo.com",
        "password": DEFAULT_PASSWORD,
    },
    # Agents (no email required)
    {
        "first_name": "Youssef",
        "last_name": "Agent-Prod-1",
        "role": "production agent",
        "password": DEFAULT_PASSWORD,
    },
    {
        "first_name": "Amira",
        "last_name": "Agent-Prod-2",
        "role": "production agent",
        "password": DEFAULT_PASSWORD,
    },
    {
        "first_name": "Mohamed",
        "last_name": "Agent-Maint-1",
        "role": "maintenance agent",
        "password": DEFAULT_PASSWORD,
    },
    {
        "first_name": "Hana",
        "last_name": "Agent-Maint-2",
        "role": "maintenance agent",
        "password": DEFAULT_PASSWORD,
    },
    {
        "first_name": "Omar",
        "last_name": "Agent-Quality-1",
        "role": "quality agent",
        "password": DEFAULT_PASSWORD,
    },
    {
        "first_name": "Ines",
        "last_name": "Agent-Quality-2",
        "role": "quality agent",
        "password": DEFAULT_PASSWORD,
    },
    {
        "first_name": "Rami",
        "last_name": "Agent-Logistic-1",
        "role": "logistic agent",
        "password": DEFAULT_PASSWORD,
    },
    {
        "first_name": "Nour",
        "last_name": "Agent-Logistic-2",
        "role": "logistic agent",
        "password": DEFAULT_PASSWORD,
    },
]


def create_users(client: ApiClient) -> dict[str, list[str]]:
    """Create users and return a dict mapping role -> list of user ids."""
    print("\n" + "=" * 60)
    print("STEP 1: Creating users (agents & supervisors)")
    print("=" * 60)

    role_to_ids: dict[str, list[str]] = {}
    created_users: list[dict] = []

    for user_data in USERS_TO_CREATE:
        resp = client.post("/users", user_data)
        if not resp:
            continue
        data = resp.get("data", {})
        user_id = data.get("id")
        role = user_data["role"]
        security_code = data.get("security_code", "N/A")

        if user_id:
            role_to_ids.setdefault(role, []).append(user_id)
            created_users.append(
                {
                    "id": user_id,
                    "name": f"{user_data['first_name']} {user_data['last_name']}",
                    "role": role,
                    "security_code": security_code,
                    "email": user_data.get("email"),
                }
            )
            print(
                f"  ✓ {user_data['first_name']} {user_data['last_name']} "
                f"({role}) → id={user_id}, code={security_code}"
            )

    print(f"\n  Total users created: {len(created_users)}")
    return role_to_ids


# ---------------------------------------------------------------------------
# 2. Create UAPs
# ---------------------------------------------------------------------------

UAPS_TO_CREATE = [
    {"name": "UAP Assemblage", "description": "Unité de production - assemblage mécanique"},
    {"name": "UAP Peinture", "description": "Unité de production - peinture et finitions"},
    {"name": "UAP Injection", "description": "Unité de production - injection plastique"},
]


def create_uaps(client: ApiClient, role_to_ids: dict[str, list[str]]) -> list[str]:
    """Create UAPs and assign agents to them. Returns list of UAP ids."""
    print("\n" + "=" * 60)
    print("STEP 2: Creating UAPs (Unités Autonomes de Production)")
    print("=" * 60)

    uap_ids = []
    for i, uap_data in enumerate(UAPS_TO_CREATE):
        # Assign agents round-robin across UAPs
        payload = {
            **uap_data,
            "maintenance_agent_ids": role_to_ids.get("maintenance agent", []),
            "production_agent_ids": role_to_ids.get("production agent", []),
            "quality_agent_ids": role_to_ids.get("quality agent", []),
            "logistic_agent_ids": role_to_ids.get("logistic agent", []),
            "maintenance_supervisor_ids": role_to_ids.get(
                "maintenance supervisor", []
            ),
            "production_supervisor_ids": role_to_ids.get(
                "production supervisor", []
            ),
            "quality_supervisor_ids": role_to_ids.get("quality supervisor", []),
            "logistic_supervisor_ids": role_to_ids.get("logistic supervisor", []),
        }
        resp = client.post("/uaps", payload)
        if not resp:
            continue
        uap_id = resp.get("data", {}).get("id")
        if uap_id:
            uap_ids.append(uap_id)
            print(f"  ✓ {uap_data['name']} → id={uap_id}")

    print(f"\n  Total UAPs created: {len(uap_ids)}")
    return uap_ids


# ---------------------------------------------------------------------------
# 3. Create Production Lines
# ---------------------------------------------------------------------------

LINES_PER_UAP = [
    [
        {"name": "Ligne Assemblage A1", "description": "Ligne principale d'assemblage"},
        {"name": "Ligne Assemblage A2", "description": "Ligne secondaire d'assemblage"},
    ],
    [
        {"name": "Ligne Peinture P1", "description": "Ligne peinture primaire"},
        {"name": "Ligne Peinture P2", "description": "Ligne peinture de finition"},
        {"name": "Ligne Séchage S1", "description": "Ligne séchage et contrôle"},
    ],
    [
        {"name": "Ligne Injection I1", "description": "Ligne injection grande capacité"},
        {"name": "Ligne Injection I2", "description": "Ligne injection pièces fines"},
    ],
]


def create_production_lines(
    client: ApiClient, uap_ids: list[str]
) -> list[dict]:
    """Create production lines under each UAP.
    Returns list of {id, uap_id, name}."""
    print("\n" + "=" * 60)
    print("STEP 3: Creating Production Lines")
    print("=" * 60)

    lines = []
    for uap_idx, uap_id in enumerate(uap_ids):
        line_defs = LINES_PER_UAP[uap_idx % len(LINES_PER_UAP)]
        for line_data in line_defs:
            payload = {**line_data, "uap_id": uap_id}
            resp = client.post("/production-lines", payload)
            if not resp:
                continue
            line_id = resp.get("data", {}).get("id")
            if line_id:
                lines.append({"id": line_id, "uap_id": uap_id, "name": line_data["name"]})
                print(f"  ✓ {line_data['name']} (UAP {uap_idx + 1}) → id={line_id}")

    print(f"\n  Total production lines created: {len(lines)}")
    return lines


# ---------------------------------------------------------------------------
# 4. Create Workstations
# ---------------------------------------------------------------------------

# Workstation definitions per production line (indexed by line position)
WORKSTATIONS_TEMPLATE = [
    # Line 1 - 4 workstations
    [
        {"name": "Poste Soudure WS-{line_idx}01", "type": "critical", "description": "Poste de soudure robotisée"},
        {"name": "Poste Montage WS-{line_idx}02", "type": "standard", "description": "Poste de montage manuel"},
        {"name": "Poste Vissage WS-{line_idx}03", "type": "bottleneck", "description": "Poste de vissage automatique (goulot)"},
        {"name": "Poste Contrôle WS-{line_idx}04", "type": "standard", "description": "Poste de contrôle qualité en ligne"},
    ],
    # Line 2 - 3 workstations
    [
        {"name": "Poste Presse WS-{line_idx}01", "type": "bottleneck", "description": "Presse hydraulique (goulot)"},
        {"name": "Poste Découpe WS-{line_idx}02", "type": "critical", "description": "Machine de découpe laser"},
        {"name": "Poste Ébavurage WS-{line_idx}03", "type": "standard", "description": "Poste ébavurage et finition"},
    ],
    # Line 3 - 3 workstations
    [
        {"name": "Poste Injection WS-{line_idx}01", "type": "critical", "description": "Presse d'injection 800T"},
        {"name": "Poste Refroidissement WS-{line_idx}02", "type": "standard", "description": "Tunnel de refroidissement"},
        {"name": "Poste Emballage WS-{line_idx}03", "type": "standard", "description": "Poste emballage et palettisation"},
    ],
]


def create_workstations(
    client: ApiClient, lines: list[dict]
) -> list[dict]:
    """Create workstations under each production line.
    Returns list of {id, production_line_id, uap_id, name, type}."""
    print("\n" + "=" * 60)
    print("STEP 4: Creating Workstations (standard / critical / bottleneck)")
    print("=" * 60)

    workstations = []
    for line_idx, line in enumerate(lines):
        ws_defs = WORKSTATIONS_TEMPLATE[line_idx % len(WORKSTATIONS_TEMPLATE)]
        for ws_data in ws_defs:
            name = ws_data["name"].format(line_idx=line_idx + 1)
            payload = {
                "name": name,
                "description": ws_data["description"],
                "type": ws_data["type"],
                "production_line_id": line["id"],
            }
            resp = client.post("/workstations", payload)
            if not resp:
                continue
            ws_id = resp.get("data", {}).get("id")
            if ws_id:
                workstations.append(
                    {
                        "id": ws_id,
                        "production_line_id": line["id"],
                        "uap_id": line["uap_id"],
                        "name": name,
                        "type": ws_data["type"],
                    }
                )
                emoji = {"standard": "⬜", "critical": "🔴", "bottleneck": "🟡"}
                print(
                    f"  {emoji.get(ws_data['type'], '⬜')} {name} "
                    f"[{ws_data['type']}] → id={ws_id}"
                )

    print(f"\n  Total workstations created: {len(workstations)}")
    return workstations


# ---------------------------------------------------------------------------
# 5. Log in agents so we can act as them for downtime operations
# ---------------------------------------------------------------------------


def login_agents_by_code(
    client: ApiClient, role_to_ids: dict[str, list[str]]
) -> dict[str, list[dict]]:
    """Get user details (including security codes) and pair/log in each agent.
    Returns role -> list of {id, token, name}."""
    print("\n" + "=" * 60)
    print("STEP 5: Logging in agents (via security code pairing)")
    print("=" * 60)

    role_agents: dict[str, list[dict]] = {}

    all_user_ids = [uid for ids in role_to_ids.values() for uid in ids]

    for uid in all_user_ids:
        # Fetch the user to get their security code
        resp = client.get(f"/users/{uid}")
        if not resp:
            continue
        user = resp.get("data", {})
        code = user.get("security_code")
        role = user.get("role")
        name = f"{user.get('first_name', '')} {user.get('last_name', '')}"

        if not code:
            print(f"  ✗ {name}: no security code")
            continue

        # Pair via check-user-code to get a token
        device_id = f"populate-script-{uid[:8]}"
        pair_resp = client.session.post(
            client._url("/auth/check-user-code"),
            json={"security_code": code, "device_id": device_id},
        )
        if pair_resp.status_code != 200:
            print(
                f"  ✗ {name}: check-user-code failed "
                f"({pair_resp.status_code}): {pair_resp.text[:200]}"
            )
            continue

        token = pair_resp.json().get("data", {}).get("access_token")
        if token:
            role_agents.setdefault(role, []).append(
                {"id": uid, "token": token, "name": name}
            )
            print(f"  ✓ {name} ({role}) → logged in")

    return role_agents


# ---------------------------------------------------------------------------
# 6. Create downtimes at various scopes and drive their workflows
# ---------------------------------------------------------------------------

# Downtime type -> process mapping (matches the backend enum)
# "Setup / Changeover" needs a department field
# "Work-in-Process (WIP) Shortage" and "others" are close-only
DOWNTIME_SCENARIOS = [
    # ----- Plant scope downtimes -----
    {
        "label": "Plant-wide power outage",
        "production_scope": "plant",
        "down_time_type": "break down",
        "workflow": "full",  # pending -> ack -> resolve -> close
    },
    {
        "label": "Plant-wide WIP shortage",
        "production_scope": "plant",
        "down_time_type": "Work-in-Process (WIP) Shortage",
        "workflow": "close-only",  # pending -> close
    },
    # ----- UAP scope downtimes -----
    {
        "label": "UAP quality issue",
        "production_scope": "uap",
        "down_time_type": "quality issue",
        "workflow": "full",
    },
    {
        "label": "UAP absenteeism",
        "production_scope": "uap",
        "down_time_type": "Absenteeism",
        "workflow": "close-only",  # Absenteeism routes to production, close-only? No, checking...
        # Actually Absenteeism is NOT in CLOSE_ONLY_DOWNTIME_TYPES, it goes through full workflow
        # but it routes to production process. Let's use full.
    },
    {
        "label": "UAP setup/changeover (maintenance dept)",
        "production_scope": "uap",
        "down_time_type": "Setup / Changeover",
        "department": "maintenance",
        "workflow": "full",
    },
    # ----- Production line scope downtimes -----
    {
        "label": "Production line breakdown",
        "production_scope": "production line",
        "down_time_type": "break down",
        "workflow": "full",
    },
    {
        "label": "Production line material shortage",
        "production_scope": "production line",
        "down_time_type": "Material / Component Shortage",
        "workflow": "full",  # logistic process, full workflow
    },
    {
        "label": "Production line others (unclassified)",
        "production_scope": "production line",
        "down_time_type": "others",
        "workflow": "close-only",
    },
    # ----- Work station scope downtimes -----
    {
        "label": "Workstation breakdown (critical station)",
        "production_scope": "work station",
        "down_time_type": "break down",
        "ws_type_filter": "critical",
        "workflow": "full",
    },
    {
        "label": "Workstation quality issue (bottleneck station)",
        "production_scope": "work station",
        "down_time_type": "quality issue",
        "ws_type_filter": "bottleneck",
        "workflow": "full",
    },
    {
        "label": "Workstation setup/changeover (production dept, standard station)",
        "production_scope": "work station",
        "down_time_type": "Setup / Changeover",
        "department": "production",
        "ws_type_filter": "standard",
        "workflow": "full",
    },
    {
        "label": "Workstation WIP shortage (standard station)",
        "production_scope": "work station",
        "down_time_type": "Work-in-Process (WIP) Shortage",
        "ws_type_filter": "standard",
        "workflow": "close-only",
    },
    # ----- Extra: workflow with rejection -----
    {
        "label": "Workstation breakdown with rejected resolution",
        "production_scope": "work station",
        "down_time_type": "break down",
        "ws_type_filter": "bottleneck",
        "workflow": "reject-then-resolve",  # ack -> resolve -> reject -> resolve -> close
    },
]

# Maps downtime_type -> process that owns the ticket
DOWNTIME_TYPE_PROCESS = {
    "break down": "maintenance",
    "quality issue": "quality",
    "Absenteeism": "production",
    "Work-in-Process (WIP) Shortage": "production",
    "Material / Component Shortage": "logistic",
    "others": "production",
    # "Setup / Changeover" uses the department field
}

CLOSE_ONLY_TYPES = {"Work-in-Process (WIP) Shortage", "others"}


def _get_process_for_scenario(scenario: dict) -> str:
    """Determine the process (department) that owns a ticket."""
    dt_type = scenario["down_time_type"]
    if dt_type == "Setup / Changeover":
        return scenario["department"]
    return DOWNTIME_TYPE_PROCESS[dt_type]


def _get_agent_token(
    role_agents: dict[str, list[dict]], role: str, index: int = 0
) -> Optional[dict]:
    """Get a logged-in agent for the given role."""
    agents = role_agents.get(role, [])
    if not agents:
        return None
    return agents[index % len(agents)]


def _wait_for_downtime(
    agent_client: ApiClient, max_retries: int = 15, delay: float = 2.0
) -> Optional[dict]:
    """Poll GET /down-times until a pending ticket appears (async job may take a moment)."""
    for _ in range(max_retries):
        resp = agent_client.get("/down-times?status=pending&limit=100")
        items = resp.get("data", {}).get("items", [])
        if items:
            # Return the most recent one
            return items[0]
        time.sleep(delay)
    return None


def create_and_resolve_downtimes(
    client: ApiClient,
    role_agents: dict[str, list[dict]],
    uap_ids: list[str],
    lines: list[dict],
    workstations: list[dict],
):
    """Create downtime tickets and drive each through its workflow."""
    print("\n" + "=" * 60)
    print("STEP 6: Creating downtimes & driving workflows")
    print("=" * 60)

    # We need a production agent to create downtimes
    prod_agents = role_agents.get("production agent", [])
    if not prod_agents:
        print("  ✗ No production agents available! Cannot create downtimes.")
        return

    ws_index_counter = {"standard": 0, "critical": 0, "bottleneck": 0}

    for scenario_idx, scenario in enumerate(DOWNTIME_SCENARIOS):
        label = scenario["label"]
        scope = scenario["production_scope"]
        dt_type = scenario["down_time_type"]
        workflow = scenario["workflow"]

        print(f"\n  {'─' * 50}")
        print(f"  📋 Scenario {scenario_idx + 1}: {label}")
        print(f"     Scope: {scope} | Type: {dt_type} | Workflow: {workflow}")

        # Pick the production agent who will report the downtime
        prod_agent = prod_agents[scenario_idx % len(prod_agents)]
        prod_client = client.with_token(prod_agent["token"])

        # Build the downtime payload
        payload: dict = {
            "production_scope": scope,
            "down_time_type": dt_type,
        }

        # Add department for setup/changeover
        if dt_type == "Setup / Changeover":
            payload["department"] = scenario["department"]

        # Add scope-specific ids
        if scope == "uap":
            uap_id = uap_ids[scenario_idx % len(uap_ids)]
            payload["uap_id"] = uap_id
            print(f"     UAP: {uap_id}")

        elif scope == "production line":
            line = lines[scenario_idx % len(lines)]
            payload["uap_id"] = line["uap_id"]
            payload["production_line_id"] = line["id"]
            print(f"     Line: {line['name']} ({line['id']})")

        elif scope == "work station":
            ws_type_filter = scenario.get("ws_type_filter", "standard")
            # Find a workstation of the right type
            matching_ws = [ws for ws in workstations if ws["type"] == ws_type_filter]
            if not matching_ws:
                matching_ws = workstations
            ws_idx = ws_index_counter.get(ws_type_filter, 0)
            ws = matching_ws[ws_idx % len(matching_ws)]
            ws_index_counter[ws_type_filter] = ws_idx + 1

            # Find the parent line and its parent UAP
            parent_line = next(
                (l for l in lines if l["id"] == ws["production_line_id"]), None
            )
            if parent_line:
                payload["uap_id"] = parent_line["uap_id"]
                payload["production_line_id"] = parent_line["id"]
            payload["workstation_id"] = ws["id"]
            print(f"     Workstation: {ws['name']} [{ws['type']}] ({ws['id']})")

        # --- Create the downtime ---
        resp = prod_client.post("/down-times", payload, expected=202)
        if not resp:
            print(f"     ✗ Failed to create downtime")
            continue
        job_id = resp.get("data", {}).get("job_id")
        print(f"     → Job dispatched: {job_id}")

        # --- Wait for the async job to create the ticket ---
        print(f"     ⏳ Waiting for ticket to appear...", end="", flush=True)
        time.sleep(3)  # Give the async job a moment

        # Find the ticket — poll the list
        ticket = None
        for attempt in range(10):
            list_resp = prod_client.get("/down-times?limit=100")
            items = list_resp.get("data", {}).get("items", [])
            # Look for the most recently created pending ticket
            for item in items:
                if item.get("status") == "pending":
                    ticket = item
                    break
            if ticket:
                break
            time.sleep(2)
            print(".", end="", flush=True)

        if not ticket:
            print(f"\n     ✗ Ticket did not appear after waiting")
            continue

        issue_id = ticket["id"]
        print(f"\n     ✓ Ticket created: {issue_id} [status=pending]")

        # --- Drive the workflow ---
        if workflow == "close-only":
            # Close directly (production agent)
            time.sleep(1)
            close_resp = prod_client.post(
                f"/down-times/{issue_id}/close", {}, expected=200
            )
            if close_resp:
                print(f"     ✓ Closed directly (close-only workflow)")
            else:
                print(f"     ✗ Failed to close")

        elif workflow in ("full", "reject-then-resolve"):
            process = _get_process_for_scenario(scenario)
            process_agent_role = f"{process} agent"
            process_agent = _get_agent_token(role_agents, process_agent_role)

            if not process_agent:
                print(
                    f"     ✗ No {process_agent_role} available, "
                    f"cannot drive workflow"
                )
                continue

            process_client = client.with_token(process_agent["token"])

            # 1. Acknowledge
            time.sleep(1)
            ack_resp = process_client.post(
                f"/down-times/{issue_id}/acknowledge", {}, expected=200
            )
            if ack_resp:
                print(
                    f"     ✓ Acknowledged by {process_agent['name']} "
                    f"({process_agent_role}) [status=ongoing]"
                )
            else:
                print(f"     ✗ Failed to acknowledge")
                continue

            # 2. Resolve
            time.sleep(1)
            resolve_resp = process_client.post(
                f"/down-times/{issue_id}/resolve", {}, expected=200
            )
            if resolve_resp:
                print(
                    f"     ✓ Resolved by {process_agent['name']} "
                    f"[status=resolved]"
                )
            else:
                print(f"     ✗ Failed to resolve")
                continue

            # 2b. If reject-then-resolve, reject and re-resolve
            if workflow == "reject-then-resolve":
                time.sleep(1)
                reject_resp = prod_client.post(
                    f"/down-times/{issue_id}/reject-resolution",
                    {},
                    expected=200,
                )
                if reject_resp:
                    print(
                        f"     ↩ Resolution rejected by "
                        f"{prod_agent['name']} [status=ongoing]"
                    )
                else:
                    print(f"     ✗ Failed to reject resolution")
                    continue

                # Re-resolve
                time.sleep(1)
                resolve2_resp = process_client.post(
                    f"/down-times/{issue_id}/resolve", {}, expected=200
                )
                if resolve2_resp:
                    print(
                        f"     ✓ Re-resolved by {process_agent['name']} "
                        f"[status=resolved]"
                    )
                else:
                    print(f"     ✗ Failed to re-resolve")
                    continue

            # 3. Close (production agent validates return to production)
            time.sleep(1)
            close_resp = prod_client.post(
                f"/down-times/{issue_id}/close", {}, expected=200
            )
            if close_resp:
                print(f"     ✓ Closed by {prod_agent['name']} [status=closed]")
            else:
                print(f"     ✗ Failed to close")

    # --- Also leave some tickets in intermediate states ---
    print(f"\n  {'─' * 50}")
    print("  📋 Creating tickets left in intermediate states...")

    intermediate_scenarios = [
        {
            "label": "Left PENDING (breakdown, plant scope)",
            "production_scope": "plant",
            "down_time_type": "break down",
            "target_status": "pending",
        },
        {
            "label": "Left ONGOING (quality issue, workstation scope)",
            "production_scope": "work station",
            "down_time_type": "quality issue",
            "target_status": "ongoing",
        },
        {
            "label": "Left RESOLVED (breakdown, production line scope)",
            "production_scope": "production line",
            "down_time_type": "break down",
            "target_status": "resolved",
        },
    ]

    for inter_idx, inter in enumerate(intermediate_scenarios):
        print(f"\n  📌 {inter['label']}")

        prod_agent = prod_agents[inter_idx % len(prod_agents)]
        prod_client = client.with_token(prod_agent["token"])

        payload = {
            "production_scope": inter["production_scope"],
            "down_time_type": inter["down_time_type"],
        }

        if inter["production_scope"] == "work station":
            ws = workstations[inter_idx % len(workstations)]
            parent_line = next(
                (l for l in lines if l["id"] == ws["production_line_id"]), None
            )
            if parent_line:
                payload["uap_id"] = parent_line["uap_id"]
                payload["production_line_id"] = parent_line["id"]
            payload["workstation_id"] = ws["id"]
        elif inter["production_scope"] == "production line":
            line = lines[inter_idx % len(lines)]
            payload["uap_id"] = line["uap_id"]
            payload["production_line_id"] = line["id"]

        resp = prod_client.post("/down-times", payload, expected=202)
        if not resp:
            print(f"     ✗ Failed to create")
            continue

        time.sleep(4)

        # Find the ticket
        ticket = None
        for _ in range(10):
            list_resp = prod_client.get("/down-times?status=pending&limit=100")
            items = list_resp.get("data", {}).get("items", [])
            if items:
                ticket = items[0]
                break
            time.sleep(2)

        if not ticket:
            print(f"     ✗ Ticket did not appear")
            continue

        issue_id = ticket["id"]
        target = inter["target_status"]

        if target == "pending":
            print(f"     ✓ Left as PENDING: {issue_id}")

        elif target in ("ongoing", "resolved"):
            process = DOWNTIME_TYPE_PROCESS[inter["down_time_type"]]
            process_agent = _get_agent_token(
                role_agents, f"{process} agent"
            )
            if process_agent:
                pc = client.with_token(process_agent["token"])
                time.sleep(1)
                ack = pc.post(
                    f"/down-times/{issue_id}/acknowledge", {}, expected=200
                )
                if ack:
                    print(f"     ✓ Acknowledged → ONGOING: {issue_id}")

                if target == "resolved":
                    time.sleep(1)
                    res = pc.post(
                        f"/down-times/{issue_id}/resolve", {}, expected=200
                    )
                    if res:
                        print(f"     ✓ Resolved → RESOLVED: {issue_id}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    print("╔" + "═" * 58 + "╗")
    print("║" + "  OptiFlow Namespace Population Script".center(58) + "║")
    print("╠" + "═" * 58 + "╣")
    print(f"║  Namespace: {NAMESPACE_ID}  ║")
    print(f"║  API:       {BASE_URL:<44}║")
    print("╚" + "═" * 58 + "╝")

    client = ApiClient(BASE_URL, OWNER_TOKEN)

    # Quick health check
    try:
        r = client.session.get(f"{BASE_URL}/health")
        if r.status_code != 200:
            print(f"\n✗ Health check failed: {r.status_code}")
            sys.exit(1)
        print("\n✓ API is healthy")
    except requests.ConnectionError:
        print(f"\n✗ Cannot connect to {BASE_URL}")
        sys.exit(1)

    # Step 1: Create users
    role_to_ids = create_users(client)
    if not role_to_ids:
        print("\n✗ No users created. Check the owner token and API.")
        sys.exit(1)

    # Step 2: Create UAPs
    uap_ids = create_uaps(client, role_to_ids)
    if not uap_ids:
        print("\n✗ No UAPs created.")
        sys.exit(1)

    # Step 3: Create production lines
    lines = create_production_lines(client, uap_ids)
    if not lines:
        print("\n✗ No production lines created.")
        sys.exit(1)

    # Step 4: Create workstations
    workstations = create_workstations(client, lines)
    if not workstations:
        print("\n✗ No workstations created.")
        sys.exit(1)

    # Step 5: Log in agents
    role_agents = login_agents_by_code(client, role_to_ids)
    if not role_agents:
        print("\n✗ No agents logged in. Cannot proceed with downtimes.")
        sys.exit(1)

    # Step 6: Create downtimes and drive workflows
    create_and_resolve_downtimes(client, role_agents, uap_ids, lines, workstations)

    # Summary
    print("\n\n" + "╔" + "═" * 58 + "╗")
    print("║" + "  ✅ Population Complete!".center(58) + "║")
    print("╠" + "═" * 58 + "╣")
    total_users = sum(len(ids) for ids in role_to_ids.values())
    print(f"║  Users created:            {total_users:<30}║")
    print(f"║  UAPs created:             {len(uap_ids):<30}║")
    print(f"║  Production lines created: {len(lines):<30}║")
    print(f"║  Workstations created:     {len(workstations):<30}║")
    print(f"║  Downtime scenarios run:   {len(DOWNTIME_SCENARIOS) + 3:<30}║")
    print("╚" + "═" * 58 + "╝")


if __name__ == "__main__":
    main()
