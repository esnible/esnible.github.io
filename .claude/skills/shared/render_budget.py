"""Pick a render DPI a vision model can actually use, and say what it costs.

Two facts drive every number here:

* **The scans are images.** A page's own raster resolution is the ceiling.
  Rendering above it interpolates; it does not resolve more. Measured over
  this corpus most files are 288-312 dpi, but plenty are not -- every page of
  `ONS_168` is 150 dpi, and `ONS_159` is 72.
* **An image handed to a vision model is downscaled before it is charged for.**
  It is fitted to roughly 1.15 megapixels with a 1568px longest edge, then
  costs about `pixels / 750` tokens. So cost tracks *pixel count up to that
  cap*, not the DPI asked for.

Together those give the rule this module encodes, which is not the intuitive
one:

* **A full page saturates the cap far below its native DPI**, so every
  full-page render above that point is the same image at the same price. A
  593x840pt page caps at ~109 dpi: rendering it at 150, 240 or 900 returns an
  identical 900x1276 view and costs an identical ~1530 tokens. Asking for more
  buys nothing but wall-clock and disk.
* **A tight crop sits under the cap**, so there DPI *does* drive cost -- and
  rendering above native means paying full price for interpolation. A
  270x160pt crop of a 150 dpi scan costs 249 tokens at native and 1533 tokens
  at 450 dpi: six times the price, for blur.

So: **crop instead of scaling, and stop at about 2x native.** Some upscale is
worth paying for -- a vision encoder's patch grid is fixed, so 8px glyphs read
better at 16px even though no information is added -- but 3-6x native is
spending tokens on interpolation.

`suggest_dpi()` is that rule. `advise()` turns it into one line a caller can
print, so the cheap path is the one you fall into without thinking about it.
"""

# Anthropic's image budget: fitted to CAP_MP megapixels with a CAP_EDGE longest
# edge, then charged at roughly pixels/TOK_DIV tokens.
CAP_MP = 1.15e6
CAP_EDGE = 1568
TOK_DIV = 750

# How far above native is worth paying for, before it is just interpolation.
DEFAULT_UPSCALE = 2.0


def native_dpi(page):
    """The page scan's own resolution, or None for a page with no raster.

    Takes the largest embedded image and measures it against the rectangle it
    is actually drawn into, so a part-page figure is not mistaken for a
    full-page scan.
    """
    best = None
    for info in page.get_images(full=True):
        xref, w, h = info[0], info[2], info[3]
        if w <= 0 or h <= 0:
            continue
        try:
            rects = page.get_image_rects(xref)
        except Exception:
            rects = []
        rect = rects[0] if rects else page.rect
        if rect.width <= 0:
            continue
        dpi = w / (rect.width / 72.0)
        if best is None or w * h > best[0]:
            best = (w * h, dpi)
    return best[1] if best else None


def cap_dpi(page, clip=None):
    """The DPI at which this render saturates the vision budget.

    Above this the image is downscaled back, so the extra pixels are discarded
    before anyone is charged for them -- or looks at them.
    """
    rect = clip if clip is not None else page.rect
    w_in, h_in = rect.width / 72.0, rect.height / 72.0
    if w_in <= 0 or h_in <= 0:
        return float(CAP_EDGE)
    return min((CAP_MP / (w_in * h_in)) ** 0.5, CAP_EDGE / max(w_in, h_in))


def cost_px(w, h):
    """(tokens, width, height, scale) for an image of a known pixel size.

    The area cap and the edge cap bite differently, and the difference matters
    for anything tall: a 1500x4186 sheet is limited by its *edge*, so it lands
    at 562x1568 -- 0.88MP, a quarter of the budget wasted, and a width that has
    collapsed to a third of what was drawn. Keeping the longest edge within
    about 2.1x the shortest is what lets a sheet spend its whole budget.
    """
    if w <= 0 or h <= 0:
        return 0, 0, 0, 1.0
    scale = min(1.0, CAP_EDGE / max(w, h), (CAP_MP / (w * h)) ** 0.5)
    fw, fh = int(w * scale), int(h * scale)
    return int(fw * fh / TOK_DIV), fw, fh, scale


def cost(page, clip, dpi):
    """(tokens, width, height, effective_dpi) once the budget has been applied."""
    rect = clip if clip is not None else page.rect
    w = rect.width / 72.0 * dpi
    h = rect.height / 72.0 * dpi
    if w <= 0 or h <= 0:
        return 0, 0, 0, 0.0
    scale = min(1.0, CAP_EDGE / max(w, h), (CAP_MP / (w * h)) ** 0.5)
    fw, fh = w * scale, h * scale
    return int(fw * fh / TOK_DIV), int(fw), int(fh), fw / (rect.width / 72.0)


def suggest_dpi(page, clip=None, upscale=DEFAULT_UPSCALE):
    """The cheap-path DPI: about `upscale` x native, never above the cap."""
    nat = native_dpi(page)
    ceiling = cap_dpi(page, clip)
    want = nat * upscale if nat else 300.0
    return max(72, int(round(min(want, ceiling))))


def advise(page, clip, dpi):
    """One line on what this render will really show, or None when it is fine.

    Fires on the two wasteful shapes: a DPI the budget will throw away, and a
    DPI far above what the scan holds.
    """
    nat = native_dpi(page)
    ceiling = cap_dpi(page, clip)
    tok, fw, fh, eff = cost(page, clip, dpi)
    notes = []
    if dpi > ceiling * 1.05:
        notes.append(
            f"capped to {fw}x{fh} (~{eff:.0f} dpi effective) -- "
            f"{ceiling:.0f} dpi would give the same image"
        )
    # Warn above the recommended upscale with a little slack, so the DPI this
    # module itself suggests never warns about itself.
    if nat and eff > nat * DEFAULT_UPSCALE * 1.15:
        cheap = suggest_dpi(page, clip)
        ctok = cost(page, clip, cheap)[0]
        if ctok < tok:
            notes.append(
                f"scan is {nat:.0f} dpi, so this is {eff / nat:.1f}x interpolation "
                f"costing ~{tok} tokens; --dpi {cheap} costs ~{ctok} and holds "
                f"every real pixel"
            )
        else:
            notes.append(f"scan is {nat:.0f} dpi, so this is {eff / nat:.1f}x interpolation")
    if not notes:
        return None
    return "note: " + "; ".join(notes)


def crop_hint(page, clip, dpi):
    """Fires when the budget is forcing a view coarser than the scan itself.

    This is the whole-page case, and the answer is never a bigger `--dpi` --
    the extra pixels are discarded again. It is `--clip`.
    """
    nat = native_dpi(page)
    if not nat:
        return None
    eff = cost(page, clip, dpi)[3]
    if eff >= nat * 0.95:
        return None
    return (f"note: this view is ~{eff:.0f} dpi against a {nat:.0f} dpi scan -- the budget, "
            f"not the DPI, is the limit. To read detail use --clip; a bigger --dpi returns "
            f"the same image")


def summary(page, clip, dpi):
    """A compact always-printed line: what it cost and what it really shows."""
    nat = native_dpi(page)
    tok, fw, fh, eff = cost(page, clip, dpi)
    bits = [f"{fw}x{fh}", f"~{tok} tok"]
    if abs(eff - dpi) > 1:
        bits.append(f"{eff:.0f} dpi effective")
    if nat:
        bits.append(f"scan {nat:.0f} dpi")
    return " | ".join(bits)
