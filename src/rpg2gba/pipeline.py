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


REFERENCE_DIR = Path("reference")


@main.command()
@click.option("--clean", is_flag=True, help="Wipe output/uranium-build/maps/ before running.")
def phase3(clean: bool) -> None:
    """Run the rxdata map deserializer (Phase 3)."""
    from rpg2gba.map_deserializer import command_catalog, driver, validate

    uranium_src, out_dir = _resolve_paths()

    n_maps = driver.run(uranium_src, out_dir, clean=clean)
    validate.validate_output(out_dir)
    command_catalog.build(out_dir, REFERENCE_DIR)
    logger.info("phase3 complete: %d maps deserialized + validated + cataloged", n_maps)


def _phase4_registry(out_dir: Path, clean: bool, fork_path: Path | None):
    """Load or pre-seed the flag registry (Phase 4 §4.1). Wipes run state on --clean."""
    from rpg2gba.conversion_agent.flag_registry import FlagRegistry

    state_path = out_dir / "flag_state.json"
    if clean:
        for d in (out_dir / "scripts", out_dir / "checkpoints"):
            if d.exists():
                shutil.rmtree(d)
        for f in (state_path, out_dir / "unhandled.jsonl", out_dir / "memo_manifest.json"):
            if f.exists():
                f.unlink()
    if state_path.is_file():
        return FlagRegistry.load(state_path, fork_path=fork_path)
    reg = FlagRegistry(fork_path=fork_path)
    reg.pre_seed(
        REFERENCE_DIR / "essentials_to_emerald_map.md",
        REFERENCE_DIR / "uranium_switches.json",
        REFERENCE_DIR / "uranium_variables.json",
    )
    reg.save(state_path)
    return reg


_DEFAULT_MODEL = "claude-sonnet-4-6"


def _phase4_backend(name: str, model: str = _DEFAULT_MODEL, usage_log_path: Path | None = None, effort: str | None = None):
    """Construct the chosen conversion backend with the frozen system prompt.

    The system prompt = the frozen instructions (`system.md`) + the event-invariant
    static context (cheatsheet, script-call reference, few-shots). Composing it once
    here — rather than in the per-event user message — keeps it byte-stable across all
    spawns so `claude -p` hits the server-side prompt cache (dedup Phase B).

    `model` selects the Claude model for the `claude_code` backend (the
    Sonnet-vs-Opus calibration knob); it is ignored by the Ollama backend, which
    is configured via OLLAMA_HOST/its own model setting. `usage_log_path`, when set,
    makes the claude_code backend append per-spawn token/cost usage there so a bulk
    run can be tallied (scripts/run_stats.py); also ignored by Ollama.
    """
    from rpg2gba.conversion_agent import prompt_builder

    static_context = prompt_builder.build_static_context(
        cheatsheet=prompt_builder.load_cheatsheet(REFERENCE_DIR),
        script_call_ref=prompt_builder.load_script_call_reference(REFERENCE_DIR),
        few_shots=prompt_builder.load_few_shots(),
    )
    system_prompt = prompt_builder.load_system_prompt() + "\n\n" + static_context
    if name == "claude_code":
        from rpg2gba.conversion_agent.backends.claude_code import ClaudeCodeBackend

        return ClaudeCodeBackend(system_prompt, model=model, usage_log_path=usage_log_path, effort=effort)
    if name == "human":
        # Interactive hand-conversion (scripts/run_human.py). Same frozen system prompt
        # so its memo entries share the production fingerprint — work done by hand and by
        # Opus dedupe against each other. `?` in the UI shows the compact lane quickref,
        # NOT this system prompt.
        from rpg2gba.conversion_agent.backends.human import HumanBackend

        qr_path = REFERENCE_DIR / "human_quickref.md"
        quickref = qr_path.read_text(encoding="utf-8") if qr_path.is_file() else ""
        return HumanBackend(system_prompt, quickref=quickref)
    from rpg2gba.conversion_agent.backends.ollama import OllamaBackend

    return OllamaBackend(system_prompt)


