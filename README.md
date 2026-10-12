# multimodal-asset-manifest

A stdlib-only validator for manifests of image/audio/video assets: schema checks, per-type metadata (dimensions, duration, fps), license fields, sha256 checksums, and optional on-disk existence + hash audit. If you ship multimodal datasets or prompt packs and need a machine-checkable manifest, use this; otherwise skip it.

## Problem

Multimodal assets pile up faster than their metadata. Files get renamed, checksums rot, licenses go undeclared, and images lack dimensions while videos lack fps — discovered only when a downstream pipeline or license review fails. Teams need one offline, dependency-free gate they can run in CI before an asset bundle ships.

## How it works

- Manifest = JSON: `{"schema_version": ..., "assets": [...]}`.
- Per asset: non-empty unique `id`, relative safe `path` (no absolute paths, no `..`), `type` in {image, audio, video, other}, required `license`.
- Type-specific required metadata: image -> `width`/`height` (positive ints) + `format`; audio -> `duration_seconds`; video -> `duration_seconds` + `width`/`height`/`fps`.
- `sha256`: optional (WARN if missing) but must be 64 lowercase hex when present.
- With `--root`: audits file existence and recomputes sha256 on disk, flagging `FILE_MISSING` / `FILE_HASH_MISMATCH`.
- Findings are `{code, severity, message, location}`; exit 1 on any ERROR.

## Quickstart (~2 min)

```bash
python multimodal_asset_manifest.py audit manifest.json --root assets/   # ~0.5s
python multimodal_asset_manifest.py audit manifest.json --json           # CI-friendly output
```

Then run the self-test suite: `python self_test.py` (~0.6s).

## Why not X

No direct equivalent found as of 2026-10-13: searches for "multimodal asset manifest validator / dataset manifest schema checker" surface format specs rather than standalone offline auditors. Nearest neighbors:

- **JSON Schema + ajv** — you'd hand-roll the per-type metadata rules, path-safety, and hash audit every time; this repo packages those decisions.
- **DVC / LakeFS data manifests** — version-control-integrated tooling with heavier setup; not a single-file check for an arbitrary asset bundle.
- **Hugging Face dataset card / metadata validators** — bound to the Hub ecosystem and its specific fields; no checksum-against-disk audit for local bundles.
- **MediaInfo / ExifTool** — excellent per-file technical metadata extraction, but no manifest-level schema (uniqueness, license, path safety) or cross-file audit.

## Performance

Measured on CPython 3.13.12, Windows 10 Pro, 2026-10-13:

- Full self-test suite (74 cases): **~0.6 s** [Measured] — repro: `python self_test.py`
- Validate a 500-asset manifest (no disk audit): **~1.3 ms/op** [Measured] — repro:

```bash
python -m timeit -s "import multimodal_asset_manifest as m, json; man=json.load(open('manifest.json'))" "m.validate_manifest(man)"
```

- sha256 recomputation on disk is IO-bound (~1 GB/s on SSD-class storage); the 5 MB fixture hashes in a few ms inside the self-test. [Measured]

## Minimal Fallback

No installs needed beyond Python 3.8+. If you cannot run the validator, approximate with:

```bash
python -c "import json;m=json.load(open('manifest.json'));print(len(m['assets']))"   # manifest parses
find assets -name "*.png" | wc -l                                                    # rough count
```

You lose schema, path-safety, license, and hash checks entirely.

## Design Trade-offs

- **Checksum format check vs trust**: missing sha256 is only a WARN (many legit bundles lack hashes), but a *malformed* hash is an ERROR — typos are worse than absence.
- **Path safety over path flexibility**: absolute paths and `..` are rejected outright; manifests should be relocatable.
- **Priority order**: data integrity (hash/disk audit) > schema completeness > convenience; `--no-hash` exists for fast schema-only passes, never default.

## Limits & Second-order Effects

- Hash audit reads whole files; multi-GB video assets make `--root` runs slow — use `--no-hash` for structure-only passes.
- It validates *declared* metadata (width/duration are not parsed from file headers); a lying manifest with correct hashes passes.
- If widely adopted, teams may treat a green manifest as license clearance; the linter checks that license strings are present, not that they are legally sufficient.

## FAQ

**Does it inspect file contents for dimensions/duration?** No — declared metadata only. Pair with ExifTool/MediaInfo if you need header-level truth.

**Can I add custom fields?** Yes; unknown fields are allowed and ignored.

**When NOT to use this tool?** Skip it for versioned dataset registries already managed by DVC/LakeFS, or if your platform enforces its own stronger ingestion schema — a second validator invites drift. Also don't rely on it for license *compliance*; it only checks presence.

## [Core Assumptions]

1. Asset bundles can be described by a single JSON manifest with relative paths rooted at one directory.
2. sha256 is the acceptable integrity baseline (no multi-hash support needed at this scale).
3. Licenses can be named by string tags; "unknown" must be explicit rather than silent.
4. Manifest checks belong in CI, so a deterministic exit-code contract (0/1/2) matters more than rich reporting.

---

Confidence: High (≥80%) for schema/path/hash behavior — 74 self-test cases including real-file hash audits. Medium (60-79%) that the default required-field set matches most teams' needs — reasonable default, not survey-validated. Data as of 2026-10-13.

---

Part of the [zhengming-toolbox](https://github.com/chenhz01/zhengming-toolbox) — 105 purpose-built AI-engineering tools across neglected niches.

Related tools: [experiment-registry-schema](https://github.com/chenhz01/experiment-registry-schema) · [image-alt-check](https://github.com/chenhz01/image-alt-check) · [metric-definition-dict](https://github.com/chenhz01/metric-definition-dict)
