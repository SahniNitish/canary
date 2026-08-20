"""Turn a fired signal into a *specific* heal prompt for `bdata scraper heal`.

The quality bar (CLAUDE.md §6): name the field, the coverage before/after, the expected
shape, and an example URL — and stay under the CLI's hard 1000-character cap. Vague prompts
("the scraper is broken") produce vague heals; over-long prompts get truncated or refused.

This module only *composes* the prompt. It never applies it — approval is the operator's
job (`canary.cli approve`), and `--auto-approve` is never used.
"""

from __future__ import annotations

from typing import Optional

from .models import Signal

# Bright Data CLI hard cap: `bdata scraper heal <id> <prompt>` — prompt max 1000 chars.
HEAL_CHAR_CAP = 1000


def prompt_for(
    signal: Signal,
    *,
    example_url: Optional[str] = None,
    expected_shape: Optional[str] = None,
) -> str:
    """Compose a bounded heal prompt from a signal.

    `expected_shape` describes what the field should look like (e.g. "a non-empty list of
    IKEA article-number strings like 501.637.54"); `example_url` is woven into the prompt
    itself (the CLI's `--url` is only a next-step hint, not sent to the heal call).
    """
    field = signal.field or "an output field"
    parts = [f"The '{field}' field regressed: {signal.detail}."]
    if expected_shape:
        parts.append(f"It should be {expected_shape}.")
    parts.append(
        "Fix the extraction so this field is captured again, and preserve the existing "
        "output schema exactly — same field names and JSON shape, do not rename or drop "
        "any other field."
    )
    if example_url:
        parts.append(f"Verify against: {example_url}")

    prompt = " ".join(parts)
    if len(prompt) > HEAL_CHAR_CAP:
        # Trim the detail sentence first, keep the schema-preservation instruction intact.
        prompt = prompt[: HEAL_CHAR_CAP - 1].rstrip() + "…"
    return prompt


def preview_rows(envelope: object) -> list[dict]:
    """Pull record-shaped rows out of a `bdata scraper heal` JSON envelope.

    The CLI documents `preview_result` on `status: awaiting_approval`. Be defensive
    about wrapping — a missing/empty preview is a validation failure, not a crash.
    """
    if isinstance(envelope, list):
        return [r for r in envelope if isinstance(r, dict)]
    if not isinstance(envelope, dict):
        return []
    preview = envelope.get("preview_result", envelope.get("preview"))
    if isinstance(preview, list):
        return [r for r in preview if isinstance(r, dict)]
    if isinstance(preview, dict):
        for key in ("data", "results", "items", "records"):
            value = preview.get(key)
            if isinstance(value, list):
                return [r for r in value if isinstance(r, dict)]
        return [preview]
    return []


def summarize_preview(envelope: object, field: str | None = "hazard") -> str:
    """One-line evidence: how many preview rows still populate `field`."""
    rows = preview_rows(envelope)
    status = envelope.get("status") if isinstance(envelope, dict) else None
    if not rows:
        return f"status={status or 'unknown'} preview_rows=0"
    if not field:
        return f"status={status or 'unknown'} preview_rows={len(rows)}"
    from .signals import is_blank
    populated = sum(1 for row in rows if not is_blank(row.get(field)))
    return (
        f"status={status or 'unknown'} preview_rows={len(rows)} "
        f"{field}_populated={populated}/{len(rows)}"
    )
