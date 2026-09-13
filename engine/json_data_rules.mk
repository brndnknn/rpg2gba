# JSON files are run through jsonproc, which is a tool that converts JSON data to an output file
# based on an Inja template. https://github.com/pantor/inja

AUTO_GEN_TARGETS += $(DATA_SRC_SUBDIR)/region_map/region_map_entries.h
$(DATA_SRC_SUBDIR)/region_map/region_map_entries.h: $(DATA_SRC_SUBDIR)/region_map/region_map_sections.json $(DATA_SRC_SUBDIR)/region_map/region_map_sections.json.txt
	$(JSONPROC) $^ $@

$(C_BUILDDIR)/region_map.o: c_dep += $(DATA_SRC_SUBDIR)/region_map/region_map_entries.h

AUTO_GEN_TARGETS += include/constants/region_map_sections.h
include/constants/region_map_sections.h: $(DATA_SRC_SUBDIR)/region_map/region_map_sections.json $(DATA_SRC_SUBDIR)/region_map/region_map_sections.constants.json.txt
	$(JSONPROC) $^ $@

# BEGIN URANIUM PATHFINDER SLICE — overlay heal_locations.json (rpg2gba). The
# assembler writes heal_locations.gen.json (vendored upstream entries + the
# Uranium white-out respawns, appended in array order so HEAL_LOCATION_* ids
# for upstream entries never renumber), gitignored; when present the build reads
# that, else the pristine upstream file. Mirrors URANIUM_MAP_GROUPS /
# URANIUM_LAYOUTS in map_data_rules.mk and URANIUM_WILD_ENCOUNTERS in Makefile.
# Keeps src/data/heal_locations.json byte-for-byte upstream. See RPG2GBA_VENDOR.md.
# Revert this var + its two uses below to restore stock.
URANIUM_HEAL_LOCATIONS := $(or $(wildcard $(DATA_SRC_SUBDIR)/heal_locations.gen.json),$(DATA_SRC_SUBDIR)/heal_locations.json)
# END URANIUM PATHFINDER SLICE

AUTO_GEN_TARGETS += $(DATA_SRC_SUBDIR)/heal_locations.h
$(DATA_SRC_SUBDIR)/heal_locations.h: $(URANIUM_HEAL_LOCATIONS) $(DATA_SRC_SUBDIR)/heal_locations.json.txt
	$(JSONPROC) $^ $@

$(C_BUILDDIR)/heal_location.o: c_dep += $(DATA_SRC_SUBDIR)/heal_locations.h

AUTO_GEN_TARGETS += include/constants/heal_locations.h
include/constants/heal_locations.h: $(URANIUM_HEAL_LOCATIONS) $(DATA_SRC_SUBDIR)/heal_locations.constants.json.txt
	$(JSONPROC) $^ $@
