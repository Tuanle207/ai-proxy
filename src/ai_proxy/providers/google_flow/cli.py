"""Google Flow provider CLI commands (mounted as `aip google-flow` in Phase 8)."""

from __future__ import annotations

import typer

google_flow_app = typer.Typer(help="Google Flow provider commands.")
projects_app = typer.Typer(help="Manage Google Flow projects.")
google_flow_app.add_typer(projects_app, name="projects")


@projects_app.command("prune")
def prune_projects() -> None:
    """Delete orphaned Flow projects."""
    typer.echo("prune google_flow projects (not wired yet)")
