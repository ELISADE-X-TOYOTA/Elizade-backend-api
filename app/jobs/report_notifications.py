"""Inventory every notification the system can send, and where it fires from.

GENERATED, NOT WRITTEN BY HAND. A hand-maintained list of templates is wrong
within a month, and wrong in the direction that matters: it keeps listing
things that stopped firing. This reads the catalogue and greps the codebase, so
"never fires" is a fact about the code rather than somebody's recollection.

That distinction has already earned its keep. Several events in this catalogue
were fully written — copy, channels, deep links — and had no caller at all: a
safety-recall notice that reported success while sending nothing, a quotation
email the app promised on screen, a reservation receipt for a hold on a car
worth millions of naira. None of them looked missing from the catalogue.

    python -m app.jobs.report_notifications            # markdown to stdout
    python -m app.jobs.report_notifications --out docs/NOTIFICATIONS.md
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

from app.domains.notifications import catalog

APP_ROOT = Path(__file__).resolve().parents[1]

#: Firing sites we do not want to count: the catalogue defining itself, and the
#: audit you are reading.
_IGNORED = {"catalog.py", "report_notifications.py"}


def _constant_names() -> dict[str, str]:
    """Map each event key back to its module-level constant name."""
    names: dict[str, str] = {}
    for name in dir(catalog):
        value = getattr(catalog, name)
        if isinstance(value, catalog.EventSpec):
            names[value.key] = name
    return names


def _python_files() -> list[Path]:
    return [p for p in APP_ROOT.rglob("*.py") if p.name not in _IGNORED]


def _parsed(path: Path):
    """AST for one file, or None if it cannot be read or parsed.

    PARSED RATHER THAN GREPPED. A text search counts the example in
    `notify.py`'s own docstring as a call site, which is exactly the sort of
    false positive that makes an audit untrustworthy — and this audit's whole
    value is that "never fires" can be relied on.
    """
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return None


def _catalog_refs(tree) -> list[tuple[str, int]]:
    """Every real `catalog.X` reference in code, as (name, line)."""
    refs: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "catalog"
        ):
            refs.append((node.attr, node.lineno))
    return refs


def _call_sites(constant: str) -> list[str]:
    """Every place that fires this event, as `path:line`."""
    hits: list[str] = []
    for path in _python_files():
        tree = _parsed(path)
        if tree is None:
            continue
        for name, line in _catalog_refs(tree):
            if name == constant:
                hits.append(f"{path.relative_to(APP_ROOT.parent).as_posix()}:{line}")
    return sorted(set(hits))


def _rich_email_events() -> set[str]:
    """Events whose caller supplies a bespoke HTML body.

    Detected structurally: a call carrying BOTH `event=catalog.X` and an
    `email_html` argument. Everything else falls back to the shared branded
    shell, which renders the catalogue's plain body — readable, but without a
    metadata table or a tailored call to action.
    """
    found: set[str] = set()
    names = _constant_names()
    by_constant = {constant: key for key, constant in names.items()}

    for path in _python_files():
        tree = _parsed(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            keywords = {kw.arg for kw in node.keywords if kw.arg}
            if "email_html" not in keywords:
                continue
            for kw in node.keywords:
                value = kw.value
                if (
                    kw.arg == "event"
                    and isinstance(value, ast.Attribute)
                    and isinstance(value.value, ast.Name)
                    and value.value.id == "catalog"
                    and value.attr in by_constant
                ):
                    found.add(by_constant[value.attr])
    return found


def build_report() -> str:
    names = _constant_names()
    rich = _rich_email_events()

    live: list[str] = []
    dormant: list[str] = []

    for event in catalog.ALL_EVENTS:
        constant = names.get(event.key, "?")
        sites = _call_sites(constant)
        channels = ", ".join(event.channels)
        email_kind = "—"
        if catalog.EMAIL in event.channels:
            email_kind = "branded HTML + text" if event.key in rich else "branded shell"

        row = (
            f"| `{event.key}` | {event.category.value} | {channels} | {email_kind} | "
            f"{'**yes**' if event.force else 'no'} | "
            f"{'<br>'.join(f'`{s}`' for s in sites) if sites else '**never fires**'} |"
        )
        (live if sites else dormant).append(row)

    header = (
        "| Event | Category | Channels | Email format | Ignores prefs | Fired from |\n"
        "|---|---|---|---|---|---|"
    )

    out: list[str] = []
    out.append("# Notification inventory")
    out.append("")
    out.append(
        "Generated by `python -m app.jobs.report_notifications`. Do not edit by hand — "
        "regenerate it. A hand-kept list goes stale in the direction that matters: it "
        "keeps listing templates that quietly stopped firing."
    )
    out.append("")
    out.append(f"**{len(catalog.ALL_EVENTS)} events** — {len(live)} wired, {len(dormant)} with no caller.")
    out.append("")
    out.append("## Live")
    out.append("")
    out.append(header)
    out.extend(live)
    out.append("")
    out.append("## No caller")
    out.append("")
    out.append(
        "Defined, with copy and channels, and nothing in the codebase fires them. "
        "Each needs a feature that does not exist yet — not a missing template."
    )
    out.append("")
    out.append(header)
    out.extend(dormant or ["| _none_ | | | | | |"])
    out.append("")

    out.append("## Copy")
    out.append("")
    out.append("The exact words a customer receives, for review.")
    out.append("")
    for event in catalog.ALL_EVENTS:
        out.append(f"### `{event.key}`")
        out.append("")
        out.append(f"- **Subject / title:** {event.title}")
        out.append(f"- **Body:** {event.body}")
        if event.deep_link:
            out.append(f"- **Opens:** `{event.deep_link}`")
        if event.requires:
            out.append(f"- **Needs:** {', '.join(f'`{r}`' for r in event.requires)}")
        out.append("")

    out.append("## Channels not in use")
    out.append("")
    sms_events = [e.key for e in catalog.ALL_EVENTS if catalog.SMS in e.channels]
    if sms_events:
        out.append(f"- **SMS** is declared by: {', '.join(f'`{k}`' for k in sms_events)}")
    else:
        out.append(
            "- **SMS** — the dispatcher supports it and a gateway can be configured, "
            "but no event declares the channel, so nothing sends SMS today."
        )
    out.append("")
    out.append("## Outside the catalogue")
    out.append("")
    out.append(
        "- **OTP** (`app/services/otp.py`) is sent directly rather than through the "
        "catalogue, because it must not be suppressible by a notification preference. "
        "It has its own branded HTML template."
    )
    out.append(
        "- **Service reminders** (`app/domains/notifications/service.py`) are sent by the "
        "rules engine using operator-editable copy from `notification_rules.config`, so "
        "`service.reminder_due` in the catalogue is unused by design."
    )
    out.append(
        "- **The previous-address warning** on an email change "
        "(`app/domains/users/service.py`) is sent direct, because it goes to an address "
        "that is no longer on the account and therefore has no preferences to read."
    )
    out.append("")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", help="write the report here instead of stdout")
    args = parser.parse_args()

    report = build_report()
    if args.out:
        target = Path(args.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(report, encoding="utf-8", newline="\n")
        print(f"wrote {target}")
    else:
        sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
