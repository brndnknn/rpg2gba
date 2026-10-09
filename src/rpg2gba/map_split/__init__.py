"""Map-split stage: cut one RMXP map into several GBA maps joined by arrow warps.

Design: `reference/guides/map_split_stage.md`. Source of truth:
`reference/split_maps.json`. `ids` holds the pure id rules every consumer may
import; `spec` loads the decisions; `derive` is the pure geometry; `stage` does
the IO."""
