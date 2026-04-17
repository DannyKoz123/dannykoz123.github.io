# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository purpose

Personal site served by GitHub Pages at `dannykoz123.github.io`. Pure static HTML/CSS/JS — there is no build system, package manager, lint config, or test suite at the repo root. Files are served as-is.

## Local development

There is no dev server to install. To preview changes, serve the repo root over HTTP so root-absolute asset paths resolve (the `method-of-images-explorer` bundle uses `/projects/...` URLs and will 404 under `file://`):

```
python3 -m http.server 8000
# then open http://localhost:8000/
```

## Site structure

Top-level pages (`index.html`, `profiles/index.html`, `projects/index.html`) all share `/styles.css` and use the same `.page-shell` → `.card` → `.page-header` + chip-nav layout. When adding a new top-level page, replicate this pattern and add a `.chip` link to the nav on every page so navigation stays consistent.

Styling conventions in `styles.css`:
- Light/dark theming via CSS custom properties in `:root` and `@media (prefers-color-scheme: dark)`. Use the existing `--bg`, `--card`, `--text`, `--muted`, `--ring`, `--accent`, `--accent-soft`, `--shadow` vars rather than hard-coded colors.
- `.projects-page` / `.projects-card` / `.page-shell-projects` override the default card chrome with a dark-themed, wider layout specifically for `/projects/`.

## Projects

Each subdirectory under `projects/` is a self-contained mini-app reachable via its own `index.html`. They use different architectures:

### `projects/learn-russian-cursive/`

Vanilla-JS handwriting practice app, no bundler. Three scripts are loaded in order with `defer` from `index.html`:

1. `js/curriculum.js` — defines `stages`/lessons, exposes `globalThis.CursiveCurriculum` (frozen).
2. `js/storage.js` — localStorage persistence under key `learn-russian-cursive` (current `STORAGE_VERSION = 3`, with migration from legacy `easy:`/`hard:` prefixed keys); exposes `globalThis.CursiveStorage`.
3. `js/main.js` — routing (hash-based: `profiles` / `stage` / `stage-detail` / `lesson`), canvas-based stroke rendering, and UI wiring against the `<template>` elements in `index.html`.

Each file is wrapped in an IIFE and communicates only via `globalThis.CursiveCurriculum` / `globalThis.CursiveStorage`. `main.js` throws on load if either global is missing, so script order in `index.html` must not change.

Bumping `STORAGE_VERSION` or changing the shape of profile/progress records requires updating `normalizeProfileRecord` / `normalizeProgressRecord` / `normalizeLegacyProgressKey` to migrate existing saved data.

UI uses `<template>` elements (`#profile-view-template`, `#stage-view-template`, `#stage-detail-view-template`, `#lesson-view-template`, etc.) cloned into `#app`. Adding a view means adding both a template in `index.html` and a render path in `main.js`.

Handwriting uses the bundled `assets/fonts/Propisi-Regular.woff` via a runtime-registered `FontFace` named `"Propisi Runtime"` (see `HANDWRITING_FONT` in `main.js`) — keep the filename/path in sync if fonts move.

### `projects/method-of-images-explorer/`

Two-level structure:
- `index.html` is a wrapper page in the site's theme that embeds the app in an `<iframe>` pointing at `./app/#/plane`.
- `app/` contains a **pre-built Vite/React bundle** (`app/index.html` + `app/assets/index-*.js` + `app/assets/index-*.css`). The source is not in this repo.

The bundled `app/index.html` references assets with root-absolute paths (`/projects/method-of-images-explorer/app/assets/...`), which is why the site must be served from the repo root (GitHub Pages path, or `python3 -m http.server` at the root). Do not hand-edit files in `app/assets/` — they are build output and the hashed filenames in `app/index.html` must match. To update this project, rebuild it in its source repo and replace the `app/` directory wholesale, then update both `index.html` files' references if the hashed filenames change.

Routing inside the app is hash-based (`#/plane`, `#/sphere`); the wrapper's "Open grounded plane / sphere" chips and the iframe `src` all depend on those hashes.

## Deployment

Pushing to `main` deploys via GitHub Pages — there is no CI step. The active feature branch for this work is `claude/add-claude-documentation-fEzkK`; develop and push there, not to `main`.