@main.command()
@click.option("--clean", is_flag=True, help="Wipe scripts/checkpoints/registry state first.")
@click.option(
    "--run",
    is_flag=True,
    help="Actually convert (spawns the backend per event — spends Pro/API budget).",
)
@click.option(
    "--backend",
    default="claude_code",
    type=click.Choice(["claude_code", "ollama"]),
)
@click.option(
    "--model",
    default=_DEFAULT_MODEL,
    help="Claude model for the claude_code backend (e.g. claude-sonnet-4-6, claude-opus-4-8).",
)
def phase4(clean: bool, run: bool, backend: str, model: str) -> None:
    """Build the conversion-agent machinery (Phase 4). Add --run to convert."""
    from rpg2gba.conversion_agent import orchestrator as orch

    _, out_dir = _resolve_paths()
    maps_dir = out_dir / "maps"
    if not maps_dir.is_dir():
        raise click.ClickException(f"{maps_dir} not found — run `phase3` first.")
    fork = os.environ.get("RPG2GBA_POKEEMERALD")
    fork_path = Path(fork) if fork and Path(fork).is_dir() else None

    registry = _phase4_registry(out_dir, clean, fork_path)
    registry.dump_header(out_dir / "intermediate" / "rpg2gba_flags.h")

    done = {p.stem for p in (out_dir / "checkpoints").glob("*.done")}
    pending = [p for p in sorted(maps_dir.glob("Map*.json")) if p.stem not in done]
    state = registry.to_state()

    if not run:
        logger.info(
            "machinery ready: %d flags + %d vars pre-seeded, %d script-switches blocked; "
            "%d/%d maps pending. Re-run with --run to convert via %s (spawns the backend "
            "per event — spends budget).",
            len(state["switches"]),
            len(state["variables"]),
            len(state["script_switches"]),
            len(pending),
            len(list(maps_dir.glob("Map*.json"))),
            backend,
        )
        return

    backend_obj = _phase4_backend(backend, model)
    orchestrator = orch.Orchestrator(backend_obj, registry, out_dir)
    # Convert common events before maps so each map's `call CommonEvent_<NNN>` has a
    # target (dedup Phase A). Idempotent: a CommonEvents.done checkpoint skips re-runs.
    ce_file = out_dir / "common_events.json"
    if ce_file.is_file():
        orchestrator.convert_common_events(ce_file)
    n = orchestrator.convert_all(maps_dir)
    logger.info("phase4: processed %d maps; triage=%s", n, orch.triage(out_dir / "unhandled.jsonl"))


@main.command("convert-map")
@click.option("--map-id", required=True)
@click.option(
    "--backend",
    default="claude_code",
    type=click.Choice(["claude_code", "ollama"]),
)
@click.option(
    "--model",
    default=_DEFAULT_MODEL,
    help="Claude model for the claude_code backend (e.g. claude-sonnet-4-6, claude-opus-4-8).",
)
def convert_map(map_id: str, backend: str, model: str) -> None:
    """Convert a single map for debugging (Phase 4; spawns the backend)."""
    from rpg2gba.conversion_agent import orchestrator as orch

    _, out_dir = _resolve_paths()
    stem = f"Map{int(map_id):03d}"
    map_file = out_dir / "maps" / f"{stem}.json"
    if not map_file.is_file():
        raise click.ClickException(f"{map_file} not found — run `phase3` first.")
    fork = os.environ.get("RPG2GBA_POKEEMERALD")
    fork_path = Path(fork) if fork and Path(fork).is_dir() else None

    registry = _phase4_registry(out_dir, clean=False, fork_path=fork_path)
    backend_obj = _phase4_backend(backend, model)
    orchestrator = orch.Orchestrator(backend_obj, registry, out_dir)
    cp = out_dir / "checkpoints" / f"{stem}.done"
    if cp.exists():
        cp.unlink()  # force re-conversion of this one map
    orchestrator.convert_map(map_file)
    logger.info("converted %s -> %s", stem, out_dir / "scripts" / f"{stem}.pory")


@main.command("convert-common-events")
@click.option(
    "--backend",
    default="claude_code",
    type=click.Choice(["claude_code", "ollama"]),
)
@click.option(
    "--model",
    default=_DEFAULT_MODEL,
    help="Claude model for the claude_code backend (e.g. claude-sonnet-4-6, claude-opus-4-8).",
)
@click.option(
    "--ce-id",
    "ce_ids",
    multiple=True,
    type=int,
    help="Convert only these common-event id(s) (debug; partial run, skips the checkpoint).",
)
def convert_common_events(backend: str, model: str, ce_ids: tuple[int, ...]) -> None:
    """Convert the common events for debugging (Phase 4 dedup A; spawns the backend)."""
    from rpg2gba.conversion_agent import orchestrator as orch

    _, out_dir = _resolve_paths()
    ce_file = out_dir / "common_events.json"
    if not ce_file.is_file():
        raise click.ClickException(f"{ce_file} not found — run `phase3` first.")
    fork = os.environ.get("RPG2GBA_POKEEMERALD")
    fork_path = Path(fork) if fork and Path(fork).is_dir() else None

    registry = _phase4_registry(out_dir, clean=False, fork_path=fork_path)
    backend_obj = _phase4_backend(backend, model)
    orchestrator = orch.Orchestrator(backend_obj, registry, out_dir)
    cp = out_dir / "checkpoints" / "CommonEvents.done"
    if not ce_ids and cp.exists():
        cp.unlink()  # force a full re-conversion (a filtered run leaves it alone)
    orchestrator.convert_common_events(ce_file, only_ids=set(ce_ids) or None)
    logger.info("converted common events -> %s", out_dir / "scripts" / "CommonEvents.pory")


if __name__ == "__main__":
    main()
