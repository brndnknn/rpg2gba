#!/usr/bin/env ruby
# Phase 2 spike — identify contents of each .dat file
#
# Prints top-level class, size/shape, and sample records for every .dat.
# Answers three open questions:
#   1. Which file holds the species table?
#   2. Does trainers.dat contain any TPSHADOW=true rows?
#   3. What is tmpbs.dat?
#
# Usage:
#   RPG2GBA_URANIUM_SRC=/path/to/_unpacked ruby scripts/spike_dat_inventory.rb

uranium_src = ENV['RPG2GBA_URANIUM_SRC'] or abort 'RPG2GBA_URANIUM_SRC not set'
data_dir    = File.join(uranium_src, 'Data')

# Stub every unknown constant so Marshal.load doesn't raise NameError.
# We only care about structure, not behaviour.
module AutoStub
  def self.const_missing(name)
    klass = Class.new do
      def initialize(*); end
      def self._load(data)
        obj = allocate
        obj.instance_variable_set(:@_raw, data)
        obj
      end
      def inspect
        vars = instance_variables.map { |v| "#{v}=#{instance_variable_get(v).inspect}" }.join(', ')
        "#<#{self.class.name || 'Stub'} #{vars}>"
      end
    end
    const_set(name, klass)
    klass
  end
end

# Minimal RMXP primitives needed for map/table data (reused from recon_maps.rb).
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
  def inspect; "#<Table #{@xsize}x#{@ysize}x#{@zsize}>"; end
end

class Color
  def self._load(data); obj = allocate; obj.instance_variable_set(:@rgba, data.unpack('d4')); obj; end
end

class Tone
  def self._load(data); obj = allocate; obj.instance_variable_set(:@rgba, data.unpack('d4')); obj; end
end

# Catch-all for Essentials classes (PBSpecies, PBMoves, etc.)
Object.extend(AutoStub)

# --- helpers ---

def describe(val, depth = 0)
  indent = '  ' * depth
  case val
  when Array
    sample = val.first(3).map { |v| describe(v, depth + 1) }
    "Array[#{val.size}] first 3:\n#{sample.map { |s| "#{indent}  #{s}" }.join("\n")}"
  when Hash
    sample = val.first(3).map { |k, v| "#{k.inspect} => #{describe(v, depth + 1)}" }
    "Hash[#{val.size}] first 3:\n#{sample.map { |s| "#{indent}  #{s}" }.join("\n")}"
  when String
    val.length > 80 ? val[0, 80].inspect + '…' : val.inspect
  when NilClass, TrueClass, FalseClass, Numeric, Symbol
    val.inspect
  else
    cls = val.class.name || val.class.to_s
    vars = val.instance_variables.first(6).map do |v|
      "#{v}=#{describe(val.instance_variable_get(v), depth + 1)}"
    end.join(', ')
    "#<#{cls} #{vars}>"
  end
end

# Files to probe — everything except save data, localisation bundles, and map files
PROBE = %w[
  attacksRS.dat
  btpokemon.dat
  bttrainers.dat
  connections.dat
  dexdata.dat
  eggEmerald.dat
  encounters.dat
  evolutions.dat
  items.dat
  messages.dat
  metadata.dat
  metrics.dat
  moves.dat
  phone.dat
  regionals.dat
  shadowmoves.dat
  tm.dat
  tmpbs.dat
  townmap.dat
  trainerlists.dat
  trainers.dat
  trainertypes.dat
  tutor.dat
  types.dat
]

puts "=== .dat spike — #{Time.now} ===\n\n"

PROBE.each do |fname|
  path = File.join(data_dir, fname)
  unless File.exist?(path)
    puts "#{fname}: NOT FOUND\n\n"
    next
  end

  begin
    raw  = File.binread(path)
    data = Marshal.load(raw)
    puts "#{fname}"
    puts "  class: #{data.class}"
    puts "  #{describe(data)}"
  rescue => e
    puts "#{fname}: ERROR — #{e.class}: #{e.message}"
  end
  puts
end

# --- Targeted: TPSHADOW check in trainers.dat ---
puts "=== TPSHADOW check in trainers.dat ===\n"
path = File.join(data_dir, 'trainers.dat')
if File.exist?(path)
  begin
    trainers = Marshal.load(File.binread(path))
    shadow_count = 0
    if trainers.is_a?(Array)
      trainers.each do |t|
        next unless t.respond_to?(:instance_variables)
        t.instance_variables.each do |v|
          val = t.instance_variable_get(v)
          if val.is_a?(Array)
            val.each do |mon|
              next unless mon.respond_to?(:instance_variables)
              mon.instance_variables.each do |mv|
                if mv.to_s =~ /shadow/i || t.instance_variable_get(mv).to_s =~ /TPSHADOW/i
                  shadow_count += 1
                end
              end
            end
          end
          shadow_count += 1 if val.to_s =~ /TPSHADOW/i
        end
      end
    end
    puts "  Trainers: #{trainers.respond_to?(:size) ? trainers.size : 'N/A'}"
    puts "  TPSHADOW hits: #{shadow_count}"
  rescue => e
    puts "  ERROR — #{e.class}: #{e.message}"
  end
end

# --- Targeted: species count from regionals.dat ---
puts "\n=== regionals.dat species count ===\n"
path = File.join(data_dir, 'regionals.dat')
if File.exist?(path)
  begin
    reg = Marshal.load(File.binread(path))
    puts "  class: #{reg.class}"
    if reg.is_a?(Array)
      puts "  entries: #{reg.size}"
      puts "  sample[0]: #{reg[0].inspect}"
      puts "  sample[1]: #{reg[1].inspect}"
    elsif reg.is_a?(Hash)
      puts "  keys: #{reg.size}"
      reg.first(5).each { |k, v| puts "  #{k.inspect} => #{v.inspect}" }
    end
  rescue => e
    puts "  ERROR — #{e.class}: #{e.message}"
  end
end
