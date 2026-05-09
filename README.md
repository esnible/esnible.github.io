# esnible.github.io

This is a test of the Journal of the Oriental Numismatic Society, converted to Markdown (currently without images) and OCRed.

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

## cspell

To improve the OCR, I intend to spell check it with cspell.

For example, `cspell jons/IS_001.md`.

