"""Phase 3 — map deserialization (rxdata → structured JSON).

Thin Python layer over `rxdata_deserializer/deserialize.rb`'s `rxdata` mode:

- `driver`   — invoke the Ruby deserializer, place per-map JSON, confirm counts.
- `validate` — conservation + schema-conformance checks (round-trip is
               impossible for Marshal; see PHASE3_PLAN.md test strategy).
- `command_catalog` — tally command codes, emit the §3.2 reference + extract the
               switch/variable tables and script-call signature list.
"""
