#!/usr/bin/env python3
"""
overcr peek — Live terminal dashboard of OverCR memory state.

Usage:
  overcr-peek              # One-shot snapshot
  overcr-peek --watch      # Live-updating (like watch)
  overcr-peek --watch --interval 3

Built using the creative-ideation skill:
  Constraint: "High concept, low effort"
  > A deep idea, lazily executed. The concept should be brilliant.
  > The implementation should take an afternoon.
"""

import json, sys, time, os
from pathlib import Path
from datetime import datetime
from collections import Counter

INDEX_DIR = Path.home() / "Documents" / "ObsidianVault" / ".overcr-index"


def load_index():
    """Load the cached OverCR index directly — no bridge calls needed."""
    stats_file = INDEX_DIR / "stats.json"
    notes_file = INDEX_DIR / "notes.jsonl"

    stats = json.loads(stats_file.read_text()) if stats_file.exists() else {}

    domain_facts = Counter()
    kind_counts = Counter()
    recent_facts = []

    if notes_file.exists():
        for line in notes_file.read_text().strip().split("\n"):
            if not line.strip():
                continue
            note = json.loads(line)
            for f in note.get("facts", []):
                kind = f.get("kind", "n/a")
                kind_counts[kind] += 1
                # Use the fact's prefix as domain, fall back to path prefix
                domain = f.get("prefix", note["path"].split("/")[0])
                domain_facts[domain] += 1
                recent_facts.append({
                    "kind": kind,
                    "claim": f.get("claim", "")[:100],
                    "domain": domain,
                    "file": Path(note["path"]).name,
                })

    recent_facts = recent_facts[-8:]

    return {
        "total_facts": stats.get("total_facts", sum(domain_facts.values())),
        "total_notes": stats.get("notes_with_facts", 0),
        "total_domains": stats.get("domains", len(domain_facts)),
        "total_tags": stats.get("tags", 0),
        "domain_facts": dict(domain_facts.most_common()),
        "kind_counts": dict(kind_counts.most_common()),
        "recent_facts": recent_facts,
    }


def render_dashboard():
    """Render the dashboard using rich."""
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.layout import Layout
    from rich.text import Text

    console = Console()
    data = load_index()

    # Stats panel
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    stats_text = Text()
    stats_text.append(f"Notes with facts:  {data['total_notes']}\n", style="green")
    stats_text.append(f"Total facts:       {data['total_facts']}\n", style="green")
    stats_text.append(f"Domains:           {data['total_domains']}\n", style="cyan")
    stats_text.append(f"Tags:              {data['total_tags']}\n", style="yellow")
    stats_text.append(f"\nLast indexed: {now}", style="dim")

    stats_panel = Panel(stats_text, title="[bold]OverCR Memory Stats[/bold]", border_style="blue")

    # Domain table
    domain_table = Table(
        title=f"[bold cyan]Knowledge Graph — {data['total_facts']} facts across {data['total_domains']} domains[/bold cyan]",
        box=None, padding=(0, 1)
    )
    domain_table.add_column("Domain", style="cyan", no_wrap=True)
    domain_table.add_column("Facts", justify="right", style="green")

    for domain, count in list(data["domain_facts"].items())[:20]:
        domain_table.add_row(domain, str(count))

    if len(data["domain_facts"]) > 20:
        domain_table.add_row(f"... and {len(data['domain_facts']) - 20} more", "")

    # Kind breakdown
    kind_text = Text()
    for kind, count in data["kind_counts"].items():
        style = "green" if kind in ("fact", "completed") else "red" if kind == "rejected" else "yellow" if kind == "next_action" else "white"
        kind_text.append(f"  {kind}: {count}\n", style=style)

    kind_panel = Panel(kind_text, title="[bold]Fact Kinds[/bold]", border_style="yellow")

    # Recent facts
    recent_text = Text()
    for f in reversed(data["recent_facts"]):
        kind = f["kind"]
        claim = f["claim"]
        domain = f["domain"]
        kind_style = "cyan" if kind == "fact" else "green" if kind == "next_action" else "red" if kind == "rejected" else "white"
        recent_text.append(f"  [{kind}] ", style=kind_style)
        recent_text.append(f"{claim}\n", style="white")
        recent_text.append(f"           ({domain} — {f['file']})\n", style="dim")

    if not data["recent_facts"]:
        recent_text.append("(no facts in cache)", style="dim")

    recent_panel = Panel(recent_text, title="[bold]Recent Facts[/bold]", border_style="green")

    # Layout
    layout = Layout()
    mid = Layout()
    mid.split_row(domain_table, kind_panel)
    layout.split_column(
        stats_panel,
        mid,
        recent_panel,
    )

    return layout


def main():
    watch_mode = "--watch" in sys.argv
    interval = 3

    if "--interval" in sys.argv:
        idx = sys.argv.index("--interval")
        if idx + 1 < len(sys.argv):
            try:
                interval = int(sys.argv[idx + 1])
            except ValueError:
                pass

    if watch_mode:
        from rich.live import Live
        from rich.console import Console
        console = Console()
        try:
            with Live(render_dashboard(), refresh_per_second=1 / interval, console=console) as live:
                while True:
                    live.update(render_dashboard())
                    time.sleep(interval)
        except KeyboardInterrupt:
            console.print("\n[yellow]overcr peek stopped[/yellow]")
    else:
        from rich.console import Console
        console = Console()
        console.print(render_dashboard())


if __name__ == "__main__":
    main()
