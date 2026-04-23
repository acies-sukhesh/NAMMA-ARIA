"""
Persistent SQLite store for PM decisions, outcomes, and learning weights.
All decisions flow through here so ARIA accumulates institutional memory.
"""

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_PATH = Path("data") / "aria_memory.db"


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    c = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init_db() -> None:
    """Create all tables and seed default learning weights."""
    c = _conn()
    with c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS decisions (
                id                     TEXT PRIMARY KEY,
                created_at             TEXT NOT NULL,
                issue_title            TEXT NOT NULL,
                issue_type             TEXT,
                priority               TEXT,
                rationale              TEXT,
                driver_welfare_score   REAL DEFAULT 0.0,
                rider_trust_score      REAL DEFAULT 0.0,
                mission_alignment      REAL DEFAULT 7.0,
                consultation_required  INTEGER DEFAULT 0,
                consultation_flags     TEXT DEFAULT '[]',
                assigned_team          TEXT,
                feature_name           TEXT,
                composite_score        REAL,
                status                 TEXT DEFAULT 'OPEN',
                outcome_score          REAL
            );

            CREATE TABLE IF NOT EXISTS outcomes (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                decision_id          TEXT NOT NULL,
                recorded_at          TEXT NOT NULL,
                driver_impact_delta  REAL DEFAULT 0.0,
                rider_impact_delta   REAL DEFAULT 0.0,
                kpi_improved         INTEGER DEFAULT 0,
                hypothesis_held      INTEGER DEFAULT 0,
                actual_vs_predicted  TEXT,
                notes                TEXT,
                FOREIGN KEY(decision_id) REFERENCES decisions(id)
            );

            CREATE TABLE IF NOT EXISTS learning_weights (
                factor          TEXT PRIMARY KEY,
                weight          REAL NOT NULL DEFAULT 1.0,
                success_count   INTEGER DEFAULT 0,
                failure_count   INTEGER DEFAULT 0,
                last_updated    TEXT
            );

            CREATE TABLE IF NOT EXISTS consultation_log (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                decision_id  TEXT,
                flag_type    TEXT,
                reason       TEXT,
                required     INTEGER DEFAULT 1,
                resolved     INTEGER DEFAULT 0,
                created_at   TEXT
            );
        """)

    # Seed default weights if the table is empty
    now = datetime.utcnow().isoformat()
    defaults = [
        ("driver_earnings_impact", 1.0),
        ("rider_trust_impact",     0.9),
        ("urgency",                0.8),
        ("strategic_importance",   0.7),
        ("effort_inverse",         0.6),
        ("consultation_cost",      0.5),
        ("compliance_risk_inverse", 0.7),
    ]
    with c:
        for factor, weight in defaults:
            c.execute(
                "INSERT OR IGNORE INTO learning_weights (factor, weight, last_updated) VALUES (?,?,?)",
                (factor, weight, now),
            )
    c.close()


# ── Decisions ──────────────────────────────────────────────────────────────────

def save_decision(decision: Dict[str, Any]) -> str:
    """Upsert a PM decision; returns its id."""
    did = decision.get("id") or f"DEC-{uuid.uuid4().hex[:8].upper()}"
    c = _conn()
    with c:
        c.execute(
            """
            INSERT OR REPLACE INTO decisions
              (id, created_at, issue_title, issue_type, priority, rationale,
               driver_welfare_score, rider_trust_score, mission_alignment,
               consultation_required, consultation_flags, assigned_team,
               feature_name, composite_score, status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                did,
                datetime.utcnow().isoformat(),
                decision.get("issue_title", ""),
                decision.get("issue_type", ""),
                decision.get("priority", ""),
                decision.get("rationale", ""),
                decision.get("driver_welfare_score", 0.0),
                decision.get("rider_trust_score", 0.0),
                decision.get("mission_alignment", 7.0),
                1 if decision.get("consultation_required") else 0,
                json.dumps(decision.get("consultation_flags", [])),
                decision.get("assigned_team", ""),
                decision.get("feature_name", ""),
                decision.get("composite_score"),
                decision.get("status", "OPEN"),
            ),
        )
    c.close()
    return did


