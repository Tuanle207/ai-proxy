"""Perplexity provider CLI commands (mounted as `aip perplexity`)."""

from __future__ import annotations

import typer

perplexity_app = typer.Typer(help="Perplexity provider commands.")
threads_app = typer.Typer(help="Manage Perplexity threads.")
perplexity_app.add_typer(threads_app, name="threads")


@threads_app.command("list")
def list_threads() -> None:
    """List known Perplexity threads."""
    typer.echo("list perplexity threads (not wired yet)")


@threads_app.command("delete")
def delete_thread(thread_ref: str) -> None:
    """Delete a Perplexity thread by workspace ref."""
    typer.echo(f"delete perplexity thread {thread_ref} (not wired yet)")
