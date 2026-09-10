"""Concrete `checker.CapabilityModel` over `rpg2gba.capability_sites`'
corpus-wide switch/variable-write scan.

`checker.py` deliberately never imports `rpg2gba.capability_sites` or
`rpg2gba.chapter_atlas` -- a `Protocol` is the seam. This module is the thin
adapter the CLI wires into `checker.check_chapter`'s `capabilities=`
argument so the `blocked:<capability>` rules (`RULE_CAPABILITY_MODEL_
UNENFORCED`, `RULE_BLOCKED_NO_GRANT_SITE`, `RULE_BLOCKED_ALREADY_GRANTED`)
can actually run instead of every `blocked:` row reporting unenforced
unconditionally -- which is what has happened to every `blocked:` row ever
authored (28 `blocked:rock_smash` and 4 `blocked:surf` in CH04/CH05 alone;
`REDERIVATION_PLAN.md` P8). It is the sibling of `beat_model.py`/
`boundary_model.py`/`route_model.py`, which solve the same layering problem
the same way.

It joins two facts that live in different places on purpose:

- **where (if anywhere) is this capability granted?** -- a fact about the
  game data, corpus-wide, from `capability_sites.derive_capability_sites`
  (`code 121`/`code 122` writes -- see that module's docstring for the full
  design and why grants are keyed to map-event sites, not chapters);
- **does the player already hold it by the time THIS chapter runs?** -- a
  fact about the chapter chain (`chapter_atlas.binding.ChapterBinding`'s
  `predecessor` pointers), joined against the first fact's `chapter_id`
  (the owning chapter of each grant site's map, itself derived once inside
  `capability_sites`, not re-derived here).
"""
from __future__ import annotations

import logging
from pathlib import Path

from rpg2gba.capability_sites import CapabilityDerivation, derive_capability_sites
from rpg2gba.chapter_atlas.binding import ChapterBinding, load_binding

from .checker import CapabilityGrant

logger = logging.getLogger(__name__)

DEFAULT_MAPS_DIR = Path("output/uranium-build/maps")
DEFAULT_SWITCHES_JSON = Path("reference/uranium_switches.json")
DEFAULT_VARIABLES_JSON = Path("reference/uranium_variables.json")
DEFAULT_CHAPTERS_JSON = Path("reference/chapters.json")


def _chain_ids(binding: ChapterBinding, chapter_id: str) -> frozenset[str]:
    """`chapter_id` plus every chapter reachable by walking `predecessor`
    pointers backward -- "this chapter or one of its predecessors," the set
    `granted_within` treats as "the player already holds it."

    The loader (`chapter_atlas.binding`) validates every `predecessor`
    resolves to a real chapter id and that the chain has no cycle-inducing
    shape it would accept, so this walk is not guarded against an infinite
    loop here -- a malformed chain is that module's fail-loud responsibility,
    not this one's to re-check.
    """
    chain: set[str] = set()
    current: str | None = chapter_id
    while current is not None:
        chain.add(current)
        current = binding.chapter(current).predecessor
    return frozenset(chain)


class ChapterCapabilityModel:
    """Satisfies `chapter_manifest.checker.CapabilityModel`.

    Built once per `check_chapter` call from the corpus-wide
    `CapabilityDerivation` (expensive: scans all 199 map JSONs) and the
    reporting chapter's own predecessor chain (cheap, in-memory).
    """

    def __init__(
        self,
        chapter_id: str,
        derivation: CapabilityDerivation,
        chain_ids: frozenset[str],
    ) -> None:
        self._chapter_id = chapter_id
        self._derivation = derivation
        self._chain_ids = chain_ids

    def grant_sites(self, name: str) -> tuple[CapabilityGrant, ...] | None:
        sites = self._derivation.grant_sites(name)
        if sites is None:
            return None
        return tuple(
            CapabilityGrant(row_id=s.row_id, map_id=s.map_id, chapter_id=s.chapter_id)
            for s in sites
        )

    def granted_within(self, name: str) -> tuple[CapabilityGrant, ...]:
        sites = self.grant_sites(name)
        if not sites:
            return ()
        return tuple(g for g in sites if g.chapter_id in self._chain_ids)


def build_capability_model(
    chapter_id: str,
    *,
    maps_dir: Path = DEFAULT_MAPS_DIR,
    switches_json: Path = DEFAULT_SWITCHES_JSON,
    variables_json: Path = DEFAULT_VARIABLES_JSON,
    chapters_json: Path = DEFAULT_CHAPTERS_JSON,
) -> ChapterCapabilityModel | None:
    """Adapter for `chapter_id`, or None when the rule cannot be enforced yet.

    Returns None -- leaving the `blocked:` rules to degrade to
    `RULE_CAPABILITY_MODEL_UNENFORCED` -- only when `chapter_id` is not a
    known chapter in `reference/chapters.json` at all, e.g. a synthetic/test
    chapter id never registered there: `granted_within`'s predecessor walk
    has nothing to walk. That is the same "this rule has never heard of you"
    degrade every other `*_model_unenforced` adapter in this package uses,
    not a hard failure of an unrelated command.

    A malformed corpus (an ambiguous capability token, a corrupt sidecar) is
    NOT that case -- `derive_capability_sites` raises through
    (`CLAUDE.md` §4.5); every result downstream of a broken derivation would
    be built on a wrong premise.
    """
    binding = load_binding()
    try:
        binding.chapter(chapter_id)
    except KeyError:
        logger.info(
            "no chapter %r in reference/chapters.json -- the capability "
            "model is unenforced for it (no predecessor chain to walk)",
            chapter_id,
        )
        return None

    derivation = derive_capability_sites(
        maps_dir=maps_dir,
        switches_json=switches_json,
        variables_json=variables_json,
        chapters_json=chapters_json,
    )
    chain_ids = _chain_ids(binding, chapter_id)
    return ChapterCapabilityModel(chapter_id, derivation, chain_ids)


__all__ = ["ChapterCapabilityModel", "build_capability_model"]