def get_decisions(limit: int = 20, status: Optional[str] = None) -> List[Dict]:
    c = _conn()
    if status:
        rows = c.execute(
            "SELECT * FROM decisions WHERE status=? ORDER BY created_at DESC LIMIT ?",
            (status, limit),
        ).fetchall()
    else:
        rows = c.execute(
            "SELECT * FROM decisions ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    c.close()
    return [dict(r) for r in rows]


def get_decision(did: str) -> Optional[Dict]:
    c = _conn()
    row = c.execute("SELECT * FROM decisions WHERE id=?", (did,)).fetchone()
    c.close()
    return dict(row) if row else None


def get_similar_past_decisions(issue_title: str, limit: int = 3) -> List[Dict]:
    """Keyword-match closed decisions to find relevant precedents."""
    words = [w.lower() for w in issue_title.split() if len(w) > 4]
    if not words:
        return []
    c = _conn()
    seen_ids = set()
    results = []
    for word in words[:4]:
        rows = c.execute(
            "SELECT * FROM decisions WHERE LOWER(issue_title) LIKE ? AND status='CLOSED' LIMIT ?",
            (f"%{word}%", limit),
        ).fetchall()
        for r in rows:
            d = dict(r)
            if d["id"] not in seen_ids:
                seen_ids.add(d["id"])
                results.append(d)
    c.close()
    return results[:limit]


# ── Outcomes ───────────────────────────────────────────────────────────────────

def record_outcome(decision_id: str, outcome: Dict[str, Any]) -> None:
    """Store an outcome and update decision status + learning weights."""
    c = _conn()
    with c:
        c.execute(
            """
            INSERT INTO outcomes
              (decision_id, recorded_at, driver_impact_delta, rider_impact_delta,
               kpi_improved, hypothesis_held, actual_vs_predicted, notes)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                decision_id,
                datetime.utcnow().isoformat(),
                outcome.get("driver_impact_delta", 0.0),
                outcome.get("rider_impact_delta", 0.0),
                1 if outcome.get("kpi_improved") else 0,
                1 if outcome.get("hypothesis_held") else 0,
                outcome.get("actual_vs_predicted", ""),
                outcome.get("notes", ""),
            ),
        )
        score = _calc_outcome_score(outcome)
        c.execute(
            "UPDATE decisions SET outcome_score=?, status='CLOSED' WHERE id=?",
            (score, decision_id),
        )
        _update_weights(c, outcome, score)
    c.close()


def _calc_outcome_score(outcome: Dict) -> float:
    score = 0.0
    if outcome.get("kpi_improved"):
        score += 0.4
    if outcome.get("hypothesis_held"):
        score += 0.3
    dd = outcome.get("driver_impact_delta", 0.0)
    rd = outcome.get("rider_impact_delta", 0.0)
    score += min(max((dd + rd) / 20.0, -0.3), 0.3)
    return round(min(max(score, 0.0), 1.0), 3)


def _update_weights(c: sqlite3.Connection, outcome: Dict, score: float) -> None:
    now = datetime.utcnow().isoformat()
    success = score >= 0.5
    affected = []
    if outcome.get("driver_impact_delta", 0) != 0:
        affected.append("driver_earnings_impact")
    if outcome.get("rider_impact_delta", 0) != 0:
        affected.append("rider_trust_impact")
    if outcome.get("kpi_improved"):
        affected += ["urgency", "strategic_importance"]
    for factor in affected:
        if success:
            c.execute(
                "UPDATE learning_weights SET success_count=success_count+1, weight=MIN(2.0,weight+0.05), last_updated=? WHERE factor=?",
                (now, factor),
            )
        else:
            c.execute(
                "UPDATE learning_weights SET failure_count=failure_count+1, weight=MAX(0.1,weight-0.03), last_updated=? WHERE factor=?",
                (now, factor),
            )


# ── Learning weights ───────────────────────────────────────────────────────────

def get_learning_weights() -> Dict[str, float]:
    c = _conn()
    rows = c.execute("SELECT factor, weight FROM learning_weights").fetchall()
    c.close()
    return {r["factor"]: r["weight"] for r in rows}


def get_weight_details() -> List[Dict]:
    c = _conn()
    rows = c.execute("SELECT * FROM learning_weights ORDER BY weight DESC").fetchall()
    c.close()
    return [dict(r) for r in rows]


# ── Summary / analytics ───────────────────────────────────────────────────────

def get_outcome_summary() -> Dict[str, Any]:
    c = _conn()
    total    = c.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
    closed   = c.execute("SELECT COUNT(*) FROM decisions WHERE status='CLOSED'").fetchone()[0]
    avg_row  = c.execute("SELECT AVG(outcome_score) FROM decisions WHERE outcome_score IS NOT NULL").fetchone()[0]
    avg      = round(avg_row or 0.0, 3)
    kpi_wins = c.execute("SELECT COUNT(*) FROM outcomes WHERE kpi_improved=1").fetchone()[0]
    hyp_wins = c.execute("SELECT COUNT(*) FROM outcomes WHERE hypothesis_held=1").fetchone()[0]
    c.close()
    return {
        "total_decisions":     total,
        "closed":              closed,
        "open":                total - closed,
        "avg_outcome_score":   avg,
        "kpi_improvements":    kpi_wins,
        "hypothesis_accuracy": hyp_wins,
    }


# Initialise on import
init_db()
