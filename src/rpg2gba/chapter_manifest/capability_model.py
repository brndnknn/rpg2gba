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
import re
from pathlib import Path

from rpg2gba.capability_sites import (
    FIELD_CAPABILITY_ITEMS,
    CapabilityDerivation,
    derive_capability_sites,
    teach_beat_name,
)
from rpg2gba.chapter_atlas.binding import ChapterBinding, load_binding

from .checker import CapabilityGrant

logger = logging.getLogger(__name__)

DEFAULT_MAPS_DIR = Path("output/uranium-build/maps")
DEFAULT_SWITCHES_JSON = Path("reference/uranium_switches.json")
DEFAULT_VARIABLES_JSON = Path("reference/uranium_variables.json")
DEFAULT_CHAPTERS_JSON = Path("reference/chapters.json")
DEFAULT_MODULES_DIR = Path(__file__).resolve().parents[1] / "playtest" / "chapters_gen"


def taught_in_chain(
    chain_ids: frozenset[str], modules_dir: Path = DEFAULT_MODULES_DIR
) -> frozenset[str]:
    """Field-capability tokens whose teach setup beat (`teach_beat_name`)
    appears in the committed generated module of any chapter in `chain_ids`.

    The move half of a field capability is a fact about the WALK, not the
    game data (CH08 §9): the player could have taught HM06 the moment it was
    received, but the generated suites teach it on first need, so a chapter
    only holds the capability once its own suite or a predecessor's has
    actually taught it. Reading the committed modules is the same pattern
    `beat_gen.seed.deferred_rows` uses for cross-chapter facts. A chapter with
    no module yet contributes nothing."""
    taught: set[str] = set()
    for cid in chain_ids:
        path = modules_dir / f"{cid.lower()}.py"
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for token in FIELD_CAPABILITY_ITEMS:
            # The generator writes module literals with repr() (single
            # quotes); hand-written modules use double. Accept both.
            name = re.escape(teach_beat_name(token))
            if re.search(rf"""["']{name}["']""", text):
                taught.add(token)
    return frozenset(taught)


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
        taught: frozenset[str] = frozenset(),
    ) -> None:
        self._chapter_id = chapter_id
        self._derivation = derivation
        self._chain_ids = chain_ids
        self._taught = taught

    def _badge_met(self, name: str) -> bool:
        required = self._derivation.field_badge_requirement(name)
        if required is None:
            return False
        distinct_in_chain = {
            w.badge_index
            for w in self._derivation.badge_writes
            if w.chapter_id in self._chain_ids
        }
        return len(distinct_in_chain) >= required

    def _item_sites_in_chain(self, name: str) -> tuple[CapabilityGrant, ...]:
        return tuple(
            CapabilityGrant(row_id=s.row_id, map_id=s.map_id, chapter_id=s.chapter_id)
            for s in self._derivation.item_grant_sites(name)
            if s.chapter_id in self._chain_ids
        )

    def obtainable(self, name: str) -> bool:
        """The game-data half of a field capability is met in this chain:
        enough badges AND one of its items granted (`FIELD_CAPABILITY_ITEMS`).
        False for a token whose item half is unmodelled. Whether the walk has
        TAUGHT the move is `held`."""
        if self._derivation.field_item_requirement(name) is None:
            return False
        return self._badge_met(name) and bool(self._item_sites_in_chain(name))

    def held(self, name: str) -> bool:
        """Obtainable AND taught by this chain's suites (`taught_in_chain`)."""
        return self.obtainable(name) and name in self._taught

    def grant_sites(self, name: str) -> tuple[CapabilityGrant, ...] | None:
        """`checker.CapabilityModel.grant_sites`.

        For a field-capability token (`capability_sites
        .FIELD_CAPABILITY_BADGE_COUNT`), the badge-count conjunct is
        NECESSARY, NOT SUFFICIENT (module docstring, `capability_sites`'s
        "Known limit" paragraph): the `move OR item` conjunct is entirely
        unmodelled. So once this chain's distinct badge count already meets
        the token's requirement, this method must NEVER report grant sites
        as if the capability were confirmed available -- doing so would let
        `checker.py` raise `blocked_already_granted` on a row that may still
        be genuinely blocked by the missing move/item. It returns `None`
        (undetermined) in that case instead, and only returns the badge
        sites while the chain's badge count still falls short (an honest
        "not yet, as far as this model can tell" that keeps a correct
        `blocked:` claim from getting a false error).

        *(2026-10-15, CH08 §9: where the item half is modelled
        (`FIELD_CAPABILITY_ITEMS`), badge met but no item in the chain is
        still an honest "not yet" -- the item grant sites are returned; a
        capability `held` in this chain returns its badge + item sites in
        the chain, so `granted_within` can confirm it. Obtainable but not yet
        taught stays `None`, exactly as before.)*
        """
        if self._derivation.field_badge_requirement(name) is not None and self._badge_met(name):
            if self.held(name):
                return self._held_sites(name)
            items = self._derivation.item_grant_sites(name)
            if items and not self._item_sites_in_chain(name):
                # An item scan that found nothing anywhere is not evidence of
                # impossibility (e.g. a derivation built without the scan),
                # so only a real later grant site answers "not yet".
                return tuple(
                    CapabilityGrant(row_id=s.row_id, map_id=s.map_id, chapter_id=s.chapter_id)
                    for s in items
                )
            return None
        sites = self._derivation.grant_sites(name)
        if sites is None:
            return None
        return tuple(
            CapabilityGrant(row_id=s.row_id, map_id=s.map_id, chapter_id=s.chapter_id)
            for s in sites
        )

    def granted_within(self, name: str) -> tuple[CapabilityGrant, ...]:
        """`checker.CapabilityModel.granted_within`.

        For a field-capability token this is always `()`: the badge-count
        model can rule the capability NOT held (chain badge count short of
        the requirement -- `grant_sites` returns real sites but none of them
        represent the capability itself being granted) or refuse to say
        (badge count met, `grant_sites` returns `None`) -- it can never
        affirmatively confirm the capability is held, since the move/item
        conjunct is unmodelled. Reporting anything non-empty here would let
        `checker.py` treat a field capability as confirmed-held from the
        badge alone.

        *(2026-10-15: a field capability `held` in this chain -- badge + item
        + taught by a chain suite -- is the one affirmative case; it returns
        its in-chain badge and item sites.)*
        """
        if self._derivation.field_badge_requirement(name) is not None:
            return self._held_sites(name) if self.held(name) else ()
        sites = self.grant_sites(name)
        if not sites:
            return ()
        return tuple(g for g in sites if g.chapter_id in self._chain_ids)

    def _held_sites(self, name: str) -> tuple[CapabilityGrant, ...]:
        badge_sites = tuple(
            CapabilityGrant(row_id=w.row_id, map_id=w.map_id, chapter_id=w.chapter_id)
            for w in self._derivation.badge_writes
            if w.chapter_id in self._chain_ids
        )
        return badge_sites + self._item_sites_in_chain(name)


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
    return ChapterCapabilityModel(
        chapter_id, derivation, chain_ids, taught=taught_in_chain(chain_ids)
    )


__all__ = ["ChapterCapabilityModel", "build_capability_model", "taught_in_chain"]
