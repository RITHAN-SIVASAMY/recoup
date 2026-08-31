"""Command-line entry points: demo, replay, verify."""

from __future__ import annotations

import typer

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command()
def demo(seed: int = 42) -> None:
    """Run the seeded batch end-to-end and print the headline block."""
    typer.secho(
        "recoup demo: not implemented yet - ingestion (Phase 02), policy (Phase 04) and "
        "measurement (Phase 10) all have to land before this can print real numbers.",
        fg=typer.colors.RED,
        err=True,
    )
    raise typer.Exit(code=1)


@app.command()
def replay() -> None:
    """Rebuild projections from the event log."""
    typer.echo("recoup replay: no event store yet (lands in Phase 01) - nothing to replay.")


@app.command()
def verify() -> None:
    """Verify the hash chain and replay equality."""
    typer.echo(
        "recoup verify: no event store yet (lands in Phase 01) - the chain is trivially empty and valid."
    )


if __name__ == "__main__":
    app()
