# JSON files are run through jsonproc, which is a tool that converts JSON data to an output file
# based on an Inja template. https://github.com/pantor/inja

# BEGIN RPG2GBA GAME PROFILE — overlay region_map_sections.json (rpg2gba). The
# assembler writes region_map_sections.gen.json (vendored upstream sections + the
# game's named locations, appended so no upstream MAPSEC_* renumbers), gitignored;
# when present the build reads that, else the pristine upstream file. Same pattern
# as RPG2GBA_HEAL_LOCATIONS below. Revert this var + its two uses to restore stock.
RPG2GBA_REGION_MAP_SECTIONS := $(or $(wildcard $(DATA_SRC_SUBDIR)/region_map/region_map_sections.gen.json),$(DATA_SRC_SUBDIR)/region_map/region_map_sections.json)
# END RPG2GBA GAME PROFILE

AUTO_GEN_TARGETS += $(DATA_SRC_SUBDIR)/region_map/region_map_entries.h
$(DATA_SRC_SUBDIR)/region_map/region_map_entries.h: $(RPG2GBA_REGION_MAP_SECTIONS) $(DATA_SRC_SUBDIR)/region_map/region_map_sections.json.txt
	$(JSONPROC) $^ $@

$(C_BUILDDIR)/region_map.o: c_dep += $(DATA_SRC_SUBDIR)/region_map/region_map_entries.h

AUTO_GEN_TARGETS += include/constants/region_map_sections.h
include/constants/region_map_sections.h: $(RPG2GBA_REGION_MAP_SECTIONS) $(DATA_SRC_SUBDIR)/region_map/region_map_sections.constants.json.txt
	$(JSONPROC) $^ $@

# BEGIN RPG2GBA GAME PROFILE — overlay heal_locations.json (rpg2gba). The
# assembler writes heal_locations.gen.json (vendored upstream entries + the
# Uranium white-out respawns, appended in array order so HEAL_LOCATION_* ids
# for upstream entries never renumber), gitignored; when present the build reads
# that, else the pristine upstream file. Mirrors RPG2GBA_MAP_GROUPS /
# RPG2GBA_LAYOUTS in map_data_rules.mk and RPG2GBA_WILD_ENCOUNTERS in Makefile.
# Keeps src/data/heal_locations.json byte-for-byte upstream. See RPG2GBA_VENDOR.md.
# Revert this var + its two uses below to restore stock.
RPG2GBA_HEAL_LOCATIONS := $(or $(wildcard $(DATA_SRC_SUBDIR)/heal_locations.gen.json),$(DATA_SRC_SUBDIR)/heal_locations.json)
# END RPG2GBA GAME PROFILE

AUTO_GEN_TARGETS += $(DATA_SRC_SUBDIR)/heal_locations.h
$(DATA_SRC_SUBDIR)/heal_locations.h: $(RPG2GBA_HEAL_LOCATIONS) $(DATA_SRC_SUBDIR)/heal_locations.json.txt
	$(JSONPROC) $^ $@

$(C_BUILDDIR)/heal_location.o: c_dep += $(DATA_SRC_SUBDIR)/heal_locations.h

AUTO_GEN_TARGETS += include/constants/heal_locations.h
include/constants/heal_locations.h: $(RPG2GBA_HEAL_LOCATIONS) $(DATA_SRC_SUBDIR)/heal_locations.constants.json.txt
	$(JSONPROC) $^ $@
