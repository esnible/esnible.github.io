#!/usr/bin/env ruby
# Compare the pipe tables written in each Markdown file with the tables kramdown
# (the site's renderer) actually produces, and list the files that disagree.
#
# A table is counted in the Markdown by its `|---|` delimiter row.
#   fewer rendered -- a table was swallowed into a paragraph; usually a line
#                     touching the table, which scripts/fix_table_blank_lines.py fixes
#   more rendered  -- kramdown, unlike GitHub, makes a table from any block of
#                     `|` lines even without a delimiter row
#
# Usage:
#     bundle exec ruby scripts/check_tables.rb            # every jons/*.md
#     bundle exec ruby scripts/check_tables.rb jons/ONS_140.md

require 'kramdown'
require 'kramdown-parser-gfm'

files = ARGV.empty? ? Dir['jons/*.md'].sort : ARGV
bad = 0
files.each do |f|
  src = File.read(f, encoding: 'utf-8')
  written = src.lines.count { |l| l =~ /^\|\s*:?-{3,}/ }
  rendered = Kramdown::Document.new(src, input: 'GFM').to_html.scan('<table').size
  next if written == rendered
  bad += 1
  kind = rendered < written ? 'FEWER' : 'MORE '
  puts "#{kind} #{f}: #{written} written, #{rendered} rendered"
end
puts "#{bad} of #{files.size} file(s) disagree"
exit(bad.zero? ? 0 : 1)
