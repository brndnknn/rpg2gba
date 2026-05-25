#!/usr/bin/env ruby
# deserialize.rb — Marshal .dat / .rxdata → JSON
#
# Usage:
#   ruby deserialize.rb dat    <input.dat>  <output.json>
#   ruby deserialize.rb rxdata <data_dir>   <output_dir>
#
# `dat` mode (Phase 2): loads one Marshal-format .dat and dumps a JSON view of
# the object graph via the generic `jsonify` walker. Unknown classes are stubbed
# automatically; only the RGSS primitives (Table/Color/Tone) and Essentials'
# OrderedHash/WordArray have the custom `_load` implementations they need.
#
# `rxdata` mode (Phase 3): deserializes every Uranium map plus CommonEvents,
# System, and MapInfos into structured JSON. Map/event/page/command containers
# are shaped explicitly into the Phase 4 input contract (see PHASE3_PLAN.md §E1);
# leaf objects fall back to the generic walker. Commands are preserved RAW —
# {code, indent, parameters} verbatim, no continuation merging, no idiom
# recognition. All interpretation happens downstream (Phase 4 / Python).
#
# Fail-loud (CLAUDE.md §4.5): any map that fails to Marshal-load aborts the run
# with its filename — no silent skip.

require 'json'

# ---- AutoStub: synthesise classes on demand so Marshal.load succeeds ----

module AutoStub
  def self.const_missing(name)
    klass = Class.new do
      def initialize(*); end

      # Default `_load` for binary-payload classes (PBSpecies, etc.).
      def self._load(data)
        obj = allocate
        obj.instance_variable_set(:@_raw, data)
        obj
      end
    end
    const_set(name, klass)
    klass
  end
end

# RGSS primitives used by tile/system data. Reused from
# scripts/spike_dat_inventory.rb and scripts/recon_maps.rb.

class Table
  def self._load(bytes)
    obj = allocate
    _dim, xs, ys, zs, size = bytes.unpack('L5')
    obj.instance_variable_set(:@xsize, xs)
    obj.instance_variable_set(:@ysize, ys)
    obj.instance_variable_set(:@zsize, zs)
    obj.instance_variable_set(:@data, bytes[20, size * 2].unpack("s#{size}"))
    obj
  end
end

class Color
  def self._load(data)
    obj = allocate
    obj.instance_variable_set(:@rgba, data.unpack('d4'))
    obj
  end
end

class Tone
  def self._load(data)
    obj = allocate
    obj.instance_variable_set(:@rgba, data.unpack('d4'))
    obj
  end
end

# WordArray — Essentials' compact integer array (175__Compiler.rb:1829). Its
# _dump packs the ints with "v*" (little-endian uint16); _load unpacks them.
class WordArray
  def self._load(str)
    obj = allocate
    obj.instance_variable_set(:@a, str.unpack('v*'))
    obj
  end
end

# OrderedHash — Essentials predates modern Ruby's insertion-order guarantee
# and ships a custom Marshal format that dumps `[keys, values]`.
# Source: reference/scripts_dump/044_Intl_Messages.rb:348-399.
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

# RPG Maker XP class graph used by maps/events/common-events/system.
# `Page` MUST be nested inside `Event` and `Condition`/`Graphic` inside `Page` —
# Marshal resolves the full constant path, and a flat layout silently misloads
# (a landmine paid for in scripts/recon_maps.rb). Marshal sets instance
# variables directly, so attr_accessors are documentation, not a load
# requirement. Any RPG::* class we forgot is auto-stubbed via const_missing so
# the generic walker can still dump it (System, MapInfo, ...).
module RPG
  def self.const_missing(name)
    klass = Class.new do
      def initialize(*); end
      def self._load(data)
        obj = allocate
        obj.instance_variable_set(:@_raw, data)
        obj
      end
    end
    const_set(name, klass)
    klass
  end

  class Map
    attr_accessor :tileset_id, :width, :height, :autoplay_bgm, :bgm,
                  :autoplay_bgs, :bgs, :encounter_list, :encounter_step,
                  :data, :events
  end

  class Event
    attr_accessor :id, :name, :x, :y, :pages

    class Page
      attr_accessor :condition, :graphic, :move_type, :move_speed,
                    :move_frequency, :move_route, :walk_anime, :step_anime,
                    :direction_fix, :through, :always_on_top, :trigger, :list

      class Condition
        attr_accessor :switch1_valid, :switch2_valid, :variable1_valid,
                      :variable2_valid, :self_switch_valid, :switch1_id,
                      :switch2_id, :variable1_id, :variable1_value,
                      :variable2_id, :variable2_value, :self_switch_ch
      end

      class Graphic
        attr_accessor :tile_id, :character_name, :character_hue, :direction,
                      :pattern, :opacity, :blend_type
      end
    end
  end

  class EventCommand
    attr_accessor :code, :indent, :parameters
  end

  class MoveRoute
    attr_accessor :repeat, :skippable, :list
  end

  class MoveCommand
    attr_accessor :code, :parameters
  end

  class CommonEvent
    attr_accessor :id, :name, :trigger, :switch_id, :list
  end

  class AudioFile
    attr_accessor :name, :volume, :pitch
  end

  BGM = BGS = ME = SE = AudioFile
