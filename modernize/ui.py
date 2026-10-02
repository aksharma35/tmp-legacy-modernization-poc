"""Console helpers so every step reads the same way on screen."""
from __future__ import annotations

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

console = Console(highlight=False)


def step(title: str, subtitle: str = "") -> None:
    console.print()
    console.print(Panel.fit(f"[bold]{title}[/bold]" + (f"\n[dim]{subtitle}[/dim]" if subtitle else ""), border_style="cyan"))


def ok(msg: str) -> None:
    console.print(f"[green]✔[/green] {msg}")


def fail(msg: str) -> None:
    console.print(f"[red]✘[/red] {msg}")


def warn(msg: str) -> None:
    console.print(f"[yellow]![/yellow] {msg}")


def info(msg: str) -> None:
    console.print(f"[dim]·[/dim] {msg}")


def table(title: str, columns: list[str], rows: list[list], styles: list[str] | None = None) -> None:
    t = Table(title=title, title_justify="left", show_lines=False, header_style="bold")
    for i, c in enumerate(columns):
        t.add_column(c, style=(styles[i] if styles else None), overflow="fold")
    for r in rows:
        t.add_row(*[x if isinstance(x, str) and x.startswith("[") and "[/" in x else escape(str(x)) for x in r])
    console.print(t)
