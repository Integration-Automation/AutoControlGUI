# What's New — AutoControl

## What's new (2026-06-23) — Composable / Filtered Candidate Locators

Refine located elements with a chain: `.within(panel).filter(has_text="Delete").nth(1)`. Full reference: [`docs/source/Eng/doc/new_features/v143_features_doc.rst`](docs/source/Eng/doc/new_features/v143_features_doc.rst).

- **`from_boxes` / `Candidates`** (`AC_locate_chain`): `anchor_locator` is a single relation and `grid_locator` is cells — neither supports composable refinement of a candidate set (the Selenium-4 / Playwright chained-locator idiom). This is a pure post-filter over boxes from *any* source (template / OCR / a11y / `fuse_elements`): `within` (region clip), `filter` (`has_text` / `near` / area / predicate), `sort_reading`, `nth` / `first` / `last`, `resolve()` / `center()`. Every method returns a new `Candidates` (no mutation) → fully headless-testable. The executor command applies a JSON `ops` list.

## What's new (2026-06-23) — Retrying Value Assertions (expect.poll)

Retry *any* value until it matches, not just the built-in checks. Full reference: [`docs/source/Eng/doc/new_features/v142_features_doc.rst`](docs/source/Eng/doc/new_features/v142_features_doc.rst).

- **`expect_poll` / `assert_poll` + matchers** (`AC_expect_poll`): `assert_eventually` only polls the fixed dict-spec checks (text/image/pixel/…). This polls any zero-arg `getter` against any `matcher` (`to_equal` / `to_contain` / `to_be_greater_than` / `to_match_regex` / `to_be_truthy` / `to_be_stable`) until it passes or times out — an OCR'd total, a row count stabilising, a custom predicate. Injectable `clock`/`sleep` → deterministic, mirrors Playwright's `expect.poll`. The executor command re-runs a nested action until a key of its result matches.

## What's new (2026-06-23) — Line / Grid / Separator Detection (Hough)

Find table grid lines and UI dividers from raw pixels. Full reference: [`docs/source/Eng/doc/new_features/v141_features_doc.rst`](docs/source/Eng/doc/new_features/v141_features_doc.rst).

- **`find_lines` / `find_grid` / `find_separators`** (`AC_find_lines`, `AC_find_grid`, `AC_find_separators`): `grid_locator` clusters *already-found* boxes and `shape_locator` finds closed rectangles — neither finds a table's ruling lines or a divider from pixels. Canny + probabilistic Hough detects straight segments (classified horizontal/vertical/diagonal), `find_grid` recovers `{rows, cols, cells}` so you can address "row 3, col 2", and `find_separators` returns the coordinates of long dividers. Injectable haystack → headless-testable; base OpenCV (`cv2.HoughLinesP`).

## What's new (2026-06-23) — Model-Free Text-Region Detection (MSER)

Find where text is on screen without running OCR. Full reference: [`docs/source/Eng/doc/new_features/v140_features_doc.rst`](docs/source/Eng/doc/new_features/v140_features_doc.rst).

- **`find_text_regions` / `find_text_lines`** (`AC_find_text_regions`, `AC_find_text_lines`): `shape_locator` finds rectangles (not text) and `locate_text` needs an OCR engine *and* the exact string — neither answers "where is *any* text?". MSER finds the glyph/word/line blobs, so a script can crop candidate boxes to feed OCR (faster + more accurate than full-frame) or detect a label appeared with no OCR dependency. `merge` unions MSER's nested per-glyph regions; `find_text_lines` groups glyphs into per-line boxes; a blank screen returns `[]`. Base OpenCV (`cv2.MSER_create`), injectable haystack → headless-testable.

## What's new (2026-06-23) — HSV Colour-Space Segmentation

Find "any shade of red" regardless of lighting. Full reference: [`docs/source/Eng/doc/new_features/v139_features_doc.rst`](docs/source/Eng/doc/new_features/v139_features_doc.rst).

- **`dominant_hue_regions` / `segment_hsv` / `color_mask`** (`AC_dominant_hue_regions`, `AC_segment_hsv`): `find_color_region` masks in RGB with a per-channel ± box — it can't match "the same colour at a different brightness" (status lights, highlights, theme tints). HSV separates hue from brightness, so a hue band + saturation/value floor catches every shade across lighting. `dominant_hue_regions(hue=…)` handles red's 0/180 wrap automatically; `segment_hsv` takes an explicit band; both return `{x,y,width,height,area,center}` blobs reusing the shared connected-components helper. Injectable haystack → headless-testable.

## What's new (2026-06-23) — Fuse & Order On-Screen Element Boxes

Turn raw OCR + icon + a11y boxes into one clean, numbered element list. Full reference: [`docs/source/Eng/doc/new_features/v138_features_doc.rst`](docs/source/Eng/doc/new_features/v138_features_doc.rst).

- **`iou` / `merge_boxes` / `fuse_elements` / `reading_order`** (`AC_fuse_elements`, `AC_reading_order`): `set_of_marks` numbers a clean element list but nothing *produced* it — a real screen parse yields three overlapping sources with duplicates and no order. These supply the missing step: drop near-duplicate boxes by IoU, union OCR/icon/a11y keeping the most trustworthy source on overlap (`source_priority` a11y > ocr > icon), and sort top-to-bottom/left-to-right with a stable `index`. Plain `dict` boxes → pure-stdlib, fully headless-testable; pairs directly with `set_of_marks`.

## What's new (2026-06-23) — Actionability Gate (Wait Until Ready Before Acting)

Don't click until the target is genuinely ready. Full reference: [`docs/source/Eng/doc/new_features/v137_features_doc.rst`](docs/source/Eng/doc/new_features/v137_features_doc.rst).

- **`wait_actionable` / `act_when_ready`** (`AC_wait_actionable`): Playwright/Cypress run an actionability check before every click — present + stopped moving + enabled + not covered — but AutoControl had none (`self_heal_click` clicks immediately; `wait_until_screen_stable` watches the whole frame). This composes the four checks into one gate and returns an `ActionabilityReport` (per-check booleans, target `point`, `reason` = first failing check). Every signal is an injectable callable (`bbox_provider` / `region_sampler` / `enabled_probe` / `hit_tester`) plus an injectable `clock`/`sleep`, so it's fully deterministic and headless-testable. The executor command gates on a template image.

## What's new (2026-06-23) — Multi-Monitor / Virtual-Desktop Geometry

Place windows and points correctly across several displays. Full reference: [`docs/source/Eng/doc/new_features/v136_features_doc.rst`](docs/source/Eng/doc/new_features/v136_features_doc.rst).

- **`enumerate_monitors` + `Monitor` / `virtual_bounds` / `monitor_at_point` / `monitor_for_window` / `to_local` / `to_virtual` / `remap_point`** (`AC_enumerate_monitors`, `AC_monitor_at_point`): `snap_window` / `arrange_grid` / the layout planner all assumed a single primary `(width, height)` — monitor-blind, unable to tile on a second display or handle a negative-origin virtual desktop. This adds the physical layer: union virtual bounds, which-monitor-owns-this-point/window, virtual↔monitor-local conversion, and equivalent-spot remapping across resolutions/DPI. Pure geometry over `Monitor` dataclasses → fully headless-testable; `enumerate_monitors` has an injectable provider (default `mss`).

## What's new (2026-06-23) — Image Pre-processing for OCR / Template Matching

Clean up the screen before reading or matching it. Full reference: [`docs/source/Eng/doc/new_features/v135_features_doc.rst`](docs/source/Eng/doc/new_features/v135_features_doc.rst).

- **`preprocess_image` + `to_grayscale` / `binarize` / `upscale` / `denoise` / `deskew` / `enhance_contrast`** (`AC_preprocess_image`): `locate_text` and `match_template` fed the *raw* capture to OCR / the matcher — small text, dark themes, low contrast and skew wrecked both, with no preprocessing seam anywhere. This adds the standard pipeline (grayscale → upscale → binarize → deskew → denoise → CLAHE) that multiplies their accuracy. Injectable haystack → ndarray; `detect_skew_angle` measures text rotation; `binarize` does otsu / adaptive. The executor command writes the cleaned image to a path. Headless-testable on synthetic arrays.

## What's new (2026-06-23) — Arrange Multiple Windows (Grid / Cascade)

Lay out a whole set of windows in one call. Full reference: [`docs/source/Eng/doc/new_features/v134_features_doc.rst`](docs/source/Eng/doc/new_features/v134_features_doc.rst).

- **`arrange_grid` / `arrange_cascade`** (`AC_arrange_grid`, `AC_arrange_cascade`): `snap_window` moves *one* window and the layout planner only *computes* rectangles — these close the loop, taking a list of window titles and actually moving every match into a grid (auto near-square shape, or explicit `rows`/`cols` + `gap`) or a diagonal cascade. Build on the layout planner and reuse `snap_window`'s injectable `mover`/`screen_size` seams, so they are fully headless-testable; return the count moved.

## What's new (2026-06-23) — Window Tiling / Layout Geometry Planner

Compute where to place application windows — halves, grids, cascades. Full reference: [`docs/source/Eng/doc/new_features/v133_features_doc.rst`](docs/source/Eng/doc/new_features/v133_features_doc.rst).

- **`tile_rect` / `grid_rects` / `cascade_rects`** (`AC_tile_rect`, `AC_grid_rects`, `AC_cascade_rects`): `save/restore_window_layout` replay *exact* saved positions and `snap_window` moves *one* window — nothing *computes* a fresh multi-window layout. This pure-geometry planner returns the target rectangles for halves, quadrants, thirds, an R×C grid and a staggered cascade given a screen work area, so a script can lay out windows deterministically. Returns `WindowRect` (`.as_tuple()` / `.to_dict()`); `gap` insets tiles; cross-platform and fully headless-testable; composes with any window-move backend.

## What's new (2026-06-23) — Locate UI Elements by Edge / Contour (No Template)

Find the clickable boxes on a screen you have never seen. Full reference: [`docs/source/Eng/doc/new_features/v132_features_doc.rst`](docs/source/Eng/doc/new_features/v132_features_doc.rst).

- **`find_shapes` / `find_rectangles`** (`AC_find_shapes`, `AC_find_rectangles`): every other locator needs something to look *for* — a template, a colour, some text. These need nothing: Canny edge detection + contour extraction returns the bounding boxes (`{x,y,width,height,area,center,aspect}`, largest first) of the distinct shapes, so a script can enumerate cards / buttons / input fields structurally and click the Nth one. `find_rectangles` keeps only convex quads and adds an `aspect_range=(min,max)` w/h filter (`(1.5,8)` wide buttons). Injectable haystack → headless-testable.

## What's new (2026-06-23) — ORB Feature Matching (Rotation / Scale / Theme Robust)

Find a target even when it is rotated, rescaled or re-themed. Full reference: [`docs/source/Eng/doc/new_features/v131_features_doc.rst`](docs/source/Eng/doc/new_features/v131_features_doc.rst).

