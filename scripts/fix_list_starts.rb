#!/usr/bin/env ruby
# Measure or fix ordered-list items that kramdown renders with a different
# number from the one printed in the Markdown.
#
# The site is built by Jekyll with kramdown, which ignores every number in an
# ordered list except as a marker: it renders the first item as 1 and counts
# up from there. So IS_009's catalogue `16.  Sel.` came out as `1.`; every
# numbered note that follows an unindented paragraph starts a new list and
# renders as `1.`; and a list whose source skips numbers (`12.` then `15.`)
# carries on as 13. GitHub's own Markdown preview honours the numbers, so
# none of this shows there.
#
# The fix is a block IAL on its own line before the item whose number is
# wrong, with a blank line above it:
#
#     {: start="16"}
#     16.  Sel. ...
#
# Before a first item it sets the list's start; before a later item it ends
# the list there and starts a new one at the printed number. Without the
# blank line kramdown attaches the IAL to the paragraph above instead. Items
# are found by kramdown itself, not by a regex, so a lazy continuation line
# or an indented paragraph can't make an IAL land inside an item. Each split
# changes the numbering after it, so the fix repeats until nothing is left.
#
# One case can't take an IAL: a list that begins on the same line as the
# list around it. kramdown reads `23. 1911. KM ...` as item 23 holding a list
# that starts at 1911 (and `6. - 1987. ...` as item 6 holding a bullet
# holding a list at 1987). The inner number is escaped (`1911\.`) instead,
# which renders as printed.
#
# Usage:
#   scripts/fix_list_starts.rb jons/IS_009.md          # measure
#   scripts/fix_list_starts.rb --fix jons/*.md         # rewrite in place
#   scripts/fix_list_starts.rb --fix --dry-run jons/*.md
#
# After --fix every file is re-parsed: every item must now render with its
# printed number, and the rendered text (tags and list-marker numbers
# stripped) must be unchanged. A file that fails either check is left alone
# and reported.

require 'kramdown'

OPTS = { input: 'GFM', hard_wrap: false }.freeze
ITEM_RE = /\A(\s*)(\d{1,9})[.)]\s/
# The inner number on a line holding nested markers: `23. 1911.`, `6. - 1987.`
NESTED_RE = /\A(\s*\d{1,9}[.)]\s+(?:[-*+]\s+)*)(\d{1,9})[.)]\s/
MAX_PASSES = 20

def render(src)
  Kramdown::Document.new(src, **OPTS)
end

# [line_index, printed, indent, nested, list_id] for each list item that
# renders with a number other than the one printed on its source line.
def mismatches(src)
  lines = src.split("\n", -1)
  out = []
  walk = lambda do |el, outer_loc|
    loc = el.options[:location]
    if el.type == :ol && loc
      start = (el.attr['start'] || 1).to_i
      el.children.each_with_index do |li, k|
        li_loc = k.zero? ? loc : li.options[:location]
        next unless li_loc

        line = lines[li_loc - 1].to_s
        nested = k.zero? && outer_loc == loc
        m = nested ? NESTED_RE.match(line) : ITEM_RE.match(line)
        next unless m

        printed = m[2].to_i
        out << [li_loc - 1, printed, nested ? nil : m[1], nested, el.object_id] if printed != start + k
      end
      el.children.each { |c| walk.call(c, loc) }
    else
      el.children.each { |c| walk.call(c, %i[li ul].include?(el.type) ? outer_loc : nil) }
    end
  end
  walk.call(render(src).root, nil)
  out
end

# One pass: escape nested same-line numbers, then insert an IAL before the
# first wrong item of each list. Only the first per list, because splitting
# there renumbers everything after it -- the next pass re-measures.
def fix_pass(src)
  lines = src.split("\n", -1)
  found = mismatches(src)
  found.select { |_, _, _, nested, _| nested }.each do |i, *|
    lines[i] = lines[i].sub(NESTED_RE) { "#{$1}#{$2}\\#{$~[0][-2]} " }
  end
  firsts = found.reject { |_, _, _, nested, _| nested }
                .group_by { |*, list_id| list_id }.values.map { |items| items.min_by(&:first) }
                .uniq(&:first)
  firsts.sort_by { |i, *| -i }.each do |i, n, indent, *|
    insert = ["#{indent}{: start=\"#{n}\"}"]
    insert.unshift('') if i.positive? && !lines[i - 1].strip.empty?
    lines.insert(i, *insert)
  end
  lines.join("\n")
end

def fix(src)
  MAX_PASSES.times do
    break if mismatches(src).empty?

    nxt = fix_pass(src)
    break if nxt == src

    src = nxt
  end
  src
end

# Rendered text with tags stripped. Numbers followed by `.`/`)` are dropped
# because an escaped nested number (`1911\.`) now renders where kramdown
# used to swallow it as a list marker; every other character must match.
def text_of(src)
  render(src).to_html.gsub(/<[^>]*>/, '').gsub(/\b\d{1,9}[.)](?=\s)/, '').gsub(/\s+/, ' ').strip
end

if $PROGRAM_NAME == __FILE__
  do_fix = ARGV.delete('--fix')
  dry_run = ARGV.delete('--dry-run')
  abort "usage: #{$PROGRAM_NAME} [--fix [--dry-run]] FILE..." if ARGV.empty?

  total = 0
  failures = 0
  ARGV.each do |path|
    src = File.read(path, encoding: 'utf-8')
    found = mismatches(src)
    next if found.empty?

    total += found.size
    puts "#{path}: #{found.size} item(s) rendered with the wrong number, at line(s) " +
         found.map { |i, n, _, nested, _| "#{i + 1} (#{n}#{nested ? ', nested' : ''})" }.join(', ')
    next unless do_fix

    fixed = fix(src)
    left = mismatches(fixed)
    same = text_of(fixed) == text_of(src)
    unless left.empty? && same
      failures += 1
      warn "  NOT FIXED #{path}: #{left.size} still wrong, text #{same ? 'unchanged' : 'CHANGED'}"
      next
    end
    File.write(path, fixed, encoding: 'utf-8') unless dry_run
  end
  puts "total: #{total}#{failures.positive? ? ", #{failures} file(s) not fixed" : ''}"
  exit(failures.positive? || (total.positive? && !(do_fix && !dry_run)) ? 1 : 0)
end
