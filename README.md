# esnible.github.io

This is a test of the Journal of the Oriental Numismatic Society, converted to Markdown (currently without images) and OCRed, then improved by Claude Code.

Currently these pages are hosted at https://esnible.github.io/

# Run locally without pushing

## Load dependencies

```bash
brew install chruby ruby-install
ruby-install ruby 3.1.2 # (The latest Ruby doesn't easily work with Jekyll)
bundle install
```

## View site

```bash
bundle exec jekyll serve
```

Browse to http://localhost:4000/

## How this repo is working

The web site https://www.orientalnumismaticsociety.org/jons/archive/ has the output of the Oriental Numismatic Society.  The text is somewhat searchable: an old version of Adobe did OCR long ago.

I'm not happy with the quality of the OCR on the oldest journals, so I used [pdfmd](https://github.com/M1ck4/pdfmd) to create Markdown without images of each file.  For example:

```bash
pdfmd ~/personal/src/ons-website/static/archive/12.pdf \
  --ocr ocrmypdf --lang eng+ara --page-breaks \
  --output ~/personal/src/ons.github.io/jons/12.md
```

I was also not happy with that OCR, so I created a Claude skill to fix it.

## cspell

To improve the OCR, I have been spell checking with cspell.

For example, `cspell jons/IS_001.md`.

## Claude

For example,

```
/fix-ocr jons/IS_010.md
```

This seems to do a good job.  In addition to improving things, I have Claude updating dictionary files which I hope will improve its behavior.  Sonnet 4.6 is seems to be good enough, and takes about 3-5 minutes to process and entire Markdown file.  Haiku 4.5 is not good enough.

I used _pdfmd_ for the initial work because it is free and produced better OCR than the early Adobe software that was used previously.  It couldn't handle the pure calligraphy of [Occasional Paper 14](https://www.orientalnumismaticsociety.org/archive/OP_014.pdf) at all.  Claude Opus 4.7 did the OCR there, and it did a much better job than pdfmd, taking 1 or 2 minutes a page.

Work is in progress on a second Claude skill to reconnect broken paragraphs and fix journal headings that pdfmd didn't detect.