end

# ---- Object → JSON walker (generic; used for leaf/aux objects) -------------

# JSON.generate refuses arbitrary objects, so walk the graph and convert
# everything to JSON-friendly primitives. Custom classes are tagged with
# `__class__` so downstream Python knows what shape it's looking at.

def jsonify(obj, seen = {}.compare_by_identity)
  return '<cycle>' if seen[obj]

  case obj
  when nil, true, false, Integer, Float, String, Symbol
    obj.is_a?(Symbol) ? obj.to_s : obj
  when Array
    seen[obj] = true
    result = obj.map { |v| jsonify(v, seen) }
    seen.delete(obj)
    result
  when Hash
    seen[obj] = true
    result = {}
    obj.each { |k, v| result[k.to_s] = jsonify(v, seen) }
    result['__class__'] = obj.class.name if obj.class != Hash
    seen.delete(obj)
    result
  when Table
    {
      '__class__' => 'Table',
      'xsize' => obj.instance_variable_get(:@xsize),
      'ysize' => obj.instance_variable_get(:@ysize),
      'zsize' => obj.instance_variable_get(:@zsize),
      'data'  => obj.instance_variable_get(:@data),
    }
  when Color, Tone
    {
      '__class__' => obj.class.name,
      'rgba' => obj.instance_variable_get(:@rgba),
    }
  else
    seen[obj] = true
    record = { '__class__' => (obj.class.name || 'Stub') }
    obj.instance_variables.each do |v|
      key = v.to_s.sub(/^@/, '')
      record[key] = jsonify(obj.instance_variable_get(v), seen)
    end
    seen.delete(obj)
    record
  end
end

# ---- rxdata shaping (Phase 3 — the Phase 4 input contract, PHASE3_PLAN §E1) -

def iv(obj, name)
  obj.nil? ? nil : obj.instance_variable_get(name)
end

def shape_audio(a)
  return nil if a.nil?
  { 'name' => iv(a, :@name), 'volume' => iv(a, :@volume), 'pitch' => iv(a, :@pitch) }
end

def shape_table(t)
  return nil if t.nil?
  {
    'xsize' => iv(t, :@xsize), 'ysize' => iv(t, :@ysize), 'zsize' => iv(t, :@zsize),
    'data'  => iv(t, :@data),
  }
end

# A command is preserved RAW: code + indent + parameters verbatim. Parameters
# may contain RMXP objects (MoveRoute, AudioFile, Color, ...) so route them
# through the generic walker — but never merge or reinterpret commands (E1).
def shape_command(c)
  { 'code' => iv(c, :@code), 'indent' => iv(c, :@indent),
    'parameters' => jsonify(iv(c, :@parameters)) }
end

def shape_move_command(c)
  { 'code' => iv(c, :@code), 'parameters' => jsonify(iv(c, :@parameters)) }
end

def shape_move_route(r)
  return nil if r.nil?
  { 'repeat' => iv(r, :@repeat), 'skippable' => iv(r, :@skippable),
    'list' => (iv(r, :@list) || []).map { |mc| shape_move_command(mc) } }
end

# Condition/graphic: dump every ivar generically (their fields are all scalars
# in RMXP). Keeps us robust to version drift in which condition fields exist.
def shape_ivars(obj)
  return nil if obj.nil?
  h = {}
  obj.instance_variables.each { |v| h[v.to_s.sub(/^@/, '')] = jsonify(obj.instance_variable_get(v)) }
  h
end

def shape_page(p)
  {
    'condition' => shape_ivars(iv(p, :@condition)),
    'graphic' => shape_ivars(iv(p, :@graphic)),
    'move_type' => iv(p, :@move_type),
    'move_speed' => iv(p, :@move_speed),
    'move_frequency' => iv(p, :@move_frequency),
    'move_route' => shape_move_route(iv(p, :@move_route)),
    'walk_anime' => iv(p, :@walk_anime),
    'step_anime' => iv(p, :@step_anime),
    'direction_fix' => iv(p, :@direction_fix),
    'through' => iv(p, :@through),
    'always_on_top' => iv(p, :@always_on_top),
    'trigger' => iv(p, :@trigger),
    'list' => (iv(p, :@list) || []).map { |c| shape_command(c) },
  }
end

def shape_event(ev)
  {
    'id' => iv(ev, :@id), 'name' => iv(ev, :@name),
    'x' => iv(ev, :@x), 'y' => iv(ev, :@y),
    'pages' => (iv(ev, :@pages) || []).map { |p| shape_page(p) },
  }
end