- **`feature_match`** (`AC_feature_match`): pixel template matching (`match_template` / `match_masked`) correlates pixels, so it breaks the moment the target is rotated, scaled by an unlisted factor, or re-coloured (light/dark theme, hover). This matches ORB *keypoints* and fits a RANSAC homography, returning the four projected `corners`, the `center`, the `inliers` count and an inlier-fraction `score`. ORB border/patch sizes auto-scale down for icon-sized templates (OpenCV's defaults reject them). Core OpenCV only (no contrib); injectable haystack → headless-testable.

## What's new (2026-06-23) — Structural-Similarity (SSIM) Comparison

Perceptual screen comparison that tells you *what* changed. Full reference: [`docs/source/Eng/doc/new_features/v130_features_doc.rst`](docs/source/Eng/doc/new_features/v130_features_doc.rst).

- **`ssim_compare` / `ssim_changed_regions`** (`AC_ssim_compare`, `AC_ssim_changed_regions`): pixel diff (`diff_screenshots`) fires on a one-pixel shift; a histogram (`detect_drift`) is blind to layout. SSIM is the standard visual-regression metric — tolerant of small illumination changes, sensitive to structural change. `ssim_compare` returns a 0..1 score (1.0 = identical); `ssim_changed_regions` returns boxes of what moved. `ignore=[[x,y,w,h]]` masks live clocks / cursors. Pure NumPy + OpenCV (no scikit-image); injectable image pair → headless-testable.

## What's new (2026-06-23) — Masked Template Matching

Match icons regardless of their background. Full reference: [`docs/source/Eng/doc/new_features/v129_features_doc.rst`](docs/source/Eng/doc/new_features/v129_features_doc.rst).

- **`match_masked` / `match_masked_all`** (`AC_match_masked`, `AC_match_masked_all`): plain template matching scores *every* pixel, so an icon clipped from one background fails over a different one. These count only the pixels you mark relevant — an explicit grayscale `mask`, or an RGBA template's alpha channel — so transparent / "don't care" pixels stop dragging the score down. Returns the same `Match` (score/center) as scored template matching; OpenCV masked `TM_CCORR_NORMED`, NaNs zeroed. Injectable haystack → headless-testable.

## What's new (2026-06-23) — Locate On-Screen Regions by Colour

Find the green status pill / red banner by colour. Full reference: [`docs/source/Eng/doc/new_features/v128_features_doc.rst`](docs/source/Eng/doc/new_features/v128_features_doc.rst).

- **`find_color_region` / `find_color_regions`** (`AC_find_color_region`): `color_stats` only describes a region's colour and `assert_pixel` checks one point — neither *locates* a coloured region. This masks pixels within `tolerance` of a target RGB and returns the connected blobs' boxes (`{x,y,width,height,area,center}`, largest first) — for status lights, progress fills, error banners where a template is brittle. Injectable haystack → headless-testable; OpenCV/NumPy via `je_open_cv`.

## What's new (2026-06-23) — Confidence-Returning Template Matching

Template matching that returns the score, searches multiple scales, and finds all occurrences. Full reference: [`docs/source/Eng/doc/new_features/v127_features_doc.rst`](docs/source/Eng/doc/new_features/v127_features_doc.rst).

- **`match_template` / `match_template_all` / `best_matches` / `TemplateMatch`** (`AC_match_template`, `AC_match_template_all`): the existing matcher (`find_object`) is single-scale and *discards the score*. This returns a `Match` with `score`/`scale`/`center`, searches `scales` for DPI/zoom tolerance, and enumerates every occurrence with non-maximum suppression. Injectable `haystack` (ndarray/path/PIL) → headless-testable on synthetic arrays; OpenCV/NumPy via the `je_open_cv` dependency.

## What's new (2026-06-23) — Wait for Window Title (Regex)

Block until a window title matches a regex (or vanishes). Full reference: [`docs/source/Eng/doc/new_features/v126_features_doc.rst`](docs/source/Eng/doc/new_features/v126_features_doc.rst).

- **`wait_until_window_title`** (`AC_wait_window_title`): `wait_for_window` matches a title substring and only waits for *appear*; `wait_until_window_closed` is substring vanish. This matches a regular expression by default (`regex=False` for substring) and can wait for the title to vanish (`present=False`) — e.g. wait for a tab to navigate to `r".*— Checkout$"`. Injectable title source, headless-testable.

## What's new (2026-06-23) — Grid / Table Cell Addressing

Address a table cell by (row, column) from cell bounding boxes. Full reference: [`docs/source/Eng/doc/new_features/v125_features_doc.rst`](docs/source/Eng/doc/new_features/v125_features_doc.rst).

- **`cluster_grid` / `locate_cell`** (`AC_grid_cell`): `anchor_locator` does pairwise relations but nothing addresses a 2-D grid. Given the cell bounding boxes (from `locate_all_image` / `find_text_matches`), this clusters them into rows (by centre-y within `row_tolerance`) and columns (by centre-x) and returns the centre of the 0-based `(row, col)` cell — ready to click. Pure clustering, fully headless-testable.

## What's new (2026-06-23) — Anchor Ordinal & Locate-All

Pick the Nth anchor-relative match, or enumerate them all. Full reference: [`docs/source/Eng/doc/new_features/v124_features_doc.rst`](docs/source/Eng/doc/new_features/v124_features_doc.rst).

- **`anchor_locate(..., ordinal=N)` / `anchor_locate_all`** (`AC_anchor_locate` ordinal, `AC_anchor_locate_all`): `anchor_locate` always returned the single nearest match — no way to grab "the 2nd row below the header" or list every row. Adds a 1-based `ordinal` selector (backward-compatible; `ordinal=1` = nearest) and `anchor_locate_all` returning every match sorted by distance — the building block for table/list-row selection. Pure ranking core, deterministic.

## What's new (2026-06-23) — Held Modifiers Across an Action Group

Hold ctrl/shift down across several actions, released even on error. Full reference: [`docs/source/Eng/doc/new_features/v123_features_doc.rst`](docs/source/Eng/doc/new_features/v123_features_doc.rst).

- **`hold_modifiers` / `plan_with_modifiers`** (`AC_with_modifiers`): `hotkey` releases its keys immediately — there was no way to hold a modifier down across several independent actions (shift-click range select, ctrl-click multi-select) with a guaranteed release. `hold_modifiers` is a context manager that presses on enter and releases in reverse on exit (in a `finally`, so nothing leaks); `plan_with_modifiers` is the pure plan. Injectable sink, deterministic.

## What's new (2026-06-23) — Unicode Text Entry (Emoji / CJK)

Type any Unicode (emoji / CJK / accented) that `write` can't. Full reference: [`docs/source/Eng/doc/new_features/v122_features_doc.rst`](docs/source/Eng/doc/new_features/v122_features_doc.rst).

- **`type_unicode` / `plan_paste` / `unicode_code_units`** (`AC_type_unicode`): `write` types through the virtual-key table and *raises* on emoji/CJK/many accented chars. `type_unicode` enters any text reliably by setting the clipboard and pasting (`modifier` ctrl/command). `unicode_code_units` splits text into UTF-16 code units (surrogate pairs) for KEYEVENTF_UNICODE backends. Pure-planning + injectable sink, deterministic.

## What's new (2026-06-23) — Wait for Region Colour

Block until a colour fills (or leaves) a screen region. Full reference: [`docs/source/Eng/doc/new_features/v121_features_doc.rst`](docs/source/Eng/doc/new_features/v121_features_doc.rst).

- **`wait_until_color`** (`AC_wait_color`): `wait_for_pixel` matches one point exactly and `wait_until_pixel_changes` detects any change at one point — neither waits for "the status light turns green" / "the progress bar fills" / "the red banner is gone". This counts pixels within `tolerance` of `target_rgb` over a region and succeeds when that fraction crosses `min_fraction` (or drops below it, `present=False`). Injectable sampler, headless-testable. Pure-stdlib.

## What's new (2026-06-23) — Relative Mouse Movement

Nudge the pointer by a delta from where it is. Full reference: [`docs/source/Eng/doc/new_features/v120_features_doc.rst`](docs/source/Eng/doc/new_features/v120_features_doc.rst).

- **`move_mouse_relative` / `relative_target`** (`AC_move_mouse_relative`): the mouse wrapper only had absolute `set_mouse_position` — no `moveRel(dx, dy)` for relative-pointer / canvas / FPS apps and incremental drags. Reads the live position and moves by the delta; `relative_target` is the pure arithmetic, and the getter/setter are injectable for headless tests. Pure-stdlib, deterministic.

## What's new (2026-06-23) — Hold Key / Auto-Repeat

Hold a key for a duration, or auto-repeat it at a fixed rate. Full reference: [`docs/source/Eng/doc/new_features/v119_features_doc.rst`](docs/source/Eng/doc/new_features/v119_features_doc.rst).

- **`hold_key` / `plan_key_hold`** (`AC_hold_key`): `type_keyboard` is an instant down+up — there was no "hold this key for N seconds" (game movement, hold-to-scroll) or "send it at R presses/second" (auto-repeat). `plan_key_hold` builds the deterministic op-plan (press/wait/release, or N spaced key events for `rate_hz`); `hold_key` routes waits to an injectable `sleep` and keys to an injectable `sink`. Pure-planning, deterministic.

## What's new (2026-06-23) — Wait Until Gone (Blocking Vanish Waits)

Block until a spinner / toast / dialog disappears. Full reference: [`docs/source/Eng/doc/new_features/v118_features_doc.rst`](docs/source/Eng/doc/new_features/v118_features_doc.rst).

- **`wait_until_gone` / `wait_until_image_gone` / `wait_until_text_gone`** (`AC_wait_image_gone`, `AC_wait_text_gone`): `wait_for_image`/`wait_for_text` only block until something *appears*, and `observer` fires async callbacks on vanish — there was no *blocking* "wait until this image/text disappears then continue" call. The generic `wait_until_gone` takes any predicate (headless-testable); the image/text helpers build it from the locate functions. `gone_for_s` debounces flicker. Returns a `WaitOutcome`. Pure-stdlib.

## What's new (2026-06-23) — Clear-Then-Type Field Entry

Reliably set a text field's value (the Playwright `fill` idiom). Full reference: [`docs/source/Eng/doc/new_features/v117_features_doc.rst`](docs/source/Eng/doc/new_features/v117_features_doc.rst).

- **`set_field_text` / `plan_field_set`** (`AC_set_field_text`): there was no single "focus → clear → set value" primitive, and `write` raises on emoji/CJK. This clears the field (select-all + delete) then enters the text — optionally via the clipboard (`paste=True`) which is the Unicode-safe path `write` can't do. `modifier` is the platform command key (`ctrl`/`command`). Pure-planning + injectable sink, deterministic.

## What's new (2026-06-22) — Multi-Waypoint Mouse Gestures

Move or drag the pointer through a polyline of waypoints. Full reference: [`docs/source/Eng/doc/new_features/v116_features_doc.rst`](docs/source/Eng/doc/new_features/v116_features_doc.rst).

- **`plan_path` / `move_along_path` / `drag_path` / `path_easings`** (`AC_move_along_path`, `AC_drag_path`): `humanize` and `tween_drag` only interpolate a single start→end hop — there was no way to drive an arbitrary chain of waypoints (signatures, marquee selects, multi-stop drags) with the button held across the whole path. `plan_path` is pure eased point math (reusing `tween_drag`'s easings, junctions de-duplicated); the move/drag dispatch through an injectable sink for headless testing. Pure-stdlib, deterministic.

## What's new (2026-06-22) — Check-Digit Algorithms

Compute / verify Luhn, Verhoeff, Damm and ISO 7064 MOD 97-10 check digits. Full reference: [`docs/source/Eng/doc/new_features/v115_features_doc.rst`](docs/source/Eng/doc/new_features/v115_features_doc.rst).

- **`luhn_validate` / `luhn_check_digit` / `verhoeff_*` / `damm_*` / `mod97_10_*`** (`AC_checksum_validate`, `AC_checksum_digit`): `pii_text` detects card/IBAN shapes by regex and `data_quality` does regex validation, but nothing computed or verified a *check digit*. This adds the four schemes behind most identifiers (cards/IMEI, national IDs, IBAN) — the shared engine `identifier_validate` builds on. Pure-stdlib, deterministic.

## What's new (2026-06-22) — GNU gettext Catalog I/O (.po / .mo)

Read/compile the de-facto translation format. Full reference: [`docs/source/Eng/doc/new_features/v114_features_doc.rst`](docs/source/Eng/doc/new_features/v114_features_doc.rst).

- **`parse_po` / `read_mo` / `GettextCatalog` / `parse_po_file` / `read_mo_file`** (`AC_gettext_translate`, `AC_gettext_ngettext`): the repo pseudo-localises and renders ICU messages but couldn't read GNU gettext `.po`/`.mo`. This parses `.po` (contexts, plurals, the `Plural-Forms` header via `gettext.c2py`), compiles a standards-compliant `.mo` that Python's own `gettext.GNUTranslations` loads, and exposes `gettext`/`ngettext`/`pgettext`. Pure-stdlib, deterministic.

## What's new (2026-06-22) — ICU-lite MessageFormat (Plural / Select)

Render count-aware localised messages. Full reference: [`docs/source/Eng/doc/new_features/v113_features_doc.rst`](docs/source/Eng/doc/new_features/v113_features_doc.rst).

- **`format_message` / `plural_category` / `ordinal_category`** (`AC_format_message`): `i18n_test.check_catalog` only compares placeholder sets and `interpolate` is flat `${var}` — neither renders `"{count, plural, one {# item} other {# items}}"`. This implements the ICU MessageFormat subset most apps use: `select`, `plural`, `selectordinal` with CLDR categories, exact `=N` selectors, the `#` count, `offset:`, nesting and apostrophe quoting. Injectable plural rules. Pure-stdlib, deterministic.

## What's new (2026-06-22) — Locale-Aware List Formatting

Join items the way a language expects ("A, B, and C"). Full reference: [`docs/source/Eng/doc/new_features/v112_features_doc.rst`](docs/source/Eng/doc/new_features/v112_features_doc.rst).

- **`format_list`** (`AC_format_list`): a naive `", ".join` gives "A, B, C" with no "and"/"or" and no localisation. This implements the CLDR list-pattern composition with conjunction / disjunction / unit styles and per-locale conjunction words + serial-comma rule (`en`/`es`/`fr`/`de`/`pt`) — `format_list(["a","b","c"])` → "a, b, and c", `locale="es"` → "a, b y c". Pure-stdlib, deterministic.

## What's new (2026-06-22) — Bidirectional-Text QA (Trojan-Source Scan)

Catch invisible Unicode directional formatting (RTL QA + Trojan-source). Full reference: [`docs/source/Eng/doc/new_features/v111_features_doc.rst`](docs/source/Eng/doc/new_features/v111_features_doc.rst).

- **`detect_bidi_issues` / `bidi_controls` / `is_bidi_balanced` / `base_direction` / `is_trojan_source` / `strip_bidi_controls` / `has_bidi_controls`** (`AC_bidi_check`, `AC_bidi_strip`): `confusables` catches lookalike characters, but bidi controls (LRO/RLO/PDF, isolates, marks) can silently reorder rendered text — an RTL-QA gap and the "Trojan Source" attack (CVE-2021-42574). This lists the controls, checks nesting balance, infers base direction, and flags reordering formatting. Pure-stdlib (`unicodedata`), deterministic.

## What's new (2026-06-22) — Readability Scoring

Score how hard text is to read; gate generated copy on a reading grade. Full reference: [`docs/source/Eng/doc/new_features/v110_features_doc.rst`](docs/source/Eng/doc/new_features/v110_features_doc.rst).

- **`flesch_reading_ease` / `flesch_kincaid_grade` / `gunning_fog` / `smog_index` / `automated_readability_index` / `readability_report` / `readability_stats` / `count_syllables`** (`AC_readability_report`): the text utilities canonicalise, match and rank text but never scored *difficulty*. This adds the classic English readability formulae over a deterministic tokeniser and syllable heuristic, so a test can assert an on-screen message or label stays within a target reading grade. Pure-stdlib (`re`/`math`), deterministic.

## What's new (2026-06-22) — Confusable / Homoglyph Detection

Catch Unicode visual spoofing (IDN-homograph phishing, lookalike labels). Full reference: [`docs/source/Eng/doc/new_features/v109_features_doc.rst`](docs/source/Eng/doc/new_features/v109_features_doc.rst).

- **`confusable_skeleton` / `is_confusable` / `detect_homoglyphs` / `is_mixed_script` / `scripts_of`** (`AC_confusable_scan`, `AC_confusable_compare`): a Cyrillic `"а"` is pixel-for-pixel a Latin `"a"`, so `"pаypal"` reads as `"paypal"` yet compares unequal. Following Unicode TR39, this folds confusables to a prototype skeleton (strings match when skeletons match) and flags mixed-script tokens. Pure-stdlib (`unicodedata`), deterministic.

## What's new (2026-06-22) — Locale-Aware String Collation

Sort strings the way a reader of the language expects. Full reference: [`docs/source/Eng/doc/new_features/v108_features_doc.rst`](docs/source/Eng/doc/new_features/v108_features_doc.rst).

- **`sort_strings` / `collation_compare` / `collation_key`** (`AC_collation_sort`, `AC_collation_compare`): Python's default `sorted` is codepoint order, so `"Z" < "a"` and `"ä"` lands far from `"a"`. This Unicode-Collation-lite key orders by base letter, then accent (secondary), then case (tertiary), with an optional `tailoring` alphabet so Swedish puts `å ä ö` after `z`. Pure-stdlib (`unicodedata`), deterministic across platforms — unlike `locale.strxfrm`.

## What's new (2026-06-22) — Transactional Outbox

Durably buffer events and drain them at-least-once. Full reference: [`docs/source/Eng/doc/new_features/v107_features_doc.rst`](docs/source/Eng/doc/new_features/v107_features_doc.rst).

- **`Outbox`** (`AC_outbox_enqueue`, `AC_outbox_pending`): `events.cloud_events` posts synchronously with no durability — a crash or network blip loses the event. The outbox persists each event first, then `drain`s pending entries through an injected sink with at-least-once delivery: a sink failure leaves the entry pending for retry until `max_attempts`, after which it is dead-lettered. `save` / `load` keep events across restarts. Pure-stdlib, deterministic.

## What's new (2026-06-22) — Optimistic-Concurrency Versioned Store

Update only if the version is unchanged (compare-and-swap / If-Match). Full reference: [`docs/source/Eng/doc/new_features/v106_features_doc.rst`](docs/source/Eng/doc/new_features/v106_features_doc.rst).

- **`VersionedStore` / `VersionConflict` / `if_match_header` / `check_if_match`** (`AC_cas_put`, `AC_cas_get`): `http_conditional` used ETag for read caching but never for write concurrency. This local compare-and-swap store `put`s only when `expected_version` matches (raising `VersionConflict` on a stale write), bumps a monotonic version, and bridges to HTTP `If-Match` — the write side of the ETag story. Pure-stdlib, deterministic.

## What's new (2026-06-22) — Per-Stream Sequence-Gap Detection

Detect missing / out-of-order / duplicate messages by sequence number. Full reference: [`docs/source/Eng/doc/new_features/v105_features_doc.rst`](docs/source/Eng/doc/new_features/v105_features_doc.rst).

- **`SequenceTracker`** (`AC_sequence_observe`): nothing tracked per-stream monotonic sequence numbers. `observe(stream, seq)` classifies each as `ok` / `duplicate` / `gap` (with the `missing` numbers) / `reorder` (late arrivals fill gaps), and exposes `gaps` and `high_water`. Complements `dedup_window`. Pure-stdlib, deterministic.

## What's new (2026-06-22) — Time-Windowed Deduplication

Drop duplicate/redelivered messages within a TTL window. Full reference: [`docs/source/Eng/doc/new_features/v104_features_doc.rst`](docs/source/Eng/doc/new_features/v104_features_doc.rst).

- **`DedupWindow`** (`AC_dedup_check`): `work_queue` dedups only in-flight references, so a completed reference re-enqueues and redelivered webhooks reprocess. This sliding-window inbox `check_and_mark`s a message id — `True` the first time, `False` for a duplicate within `ttl_s` — converting at-least-once delivery to exactly-once-in-window. Injectable clock, bounded size. Pure-stdlib, deterministic.

## What's new (2026-06-22) — Idempotency-Key Store

Run a side effect once, replay its response on retries. Full reference: [`docs/source/Eng/doc/new_features/v103_features_doc.rst`](docs/source/Eng/doc/new_features/v103_features_doc.rst).

- **`IdempotencyStore` / `request_fingerprint` / `IdempotencyConflict`** (`AC_idempotency_begin`, `AC_idempotency_complete`): `RetryPolicy` re-executes and `work_queue` dedups only in-flight refs — nothing cached the first result. This Stripe-style store returns `new`/`in_progress`/`completed` for a key, replays the stored response, raises on a fingerprint conflict, and supports injectable-clock TTL + JSON persistence. Pure-stdlib, deterministic.

## What's new (2026-06-22) — Moving-Average Smoothing

Smooth a noisy value series. Full reference: [`docs/source/Eng/doc/new_features/v102_features_doc.rst`](docs/source/Eng/doc/new_features/v102_features_doc.rst).

- **`sma` / `wma` / `ewma` / `rolling`** (`AC_sma`, `AC_ewma`): `stats.describe` summarizes a whole sample and `timeseries` rolls counters into rates, but nothing smoothed a noisy signal. This adds trailing simple/weighted/exponentially-weighted moving averages and a generic rolling reducer, all returning a same-length list aligned to the input timeline. Pure-stdlib, deterministic.

## What's new (2026-06-22) — Single-Series Anomaly Detection

Flag the spike in one live metric series. Full reference: [`docs/source/Eng/doc/new_features/v101_features_doc.rst`](docs/source/Eng/doc/new_features/v101_features_doc.rst).

- **`detect_anomalies` / `mad_anomalies` / `zscore_anomalies` / `ewma_control`** (`AC_detect_anomalies`): `data_drift` is two-batch distribution shift and `slo.burn_alerts` only thresholds budget burn — neither points at *which* value in one series is anomalous. This flags outliers via robust MAD (modified z-score), plain z-score, and an EWMA control chart (with an optional in-control baseline) — `{index, value, score, is_anomaly}` records. Pure-stdlib, deterministic.

## What's new (2026-06-22) — Near-Duplicate Text Detection (SimHash / MinHash)

Fingerprint text to find near-dups at scale. Full reference: [`docs/source/Eng/doc/new_features/v100_features_doc.rst`](docs/source/Eng/doc/new_features/v100_features_doc.rst).

- **`simhash` / `near_duplicates` / `minhash_signature` / `minhash_similarity`** (`AC_simhash`, `AC_near_duplicates`): `fuzzy_dedupe` is O(n²) pairwise with no stable fingerprint and `image_dedup` only hashes pixels. This adds the text analog — SimHash (Hamming-distance near-dup clustering) and MinHash (estimated Jaccard) using a fixed `blake2b` hash for deterministic fingerprints. Pairs with `normalize_text`. Pure-stdlib.

## What's new (2026-06-22) — String-Distance Similarity Metrics

Match typos and reordered tokens. Full reference: [`docs/source/Eng/doc/new_features/v99_features_doc.rst`](docs/source/Eng/doc/new_features/v99_features_doc.rst).

- **`levenshtein` / `damerau_levenshtein` / `jaro` / `jaro_winkler` / `jaccard` / `dice` / `similarity`** (`AC_text_similarity`): `fuzzy` exposed only difflib's gestalt ratio. This adds the edit-distance and token-set metrics it lacks — Jaro-Winkler (standard for short labels), Damerau (transposition-aware), and char-n-gram Jaccard/Dice — plus a unified `similarity()` that normalizes every metric to `[0, 1]`. Pairs with `normalize_text`. Pure-stdlib, deterministic.

## What's new (2026-06-22) — Time-Series Transforms

Turn counters into rates; downsample and resample. Full reference: [`docs/source/Eng/doc/new_features/v98_features_doc.rst`](docs/source/Eng/doc/new_features/v98_features_doc.rst).

- **`ts_rate` / `ts_irate` / `ts_increase` / `ts_delta` / `ts_downsample` / `ts_resample`** (`AC_ts_rate`, `AC_ts_downsample`): `observability` counters store only the current value (no counter→rate anywhere) and `cost_telemetry` only buckets by day. This adds Prometheus-style reset-aware rate/increase/delta over `(timestamp, value)` series, tumbling-bucket downsampling (avg/sum/min/max/first/last/count), and grid resampling (last/linear/none). No wall clock — deterministic. Pure-stdlib.

## What's new (2026-06-22) — Unicode Text Normalisation & Slugify

Canonicalize text before fuzzy/search/OCR matching. Full reference: [`docs/source/Eng/doc/new_features/v97_features_doc.rst`](docs/source/Eng/doc/new_features/v97_features_doc.rst).

- **`normalize_text` / `deaccent` / `slugify` / `normalize_quotes` / `fold_whitespace`** (`AC_normalize_text`, `AC_slugify`): `fuzzy` and `search_index.tokenize` only lowercase and OCR matching only `.lower()`+substring, so `"Café"` (NFC) vs `"Café"` (NFD) vs `"cafe"` compare unequal. This adds the missing canonicalization layer (NFKC + casefold + whitespace fold, accent stripping, smart-quote mapping, ASCII slugs). Pure-stdlib (`unicodedata`), deterministic.

## What's new (2026-06-22) — JSON-Schema Compatibility Checking

Classify schema changes as backward/forward/full. Full reference: [`docs/source/Eng/doc/new_features/v96_features_doc.rst`](docs/source/Eng/doc/new_features/v96_features_doc.rst).

- **`check_compatibility` / `diff_schemas` / `is_backward_compatible` / `is_forward_compatible` / `is_full_compatible`** (`AC_check_compatibility`): we could validate against and generate JSON Schemas but couldn't answer "will an old consumer still read new data?". This classifies changes (added-required field, removed field, narrowed/widened type, enum add/remove) under Confluent/Avro backward/forward/full rules over the object subset. Pure-stdlib, deterministic.

## What's new (2026-06-22) — Typed Configuration Schema

Validate config into a typed object. Full reference: [`docs/source/Eng/doc/new_features/v95_features_doc.rst`](docs/source/Eng/doc/new_features/v95_features_doc.rst).

- **`ConfigSchema` / `ConfigField` / `validate_config` / `coerce`** (`AC_validate_config`): `assets._coerce` coerces one value and `json_schema` validates structure, but nothing bound a resolved config dict into a typed object with required-field enforcement and choice constraints. This coerces types (`str`/`int`/`float`/`bool`), applies defaults, enforces required/choices, and returns `{ok, config, errors}` — a stdlib pydantic-settings analog. Pure-stdlib, deterministic.

## What's new (2026-06-22) — OTLP/JSON Span Export

Export spans the way a collector ingests them. Full reference: [`docs/source/Eng/doc/new_features/v94_features_doc.rst`](docs/source/Eng/doc/new_features/v94_features_doc.rst).

- **`spans_to_otlp` / `attributes_to_otlp` / `write_otlp`** (`AC_spans_to_otlp`): `agent_trace.to_otel` returned flat dicts that aren't valid OTLP/JSON (no resourceSpans/scopeSpans nesting, times not as uint64 strings). This wraps spans in the proper envelope with hex IDs, uint64-string times, and OTLP `KeyValue` attribute encoding — what an OpenTelemetry collector's file exporter reads. Pairs with `trace_context`. Pure-stdlib, deterministic.

## What's new (2026-06-22) — Canonical Log Lines & Structured Logging

One wide event per run, with trace correlation. Full reference: [`docs/source/Eng/doc/new_features/v93_features_doc.rst`](docs/source/Eng/doc/new_features/v93_features_doc.rst).

- **`CanonicalLogLine` / `JSONLogFormatter` / `bind_trace_context`** (`AC_canonical_log`): `logging_instance` emits a fixed pipe-delimited string with no JSON and no trace/span fields. This adds a Stripe-style canonical log line (field accumulator + `timer` with injectable clock) and a JSON `logging.Formatter` that carries `trace_id`/`span_id` — the log-trace correlation counterpart to `trace_context`. Pure-stdlib, deterministic.

## What's new (2026-06-22) — Conditional HTTP Requests & Cache Validators

Skip re-downloading unchanged resources (ETag / 304). Full reference: [`docs/source/Eng/doc/new_features/v92_features_doc.rst`](docs/source/Eng/doc/new_features/v92_features_doc.rst).

- **`store_validators` / `conditioned_call` / `is_fresh` / `parse_cache_control` / `is_not_modified`** (`AC_parse_cache_control`, `AC_store_validators`): `http_request` never sent `If-None-Match`/`If-Modified-Since` nor read `Cache-Control`, so every poll re-downloaded. This extracts validators, parses `Cache-Control` (max-age/no-store/…), decides freshness by an explicit age, conditions the next request, and detects `304 Not Modified`. Pure-stdlib, deterministic.

## What's new (2026-06-22) — Cookie Jar (HTTP Session Carry)

Carry a session across HTTP calls. Full reference: [`docs/source/Eng/doc/new_features/v91_features_doc.rst`](docs/source/Eng/doc/new_features/v91_features_doc.rst).

- **`CookieJar` / `parse_set_cookie`** (`AC_cookie_header`, `AC_parse_set_cookie`): `http_request` is stateless — no session cookies persisted across calls, so a login-then-call flow couldn't carry a session headlessly. This parses `Set-Cookie` headers into a jar, builds the `Cookie` request header, and saves/loads the jar as JSON (cookies cleared on `Max-Age<=0`/empty). Pure-stdlib, deterministic.

## What's new (2026-06-22) — HTTP Content Negotiation & Decompression

Build `Accept` headers and decode gzip/deflate. Full reference: [`docs/source/Eng/doc/new_features/v90_features_doc.rst`](docs/source/Eng/doc/new_features/v90_features_doc.rst).

- **`build_accept` / `build_accept_encoding` / `parse_quality_values` / `decode_body` / `negotiated_call`** (`AC_decode_body`, `AC_parse_quality_values`): `urllib`/`http_request` never set `Accept-Encoding` nor decoded `Content-Encoding`, so compressed bodies arrived raw. This adds `Accept`/`Accept-Encoding` builders, a q-value parser (sorted by quality), and gzip/deflate (incl. raw deflate) decoding. Brotli excluded (not stdlib). Pure-stdlib, deterministic.

## What's new (2026-06-22) — multipart/form-data Build & Parse

Build file-upload bodies. Full reference: [`docs/source/Eng/doc/new_features/v89_features_doc.rst`](docs/source/Eng/doc/new_features/v89_features_doc.rst).

- **`build_multipart` / `parse_multipart` / `MultipartFile`** (`AC_build_multipart`, `AC_parse_multipart`): `http_request` sent only JSON/raw — there was no file upload, and stdlib `cgi` (which parsed multipart) was removed in 3.13. This assembles a `multipart/form-data` body from text fields and files with an injectable boundary (byte-stable), and parses one back into `{fields, files}`. Pure-stdlib, deterministic.

## What's new (2026-06-22) — Secret Redaction for Config & Logs

Mask secrets before logging or exporting. Full reference: [`docs/source/Eng/doc/new_features/v88_features_doc.rst`](docs/source/Eng/doc/new_features/v88_features_doc.rst).

- **`redact_config` / `redact_secret_text`** (`AC_redact_config`, `AC_redact_secret_text`): `utils/redaction` only blurs screenshots and `secrets_scan` only *detects* — neither returned a masked copy. This reuses the `secrets_scan` detector (key-name patterns, AWS/bearer formats, high-entropy) to return a redacted deep copy of a config structure, and to mask secret-looking tokens in a free-text log line (preserving surrounding words). Vault refs (`${secrets.*}`) are left intact. Pure-stdlib, deterministic.

## What's new (2026-06-22) — RFC 8288 Link Header & Pagination

Parse `Link` headers and follow `rel="next"`. Full reference: [`docs/source/Eng/doc/new_features/v87_features_doc.rst`](docs/source/Eng/doc/new_features/v87_features_doc.rst).

- **`parse_link_header` / `next_url` / `links_by_rel` / `paginate`** (`AC_parse_link_header`, `AC_next_url`): paginated REST APIs return `Link: <...>; rel="next"` but nothing parsed it. This parses the header (quoted values with commas, multiple links), indexes by relation, and `paginate` walks `rel="next"` over an injected `fetch` (transport/cassette) up to `max_pages`. Pure-stdlib, deterministic.

## What's new (2026-06-22) — Referential Integrity Checks

Foreign-key, unique, accepted-values and row-count checks across tables. Full reference: [`docs/source/Eng/doc/new_features/v86_features_doc.rst`](docs/source/Eng/doc/new_features/v86_features_doc.rst).

- **`check_foreign_key` / `check_unique_key` / `check_accepted_values` / `check_row_count`** (`AC_check_foreign_key`, `AC_check_unique_key`, `AC_check_accepted_values`, `AC_check_row_count`): `validate_rows` is intra-row, single-table (its `unique` only dedupes within one batch). This adds dbt-style generic checks — parent/child foreign keys across two tables, single/composite key uniqueness, accepted-values, and row-count bounds — over rows from `load_rows`/`query_sqlite`. Pure-stdlib, deterministic.

## What's new (2026-06-22) — URI-Scheme Value References

Store pointers, not secrets, in config. Full reference: [`docs/source/Eng/doc/new_features/v85_features_doc.rst`](docs/source/Eng/doc/new_features/v85_features_doc.rst).

- **`resolve_ref` / `resolve_refs_in` / `is_ref` / `RefResolver`** (`AC_resolve_ref`, `AC_resolve_refs`): `interpolate` hardcoded only `${secrets.NAME}` and `AssetStore` refs were vault-name-only — there was no general read-time indirection. This resolves `env://VAR`, `file://path` (with an optional `base_dir` traversal guard), and `secret://name` (injectable resolver or the governance broker), and walks nested structures resolving every reference. Env reader / secret resolver / base dir are injectable. Pure-stdlib, deterministic.

## What's new (2026-06-21) — W3C Baggage Propagation

Carry cross-cutting key-value context across HTTP. Full reference: [`docs/source/Eng/doc/new_features/v84_features_doc.rst`](docs/source/Eng/doc/new_features/v84_features_doc.rst).

- **`Baggage` / `parse_baggage` / `format_baggage` / `inject_baggage` / `extract_baggage`** (`AC_baggage_parse`, `AC_baggage_format`): `trace_context` carried trace/span identity but nothing propagated cross-cutting context (`run_id`/`tenant`/`experiment`). This implements the W3C Baggage header — a percent-encoded `key=value` list — with an immutable `Baggage` (set/remove return new instances) and case-insensitive inject/extract over a headers dict. Pairs with `trace_context`. Pure-stdlib, deterministic.

## What's new (2026-06-21) — Dataset Diff (Row-Set Change Report)

Diff two tabular extracts by key. Full reference: [`docs/source/Eng/doc/new_features/v83_features_doc.rst`](docs/source/Eng/doc/new_features/v83_features_doc.rst).

- **`diff_rows` / `cell_changes` / `summarize_diff`** (`AC_diff_rows`, `AC_cell_changes`): the framework diffed screens/snapshots but had nothing to diff two **tabular** row-sets by key. This keys both sides and reports `{added, removed, changed, unchanged}` (changed carries `{key, old, new}`), expands per-cell `{key, column, old, new}` changes, and counts each bucket. Supports composite keys; last-write-wins on duplicates. Pure-stdlib, deterministic.

## What's new (2026-06-21) — Distribution Drift Detection

Check whether today's data is shaped like the baseline. Full reference: [`docs/source/Eng/doc/new_features/v82_features_doc.rst`](docs/source/Eng/doc/new_features/v82_features_doc.rst).

- **`psi` / `ks_two_sample` / `categorical_drift` / `detect_drift`** (`AC_detect_drift`, `AC_categorical_drift`): `stats` had A/B experiment tests but no Population Stability Index and no KS two-sample test for reference-vs-current distributions. This adds PSI (quantile-binned log-ratio), the KS statistic with a Kolmogorov p-value, and a categorical chi-square + total-variation summary — pairing with `data_profile`. `detect_drift` gives a one-call `{psi, drifted, ks}` verdict. Pure-stdlib, deterministic.

## What's new (2026-06-21) — Layered Configuration Resolver

Compose config with `defaults < file < env < CLI` precedence. Full reference: [`docs/source/Eng/doc/new_features/v81_features_doc.rst`](docs/source/Eng/doc/new_features/v81_features_doc.rst).

- **`LayeredConfig` / `deep_merge` / `SourceTrace`** (`AC_resolve_config`, `AC_explain_config`): `json_patch.merge_patch` merges two docs, `config_sync` is last-write-wins, `AssetStore` is flat-per-env — none compose an ordered precedence stack with deep merge or report which layer won each key. `add_layer(name, mapping, priority)` then `resolve()` deep-merges (nested dicts recursively, scalars/lists replaced); `explain("db.host")` names the winning layer. Layers are caller-supplied (env passed in, never `os.environ` implicitly). Pure-stdlib, deterministic.

## What's new (2026-06-21) — Server-Sent Events (SSE) Client Parser

Consume `text/event-stream` responses. Full reference: [`docs/source/Eng/doc/new_features/v80_features_doc.rst`](docs/source/Eng/doc/new_features/v80_features_doc.rst).

- **`parse_event_stream` / `SSEParser` / `SSEEvent`** (`AC_parse_sse`): the MCP HTTP transport emits SSE, but nothing consumed it — a streaming LLM/agent/chatops endpoint left `http_request` with a raw blob. This implements the WHATWG event-stream parsing algorithm (`event`/`data`/`id`/`retry`, comments, the leading-space rule, blank-line dispatch) with an incremental `feed` for chunks and a one-shot `parse_event_stream`. Pure-stdlib, fully deterministic.

## What's new (2026-06-21) — Dotenv (.env) Parsing

Read 12-factor `.env` files into config. Full reference: [`docs/source/Eng/doc/new_features/v79_features_doc.rst`](docs/source/Eng/doc/new_features/v79_features_doc.rst).

- **`parse_dotenv` / `load_dotenv` / `dotenv_values` / `dump_dotenv`** (`AC_parse_dotenv`, `AC_load_dotenv`): `load_vars_from_json` ingested flat JSON but nothing read the de-facto `.env` file. This parses `KEY=VALUE` lines (`export` prefixes, single/double quoting, `\n`/`\t` escapes, inline comments) into a plain dict — no `python-dotenv` dependency. The loader merges into a caller-supplied mapping rather than mutating `os.environ`, so it stays safe and deterministic. Pure-stdlib.

## What's new (2026-06-21) — RFC 9457 Problem Details Parsing

Read standardized API errors out of HTTP responses. Full reference: [`docs/source/Eng/doc/new_features/v78_features_doc.rst`](docs/source/Eng/doc/new_features/v78_features_doc.rst).

- **`parse_problem` / `is_problem` / `raise_for_problem` / `ProblemDetails`** (`AC_parse_problem`): `http_request` returned a non-2xx body unparsed, so flows and `assert_http` had no structured way to read a standardized API error. This parses the RFC 9457 `application/problem+json` document — registered `type`/`title`/`status`/`detail`/`instance` members plus vendor extensions — returning `None` for non-problem responses or raising `HttpProblemError`. Pure-stdlib, fully deterministic.

## What's new (2026-06-21) — Data Profiling & Schema Inference

Survey a row-set and propose a validation schema. Full reference: [`docs/source/Eng/doc/new_features/v77_features_doc.rst`](docs/source/Eng/doc/new_features/v77_features_doc.rst).

- **`profile_rows` / `infer_schema`** (`AC_profile_rows`, `AC_infer_schema`): `validate_rows` consumes a hand-written schema and `stats.describe` summarizes one numeric list — nothing surveyed a whole row-set. This profiles each column (null fraction, cardinality, inferred type, top values, numeric min/max/mean) and infers a `validate_rows`-compatible schema (required where non-null, unique where distinct, numeric bounds) — the profiler step that feeds the existing validator. Pure-stdlib, fully deterministic.

## What's new (2026-06-21) — W3C Trace Context Propagation

Correlate spans and logs across HTTP boundaries. Full reference: [`docs/source/Eng/doc/new_features/v76_features_doc.rst`](docs/source/Eng/doc/new_features/v76_features_doc.rst).

- **`SpanContext` / `new_root_context` / `child_context` / `inject_context` / `extract_context`** (`AC_trace_inject`, `AC_trace_extract`): the existing tracer and `agent_trace` spans carried no IDs, so a span on one side of an HTTP call couldn't be correlated with the work it triggered on the other. This implements the W3C Trace Context standard — generate/parse/propagate `traceparent` + `tracestate` headers (version-`00`, rejects malformed/all-zero IDs), with an injectable RNG for deterministic IDs in tests. Pure-stdlib.

## What's new (2026-06-21) — HTTP Record & Replay Cassette

Re-run API flows in CI with no live server. Full reference: [`docs/source/Eng/doc/new_features/v75_features_doc.rst`](docs/source/Eng/doc/new_features/v75_features_doc.rst).

- **`Cassette` / `CassetteMissError`** (`AC_http_replay`): the HTTP client hardcoded its `urllib` transport, so a flow driving a real API couldn't be re-run offline. The client now exposes a `build_call` / `urllib_transport` seam, and this adds a VCR-style cassette — `replay` returns a recorded response for a matching request (pure, no network — the CI-valuable half), `recording_transport` is a thin pass-through over the live transport. Match on `method`/`url` (optionally `body`); `save`/`load` JSON cassettes. Pure-stdlib.

## What's new (2026-06-21) — Bulkhead & Rate-Limit Headers

Cap concurrency, honor server back-off. Full reference: [`docs/source/Eng/doc/new_features/v74_features_doc.rst`](docs/source/Eng/doc/new_features/v74_features_doc.rst).

- **`Bulkhead` / `next_delay` / `parse_retry_after` / `parse_ratelimit`** (`AC_bulkhead_run`, `AC_retry_after`): `resilience` recovers and `rate_limit` paces, but nothing capped *simultaneous* in-flight calls (a slow dependency could exhaust every worker) and the HTTP client ignored `Retry-After`/`RateLimit-*`. This adds a bulkhead (bounded-concurrency permit that sheds load with `BulkheadFullError` when full) and parsers for the server's advised delay (delta-seconds or HTTP-date). Non-blocking permit counting → deterministic, no threads in tests. Pure-stdlib.

## What's new (2026-06-21) — Streaming Latency Percentiles

Mergeable p99 for load/soak runs. Full reference: [`docs/source/Eng/doc/new_features/v73_features_doc.rst`](docs/source/Eng/doc/new_features/v73_features_doc.rst).

- **`LatencyDigest` / `exact_percentiles`** (`AC_percentiles`): `stats.percentile` needs the full sorted list; this adds a HdrHistogram-style digest with O(1) `record`, bounded memory (significant-figure buckets), and `merge` for cross-shard aggregation — the property you need for a correct aggregate p99 from per-worker results. `exact_percentiles` covers the small-set case (arbitrary quantiles). Pure-stdlib `math`.

## What's new (2026-06-21) — Service-Level Objectives (SLO)

SLI, error budget and burn-rate alerts. Full reference: [`docs/source/Eng/doc/new_features/v72_features_doc.rst`](docs/source/Eng/doc/new_features/v72_features_doc.rst).

- **`evaluate_slo` / `burn_rate` / `burn_alerts` / `default_burn_rules`** (`AC_evaluate_slo`, `AC_burn_alerts`): the framework emitted raw signals but had no SLO layer. This computes the SLI over outcome records (`[{timestamp, ok}]`), the error budget against a target, and the **multi-window multi-burn-rate** alerts from the Google SRE workbook (page 14.4×@1h, 6×@6h; ticket 1×@3d — firing only when both windows exceed the threshold). Records are plain data, clock injectable, fully deterministic. Pure-stdlib.

## What's new (2026-06-21) — Chaos Experiments

Inject faults, verify the system holds. Full reference: [`docs/source/Eng/doc/new_features/v71_features_doc.rst`](docs/source/Eng/doc/new_features/v71_features_doc.rst).

- **`ChaosExperiment` / `run_experiment` / `Probe` / `latency_fault` / `exception_fault`** (`AC_run_chaos`): `resilience` *recovers* from failures; this *causes* them and checks a steady-state hypothesis still holds (Chaos Toolkit lifecycle — verify before, inject faults, verify after, roll back LIFO). Probes/faults/rollbacks are callables; the clock/RNG/sleep are injectable so experiments run **deterministically** in tests with no real failures or sleeping. `AC_run_chaos` drives an action-list spec. Pure-stdlib.

## What's new (2026-06-21) — JSON Contract & Snapshot Matching

Match, diff and snapshot JSON payloads. Full reference: [`docs/source/Eng/doc/new_features/v70_features_doc.rst`](docs/source/Eng/doc/new_features/v70_features_doc.rst).

- **`match_json` / `diff_json` / `normalize_json` / `snapshot_json`** (`AC_match_json`, `AC_diff_json`): `json_schema` validates against an authored schema and `jsonpath` extracts, but nothing matched two payloads with relaxed rules or diffed them path-by-path. This adds contract/snapshot matching — `partial` (subset), `match_type` (Pact-style `like`), `ignore` volatile paths — returning `{path, kind}` mismatches (`missing`/`extra`/`changed`), plus golden-master `snapshot_json`. Composes with `json_schema` + `json_patch`; pure-stdlib.

## What's new (2026-06-21) — SLSA Build Provenance

Attest what was built. Full reference: [`docs/source/Eng/doc/new_features/v69_features_doc.rst`](docs/source/Eng/doc/new_features/v69_features_doc.rst).

- **`build_provenance` / `subject_for` / `verify_provenance` / `write_provenance`** (`AC_build_provenance`, `AC_verify_provenance`): the framework signs action files and inventories deps (SBOM) but couldn't attest *what was produced by which build*. This adds an in-toto v1 Statement with a SLSA v1 provenance predicate over file `sha256` digests, and a verifier that re-hashes the artifacts (tamper → mismatch). Complements `action_signing` + `sbom`; pure-stdlib `hashlib`+`json`, fully offline.

## What's new (2026-06-21) — Feature Flags

Toggle behavior with targeting & rollout. Full reference: [`docs/source/Eng/doc/new_features/v68_features_doc.rst`](docs/source/Eng/doc/new_features/v68_features_doc.rst).

- **`FlagStore` / `evaluate_flag` / `is_enabled` / `assign_variant`** (`AC_evaluate_flag`, `AC_flag_enabled`): `decision_table` is one-shot DMN and `ab_locator` is locator A/B — neither is a product flag store with sticky % rollout. This adds an OpenFeature-shaped engine: targeting rules (`eq`/`in`/`semver_*`…), weighted variants, kill switch, and consistent-hash bucketing (`sha256(key.salt.context_key)`) so a subject is **sticky**. Returns `{value, variant, reason}` (`TARGETING_MATCH`/`SPLIT`/`DISABLED`/`ERROR`). Pure-stdlib, deterministic.

## What's new (2026-06-21) — Text Diff, Patch & Three-Way Merge

Apply and merge text diffs. Full reference: [`docs/source/Eng/doc/new_features/v67_features_doc.rst`](docs/source/Eng/doc/new_features/v67_features_doc.rst).

- **`unified_diff` / `apply_unified` / `three_way_merge`** (`AC_unified_diff`, `AC_apply_unified`, `AC_three_way_merge`): `difflib` *generates* a unified diff but the stdlib can't *apply* one, and there was no three-way merge. This adds the missing applier (walks `@@` hunks, verifies context, raises on mismatch) and a line-based three-way merge (non-overlapping edits combine cleanly; overlapping ones emit `<<<<<<<` conflict markers). Complements `json_patch` (structured JSON); pure-stdlib `difflib`.

## What's new (2026-06-21) — Calendar Recurrence Rules (RRULE)

Schedule "every 2nd Tuesday". Full reference: [`docs/source/Eng/doc/new_features/v66_features_doc.rst`](docs/source/Eng/doc/new_features/v66_features_doc.rst).

- **`parse_rrule` / `occurrences` / `next_occurrence`** (`AC_rrule_occurrences`, `AC_rrule_next`): the scheduler's cron is 5-field interval-only — it can't express "every 2nd Tuesday", "the last weekday of the month", or "every weekday for 10 occurrences". This adds an RFC 5545 (iCalendar) RRULE parser + occurrence expander supporting `FREQ`/`INTERVAL`/`COUNT`/`UNTIL`/`BYDAY` (with ordinals like `2MO`/`-1FR`)/`BYMONTHDAY`/`BYMONTH`/`BYSETPOS`/`WKST`. Pure-stdlib `datetime`+`calendar`, injectable clock for deterministic `next_occurrence`.

## What's new (2026-06-21) — Statistics & A/B Significance

Decide whether a difference is real. Full reference: [`docs/source/Eng/doc/new_features/v65_features_doc.rst`](docs/source/Eng/doc/new_features/v65_features_doc.rst).

- **`describe` / `percentile` / `two_proportion_z_test` / `welch_t_test` / `cohens_d` / `chi_square_2x2`** (`AC_describe_stats`, `AC_ab_significance`): `ab_locator` ranks by raw success rate and `run_history` stores durations, but nothing computed percentiles or significance. This adds the analysis layer — summary stats + p50/p90/p95/p99, a two-proportion z-test (with CI), Welch's t-test (exact t-distribution p-value via the incomplete beta — no SciPy), Cohen's d, and a 2×2 chi-square. The normal CDF is exact via `math.erf`; validated against textbook values (incl. the chi²=z² identity). Pure-stdlib `math`+`statistics`.

## What's new (2026-06-21) — Full-Text Search (BM25)

Rank a document corpus by relevance. Full reference: [`docs/source/Eng/doc/new_features/v64_features_doc.rst`](docs/source/Eng/doc/new_features/v64_features_doc.rst).

- **`SearchIndex` / `search_documents` / `tokenize`** (`AC_search_documents`, `ac_search_documents`): `fuzzy` is pairwise and `skill_library` matches substrings alphabetically — neither ranks a corpus by relevance. This adds an inverted-index search ranked with Okapi BM25 (`k1=1.5`, `b=0.75`, `IDF = ln(1+(N−df+0.5)/(df+0.5))`) or TF-IDF, so a rare term out-ranks a common one, term frequency saturates, and long docs are normalized down. Incremental `add`/`remove`, optional stop-words, deterministic ranking. Pure-stdlib `math`+`collections`+`re` — no database.

## What's new (2026-06-21) — JSON Pointer, Patch & Merge Patch

Address, diff and patch JSON. Full reference: [`docs/source/Eng/doc/new_features/v63_features_doc.rst`](docs/source/Eng/doc/new_features/v63_features_doc.rst).

- **`resolve_pointer` / `make_patch` / `apply_patch` / `merge_patch` / `make_merge_patch`** (`AC_resolve_pointer`, `AC_apply_json_patch`, `AC_make_json_patch`, `AC_merge_patch`): `jsonpath` is read-only and `approval` compares whole artifacts — nothing could address one location, compute a structured delta, or apply a partial update. This adds the three IETF primitives — JSON Pointer (RFC 6901), JSON Patch (RFC 6902, all six ops, **atomic** apply), and JSON Merge Patch (RFC 7386, `null` deletes) — for config-drift detection, partial updates, HTTP PATCH bodies, and golden-master deltas. Pure-stdlib `json`+`copy`, validated against the RFC test vectors.

## What's new (2026-06-21) — Client-Side Rate Limiting

Stay under API quotas. Full reference: [`docs/source/Eng/doc/new_features/v62_features_doc.rst`](docs/source/Eng/doc/new_features/v62_features_doc.rst).

- **`TokenBucket` / `SlidingWindowLimiter` / `throttle`** (`AC_rate_limit`, `ac_rate_limit`): `RetryPolicy`/`CircuitBreaker` recover from failures but nothing shaped the *rate* of calls. This adds a token bucket (smooth rate + burst), a sliding-window limiter (Cloudflare's O(1) weighted counter), and a leading-edge throttle decorator. Every limiter takes an injectable `clock` (and `acquire` a `sleep`) so it's fully deterministic in CI with no real delays. `AC_rate_limit` gates an action against a named bucket, returning `{acquired, tokens, wait}`.

## What's new (2026-06-21) — JSON Web Tokens (JWT)

Mint and verify bearer tokens for the APIs you automate. Full reference: [`docs/source/Eng/doc/new_features/v61_features_doc.rst`](docs/source/Eng/doc/new_features/v61_features_doc.rst).

- **`encode_jwt` / `decode_jwt` / `ClaimsPolicy`** (`AC_jwt_encode`, `AC_jwt_decode`): the framework had HMAC *file* signing and an ACME-bound RS256 JWS, but nothing to mint/verify a compact bearer JWT. This adds a pure-stdlib HS256/384/512 codec with full claim validation (`exp`/`nbf`/`aud`/`iss`, injectable clock) that drops straight into `http_request`'s bearer auth. Safe by default: rejects `alg:none`, enforces an algorithm allowlist (anti-confusion), and compares signatures with `hmac.compare_digest`. `AC_jwt_decode` returns `{ok, claims}` so flows can branch without raising.

## What's new (2026-06-21) — License Policy Gate

Flag disallowed dependency licenses. Full reference: [`docs/source/Eng/doc/new_features/v60_features_doc.rst`](docs/source/Eng/doc/new_features/v60_features_doc.rst).

- **`evaluate_sbom` / `evaluate_license` / `normalize_spdx` / `license_findings_to_sarif`** (`AC_check_licenses`, `ac_check_licenses`): the SBOM recorded each dependency's license name but never *judged* it. This normalizes license strings to SPDX ids and evaluates them against an allowlist/denylist (with a built-in `DEFAULT_COPYLEFT` set), understanding SPDX expressions (`OR` = choice, `AND` = all), then bridges violations into SARIF (`denied`→error, `unknown`→warning). Pure-stdlib, fully offline — the license-compliance lane beside the OSV vulnerability lane.

## What's new (2026-06-21) — OpenVEX Vulnerability Triage

Suppress the vulns that don't affect you. Full reference: [`docs/source/Eng/doc/new_features/v59_features_doc.rst`](docs/source/Eng/doc/new_features/v59_features_doc.rst).

- **`vex_statement` / `build_vex` / `apply_vex`** (`AC_apply_vex`, `ac_apply_vex`): the OSV scanner surfaces every known CVE forever — there was no way to record "we checked, this one doesn't affect us". This authors [OpenVEX](https://openvex.dev) 0.2.0 statements and applies them to the scanner's findings: `not_affected`/`fixed` **suppress** a finding, `affected`/`under_investigation` **annotate** it. Statements join on the vuln id *or* an alias, optionally product-scoped; `not_affected` requires a justification or impact statement. Pure-stdlib; chains directly after `AC_scan_vulns`.

## What's new (2026-06-21) — Dependency Vulnerability Scanning (OSV)

Match the SBOM against known CVEs. Full reference: [`docs/source/Eng/doc/new_features/v58_features_doc.rst`](docs/source/Eng/doc/new_features/v58_features_doc.rst).

- **`scan_components` / `match_package` / `is_affected` / `findings_to_sarif`** (`AC_scan_vulns`, `ac_scan_vulns`): `build_sbom` only *inventoried* dependencies and `to_sarif` only *exported* findings — nothing ever **produced** a vulnerability finding. This matches the SBOM's `(ecosystem, name, version)` components against an [OSV](https://osv.dev) advisory database (sweeping `introduced`/`fixed`/`last_affected` ranges, PEP-503 name normalization, severity→SARIF level) and bridges results into the existing SARIF exporter for GitHub/Azure DevOps code scanning. The advisory DB is **injected as data** (offline, deterministic); the live `osv.dev` query is an optional `fetcher` seam. Pure-stdlib `re`.

## What's new (2026-06-21) — JSON Schema Validation

Validate nested JSON against a real schema. Full reference: [`docs/source/Eng/doc/new_features/v57_features_doc.rst`](docs/source/Eng/doc/new_features/v57_features_doc.rst).

- **`validate_json` / `is_valid` / `assert_schema`** (`AC_validate_json`, `ac_validate_json`): the framework only *generated* JSON Schema and `data_quality` is a flat per-column checker — neither could validate a nested API request/response body. This adds the consumer: a JSON Schema (Draft 2020-12 subset) validator that reports **every** violation as `{path, keyword, message}` (e.g. `$.age maximum`). Covers `type` (incl. integral-float `integer`), `enum`/`const`, numeric/string bounds, array & object keywords, `allOf`/`anyOf`/`oneOf`/`not`, boolean schemas and local `$ref`. Pure-stdlib `re`; pairs with `json_query` and the `http_request` helper.

## What's new (2026-06-20) — SARIF 2.1.0 Findings Export

Unify scanner findings for GitHub code scanning. Full reference: [`docs/source/Eng/doc/new_features/v56_features_doc.rst`](docs/source/Eng/doc/new_features/v56_features_doc.rst).

- **`to_sarif` / `write_sarif` / `make_finding` / `from_lint_issues` / `from_audit_findings`** (`AC_export_sarif`, `ac_export_sarif`): the framework's findings producers (action-lint, secrets scan, WCAG audit, guardrail) had no common export. This builds a SARIF 2.1.0 document — with auto rule catalog and stable `partialFingerprints` for cross-run dedupe — that GitHub/Azure DevOps code scanning ingests as line-anchored alerts. Pure-stdlib `json`+`hashlib`; adapters normalize the existing lint/audit shapes.

## What's new (2026-06-20) — Text PII Detection & Redaction

Mask PII in text before it leaks. Full reference: [`docs/source/Eng/doc/new_features/v55_features_doc.rst`](docs/source/Eng/doc/new_features/v55_features_doc.rst).

- **`detect_pii` / `redact_pii_text`** (`AC_detect_pii` / `AC_redact_pii`, `ac_*`): image redaction existed but text (OCR, clipboard, LLM I/O, logs) had no string-level PII handling. This detects emails / phones / SSNs / credit cards / IPv4 / IBANs over plain text and redacts with `label` / `mask` / `partial` / `hash`. Overlapping spans dedupe (a card isn't also a phone); patterns are backtracking-safe. Pure-stdlib `re`+`hashlib`.

## What's new (2026-06-20) — Self-Healing Locator Write-Back

Persist corrected locators so heals aren't forgotten. Full reference: [`docs/source/Eng/doc/new_features/v54_features_doc.rst`](docs/source/Eng/doc/new_features/v54_features_doc.rst).

- **`RepairStore` / `repair_from_heal`** (`AC_repair_record` / `AC_repair_resolved` / `AC_repair_pending` / `AC_repair_approve`, `ac_*`): runtime self-healing previously **threw away** the corrected location, so every run re-healed. This records the corrected locator (coords/VLM description/method) from a heal, **auto-applies** it when `confidence >= auto_threshold` (default 0.9) or queues a reviewable suggestion, and `resolved(key)` returns the learned fix for reuse. Closes the heal→durable-fix loop; pure-stdlib, fully testable.

## What's new (2026-06-20) — DMN-Style Decision Tables

Externalize branching into reviewable rule tables. Full reference: [`docs/source/Eng/doc/new_features/v53_features_doc.rst`](docs/source/Eng/doc/new_features/v53_features_doc.rst).

- **`evaluate_table` / `DecisionTable`** (`AC_decision_table`, `ac_decision_table`): replaces nested `AC_if_var` chains with rows of `conditions -> outputs` and a hit policy (`UNIQUE`/`FIRST`/`PRIORITY`/`COLLECT`). Cell conditions are wildcard / literal / `{op, value}` using the executor's standard comparators (reused, not duplicated). Pure-stdlib, fully testable; the DMN way to keep business rules data-driven.

## What's new (2026-06-20) — Saga / Compensating Rollback

Undo completed steps when a later one fails. Full reference: [`docs/source/Eng/doc/new_features/v52_features_doc.rst`](docs/source/Eng/doc/new_features/v52_features_doc.rst).

- **`Saga` / `run_saga`** (`AC_run_saga`, `ac_run_saga`): records a compensating action per step; on any failure runs the completed steps' compensations in **LIFO** order — the durable-transaction primitive `AC_try` (single-block) couldn't provide. Forward actions/compensations are callables (or JSON action lists), so it's fully unit-tested with no side effects; compensation is best-effort (a failing undo is logged, rollback continues). Returns `{ok, completed, compensated, failed_step, error}`.

## What's new (2026-06-20) — JSONPath Querying

Query API/DB JSON with wildcards, recursion, filters. Full reference: [`docs/source/Eng/doc/new_features/v51_features_doc.rst`](docs/source/Eng/doc/new_features/v51_features_doc.rst).

- **`json_query` / `json_query_one` / `json_extract`** (`AC_json_query` / `AC_json_extract`, `ac_*`): the executor's path walker only split on `.` and indexed — this adds a JSONPath subset (`$`, `.key`, `[n]`/`[-n]`, `*`/`[*]`, `..` recursive descent, `[?(@.k op v)]` filters) over parsed JSON, so array-bearing API/DB responses are easy to extract from. `json_extract` runs a `{key: path}` mapping into a flat dict. Pure-stdlib `re`; the path engine `AC_http_to_var` and DB-row flows were missing.

## What's new (2026-06-20) — Multi-Channel Webhook Notifications

Alert Teams/Discord/Slack/webhook. Full reference: [`docs/source/Eng/doc/new_features/v50_features_doc.rst`](docs/source/Eng/doc/new_features/v50_features_doc.rst).

- **`notify_webhook` / `WebhookChannel`** (`AC_notify_webhook`, `ac_notify_webhook`): `notify` was desktop-toast only and ChatOps shipped Slack only — this sends to **Slack / Discord / Microsoft Teams / raw** webhooks, building the transport-shaped payload (Slack & Teams MessageCard use `text`, Discord uses `content`) and POSTing via the egress-guarded HTTP client. The `poster` transport is injectable (or `set_default_poster`), so sending is unit-tested with no network.

## What's new (2026-06-20) — Outbound CloudEvents Emitter

Emit run/automation events as CloudEvents. Full reference: [`docs/source/Eng/doc/new_features/v49_features_doc.rst`](docs/source/Eng/doc/new_features/v49_features_doc.rst).

- **`to_cloudevent` / `EventEmitter` / `post_cloudevent`** (`AC_emit_event`, `ac_emit_event`): the repo could receive webhooks but not **emit** events — this wraps run-lifecycle/assertion/failure data in a CloudEvents 1.0 (CNCF) envelope and optionally POSTs it over the egress-guarded HTTP client (interop with Knative, Azure Event Grid, iPaaS, generic webhooks). The `sink`/`poster` transport is injectable, so emission is unit-tested with no network.

## What's new (2026-06-20) — Environment-Scoped Typed Asset Store

Per-environment typed config + credential refs. Full reference: [`docs/source/Eng/doc/new_features/v48_features_doc.rst`](docs/source/Eng/doc/new_features/v48_features_doc.rst).

- **`AssetStore` / `active_environment`** (`AC_set_asset` / `AC_get_asset` / `AC_list_assets`, `ac_*`): the orchestrator "Assets/lockers" pillar — centrally-managed config values that differ by environment (dev/staging/prod) and carry a type (`text`/`int`/`bool`/`credential`). `get` coerces to the declared type and falls back to the default env; `credential` assets hold a secret *reference* that `resolve` turns into the real value via an injected resolver (Python-only, so secrets never enter `get`/executor records). Fills the gap the secret vault (secret-only) and config-sync (whole-blob) left.

## What's new (2026-06-20) — Task / Process Mining (Automation-Candidate Discovery)

Discover what to automate from recorded action logs. Full reference: [`docs/source/Eng/doc/new_features/v47_features_doc.rst`](docs/source/Eng/doc/new_features/v47_features_doc.rst).

- **`mine_action_log` / `find_repeated_sequences` / `directly_follows` / `rank_automation_candidates`** (`AC_mine_actions`, `ac_mine_actions`): mines a recorded action log for frequent, repeatable command n-grams, builds a directly-follows graph, and ranks automation candidates by `count × length` — the RPA "task mining" pillar AutoControl recorded data for but never analysed. Pure-stdlib; operates on the existing action-list shape; a candidate that recurs and spans several steps is a strong "extract into a skill" signal.

## What's new (2026-06-20) — Stuck-Loop Guard (Agent Loop Progress Detection)

Catch agents stuck in no-progress loops. Full reference: [`docs/source/Eng/doc/new_features/v46_features_doc.rst`](docs/source/Eng/doc/new_features/v46_features_doc.rst).

- **`LoopGuard` / `digest_result`** (`AC_loop_guard_observe` / `AC_loop_guard_reset`, `ac_*`): the top computer-use failure mode is an agent repeating an action with no effect — and the model can't see its own loop. `LoopGuard` watches the `(tool, args, result)` stream and flags `repeat` (same call N times), `ping_pong` (A-B-A-B), and `no_op` (observation digest unchanged), escalating `ok`→`warn`→`critical` by run length. Complements the step/time budget and offline trajectory eval; pure-stdlib, deterministic.

## What's new (2026-06-20) — Coordinate-Space Mapping (Model Grid ⇄ Physical Pixels)

Translate computer-use model clicks to real pixels. Full reference: [`docs/source/Eng/doc/new_features/v45_features_doc.rst`](docs/source/Eng/doc/new_features/v45_features_doc.rst).

- **`CoordinateSpace` / `xga_space` / `normalized_space` / `downscale_png`** (`AC_to_physical` / `AC_to_model`, `ac_*`): computer-use/VLA models click in a fixed grid (Anthropic downscales to XGA; Gemini returns a 1000×1000 grid), not physical pixels. This maps both ways (round + clamp), `xga_space` aspect-preserves without upscaling, and `downscale_png` resizes a screenshot to the model's input size (Pillow, already core). Pure-arithmetic mapping — unit-tested without a model/GPU.

## What's new (2026-06-20) — Voice-Command Router

Trigger flows hands-free from recognized speech. Full reference: [`docs/source/Eng/doc/new_features/v44_features_doc.rst`](docs/source/Eng/doc/new_features/v44_features_doc.rst).

- **`VoiceRouter`** (`AC_voice_register` / `AC_voice_dispatch` / `AC_voice_list` / `AC_voice_clear`, `ac_*`): map spoken trigger phrases to `AC_*` action lists; feed it recognized text and it runs the closest registered command (phrase matching reuses the fuzzy matcher, so "save the file" fires "save file"). **Speech-to-text is out of scope and injectable** — the router takes text and a `recognizer`/`runner` callable, so routing is fully unit-tested without audio or any speech dependency (a real Vosk/mic recogniser plugs into `listen_once`).

## What's new (2026-06-20) — Locale-Aware Number, Currency & Date Parsing

Parse localized numbers/currency/dates. Full reference: [`docs/source/Eng/doc/new_features/v43_features_doc.rst`](docs/source/Eng/doc/new_features/v43_features_doc.rst).

- **`parse_decimal` / `parse_number` / `format_decimal` / `format_currency` / `format_date`** (`AC_parse_decimal` / `AC_parse_number` / `AC_format_decimal` / `AC_format_currency` / `AC_format_date`, `ac_*`): OCR/UI text like `"1.234,56"` (de_DE) parses correctly to `1234.56` via **Babel**'s CLDR data, and values format back per-locale. `babel` is an optional `[locale]` extra, imported lazily; functional tests run under `importorskip` (wiring/facade always verified).

## What's new (2026-06-20) — Perceptual-Hash Image Dedupe

Collapse near-identical screenshots. Full reference: [`docs/source/Eng/doc/new_features/v42_features_doc.rst`](docs/source/Eng/doc/new_features/v42_features_doc.rst).

- **`average_hash` / `dhash` / `hamming_distance` / `images_similar` / `dedupe_images`** (`AC_image_hash` / `AC_dedupe_images`, `ac_*`): perceptual hashing maps visually similar images to close fingerprints, so near-duplicate frames in a recording or step report cluster by Hamming distance and collapse to one representative. Uses **Pillow** (already core — no extra dep); the dedupe/compare logic is pure Python with an injectable `hasher`, so clustering is unit-tested without any image and the real Pillow path under `importorskip`.

## What's new (2026-06-20) — S3-Compatible Artifact Store

Push run artifacts to object storage. Full reference: [`docs/source/Eng/doc/new_features/v41_features_doc.rst`](docs/source/Eng/doc/new_features/v41_features_doc.rst).

- **`S3ArtifactStore`** (`AC_s3_upload` / `AC_s3_download` / `AC_s3_list` / `AC_s3_delete`, `ac_*`): upload/download/list/delete reports, screenshots, and recordings against any S3-compatible bucket (AWS S3, MinIO, R2). `boto3` is an **optional** `[s3]` extra and the client is **injectable**, so the store's logic — and the executor path — are fully unit-tested with a fake client (no boto3/network); the live AWS path is honestly noted as CI-unverifiable. The whole API is relative to the store `prefix`. A module-level default store backs the commands.

## What's new (2026-06-20) — Fuzzy String Matching & Dedupe

Match noisy OCR/UI text robustly. Full reference: [`docs/source/Eng/doc/new_features/v40_features_doc.rst`](docs/source/Eng/doc/new_features/v40_features_doc.rst).

- **`fuzzy_ratio` / `fuzzy_best_match` / `fuzzy_matches` / `fuzzy_dedupe`** (`AC_fuzzy_ratio` / `AC_fuzzy_best_match` / `AC_fuzzy_dedupe`, `ac_*`): score similarity (0..1), pick the closest candidate from a list, or collapse near-duplicates — so a flow can act on "the button that *looks like* Submit" rather than an exact label. The default backend is stdlib `difflib` (**zero extra deps**); the optional `[fuzzy]` extra adds `rapidfuzz` for speed, with scores normalised either way. `ignore_case` and `score_cutoff` supported.

## What's new (2026-06-19) — Video Step-Overlay Report

Caption screenshots into a walkthrough video. Full reference: [`docs/source/Eng/doc/new_features/v39_features_doc.rst`](docs/source/Eng/doc/new_features/v39_features_doc.rst).

- **`write_step_video`** (`AC_write_step_video`, `ac_write_step_video`): turns per-step screenshots into a shareable video where each frame is held for a few seconds with its caption and a pass/fail colour banner burned in. The assembly logic (`build_overlay_plan` / `render_overlay_frame`) is separated from OpenCV via injectable `loader`/`drawer`/`writer_factory` hooks — unit-testable with fakes and no `cv2`/`numpy` dependency; the real path lazily imports `cv2` only when those hooks are absent. The visual companion to the HTML/JSON reports.

## What's new (2026-06-19) — Agent Observability (GenAI OpenTelemetry Spans)

OTel GenAI-convention spans for LLM runs. Full reference: [`docs/source/Eng/doc/new_features/v38_features_doc.rst`](docs/source/Eng/doc/new_features/v38_features_doc.rst).

- **`AgentTrace`** (`AC_trace_record` / `AC_trace_summary` / `AC_trace_export` / `AC_trace_reset`, `ac_*`): records spans whose attributes follow the OpenTelemetry **GenAI semantic conventions** (`gen_ai.operation.name`, `gen_ai.system`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`/`output_tokens`, `gen_ai.tool.name`) and the `"{operation} {model}"` span name. `to_otel()` drops into an OTLP exporter; `summary()` rolls up token cost and latency; an `operation()` context manager times live blocks and marks errors. Pure-stdlib (no `opentelemetry` dep), injectable clock; pairs with trajectory evaluation (record here, score there).

## What's new (2026-06-19) — Compliance Control Report (SOC2 / ISO 27001)

Map governance evidence to named controls. Full reference: [`docs/source/Eng/doc/new_features/v37_features_doc.rst`](docs/source/Eng/doc/new_features/v37_features_doc.rst).

- **`build_compliance_report`** (`AC_compliance_report`, `ac_compliance_report`): the framework already ships the controls an auditor cares about — egress allowlist, JIT credential leases, maker-checker approval, secrets scanner, audit logging, CycloneDX SBOM. This maps a flat `evidence` mapping to SOC2 (CC6.1/CC6.3/CC6.8/CC7.3/CC8.1) and ISO 27001 (A.5.23/A.8.16/A.8.30) controls, each marked `satisfied`/`gap`/`not_assessed`, and renders JSON or a standalone HTML table. The capstone of the governance set — a reporting aid, not a certification.

## What's new (2026-06-19) — Agent Trajectory Evaluation

Score an agent run against a rubric. Full reference: [`docs/source/Eng/doc/new_features/v36_features_doc.rst`](docs/source/Eng/doc/new_features/v36_features_doc.rst).

- **`evaluate_trajectory`** (`AC_evaluate_trajectory`, `ac_evaluate_trajectory`): scores a recorded trajectory (ordered `{action, args, observation}` steps) against a declarative rubric — `required_actions` (+`ordered`), `forbidden_actions`, `max_steps`, `success_contains`. Returns `{passed, score, steps, checks}` where `score` is the fraction of applicable checks passed and each `check` pinpoints a violated expectation. A deterministic, dependency-free signal for agent regression testing; the rubric is plain data so it lives in JSON action files and travels over MCP.

## What's new (2026-06-19) — Approval Testing (Golden-Master Baselines)

Lock outputs against a human-approved baseline. Full reference: [`docs/source/Eng/doc/new_features/v35_features_doc.rst`](docs/source/Eng/doc/new_features/v35_features_doc.rst).

- **`verify_artifact` / `approve_artifact`** (`AC_verify_artifact` / `AC_approve_artifact` / `AC_pending_artifacts`, `ac_*`): golden-master / snapshot testing for *any* artifact (text, JSON, OCR output, screenshot bytes). `verify_artifact` compares produced content to `<name>.approved.<ext>`; a mismatch or missing baseline writes `<name>.received.<ext>` for review and fails, and `approve_artifact` promotes a reviewed received file to the baseline. Complements pixel diffing with a review-gated baseline you commit alongside the test; names are path-traversal-checked.

## What's new (2026-06-19) — Network Egress Allowlist Guard

Pin which hosts automation may reach. Full reference: [`docs/source/Eng/doc/new_features/v34_features_doc.rst`](docs/source/Eng/doc/new_features/v34_features_doc.rst).

- **`EgressPolicy` / `set_egress_policy`** (`AC_egress_allow` / `AC_egress_check` / `AC_egress_reset`, `ac_*`): an allow list (default-deny) and/or deny list of `fnmatch` host globs (`*.example.com`) consulted by **every** `http_request` (so `AC_http` and all features built on it are covered at once). Blocked hosts raise `EgressBlocked` *before* a socket opens. Starts in allow-all mode — no behavior change until an operator locks egress down. Closes the exfiltration surface for unattended automation.

## What's new (2026-06-19) — Just-In-Time Credential Leases

Zero standing privilege for secrets. Full reference: [`docs/source/Eng/doc/new_features/v33_features_doc.rst`](docs/source/Eng/doc/new_features/v33_features_doc.rst).

- **`CredentialBroker`** (`AC_lease_secret` / `AC_lease_valid` / `AC_revoke_lease` / `AC_lease_active`, `ac_*`): a consumer takes a short-lived *lease* (token bound to a secret name + expiry); the real value is fetched only at `redeem` time, only while valid, through a pluggable resolver (an unlocked `SecretManager`, env, vault). Secret values never enter executor/MCP records — the executor/MCP/Builder surfaces manage the lease lifecycle only; `redeem` is a deliberate Python-API-only escape hatch. Clock and resolver injectable.

## What's new (2026-06-19) — Maker-Checker Approval Gate

Segregation of duties for high-risk steps. Full reference: [`docs/source/Eng/doc/new_features/v32_features_doc.rst`](docs/source/Eng/doc/new_features/v32_features_doc.rst).

- **`ApprovalGate`** (`AC_approval_request` / `AC_approval_approve` / `AC_approval_reject` / `AC_approval_status`, `ac_*`): a *maker* files a high-risk action and gets a token; a *checker* — required to be a **different** principal — approves or rejects it; the action proceeds only once `is_approved` is true. State is an optional shared JSON file so the dispatcher and the human approver can run as separate processes. Pure-stdlib, SOC2-style four-eyes control.

## What's new (2026-06-19) — Plugin SDK

Third-party `AC_*` commands via entry points. Full reference: [`docs/source/Eng/doc/new_features/v31_features_doc.rst`](docs/source/Eng/doc/new_features/v31_features_doc.rst).

- **`discover_plugins` / `load_plugins`** (`AC_list_plugins` / `AC_load_plugins`, `ac_*`): a pip package registers new executor commands declaratively in the `je_auto_control.commands` entry-point group; AutoControl discovers and registers them at runtime (immediately usable from JSON flows, socket server, scheduler, MCP). Broken plugins are skipped; the declarative, namespaced complement to the runtime path loader.

## What's new (2026-06-19) — MCP Structured Output

MCP 2025-06-18 structured tool output. Full reference: [`docs/source/Eng/doc/new_features/v30_features_doc.rst`](docs/source/Eng/doc/new_features/v30_features_doc.rst).

- **`MCPTool(output_schema=...)`** — a tool may declare an `outputSchema`; its dict result is returned as `structuredContent` in the `tools/call` response so clients/LLMs consume a typed, schema-validated object instead of re-parsing text. `to_descriptor()` advertises it in `tools/list`; non-dict results and schema-less tools are unchanged. `ac_validate_rows` is the first built-in to adopt it.

## What's new (2026-06-19) — Tweened Drag

Deterministic eased drags. Full reference: [`docs/source/Eng/doc/new_features/v29_features_doc.rst`](docs/source/Eng/doc/new_features/v29_features_doc.rst).

- **`tween_points` / `tween_drag` / `easing_names`** (`AC_tween_drag`, `ac_tween_drag`): drag from `start` to `end` along an eased curve (linear / ease_in_out_quad / ease_out_cubic / ease_in_cubic) — deterministic, pure-math path, injectable sink for tests; complements the humanized jitter.

## What's new (2026-06-19) — Process-Doc (SOP) Generator

Turn an action list into a step-by-step SOP. Full reference: [`docs/source/Eng/doc/new_features/v28_features_doc.rst`](docs/source/Eng/doc/new_features/v28_features_doc.rst).

- **`generate_sop` / `write_sop`** (`AC_generate_sop`, `ac_generate_sop`): map a recorded/authored action list to numbered, human-readable steps + an HTML document (UiPath Task-Capture deliverable); content HTML-escaped, unknown commands degrade gracefully.

## What's new (2026-06-19) — Heal Analytics & Secret Scan

Two pure-stdlib audit/analysis tools. Full reference: [`docs/source/Eng/doc/new_features/v27_features_doc.rst`](docs/source/Eng/doc/new_features/v27_features_doc.rst).

- **Self-heal analytics** — `analyze_heal_log` / `heal_stats` (`AC_heal_stats`, `ac_heal_stats`): aggregate the self-heal log into heal-rate, strategy mix, fallback-rate, avg latency and the most-brittle locators — catch decaying selectors before they fail.
- **Secret scan** — `scan_secrets(data)` (`AC_scan_secrets`, `ac_scan_secrets`): flag hardcoded secrets in action JSON (by key name, value pattern, or high entropy) that should use `${secrets.*}`; vault refs ignored, previews masked.

## What's new (2026-06-19) — CI Annotations & Clipboard History

Two pure-stdlib utilities. Full reference: [`docs/source/Eng/doc/new_features/v26_features_doc.rst`](docs/source/Eng/doc/new_features/v26_features_doc.rst).

- **CI annotations** — `emit_annotations(results)` (`AC_ci_annotations`, `ac_ci_annotations`): turn result dicts into GitHub Actions workflow commands (`::error file=...,line=...::msg`) so failures show inline in a PR, no reporter action needed.
- **Clipboard history** — `ClipboardHistory` / `default_clipboard_history` (`AC_clip_history_capture`/`list`/`search`/`start`/`stop`, `ac_clip_history_*`): a capped, searchable, newest-first ring buffer of copied text with an optional background poller.

## What's new (2026-06-19) — Resilience Primitives

Reusable retry + circuit-breaker primitives. Full reference: [`docs/source/Eng/doc/new_features/v25_features_doc.rst`](docs/source/Eng/doc/new_features/v25_features_doc.rst).

- **RetryPolicy** — `RetryPolicy(...).run(fn)` / `retry_call(fn)`: retry on configured exceptions with exponential backoff (injectable sleep). (The existing `AC_retry` flow command already retries an action body; this is the reusable callable wrapper.)
- **CircuitBreaker** — `CircuitBreaker` / `CircuitOpenError` (`AC_circuit_call`, `ac_circuit_call`): open after N consecutive failures, short-circuit until a reset timeout, then half-open — stops a retry storm hammering a downed dependency. Injectable clock; `AC_circuit_call` runs an action list through a named breaker.

## What's new (2026-06-19) — Timed Input Macros

Replay input with timing fidelity + a press-hold-release DSL, full stack. Full reference: [`docs/source/Eng/doc/new_features/v24_features_doc.rst`](docs/source/Eng/doc/new_features/v24_features_doc.rst).

- **Timed timeline replay** — `replay_timeline(events, speed=...)` (`AC_replay_timeline`, `ac_replay_timeline`): replay events honoring each `delta_ms` gap, scaled by `speed` and clampable; ops = move/click/scroll/press/release/key.
- **Input-sequence DSL** — `run_sequence(steps)` (`AC_input_sequence`, `ac_input_sequence`): declarative press/hold/release chords + `repeat`/`wait`. Both inject sink+sleep for deterministic tests.

## What's new (2026-06-19) — Semantic Screen State

The semantic companion to the pixel diff, full stack. Full reference: [`docs/source/Eng/doc/new_features/v23_features_doc.rst`](docs/source/Eng/doc/new_features/v23_features_doc.rst).

- **Snapshot & diff** — `snapshot` / `diff_snapshots` / `snapshot_screen` / `screen_changed` (`AC_screen_snapshot` / `AC_screen_diff` / `AC_screen_changed`, `ac_*`): normalize the a11y tree to `{role, name, bbox}` and report what **appeared / vanished / moved** with a human-readable summary — the feedback signal an agent needs to verify a step ("Save dialog appeared").
- **Describe the screen** — `describe_screen` (`AC_describe_screen`, `ac_describe_screen`): a compact "where am I" — role counts + interactive control labels.

## What's new (2026-06-19) — Set-of-Marks Overlay

The standard VLM-grounding format, full stack. Full reference: [`docs/source/Eng/doc/new_features/v22_features_doc.rst`](docs/source/Eng/doc/new_features/v22_features_doc.rst).

- **Number elements** — `mark_elements` / `render_marks` / `resolve_mark` (pure + Pillow): assign `1..N` to interactable elements (with centre/role/text), draw numbered red boxes on a screenshot, and map a chosen number back to its element — so a VLM picks a *number* instead of guessing pixels (directly strengthens the existing VLM locator).
- **Mark-then-click loop** — `mark_screen(render_path=...)` / `mark_click(n)` (`AC_mark_screen` / `AC_mark_click`, `ac_*`): number the live a11y tree (+ optional overlay screenshot), feed marks+image to a model, then click mark `n`.

## What's new (2026-06-19) — Checkpoint & Resume

Durable execution for long flows + a `py.typed` marker, full stack. Full reference: [`docs/source/Eng/doc/new_features/v21_features_doc.rst`](docs/source/Eng/doc/new_features/v21_features_doc.rst).

- **Flow checkpoint & resume** — `run_resumable(actions, run_id=..., store=...)` / `CheckpointStore` (`AC_run_resumable` / `AC_checkpoint_status` / `AC_checkpoint_clear`, `ac_*`): persist step-index + variables after each step; on re-run with the same `run_id`, fast-forward past completed steps and rehydrate variables — a flow that crashes at step 400 resumes at 400, not 0. Pluggable (SQLite default), cleared on completion.
- **`py.typed` marker** — ships the PEP 561 marker so Mypy/Pyright/Pylance honor AutoControl's inline type hints in downstream code (the repo's typed API was previously invisible to type checkers).

## What's new (2026-06-19) — i18n / l10n Testing

Three pure-stdlib internationalization/localization testing helpers that compound, full stack. Full reference: [`docs/source/Eng/doc/new_features/v20_features_doc.rst`](docs/source/Eng/doc/new_features/v20_features_doc.rst).

- **Pseudo-localization** — `pseudo_localize` / `pseudo_localize_catalog` (`AC_pseudo_localize`, `ac_pseudo_localize`): accent + pad UI strings (placeholders preserved, `⟦…⟧` wrapped) to flush out hardcoded text and pre-stress layout before real translation.
- **Text-overflow detection** — `check_overflow(elements)` (`AC_check_overflow`, `ac_check_overflow`): flag text whose estimated width exceeds its widget bounds (the #1 l10n bug), computed from the a11y bounds AutoControl already reads.
- **Catalog completeness** — `check_catalog(base, target)` (`AC_check_catalog`, `ac_check_catalog`): diff a translation catalog for missing / orphaned / empty keys and placeholder mismatches — a CI gate against blank UI.

## What's new (2026-06-19) — Data Quality

Three pure-stdlib data-quality helpers (the gate between `load_rows`/OCR and downstream entry), full stack. Full reference: [`docs/source/Eng/doc/new_features/v19_features_doc.rst`](docs/source/Eng/doc/new_features/v19_features_doc.rst).

- **Row schema validation** — `validate_rows(rows, schema)` (`AC_validate_rows`, `ac_validate_rows`): declarative per-field rules (type/required/regex/min/max/min_len/max_len/allowed/unique); returns `{ok, valid, invalid, errors}` so bad scraped/OCR data is caught before it corrupts an ERP/form.
- **Field extraction** — `extract_fields(text, fields, patterns)` (`AC_extract_fields`, `ac_extract_fields`): named regex presets (email/url/ipv4/phone/date_iso/amount/hashtag) + custom patterns over free text / OCR blobs.
- **Row masking** — `mask_rows(rows, rules)` (`AC_mask_rows`, `ac_mask_rows`): mask columns before export — `redact` / `hash` (SHA-256) / `partial` (keep last 4); complements the screenshot-only redaction.

## What's new (2026-06-19) — SBOM & Suite Sharding

Two pure-stdlib ops tools (security + scale research angles), full stack. Full reference: [`docs/source/Eng/doc/new_features/v18_features_doc.rst`](docs/source/Eng/doc/new_features/v18_features_doc.rst).

- **CycloneDX SBOM** — `build_sbom` / `write_sbom` (`AC_generate_sbom`, `ac_generate_sbom`): emit a CycloneDX 1.6 dependency SBOM (name/version/purl/license) for supply-chain compliance (EU CRA / EO 14028); `root` limits to a package's closure, `extra_components` inventories action files. No third-party dependency.
- **Duration-aware suite sharding** — `shard_flows` / `merge_results` (`AC_shard_suite` / `AC_merge_results`): bin-pack flows into N shards balanced by historical per-flow duration (so the slowest worker, not test count, defines runtime), then merge per-shard reports into one rollup.

## What's new (2026-06-19) — Reactive Observer

A non-blocking screen observer (SikuliX `observe` model), full stack (facade, `AC_*`, MCP, Script Builder). Full reference: [`docs/source/Eng/doc/new_features/v17_features_doc.rst`](docs/source/Eng/doc/new_features/v17_features_doc.rst).

- **`ScreenObserver`** (`AC_observe_add` / `AC_observe_remove` / `AC_observe_list` / `AC_observe_poll` / `AC_observe_start` / `AC_observe_stop`, `ac_observe_*`): register watches that fire on **appear** / **vanish** / **change** of an image/text/pixel and run a callback or action list — react to dialogs/progress/status while the main flow continues.
- **Testable by design** — detection is an injectable `predicate`; transition logic is unit-tested via `poll_once()` with synthetic values. Built-in `image_predicate` / `text_predicate` / `pixel_predicate` wrap the existing locate/OCR/pixel helpers.

## What's new (2026-06-19) — WCAG 2.2 Audit

The accessibility audit gains a WCAG 2.2 / EN 301 549 success-criterion layer, full stack (facade, `AC_*`, MCP, Script Builder). Full reference: [`docs/source/Eng/doc/new_features/v16_features_doc.rst`](docs/source/Eng/doc/new_features/v16_features_doc.rst).

- **WCAG-tagged conformance audit** — `wcag_audit(level="AA")` (`AC_wcag_audit`, `ac_wcag_audit`): tags every defect with its WCAG success-criterion id/level/impact (4.1.2, 1.4.3, 1.4.10) and returns a conformance report with `by_criterion`/`by_impact` counts, filtered to A/AA/AAA — mappable to EN 301 549 for EAA compliance evidence.
- **Target Size (SC 2.5.8)** — `audit_target_size(elements, min_px=24)`: new WCAG 2.2 rule flagging interactive targets smaller than 24×24 px, computed from element bounds; `tag_issue` adds SC tagging to any existing audit issue.

## What's new (2026-06-19) — Memory & Determinism

Two pure-stdlib tools from the agent/QA research round, full stack (facade, `AC_*`, MCP, Script Builder). Full reference: [`docs/source/Eng/doc/new_features/v15_features_doc.rst`](docs/source/Eng/doc/new_features/v15_features_doc.rst).

- **Agent episodic memory** — `AgentMemory` (`AC_memory_remember` / `AC_memory_recall` / `AC_memory_recent` / `AC_memory_forget` / `AC_memory_stats`, `ac_memory_*`): SQLite store of `(goal → trajectory → outcome)` episodes with keyword recall to inject past experience into the planner's context — cross-run learning, no embedding dependency.
- **Deterministic run** — `DeterministicRun` / `seed_everything` (`AC_seed_everything`, `ac_seed_everything`): pin the RNG seed and freeze `time.time` for a `with` block (recording the choices for replay) to kill time/randomness flakiness; `time.monotonic` left intact so timeouts still work.

## What's new (2026-06-19) — Office I/O

Headless read/write for Excel/Word/PowerPoint, full stack (facade, `AC_*`, MCP, Script Builder). Optional extra: `pip install je_auto_control[office]`. Full reference: [`docs/source/Eng/doc/new_features/v14_features_doc.rst`](docs/source/Eng/doc/new_features/v14_features_doc.rst).

- **Excel** — `read_workbook` / `write_workbook` (`AC_read_workbook` / `AC_write_workbook`, `ac_read_workbook` / `ac_write_workbook`): read an `.xlsx` worksheet into row dicts (first row = keys) and write rows back, no GUI.
- **Word** — `read_document` / `write_document` (`AC_read_document` / `AC_write_document`): read/write `.docx` paragraphs.
- **PowerPoint** — `read_presentation` / `write_presentation` (`AC_read_presentation` / `AC_write_presentation`): read per-slide text; write slides as `{title, body:[...]}`.

The backing libraries (`openpyxl`/`python-docx`/`python-pptx`) are optional — each call raises a clear error if missing, and `import je_auto_control` pulls none of them.

## What's new (2026-06-19) — Agent Toolkit

Three pure-stdlib tools for LLM/agent-driven automation, full stack (facade, `AC_*`, MCP, Script Builder). Full reference: [`docs/source/Eng/doc/new_features/v13_features_doc.rst`](docs/source/Eng/doc/new_features/v13_features_doc.rst).

- **Skill / playbook library** — `SkillLibrary` (`AC_skill_save` / `AC_skill_run` / `AC_skill_list` / `AC_skill_remove` / `AC_skill_search`, `ac_skill_*`): store named, reusable action sequences on disk, search them by name/description/tags, and replay across runs — the durable counterpart to in-memory macros.
- **Prompt-injection guardrail** — `assess_text` / `scan_text` / `redact_text` (`AC_guard_text`, `ac_guard_text`): scan untrusted screen/OCR text for injection patterns (instruction-override, system-prompt exfiltration, jailbreak/chat-template markers …) before feeding it to an LLM; returns `{suspicious, score, findings, redacted}`.
- **A2A agent card** — `build_agent_card` / `write_agent_card` (`AC_agent_card`, `ac_agent_card`): publish an A2A agent card so other agents can discover and call AutoControl as a GUI-automation peer.

## What's new (2026-06-19) — Authoring & Debugging

Two pure-stdlib authoring-time tools, full stack (facade, `AC_*`, MCP, Script Builder). Full reference: [`docs/source/Eng/doc/new_features/v12_features_doc.rst`](docs/source/Eng/doc/new_features/v12_features_doc.rst).

- **Element repository** — `ElementRepository` (`AC_element_save` / `AC_element_find` / `AC_element_click` / `AC_element_remove` / `AC_element_list`, `ac_element_*`): save native-UI locators under friendly names (object repository) and reuse them — `repo.click("login.submit")` instead of repeating name/role everywhere; a UI change is fixed in one place.
- **Step debugger / tracer** — `FlowDebugger` (breakpoints, `step`/`continue_`/`run_to_end`, live `variables()`) and `trace_actions` (`AC_debug_trace`, `ac_debug_trace`): step through an action list one command at a time with variables persisting across steps, or get a per-step `{index, command, result}` trace (with `dry_run` to plan without running).

## What's new (2026-06-19) — Test & Tooling Batch

Three pure-stdlib quality-of-life tools, full stack (facade, `AC_*`, MCP, Script Builder). Full reference: [`docs/source/Eng/doc/new_features/v11_features_doc.rst`](docs/source/Eng/doc/new_features/v11_features_doc.rst).

- **Synthetic test data** — `generate_rows(schema, count, seed=...)` / `write_dataset` (`AC_generate_data`, `ac_generate_data`): deterministic fake rows (name/email/phone/int/choice/date…) to drive data-driven runs without real PII; no Faker.
- **MCP registry manifest** — `write_server_manifest("server.json", include_tools=True)` (`AC_mcp_manifest`, `ac_mcp_manifest`): publish a registry-valid `server.json` so MCP agents/IDEs can discover this server.
- **Risk-based test selection** — `rank_flows` / `select_flows` (`AC_rank_tests` / `AC_select_tests`): rank flows by recent failures, flakiness, staleness and never-run from run history; run the riskiest first or only the top-k.

## What's new (2026-06-19) — Transactional Queue

Turn AutoControl from "run a script" into "run a robot." A SQLite-backed work queue implements the production-RPA dispatcher/performer pattern: enqueue items, process one at a time with per-item status, dedup and retry, so a run of thousands is **resumable after a crash** and parallelizable. Pure stdlib, full stack. Full reference: [`docs/source/Eng/doc/new_features/v10_features_doc.rst`](docs/source/Eng/doc/new_features/v10_features_doc.rst).

- **Dispatcher/performer** — `WorkQueue.add()` enqueues (dedupes by reference); `get_next()` atomically claims the oldest item; `complete()` / `fail()` record the outcome. `AC_queue_add` / `AC_queue_next` / `AC_queue_complete` / `AC_queue_fail` / `AC_queue_stats`.
- **Failure semantics** — application errors retry up to `max_retries`; **business** errors (`BusinessError` / `kind="business"`) never retry. `stats()` gives per-status counts for dashboards.

## What's new (2026-06-19) — Unattended Reliability

Three practitioner-pain fixes for unattended / login automation, all headless and full-stack. Full reference: [`docs/source/Eng/doc/new_features/v9_features_doc.rst`](docs/source/Eng/doc/new_features/v9_features_doc.rst).

- **OTP / TOTP for 2FA** — `generate_totp` / `verify_totp` (`AC_otp_to_var`, `ac_generate_otp`): mint the current 6-digit code from a base32 secret to type into a login form (reuses the remote-desktop TOTP engine).
- **Native file dialogs** — `handle_file_dialog` (`AC_handle_file_dialog`): wait for the OS Open/Save/folder dialog, type the path, confirm — in one call, with an injectable driver.
- **Locked-session guard** — `ensure_interactive_session` / `is_session_locked` (`AC_assert_session_active`): fail clearly when the workstation is locked / disconnected instead of emitting phantom clicks.

## What's new (2026-06-19) — Popup Watchdog

The #1 cause of unattended-automation failure is an unexpected dialog the script never coded for (UAC, "session expiring", Windows Update, a modal). The popup watchdog runs a concurrent guard thread that watches for registered patterns and dismisses them independently of the main flow. Surfaced by the practitioner pain-point research as the top unattended failure cause; full stack (facade, `AC_*`, MCP, Script Builder), fully headless. Full reference: [`docs/source/Eng/doc/new_features/v8_features_doc.rst`](docs/source/Eng/doc/new_features/v8_features_doc.rst).

- **Auto-dismiss popups** — `default_popup_watchdog.add_window_rule(title, action="close")` then `.start()` (`AC_watchdog_add` / `AC_watchdog_start` / `AC_watchdog_stop` / `AC_watchdog_list`): closes a matching window or presses a key (`enter`/`esc`) when it appears.
- **Custom rules** — `PopupWatchdog` / `WatchdogRule` pair any detector (image/a11y/text) with a dismisser; a failing rule is logged and skipped, never killing the guard loop.

## What's new (2026-06-19) — Native UI Control

Object-level desktop automation: read and drive native controls through the OS accessibility API (by name / role / app / **AutomationId**) instead of clicking pixels or OCR-ing text — far more reliable for native apps. The accessibility layer previously only listed/found/clicked; it now also acts. Ships through the full stack (facade, `AC_*`, MCP, Script Builder) with a Windows UIAutomation backend; unsupported backends raise a clear error. Full reference: [`docs/source/Eng/doc/new_features/v7_features_doc.rst`](docs/source/Eng/doc/new_features/v7_features_doc.rst).

- **Read / set value** — `control_get_value` / `control_set_value` (`AC_control_get_value` / `AC_control_set_value`): read a textbox/combo value (no OCR) and set it in one call (no per-key typing).
- **Invoke / toggle** — `control_invoke` / `control_toggle` (`AC_control_invoke` / `AC_control_toggle`): press a button or flip a checkbox via its control pattern.
- **Read a table/grid** — `read_control_table` (`AC_read_table`): scrape a grid/list/table control into rows of cell strings — desktop data extraction without OCR.
- Targets a control by `name` / `role` / `app_name` / `automation_id` (the stable Windows identifier), so it survives layout/localization changes.

## What's new (2026-06-19)

Two headless cores that shipped without the rest of their stack are now
first-class. Both gain a facade re-export, an `AC_*` executor command, an
MCP tool, and a Script Builder entry, with headless tests. Full reference:
[`docs/source/Eng/doc/new_features/v6_features_doc.rst`](docs/source/Eng/doc/new_features/v6_features_doc.rst).

- **Visual regression (golden images)** — `take_golden` / `compare_to_golden` (`AC_take_golden` / `AC_assert_visual`): capture a baseline screenshot and fail when the screen drifts beyond a pixel tolerance, with a highlighted diff image and mask regions. `AC_assert_visual` auto-creates the baseline on first run. PIL-only.
- **Finite-state machine** — `run_state_machine` (`AC_run_state_machine`): drive a script as a declarative `{initial, states}` spec whose `on_enter` actions run through the executor and whose transitions fire on `after` / `if_var_eq` / predicate guards, bounded by `max_steps` / `global_timeout_s`.

## What's new (2026-06-18)

Eight headless capabilities that round out scripting, integration, and CI
use: a real command-line interface, recording-to-code generation, and
first-class HTTP / SQL / email / PDF / wait steps. Each ships a headless
Python API, an `AC_*` executor command, an MCP tool, and a visual Script
Builder entry, and is covered by headless tests (network / SMTP / PDF
backends are injected, so nothing touches the outside world). Full
reference page:
[`docs/source/Eng/doc/new_features/v5_features_doc.rst`](docs/source/Eng/doc/new_features/v5_features_doc.rst).

**Command-line interface**
- **`je_auto_control` console script** — run and inspect action files from a shell / CI: `run` (with `--var`, `--dry-run`), `validate` (alias `lint`), `list-commands`, `fmt`, `record`, `codegen`, `version`.

**Code generation**
- **Recording → code** — `generate_code` / `generate_code_file` (`AC_generate_code`, `je_auto_control codegen`) turn a recording or action file into a pytest test, standalone Python, or Robot suite. The default `calls` style emits readable `ac.<fn>(...)` statements, falling back to `ac.execute_action([...])` for flow control.

**Integrations**
- **HTTP / API** — `http_request` (`AC_http_request`): method, headers, JSON or raw body, basic / bearer auth, explicit timeout; non-2xx responses are returned (not raised) so you can assert on status. `AC_http_to_var` now shares the client and can POST bodies.
- **SQL** — `query_sqlite` (`AC_sql_to_var` / `AC_assert_db`): read-only, parameter-bound SQLite queries into a variable, or a scalar assertion (e.g. `SELECT COUNT(*) ... == 0`).
- **Email (SMTP)** — `send_email` (`AC_send_email`): stdlib SMTP with TLS on by default (STARTTLS or implicit SSL over a verified context), attachments, and multiple recipients.
- **PDF** — `extract_pdf_text` / `pdf_metadata` / `assert_pdf_text` (`AC_pdf_to_var` / `AC_assert_pdf_text`): text extraction and content assertions, backed by the optional `pypdf` extra (`pip install je_auto_control[pdf]`).

**Smart waits**
- **Wait for a file** — `wait_until_file` (`AC_wait_for_file`) blocks until a file exists and its size stops growing (a download finished writing).
- **Wait for a TCP port** — `wait_until_port` (`AC_wait_for_port`) blocks until `host:port` accepts connections (pairs with `launch_process`).
- **Wait for a process** — `wait_until_process` (`AC_wait_for_process`) blocks until a process appears or exits — the companion to `launch_process` / `kill_process` (requires psutil).

**Security** — HTTP / SMTP enforce http/https or TLS with verified certificates and explicit timeouts; SQL is read-only and parameter-bound; file paths are resolved before I/O.

## What's new (2026-06-17)

Thirty-plus automation primitives across input realism, vision, flow
control, triggers, window management, and file security — plus recoverable
deletion and an editor undo. Each ships with a headless API, an `AC_*`
executor command, and a visual Script Builder entry; vision and window
features keep their geometry / IO operations injectable so the logic is
fully unit-tested. Full reference page:
[`docs/source/Eng/doc/new_features/v4_features_doc.rst`](docs/source/Eng/doc/new_features/v4_features_doc.rst).

**Human-like input**
- **Human-like mouse motion** — `move_mouse_humanized` walks an eased, bowed cubic-Bezier path with optional overshoot + jitter, deterministic by `seed` (`AC_human_move`).
- **Human-like typing** — `type_text_humanized` types character by character with a jittered per-key delay and optional "thinking" pauses, seedable (`AC_human_type`).

**Vision**
- **VLM natural-language assertion** — `assert_by_description` asks a vision-language model whether the screen matches a description; the `verify()` companion to `locate_by_description` (`AC_assert_vlm`).
- **Scroll-to-find** — `scroll_until_visible` scrolls a direction until a template image or OCR text appears, or the budget runs out (`AC_scroll_to_find`).
- **Region colour stats** — `region_color_stats` reports a region's average + dominant colour and that colour's pixel fraction (`AC_region_color_stats`).
- **QR reading** — `read_qr_codes` decodes QR codes in a screen region via OpenCV's `QRCodeDetector` (no new dependency) (`AC_read_qr`).

**Flow control & variables**
- **Reusable macros** — `AC_define_macro` / `AC_call_macro`: define a named, parameterised action sub-routine once and call it with `${arg}` bindings.
- **In-process parallel** — `AC_parallel` runs branch action lists concurrently, each on an isolated executor so branches never race on shared variables.
- **Performance-budget assertion** — `assert_duration` / `AC_assert_duration` fails a block that takes longer than a millisecond budget.
- **Read into a variable** — `AC_ocr_to_var`, `AC_shell_to_var`, `AC_read_file_to_var`, `AC_http_to_var` (body or dotted JSON path), `AC_now_to_var` (strftime), `AC_random_to_var` (seeded int / float / choice).
- **Transform a variable** — `AC_transform_var`: upper / lower / strip / title / replace / regex-extract / slice, in place or into a new variable.
- **Assert a variable** — `assert_variable` / `AC_assert_var`: eq / ne / lt / gt / contains / regex through the assertion DSL.

**Triggers & smart waits**
- **Composite triggers** — `AllOfTrigger` / `AnyOfTrigger` / `SequenceTrigger` combine any existing trigger by boolean AND / OR / ordered sequence.
- **Cron trigger** — `CronTrigger` fires on a five-field cron expression, composing with the boolean triggers (e.g. "at 09:00 *and* only if the image is on screen").
- **More smart waits** — `wait_until_clipboard_changes` (`AC_wait_clipboard_change`) and `wait_until_window_closed` (`AC_wait_window_closed`).

**Window management**
- **Per-window capture** — `capture_window` screenshots exactly a window's bounds by title (`AC_capture_window`).
- **Layout save / restore** — `save_window_layout` / `restore_window_layout` snapshot every window's position to JSON and move them all back later (`AC_save_window_layout` / `AC_restore_window_layout`).
- **Snap / tile** — `snap_window` moves a window to a screen half, quarter, or maximize (`AC_snap_window`).

**File security & safety**
- **Action-file signing** — `sign_action_file` / `verify_action_file` (HMAC-SHA256 sidecar); `execute_files` can require signatures via `JE_AUTOCONTROL_REQUIRE_SIGNED_ACTIONS` (`AC_sign_action_file` / `AC_verify_action_file`).
- **Action-file encryption** — `encrypt_action_file` / `decrypt_action_file` (Fernet, AES-128-CBC + HMAC) (`AC_encrypt_action_file` / `AC_decrypt_action_file`).
- **Recoverable deletion** — `move_to_trash` sends a file to the OS recycle bin (Win32 `SHFileOperation` undo flag / macOS Trash / Linux XDG trash, preferring `send2trash`) (`AC_move_to_trash`).

**Reporting & notifications**
- **Screenshot annotation** — `annotate_screenshot` draws labelled boxes / translucent highlights / arrows / text onto a capture (`AC_annotate_screenshot`).
- **Desktop notifications** — `notify` shows a cross-platform toast (notify-send / osascript / PowerShell), injection-safe (`AC_notify`).

**GUI**
- **Recording Editor undo** — every edit is snapshotted; **Ctrl+Z** (and an Undo button) restore the prior state.
- **Triggers tab** — "Combine selected" wraps chosen triggers into a composite; new **Cron** trigger type.
- **Assertions tab** — new **VLM** ("screen matches description") assertion kind.
- Every new `AC_*` command appears in the visual **Script Builder**.

**Fixes** — repaired the USB-passthrough approval-prompt crash on PySide6 6.11.1 (`Q_ARG(object)` → a Qt signal), eight stale / broken GUI + USB tests, two lost exception chains, and brought thirteen functions back under the cyclomatic-complexity gate.

## What's new (2026-06)

Nine additions that turn the automation primitives into a full **QA / test
framework**: assert screen state, drive scripts from data, detect and
quarantine flaky tests, run a scored suite, emit CI-native reports, audit
accessibility / i18n, fan a script across a device matrix, and assert on
audio / video. Each ships with a headless API, an `AC_*` executor command,
an `ac_*` MCP tool, and a Qt GUI tab. Full reference page:
[`docs/source/Eng/doc/new_features/v3_features_doc.rst`](docs/source/Eng/doc/new_features/v3_features_doc.rst).

**Assertions**
- **Assertion DSL** — verify screen state instead of only driving it: `assert_text` (OCR, `regex` + `present=False` for absence), `assert_image`, `assert_pixel`, `assert_window`, `assert_clipboard` (`equals` / `contains` / `regex`, `present=False` to confirm a secret was cleared), `assert_process` (a named process is / isn't running, via psutil). Returns an `AssertionResult`; raises `AutoControlAssertionException` on mismatch with optional failure screenshot (`AC_assert_text / _image / _pixel / _window / _clipboard / _process`).
- **Off-screen assertions** — `assert_file` (existence / substring / SHA-256 / minimum size — verify a download or export) and `assert_http` (an http/https endpoint returns a status + optional body text, always with an explicit timeout). Both extend the DSL beyond the screen and plug into the combinators below (`AC_assert_file / AC_assert_http`).
- **Assertion combinators** — `assert_all([...specs])` runs a batch as *soft assertions* (every spec is checked, all failures collected before raising) and returns a `GroupAssertionResult`; `assert_any([...specs])` is the OR-complement (passes when at least one spec passes, short-circuiting — e.g. *either* a success dialog *or* a redirect confirms a login); `assert_eventually(spec, timeout, interval)` retries one declarative assertion spec until it passes or times out (e.g. poll a health endpoint until it returns 200, or wait for a download file to appear). Both are spec-driven (`{"kind": "text", "text": "Saved"}`, `{"kind": "http", "url": "..."}`) so they work identically from Python, JSON, and MCP across every assertion kind — text/image/pixel/window/clipboard/process/file/http (`AC_assert_all / AC_assert_eventually`).
- **Media assertions** — `assert_audio_activity` (record + RMS threshold for sound vs silence) and `assert_video_changes` (mean frame-to-frame diff over a segment for motion vs static); pure numeric cores, lazy `sounddevice` / OpenCV (`AC_assert_audio / AC_assert_video_changes`).

**Data-driven execution**
- **Data sources** — `load_rows` connectors for CSV / JSON / SQLite / Excel / inline; the `AC_for_each_row` block command runs a body once per row with `${row.column}` access. SQLite is single read-only `SELECT`/`WITH` only; paths are `realpath`-validated. `${var}` interpolation now resolves dotted dict-key / list-index paths while preserving types (`AC_load_data`).

**Flaky detection & quarantine**
- **Flaky report** — score intermittent failures from run history by pass↔fail flip rate, grouped by script / source (`AC_flaky_report`).
- **Quarantine** — a persistent (mode 0600) skip-list the suite runner honours; `auto_quarantine_from_flakiness` auto-populates it above a flip-rate threshold (`AC_quarantine_add / _remove / _list / _clear / _auto`).

**Suite runner + CI reports**
- **QA suite orchestration** — `run_suite` turns action lists into scored cases with setup / teardown, tags, and data-driven expansion; assertion failures → failed, other exceptions → error, quarantined → skipped (`AC_run_suite`).
- **JUnit / Allure reports** — `write_junit_xml` + `write_allure_results` (or `junit_path` / `allure_dir` on `AC_run_suite`) emit reports Jenkins / GitHub Actions / GitLab CI / Allure parse natively.

**Audit, matrix, media**
- **Accessibility / i18n audit** — reuse the a11y tree + OCR to find missing accessible names, WCAG contrast-ratio failures, and ellipsis-truncated strings (`AC_audit_accessibility / AC_audit_contrast`).
- **Mobile device matrix** — fan one action list across many Android / iOS devices in parallel, each on an isolated executor, targeting the current device via `${device.*}`; per-device pass/fail, failures isolated (`AC_run_device_matrix`).

## What's new (2026-05)

Twenty-seven additions covering smarter locators, deeper IDE / ops
tooling, four new platforms (Wayland, Wayland-libei, Android
widget-tree, iOS), screenshot PII redaction, and a generic
plan-execute-verify agent loop. Each ships with a headless API, an
`AC_*` executor command, an `ac_*` MCP tool, and (where it makes
sense) a Qt GUI tab. Full reference page:
[`docs/source/Eng/doc/new_features/v2_features_doc.rst`](docs/source/Eng/doc/new_features/v2_features_doc.rst).

**Locator + selector intelligence**
- **Self-healing locator** — `image_template → VLM` fallback with a JSON-lines audit log (`AC_self_heal_locate / _click`).
- **Anchor-based locator** — find element B by spatial relation (`above`, `below`, `left_of`, `right_of`, `near`) to anchor A; anchor and target can use different backends (image / OCR / VLM / a11y).
- **OCR with structured output** — cluster raw OCR matches into rows, tables, and `label:value` form fields (`AC_ocr_read_structure`).
- **Smart waits** — `wait_until_screen_stable`, `wait_until_pixel_changes`, `wait_until_region_idle`: frame-diff replacements for `time.sleep`.
- **A/B locator framework** — race N strategies for the same target; recommend the historically best one from a persisted ledger.

**Operations + observability**
- **LLM cost telemetry** — per-call token + USD log with day / model / provider rollup (`record_llm_call`, `summarise_llm_costs`).
- **Trace replay UI** — scrubbable timeline over the existing time-travel recordings with per-step action list.
- **Failure → ticket automation** — fan a failure report out to Jira / Linear / GitHub Issues when a scheduled / triggered / REST run fails.
- **Container CI templates** — GitHub Actions + GitLab CI workflows that build the image, run the headless pytest suite under Xvfb, and smoke-test the REST entrypoint; XFCE+x11vnc Dockerfile variant for flows that need a real WM.
- **Cross-host DAG orchestrator** — parallel execution with skip-on-failure cascade across local + admin-console-registered hosts (`run_dag`, `AC_run_dag`).
- **Multi-viewer presence** — roster + controller/observer roles for the remote desktop, with a thread-safe Python `PresenceRegistry` independent of aiortc.

**Agent + integrations**
- **Computer-use high-level API** — `run_computer_use(goal, ...)` wraps `ComputerUseAgentBackend` + `AgentLoop`; auto-detects display size; bounded by `max_steps` / `wall_seconds`.
- **Generic agent loop JSON + MCP** — `AC_run_agent` / `ac_run_agent` expose the closed-loop `AgentLoop` (plan → act → verify → retry) with pluggable Anthropic / OpenAI backends; the Anthropic-only Computer-Use raw path remains via `AC_computer_use`.
- **WebRunner convenience commands** — `web_open` / `web_quit` / `web_screenshot` / `web_current_url` on top of the existing `je_web_runner` bridge; same surface exposed as `AC_web_*` and `ac_web_*`.
- **Chat-ops bot** — transport-agnostic `CommandRouter` + polling Slack adapter. Built-in commands: `/help`, `/scripts`, `/run`, `/screenshot`, `/status`. RBAC via `required_role`.

**Privacy + safety**
- **Screenshot PII redaction** — `RedactionEngine` with built-in detectors for email / credit card / SSN / phone (regex against caller-supplied OCR tokens) plus accessibility-tree secure-text-field detection. Forced regions for sticky overlays. Env-var-driven default policy `JE_AUTOCONTROL_REDACTION=off|moderate|strict`. Wired through `AC_redact_screenshot` + `ac_redact_screenshot`.

**Platform coverage**
- **Wayland CLI backend** — `wtype` / `ydotool` / `grim` with `XDG_SESSION_TYPE` auto-detect and X11 (XWayland) fallback; override via `JE_AUTOCONTROL_LINUX_DISPLAY_SERVER=x11|wayland|auto`.
- **Wayland libei native** — ctypes binding to `libei.so.*` for microsecond-latency input; opt-in via `JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND=libei|cli|auto`. Defaults to libei when loadable.
- **macOS Accessibility deep-dive** — recursive `dump_accessibility_tree()` plus a polling `AccessibilityRecorder` for focus / bounds events.
- **Android — adb shell primitives** — `AC_android_tap/swipe/key/text/screenshot` route through `adb` for any phone over USB / Wi-Fi adb. No daemon required.
- **Android — uiautomator2 widget tree** — `AC_android_find_element/click_element/dump_hierarchy` add selector-based widget lookup (`text` / `resource_id` / `description` / `class_name`) and live XML hierarchy dump on top of the adb path.
- **iOS — XCUITest via WebDriverAgent** — new `je_auto_control.ios.*` namespace: `tap`, `swipe`, `long_press`, `type_text`, `press_key`, `screenshot`, `screen_size`, `find_element` / `click_element` (XCUITest selectors: `name`, `class_name`, `predicate`), `dump_source`. Seven new `AC_ios_*` executor commands and matching `ac_ios_*` MCP tools. `facebook-wda` is an optional pip dep; loads lazily so non-Mac hosts still import the package.

**Developer experience**
- **autocontrol-lsp completion** — the language server now tracks `didOpen` / `didChange` / `didClose`, publishes diagnostics for invalid JSON and unknown `AC_*` commands, and provides signature help generated from the live executor table.
- **`.pyi` stub generator** — `python -m je_auto_control.utils.stubs.generator je_auto_control/actions.pyi` emits an IDE-facing stub so every `AC_*` command autocompletes with parameter hints.
- **VS Code extension** — bundled extension now ships `AutoControl: Run / Screenshot / Preview` commands that hit the local REST API.
- **Browser extension recorder** — Manifest V3 extension under `browser-extension/`: capture clicks, typing, navigation, form submissions in a tab and export them as `AC_web_*` / `WR_*` JSON.
- **pytest plugin + Gherkin BDD** — `pytest11` entry point auto-loads; `@pytest.mark.autocontrol` arms screenshot-on-failure; `bdd_steps.register_pytest_bdd_steps(pytest_bdd)` wires `Given/When/Then` onto every `AC_*` verb.
- **Visual flow editor** — node-based view that round-trips to the same JSON action format the list-based Script Builder uses.

---
