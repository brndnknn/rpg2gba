"""Top-level CLI for rpg2gba pipeline phases."""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Callable

import click

from rpg2gba.pbs_converter._id_map import IdMap

logger = logging.getLogger("rpg2gba.pipeline")

ID_MAP_PATH = Path("reference/uranium_id_map.json")


def _repo_root() -> Path:
    """Repo root = three levels up from this file (src/rpg2gba/pipeline.py)."""
    return Path(__file__).resolve().parents[2]


def _load_dotenv() -> None:
    """Populate os.environ from a repo-root .env-paths file, without external deps.

    Shell-set values win: keys already present in os.environ are left alone.
    Lines are `KEY=VALUE`; blank lines and `#` comments are ignored. A missing
    .env-paths is fine (returns silently) — this is a convenience, not a
    requirement. (Named .env-paths, not .env: it holds only filesystem paths,
    no secrets, and the unsuffixed name collides with a tooling read-deny rule.)
    """
    env_path = _repo_root() / ".env-paths"
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable DEBUG logging.")
def main(verbose: bool) -> None:
    """rpg2gba — RPG Maker XP to GBA ROM conversion pipeline."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )


def _resolve_paths() -> tuple[Path, Path]:
    """Resolve Uranium source + output directories from env vars."""
    _load_dotenv()
    uranium_src_env = os.environ.get("RPG2GBA_URANIUM_SRC")
    if not uranium_src_env:
        raise click.ClickException(
            "RPG2GBA_URANIUM_SRC is not set. Point it at the unpacked Uranium tree "
            "(see PHASE2_PLAN.md §Prerequisites)."
        )
    uranium_src = Path(uranium_src_env)
    if not (uranium_src / "Data").is_dir():
        raise click.ClickException(
            f"RPG2GBA_URANIUM_SRC={uranium_src} has no Data/ subdirectory."
        )
    out_dir = Path(os.environ.get("RPG2GBA_OUTPUT", "output")) / "uranium-build"
    return uranium_src, out_dir


# Each converter registers itself here. The build agent fills these in as it
# implements §2.1–§2.10 of PHASE2_PLAN.md. Signature:
#     run(uranium_src: Path, out_dir: Path, id_map: IdMap) -> None
PHASE2_CONVERTERS: list[tuple[str, Callable[[Path, Path, IdMap], None]]] = []


def _load_converters() -> None:
    """Lazy-import each Phase 2 converter and register its `run` callable.

    Skips any module that hasn't been implemented yet (still a stub with no
    `run` symbol). This lets the pipeline run partial Phase 2 work without
    waiting for every converter to be written.
    """
    from importlib import import_module

    module_order = [
        "pokemon",
        "moves",
        "items",
        "abilities",
        "tm_hm",
        "trainers",
        "encounters",
        "metadata",
        "tmpbs",
    ]
    for name in module_order:
        try:
            mod = import_module(f"rpg2gba.pbs_converter.{name}")
        except ModuleNotFoundError:
            logger.debug("converter %s not present yet, skipping", name)
            continue
        run = getattr(mod, "run", None)
        if run is None:
            logger.debug("converter %s has no run() yet, skipping", name)
            continue
        PHASE2_CONVERTERS.append((name, run))


@main.command()
@click.option("--clean", is_flag=True, help="Wipe output/uranium-build/ before running.")
@click.option(
    "--only",
    default=None,
    help="Run only the named converter (e.g. --only pokemon). Useful for debugging.",
)
def phase2(clean: bool, only: str | None) -> None:
    """Run PBS converters (Phase 2)."""
    uranium_src, out_dir = _resolve_paths()
    if clean and out_dir.exists():
        logger.info("wiping %s", out_dir)
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    id_map = IdMap.load(ID_MAP_PATH)

    _load_converters()
    if only is not None:
        matched = [(n, f) for n, f in PHASE2_CONVERTERS if n == only]
        if not matched:
            raise click.ClickException(
                f"--only={only} matched none of: "
                f"{[n for n, _ in PHASE2_CONVERTERS] or 'no converters implemented yet'}"
            )
        targets = matched
    else:
        targets = PHASE2_CONVERTERS

    if not targets:
        logger.warning("no Phase 2 converters are implemented yet — nothing to do")
        return

    for name, run in targets:
        logger.info("running converter: %s", name)
        run(uranium_src, out_dir, id_map)

    id_map.save(ID_MAP_PATH)
    logger.info("saved id map → %s", ID_MAP_PATH)


@main.command()
@click.option("--clean", is_flag=True)
def phase3(clean: bool) -> None:
    """Run rxdata deserializer (Phase 3)."""
    raise NotImplementedError("Phase 3 is not yet implemented.")


@main.command()
@click.option("--clean", is_flag=True)
def phase4(clean: bool) -> None:
    """Run conversion agent orchestrator (Phase 4)."""
    raise NotImplementedError("Phase 4 is not yet implemented.")


@main.command("convert-map")
@click.option("--map-id", required=True)
@click.option(
    "--backend",
    default="ollama",
    type=click.Choice(["ollama", "claude_code"]),
)
def convert_map(map_id: str, backend: str) -> None:
    """Convert a single map for debugging (Phase 4)."""
    raise NotImplementedError("convert-map is not yet implemented.")


if __name__ == "__main__":
    main()
