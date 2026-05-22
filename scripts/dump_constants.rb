#!/usr/bin/env ruby
# dump_constants.rb — extract PBSpecies/PBMoves/PBItems/PBAbilities internal names
#
# pbAddScript() in Compiler.rb stores the auto-generated constant classes (e.g.
# `class PBSpecies; ORCHYNX=1; RAPTORCH=3; ...; end`) in `Data/Constants.rxdata`
# as a list of [id, section_name, deflated_source] triples. We parse each
# class body's `<NAME> = <int>` lines into a JSON map per category.
#
# Output: per-section JSON sidecars under reference/. Format:
#   { "<id>": "<INTERNAL_NAME>", ... }
#
# These are the canonical source for `SPECIES_*`/`MOVE_*`/etc. constant minting
# in Phase 2. Committed (small reference data).
#
# Usage:
#   RPG2GBA_URANIUM_SRC=/path/to/_unpacked ruby scripts/dump_constants.rb [out_dir]

require 'json'
require 'zlib'

uranium_src = ENV['RPG2GBA_URANIUM_SRC'] or abort 'RPG2GBA_URANIUM_SRC not set'
out_dir     = ARGV[0] || File.join(__dir__, '..', 'reference')
src_path    = File.join(uranium_src, 'Data', 'Constants.rxdata')

abort "Constants.rxdata not found at #{src_path}" unless File.exist?(src_path)
Dir.mkdir(out_dir) unless Dir.exist?(out_dir)

# Sections we care about for Phase 2 / Phase 6.
WANTED = {
  'PBSpecies'   => 'species_internal_names',
  'PBMoves'     => 'move_internal_names',
  'PBItems'     => 'item_internal_names',
  'PBAbilities' => 'ability_internal_names',
  'PBTypes'     => 'type_internal_names',
  'PBTrainers'  => 'trainer_class_internal_names',
}.freeze

scripts = Marshal.load(File.binread(src_path))
unless scripts.is_a?(Array)
  abort "expected Constants.rxdata to deserialize as Array, got #{scripts.class}"
end

written = []
scripts.each do |entry|
  # Each entry is [id, section_name, deflated_source_bytes]
  _id, section_name, deflated = entry
  next unless WANTED.key?(section_name)

  source = Zlib::Inflate.inflate(deflated).force_encoding('windows-1252').encode('utf-8', invalid: :replace, undef: :replace)
  pairs = {}
  source.each_line do |line|
    line.strip!
    # Constant names are conventionally all-caps, but Uranium's PBS contains
    # author typos with stray lowercase letters (e.g. `POKeBALL=211`). Accept
    # any identifier so those ids aren't silently dropped (fail-loud downstream
    # depends on every shipped id having an internal name).
    if (m = line.match(/^([A-Za-z][A-Za-z0-9_]*)\s*=\s*(\d+)\s*$/))
      pairs[m[2]] = m[1]
    end
  end

  out_path = File.join(out_dir, "#{WANTED[section_name]}.json")
  File.write(out_path, JSON.pretty_generate(pairs) + "\n")
  written << "#{WANTED[section_name]}.json (#{pairs.size} entries from #{section_name})"
end

if written.empty?
  warn "found no wanted sections; sections in Constants.rxdata:"
  scripts.each { |_, name, _| warn "  #{name}" }
  exit 1
end

puts "wrote #{written.size} sidecars to #{out_dir}/:"
written.each { |w| puts "  #{w}" }
