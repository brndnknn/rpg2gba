import click


@click.group()
def main() -> None:
    """rpg2gba — RPG Maker XP to GBA ROM conversion pipeline."""


@main.command()
@click.option("--clean", is_flag=True, help="Wipe output before running.")
def phase2(clean: bool) -> None:
    """Run PBS converters (Phase 2)."""
    raise NotImplementedError


@main.command()
@click.option("--clean", is_flag=True)
def phase3(clean: bool) -> None:
    """Run rxdata deserializer (Phase 3)."""
    raise NotImplementedError


@main.command()
@click.option("--clean", is_flag=True)
def phase4(clean: bool) -> None:
    """Run conversion agent orchestrator (Phase 4)."""
    raise NotImplementedError


@main.command("convert-map")
@click.option("--map-id", required=True)
@click.option("--backend", default="ollama", type=click.Choice(["ollama", "claude_code", "anthropic_api"]))
def convert_map(map_id: str, backend: str) -> None:
    """Convert a single map for debugging."""
    raise NotImplementedError
