#!/usr/bin/env ruby
# deserialize.rb — Marshal .dat / .rxdata → JSON
#
# Usage:
#   ruby deserialize.rb dat    <input.dat>  <output.json>
#   ruby deserialize.rb rxdata <data_dir>   <output_dir>     # Phase 3
#
# `dat` mode (Phase 2): loads one Marshal-format .dat and dumps a JSON view
# of the object graph. Unknown classes are stubbed automatically — only the
# RGSS primitives (Table/Color/Tone) and Essentials' OrderedHash have the
# custom `_load` implementations they need to Marshal-load correctly.
#
# `rxdata` mode is a stub for Phase 3; raises NotImplementedError.
#
# All interpretation of the resulting JSON happens downstream in Python.

require 'json'

# ---- AutoStub: synthesise classes on demand so Marshal.load succeeds ----

module AutoStub
  def self.const_missing(name)
    klass = Class.new do
      def initialize(*); end

      # Default `_load` for binary-payload classes (PBSpecies, etc.).
      # Most Essentials enum-like classes store a single integer in the
      # marshal payload; if not, callers get @_raw to inspect.
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

# Anything else (PBTrainer, PBSpecies, RPG::Map, ...) gets a stub.
Object.extend(AutoStub)

# ---- Object → JSON walker --------------------------------------------------

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
  raise NotImplementedError, "rxdata mode is Phase 3 work — not yet implemented"

else
  abort "usage:\n  deserialize.rb dat <input.dat> <output.json>\n  deserialize.rb rxdata <data_dir> <output_dir>"
end
