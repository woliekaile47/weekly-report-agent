"""Adapted from AgentOps Studio context_compaction.py, MIT (c) 2026 hyf020908.

Pinned upstream: 2a12d8095ea19f79c54a5395792f4e8045eb3aec.
Reuse the resolved/open/new revision delta. Exact stable IDs replace fuzzy text
matching; only explicit program verification resolves an item, never omission.
See third_party/licenses/agentops-MIT.txt and reuse-manifest.json.
"""


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        value = str(item).strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def update_revision_ledger(previous: dict, current_issues: list[str], verified: list[str]) -> dict:
    current_issues = _unique(current_issues)
    previous_open = previous.get("open_issues", [])
    resolved = [issue for issue in previous_open if issue in verified]
    still_open = [issue for issue in previous_open if issue not in verified]
    new = [issue for issue in current_issues if issue not in previous_open]
    return {
        "resolved_issues": [
            issue
            for issue in _unique(previous.get("resolved_issues", []) + resolved + verified)
            if issue not in current_issues
        ],
        "open_issues": _unique(still_open + current_issues),
        "new_issues": new,
        "iteration": previous.get("iteration", 0) + 1,
    }