def shape_map(map, map_id)
  events = iv(map, :@events) || {}
  # RMXP stores events as Hash{id => Event}; emit a list sorted by id for a
  # stable, idempotent diff.
  sorted = events.keys.sort.map { |k| shape_event(events[k]) }
  {
    'map_id' => map_id,
    'tileset_id' => iv(map, :@tileset_id),
    'width' => iv(map, :@width),
    'height' => iv(map, :@height),
    'autoplay_bgm' => iv(map, :@autoplay_bgm),
    'bgm' => shape_audio(iv(map, :@bgm)),
    'autoplay_bgs' => iv(map, :@autoplay_bgs),
    'bgs' => shape_audio(iv(map, :@bgs)),
    'encounter_list' => jsonify(iv(map, :@encounter_list)),
    'encounter_step' => iv(map, :@encounter_step),
    'tiles' => shape_table(iv(map, :@data)),
    'events' => sorted,
  }
end

def shape_common_event(ce)
  return nil if ce.nil?
  {
    'id' => iv(ce, :@id), 'name' => iv(ce, :@name),
    'trigger' => iv(ce, :@trigger), 'switch_id' => iv(ce, :@switch_id),
    'list' => (iv(ce, :@list) || []).map { |c| shape_command(c) },
  }
end

def write_json(path, obj)
  File.write(path, JSON.pretty_generate(obj) + "\n")
end

# Marshal resolves a class's full constant path at the C level and does NOT
# trigger Ruby's `const_missing` for *nested* names (RPG::System,
# RPG::System::Words, ...) the way it does for top-level ones. So load
# leniently: on "undefined class/module X::Y", synthesise the missing
# constants as stub classes and retry. Each retry defines one more level, so a
# deep path converges in a few passes.
def marshal_load_lenient(bytes)
  Marshal.load(bytes)
rescue ArgumentError => e
  m = e.message.match(%r{undefined class/module ([\w:]+)})
  raise unless m
  parent = Object
  m[1].split('::').each do |part|
    parent = if parent.const_defined?(part, false)
               parent.const_get(part, false)
             else
               parent.const_set(part, Class.new { def initialize(*); end })
             end
  end
  retry
end

def run_rxdata(data_dir, out_dir)
  abort "data dir not found: #{data_dir}" unless Dir.exist?(data_dir)
  maps_out = File.join(out_dir, 'maps')
  require 'fileutils'
  FileUtils.mkdir_p(maps_out)

  map_files = Dir.glob(File.join(data_dir, 'Map[0-9]*.rxdata')).sort
  abort "no Map*.rxdata found in #{data_dir}" if map_files.empty?

  count = 0
  map_files.each do |path|
    base = File.basename(path, '.rxdata')      # e.g. "Map007"
    map_id = base.sub('Map', '').to_i
    begin
      map = marshal_load_lenient(File.binread(path))
    rescue => e
      abort "FAILED to load #{path}: #{e.class}: #{e.message}"
    end
    write_json(File.join(maps_out, "#{base}.json"), shape_map(map, map_id))
    count += 1
  end

  # CommonEvents.rxdata → array of RPG::CommonEvent (index 0 is nil).
  ce_path = File.join(data_dir, 'CommonEvents.rxdata')
  if File.exist?(ce_path)
    ces = marshal_load_lenient(File.binread(ce_path))
    shaped = ces.map { |ce| shape_common_event(ce) }.compact
    write_json(File.join(out_dir, 'common_events.json'), shaped)
  end

  # System.rxdata → RPG::System (switches/variables name arrays + much more).
  sys_path = File.join(data_dir, 'System.rxdata')
  if File.exist?(sys_path)
    sys = marshal_load_lenient(File.binread(sys_path))
    write_json(File.join(out_dir, 'system.json'), jsonify(sys))
  end

  # MapInfos.rxdata → Hash{id => RPG::MapInfo} (names + tree, for Phase 5).
  mi_path = File.join(data_dir, 'MapInfos.rxdata')
  if File.exist?(mi_path)
    mi = marshal_load_lenient(File.binread(mi_path))
    write_json(File.join(out_dir, 'map_infos.json'), jsonify(mi))
  end

  puts "wrote #{count} maps + common_events/system/map_infos to #{out_dir}"
end

# Anything else (PBTrainer, PBSpecies, ...) gets a stub.
Object.extend(AutoStub)

# ---- CLI dispatch ----------------------------------------------------------

mode, *rest = ARGV
case mode
when 'dat'
  input, output = rest
  abort 'usage: deserialize.rb dat <input.dat> <output.json>' unless input && output
  abort "input not found: #{input}" unless File.exist?(input)

  obj = Marshal.load(File.binread(input))
  File.write(output, JSON.pretty_generate(jsonify(obj)) + "\n")
  puts "wrote #{output} (#{File.size(output)} bytes)"

when 'rxdata'
  data_dir, out_dir = rest
  abort 'usage: deserialize.rb rxdata <data_dir> <output_dir>' unless data_dir && out_dir
  run_rxdata(data_dir, out_dir)

else
  abort "usage:\n  deserialize.rb dat <input.dat> <output.json>\n  deserialize.rb rxdata <data_dir> <output_dir>"
end
