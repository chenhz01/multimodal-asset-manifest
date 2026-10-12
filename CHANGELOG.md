# Changelog

## v0.1.1 (2026-10-13)

Round-2 revision after full self-review of the v0.1.0 draft:

- Added 4 extreme-edge test cases (empty-file hash audit, 5 MB hash
  computation, `images/../images/x` parent-reference traversal, `type: other`
  minimal assets); suite grew 70 -> 74 cases, all PASS.
- Removed dead line from the CLI test helper; fixed the missing-schema-version
  fixture to actually omit the key instead of setting it to null.
- Measured and documented Performance numbers ([Measured] tags, repro commands).
- Added ALIGNMENT.md (rules 85-100 audit, 16 items with evidence).

## v0.1.0 (2026-10-13)

Initial draft:

- Manifest schema validation: schema_version, assets list, unique ids,
  relative path safety (no absolute paths, no `..`), type whitelist
  {image, audio, video, other}, required license with "unknown" warning.
- Type-specific metadata rules (image width/height/format; audio duration;
  video duration/width/height/fps) with bool-as-number rejection.
- sha256 format validation plus optional on-disk existence and hash audit
  (`--root`, `--no-hash`).
- CLI (`audit`, `--root`, `--no-hash`, `--json`) with exit-code contract 0/1/2.
- Self-test suite: 70 cases across functional / exception / extreme-edge
  classes, `SUMMARY: PASS n/n` reporting, four-defence template.
- README, MIT LICENSE.
