#!/usr/bin/env ruby
# dump_messages.rb — extract Uranium display strings from messages.dat
#
# Essentials routes all UI-visible strings (species names, move descriptions,
# etc.) through `MessageTypes`, which Marshal.dumps a 2D array to messages.dat.
# The custom-binary .dat files (dexdata.dat, moves.dat, items.dat) carry only
# numeric IDs — names live here.
#
# Output: per-type JSON sidecars under reference/. Format:
#   { "<id>": "<string>", ... }
#
# These JSONs are committed to git (small, hand-reviewable, treated as
# reference data per PHASE2_PLAN.md §2.0).
#
# Usage:
#   RPG2GBA_URANIUM_SRC=/path/to/_unpacked ruby scripts/dump_messages.rb [out_dir]
#   (out_dir defaults to reference/)

require 'json'

# Essentials predates modern Ruby's Hash-preserves-insertion-order guarantee
# and ships its own OrderedHash with a custom Marshal format.
# Source: reference/scripts_dump/044_Intl_Messages.rb:348-399.
# `_dump` serialised `Marshal.dump([keys, values])`; `_load` does the inverse.
class OrderedHash < Hash
  def self._load(string)
    ret = new
    keys, values = Marshal.load(string)
    keys.each_with_index { |k, i| ret[k] = values[i] }
    ret
  end

  def _dump(_depth = 100)
    Marshal.dump([keys, values])
  end
end

uranium_src = ENV['RPG2GBA_URANIUM_SRC'] or abort 'RPG2GBA_URANIUM_SRC not set'
out_dir     = ARGV[0] || File.join(__dir__, '..', 'reference')
src_path    = File.join(uranium_src, 'Data', 'messages.dat')

abort "messages.dat not found at #{src_path}" unless File.exist?(src_path)
Dir.mkdir(out_dir) unless Dir.exist?(out_dir)

# Per scripts_dump/044_Intl_Messages.rb, line 642+.
TYPE_TO_FILE = {
  1  => 'species_names',
  2  => 'species_kinds',
  3  => 'species_pokedex',
  4  => 'species_form_names',
  5  => 'move_names',
  6  => 'move_descriptions',
  7  => 'item_names',
  8  => 'item_descriptions',
  9  => 'ability_names',
  10 => 'ability_descriptions',
  11 => 'type_names',
  12 => 'trainer_type_names',
  13 => 'trainer_names',
  14 => 'trainer_begin_speech',
  15 => 'trainer_end_speech_win',
  16 => 'trainer_end_speech_lose',
  17 => 'region_names',
  18 => 'place_names',
  19 => 'place_descriptions',
  20 => 'map_names',
  21 => 'phone_messages',
  22 => 'script_texts',
}.freeze

messages = Marshal.load(File.binread(src_path))
unless messages.is_a?(Array)
  abort "expected messages.dat to deserialize as Array, got #{messages.class}"
end

written = []
TYPE_TO_FILE.each do |type_id, name|
  bucket = messages[type_id]
  next if bucket.nil? || (bucket.respond_to?(:empty?) && bucket.empty?)

  # Bucket is either an Array indexed by id, or a Hash of id => string.
  pairs =
    if bucket.is_a?(Array)
      bucket.each_with_index.map { |s, i| [i, s] }.reject { |_, s| s.nil? }
    elsif bucket.is_a?(Hash)
      bucket.to_a
    else
      warn "type #{type_id} (#{name}): unexpected class #{bucket.class}, skipping"
      next
    end

  payload = pairs.to_h { |id, s| [id.to_s, s.to_s.force_encoding('windows-1252').encode('utf-8', invalid: :replace, undef: :replace)] }
  out_path = File.join(out_dir, "#{name}.json")
  File.write(out_path, JSON.pretty_generate(payload) + "\n")
  written << "#{name}.json (#{payload.size} entries)"
end

puts "wrote #{written.size} sidecars to #{out_dir}/:"
written.each { |w| puts "  #{w}" }
