#!/usr/bin/env ruby
# Phase 0.3 — Map inventory
#
# Counts events per map, estimates total event commands, and flags maps with
# complex events (many commands or unknown command codes).
#
# Usage:
#   RPG2GBA_URANIUM_SRC=/path/to/uranium ruby scripts/recon_maps.rb

require 'set'

uranium_src = ENV['RPG2GBA_URANIUM_SRC'] or abort 'RPG2GBA_URANIUM_SRC not set'
data_dir    = File.join(uranium_src, 'Data')
out_path    = 'reference/map_inventory.md'

# --- RPG Maker XP class stubs ---
# Minimal enough for Marshal.load to succeed without the RMXP runtime.

class Table
  def marshal_load(data)
    _dim, @xsize, @ysize, @zsize, size = data.unpack('L5')
    @data = data[20..].unpack("s#{size}")
  end
  def [](x, y = 0, z = 0)
    @data[z.to_i * (@ysize || 1) * (@xsize || 1) + y.to_i * (@xsize || 1) + x.to_i] rescue 0
  end
end

class Color
  def marshal_load(data); @r, @g, @b, @a = data.unpack('D4'); end
end

class Tone
  def marshal_load(data); @r, @g, @b, @a = data.unpack('D4'); end
end

module RPG
  class Map
    attr_accessor :tileset_id, :width, :height, :autoplay_bgm, :bgm,
                  :autoplay_bgs, :bgs, :encounter_list, :encounter_step,
                  :data, :events
    def initialize; @events = {}; end
  end

  class Event
    attr_accessor :id, :name, :x, :y, :pages
    def initialize; @pages = []; end
  end

  class EventPage
    attr_accessor :condition, :graphic, :move_type, :move_speed, :move_frequency,
                  :move_route, :walk_anime, :step_anime, :direction_fix,
                  :through, :always_on_top, :trigger, :list
    def initialize; @list = []; end
  end

  class EventCommand
    attr_accessor :code, :indent, :parameters
    def initialize(code = 0, indent = 0, parameters = [])
      @code = code; @indent = indent; @parameters = parameters
    end
  end

  class MoveRoute
    attr_accessor :repeat, :skippable, :list
    def initialize; @list = []; end
  end

  class MoveCommand
    attr_accessor :code, :parameters
    def initialize(code = 0, parameters = []); @code = code; @parameters = parameters; end
  end

  class AudioFile
    attr_accessor :name, :volume, :pitch
    def initialize(name = '', volume = 80, pitch = 100)
      @name = name; @volume = volume; @pitch = pitch
    end
  end

  BGM = BGS = ME = SE = AudioFile

  class EventCondition
    attr_accessor :switch1_valid, :switch2_valid, :variable1_valid, :variable2_valid,
                  :self_switch_valid, :switch1_id, :switch2_id, :variable1_id,
                  :variable1_value, :variable2_id, :variable2_value, :self_switch_ch
    def initialize
      @switch1_valid = @switch2_valid = @variable1_valid =
        @variable2_valid = @self_switch_valid = false
    end
  end

  class EventGraphic
    attr_accessor :tile_id, :character_name, :character_hue, :direction,
                  :pattern, :opacity, :blend_type
    def initialize
      @tile_id = 0; @character_name = ''; @character_hue = 0
      @direction = 2; @pattern = 0; @opacity = 255; @blend_type = 0
    end
  end
end

# Command codes common in vanilla Essentials — not inherently complex.
COMMON_CODES = Set.new([
  0, 101, 401, 102, 402, 403, 404, 111, 411, 112, 412, 113, 115,
  117, 118, 119, 121, 122, 123, 124, 125, 126, 127, 128, 129,
  131, 132, 133, 134, 135, 136, 201, 202, 203, 204, 205, 206,
  207, 208, 209, 210, 211, 212, 213, 214, 221, 222, 223, 224,
  225, 231, 232, 233, 234, 235, 236, 241, 242, 243, 244, 245,
  246, 247, 248, 249, 250, 251, 261, 281, 282, 283, 284, 285,
  301, 302, 303, 311, 312, 313, 314, 315, 316, 317, 318, 319,
  320, 321, 322, 331, 332, 333, 334, 335, 336, 340, 341, 342,
  351, 352, 353, 354, 355, 655,
])

COMPLEX_THRESHOLD = 30  # pages with more commands than this get flagged

# --- Process maps ---
map_files = Dir.glob(File.join(data_dir, 'Map[0-9]*.rxdata')).sort
abort "No map files found in #{data_dir}" if map_files.empty?

results     = []
total_events = 0
total_pages  = 0

map_files.each do |path|
  map_id = File.basename(path, '.rxdata').sub('Map', '').to_i
  begin
    map = Marshal.load(File.binread(path))

    event_count = map.events.size
    total_events += event_count

    page_data = map.events.values.flat_map do |ev|
      ev.pages.map do |page|
        cmds  = page.list || []
        codes = cmds.map(&:code)
        { commands: cmds.size, unknown: codes.reject { |c| COMMON_CODES.include?(c) }.uniq }
      end
    end

    total_pages   += page_data.size
    max_cmds       = page_data.map { |p| p[:commands] }.max || 0
    all_unknown    = page_data.flat_map { |p| p[:unknown] }.uniq.sort
    complex        = max_cmds >= COMPLEX_THRESHOLD || all_unknown.any?

    results << { id: map_id, events: event_count, pages: page_data.size,
                 max_cmds: max_cmds, unknown: all_unknown, complex: complex }
  rescue => e
    results << { id: map_id, error: e.message }
  end
end

# --- Write output ---
complex_maps = results.select { |r| r[:complex] && !r[:error] }

lines = [
  '# Map Inventory',
  '',
  "Total maps: #{map_files.size}",
  "Total events: #{total_events}",
  "Total pages: #{total_pages}",
  "Complex maps (≥#{COMPLEX_THRESHOLD} commands in a page, or unknown codes): #{complex_maps.size}",
  '',
  '## All maps',
  '',
  '| Map ID | Events | Pages | Max cmds/page | Unknown codes | Complex |',
  '|---|---|---|---|---|---|',
]

results.each do |r|
  if r[:error]
    lines << "| #{r[:id]} | — | — | — | — | ERROR: #{r[:error]} |"
  else
    unknown_str = r[:unknown].empty? ? '' : r[:unknown].join(', ')
    flag        = r[:complex] ? '⚠' : ''
    lines << "| #{r[:id]} | #{r[:events]} | #{r[:pages]} | #{r[:max_cmds]} | #{unknown_str} | #{flag} |"
  end
end

lines += [
  '',
  '## Complex maps',
  '',
]
if complex_maps.empty?
  lines << 'None.'
else
  complex_maps.each do |r|
    lines << "- **Map #{r[:id]}**: #{r[:events]} events, max #{r[:max_cmds]} cmds/page" \
             "#{r[:unknown].any? ? ", unknown codes: #{r[:unknown].join(', ')}" : ''}"
  end
end

File.write(out_path, lines.join("\n") + "\n")
puts "Written: #{out_path}"
