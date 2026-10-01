# UI reference study

Status: implementation authorized on October 1, 2026. The latest five-screen purple Slice concept supersedes the earlier blue/dark-only direction.

The user supplied three mobile screenshots in the October 1, 2026 conversation. These notes record observations; the original image files are not stored in this repository.

## Preparation screen

The second screenshot makes the 3D model and perspective build plate the main surface. A black background and muted gray grid keep attention on the model. Small floating controls sit along the upper and right edges. A three-item bottom navigation separates Prepare, Preview, and Machine, with blue indicating the active section.

## Toolpath preview

The first screenshot keeps the same scene and navigation. Contrasting blue and orange toolpaths show the layer structure. A panel immediately below the viewport pairs the layer count with Z height, then a large slider supports layer inspection. Camera controls and a small axis indicator stay close to the scene.

## Print review

The third screenshot presents a file title, a centered model thumbnail, and three compact rows for speed, filament mass, and print duration. Labels sit on the left and values on the right. A prominent green Print button sits at the bottom. This is a reference for visual hierarchy; the existing table-clear confirmation and hash-bound print approval must remain explicit in any later design.

## Direction for a later implementation

Use a mobile-first, viewport-first product layout with restrained dark surfaces. Group work into preparation, preview, and machine contexts. Keep secondary controls compact, give touch targets adequate size, and use text labels for important actions. Reserve blue for selection and navigation; use a distinct primary print action. Show progress, errors, and save confirmation near the action that causes them.

Retain the existing desktop workflow, accessible contrast, keyboard operation, and physical-print safeguards. Avoid decorative marketing sections and extra motion. The latest upstream Taste skill describes landing pages and portfolios as its main scope and excludes multi-step product UI; use only applicable reference-reading principles, not its marketing layout or framework defaults.

## Requested skill sources

- Taste: https://github.com/leonxlnx/taste-skill
- I Have ADHD: https://github.com/ayghri/i-have-adhd
- Caveman: already available locally in the Codex skills catalog.

## Implemented Slice concept

Five responsive stages: Import, Prepare, Preview, Validate and Print. Neutral light/dark surfaces, purple #8754D9, large touch targets and collapsed technical details. Existing native HTML/CSS/Three.js stack retained. Mobile and desktop use the same real workflow.

Only supported STL/3MF inputs and actual Home Assistant telemetry are exposed. Preview remains the real top-down layer extrusion path, not a fabricated speed-colored 3D render. Camera, cloud library, scaling and infill editing are not shown because the current backend does not provide these capabilities. Validation does not imply a fresh hardware preflight: this runs at send time. Table-clear consent, hash-bound confirmation and at-most-once start remain intact.
