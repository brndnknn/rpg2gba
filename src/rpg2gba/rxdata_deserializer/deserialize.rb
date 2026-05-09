# deserialize.rb — rxdata → JSON
#
# Usage:
#   ruby deserialize.rb <data_dir> <output_dir>
#
# Loads every Map*.rxdata file in data_dir using RPG Maker XP class stubs,
# dumps each map as JSON to output_dir/map_NNN.json.
# Also deserializes CommonEvents.rxdata and System.rxdata.
#
# This script is intentionally minimal. All interpretation of the resulting
# JSON happens downstream in Python.

raise NotImplementedError, "deserialize.rb is not yet implemented"
