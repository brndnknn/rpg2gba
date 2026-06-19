# Map JSON data

# Inputs
MAPS_DIR = $(DATA_ASM_SUBDIR)/maps
LAYOUTS_DIR = $(DATA_ASM_SUBDIR)/layouts

# BEGIN URANIUM PATHFINDER SLICE — overlay manifests (rpg2gba). The assembler writes
# *.gen.json (vendored upstream maps/layouts + the Uranium slice, gitignored); when
# present the build reads those, else the pristine upstream files. Keeps
# data/maps/map_groups.json + data/layouts/layouts.json byte-for-byte upstream.
# $(wildcard) resolves at parse time; the assembler runs before make. See
# engine/RPG2GBA_VENDOR.md. Revert these two vars + their uses below to restore stock.
URANIUM_MAP_GROUPS := $(or $(wildcard $(MAPS_DIR)/map_groups.gen.json),$(MAPS_DIR)/map_groups.json)
URANIUM_LAYOUTS    := $(or $(wildcard $(LAYOUTS_DIR)/layouts.gen.json),$(LAYOUTS_DIR)/layouts.json)
# END URANIUM PATHFINDER SLICE

# Outputs
MAPS_OUTDIR := $(MAPS_DIR)
LAYOUTS_OUTDIR := $(LAYOUTS_DIR)
INCLUDECONSTS_OUTDIR := include/constants

AUTO_GEN_TARGETS += $(INCLUDECONSTS_OUTDIR)/map_groups.h
AUTO_GEN_TARGETS += $(INCLUDECONSTS_OUTDIR)/layouts.h
AUTO_GEN_TARGETS += $(INCLUDECONSTS_OUTDIR)/map_event_ids.h
AUTO_GEN_TARGETS += $(DATA_SRC_SUBDIR)/map_group_count.h

MAP_DIRS := $(dir $(wildcard $(MAPS_DIR)/*/map.json))
MAP_CONNECTIONS := $(patsubst $(MAPS_DIR)/%/,$(MAPS_DIR)/%/connections.inc,$(MAP_DIRS))
MAP_EVENTS := $(patsubst $(MAPS_DIR)/%/,$(MAPS_DIR)/%/events.inc,$(MAP_DIRS))
MAP_HEADERS := $(patsubst $(MAPS_DIR)/%/,$(MAPS_DIR)/%/header.inc,$(MAP_DIRS))
MAP_JSONS := $(patsubst $(MAPS_DIR)/%/,$(MAPS_DIR)/%/map.json,$(MAP_DIRS))

$(DATA_ASM_BUILDDIR)/maps.o: $(DATA_ASM_SUBDIR)/maps.s $(LAYOUTS_DIR)/layouts.inc $(LAYOUTS_DIR)/layouts_table.inc $(MAPS_DIR)/headers.inc $(MAPS_DIR)/groups.inc $(MAPS_DIR)/connections.inc $(MAP_CONNECTIONS) $(MAP_HEADERS)
	$(PREPROC) $< charmap.txt | $(CPP) $(CPPFLAGS) -I include - | $(PREPROC) -ie $< charmap.txt | $(AS) $(ASFLAGS) -o $@
$(DATA_ASM_BUILDDIR)/map_events.o: $(DATA_ASM_SUBDIR)/map_events.s $(MAPS_DIR)/events.inc $(MAP_EVENTS)
	$(PREPROC) $< charmap.txt | $(CPP) $(CPPFLAGS) -I include - | $(PREPROC) -ie $< charmap.txt | $(AS) $(ASFLAGS) -o $@

$(MAPS_OUTDIR)/%/header.inc $(MAPS_OUTDIR)/%/events.inc $(MAPS_OUTDIR)/%/connections.inc: $(MAPS_DIR)/%/map.json $(INCLUDECONSTS_OUTDIR)/map_groups.h
	$(MAPJSON) map emerald $< $(URANIUM_LAYOUTS) $(@D)


$(MAPS_OUTDIR)/connections.inc $(MAPS_OUTDIR)/groups.inc $(MAPS_OUTDIR)/events.inc $(MAPS_OUTDIR)/headers.inc $(INCLUDECONSTS_OUTDIR)/map_groups.h $(DATA_SRC_SUBDIR)/map_group_count.h: $(URANIUM_MAP_GROUPS) $(MAP_JSONS) .map_version
	@$(MAPJSON) groups $(MAP_VERSION) $(filter-out .map_version,$^) $(MAPS_OUTDIR) $(INCLUDECONSTS_OUTDIR)
	@echo "$(MAPJSON) groups $(MAP_VERSION) $(URANIUM_MAP_GROUPS) <MAP_JSONS> $(MAPS_OUTDIR) $(INCLUDECONSTS_OUTDIR)"

$(LAYOUTS_OUTDIR)/layouts.inc $(LAYOUTS_OUTDIR)/layouts_table.inc $(INCLUDECONSTS_OUTDIR)/layouts.h: $(URANIUM_LAYOUTS) .map_version
	$(MAPJSON) layouts $(MAP_VERSION) $< $(LAYOUTS_OUTDIR) $(INCLUDECONSTS_OUTDIR)

# Generate constants for map events, which depend on data that's distributed across the map.json files.
# There's a lot of map.json files, so we print an abbreviated output with echo.
$(INCLUDECONSTS_OUTDIR)/map_event_ids.h: $(MAP_JSONS)
	@$(MAPJSON) event_constants emerald $^ $(INCLUDECONSTS_OUTDIR)/map_event_ids.h
	@echo "$(MAPJSON) event_constants emerald <MAP_JSONS> $(INCLUDECONSTS_OUTDIR)/map_event_ids.h"

.map_version : FORCE
	@(echo "$(MAP_VERSION)" | cmp $@ -) || echo "$(MAP_VERSION)" > .map_version

FORCE:
.PHONY : FORCE
