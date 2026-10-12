# -*- coding: utf-8 -*-
"""multimodal-asset-manifest: manifest schema + missing-metadata audit (stdlib).

Validates a JSON manifest describing image/audio/video assets: required
fields, type-specific metadata (dimensions/duration/fps), relative-path
safety, sha256 checksum format, optional on-disk existence + hash audit.
"""
import argparse
import hashlib
import json
import os
import re
import sys

__version__ = "0.1.1"

VALID_TYPES = {"image", "audio", "video", "other"}
SHA_RE = re.compile(r"[0-9a-f]{64}")


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _require_positive_num(obj, field, loc, add):
    v = obj.get(field)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
        add("ASSET_FIELD_MISSING", "ERROR",
            "%s requires positive number field '%s'" % (loc.rsplit("[", 1)[-1].rstrip("]"), field), loc)
        return False
    return True


def validate_manifest(manifest, root=None, verify_hash=True):
    """Validate a manifest dict; return a list of finding dicts.

    Raises TypeError when manifest is not a dict. When `root` is given,
    audits file existence and (optionally) recomputes sha256 on disk.
    """
    if not isinstance(manifest, dict):
        raise TypeError("manifest must be a dict")
    findings = []

    def add(code, sev, msg, loc):
        findings.append({"code": code, "severity": sev, "message": msg, "location": loc})

    if "schema_version" not in manifest:
        add("MISSING_SCHEMA_VERSION", "ERROR", "manifest lacks 'schema_version'", "$")
    assets = manifest.get("assets")
    if not isinstance(assets, list):
        add("ASSETS_NOT_LIST", "ERROR", "manifest.assets must be a list", "$.assets")
        return findings

    seen_ids = set()
    for i, a in enumerate(assets):
        loc = "$.assets[%d]" % i
        if not isinstance(a, dict):
            add("ASSET_NOT_OBJECT", "ERROR", "asset must be an object", loc)
            continue
        aid = a.get("id")
        if not isinstance(aid, str) or not aid.strip():
            add("ASSET_ID_INVALID", "ERROR", "asset id must be a non-empty string", loc)
        elif aid in seen_ids:
            add("ASSET_ID_DUP", "ERROR", "duplicate asset id: %s" % aid, loc)
        else:
            seen_ids.add(aid)

        p = a.get("path")
        path_ok = isinstance(p, str) and p.strip()
        if not path_ok:
            add("ASSET_PATH_INVALID", "ERROR", "asset path must be a non-empty string", loc)
        else:
            norm = p.replace("\\", "/")
            if p.startswith("/") or (len(p) > 1 and p[1] == ":"):
                add("ASSET_PATH_ABSOLUTE", "ERROR", "asset path must be relative", loc)
            if ".." in norm.split("/"):
                add("ASSET_PATH_TRAVERSAL", "ERROR", "asset path must not contain '..'", loc)

        t = a.get("type")
        if t not in VALID_TYPES:
            add("ASSET_TYPE_INVALID", "ERROR",
                "asset type must be one of %s" % sorted(VALID_TYPES), loc)
            t = None

        lic = a.get("license")
        if not isinstance(lic, str) or not lic.strip():
            add("ASSET_LICENSE_MISSING", "ERROR", "asset license is required", loc)
        elif lic.strip().lower() == "unknown":
            add("ASSET_LICENSE_UNKNOWN", "WARN", "asset license is 'unknown'", loc)

        sha = a.get("sha256")
        sha_ok = isinstance(sha, str) and SHA_RE.fullmatch(sha)
        if sha is None:
            add("ASSET_SHA_MISSING", "WARN", "asset sha256 not declared", loc)
        elif not sha_ok:
            add("ASSET_SHA_MALFORMED", "ERROR",
                "asset sha256 must be 64 lowercase hex chars", loc)

        if t == "image":
            for fld in ("width", "height"):
                v = a.get(fld)
                if isinstance(v, bool) or not isinstance(v, int) or v <= 0:
                    add("ASSET_FIELD_MISSING", "ERROR",
                        "image asset requires positive integer '%s'" % fld, loc)
            if not isinstance(a.get("format"), str) or not a.get("format"):
                add("ASSET_FIELD_MISSING", "ERROR", "image asset requires 'format'", loc)
        elif t == "audio":
            _require_positive_num(a, "duration_seconds", loc, add)
        elif t == "video":
            _require_positive_num(a, "duration_seconds", loc, add)
            for fld in ("width", "height", "fps"):
                _require_positive_num(a, fld, loc, add)

        if root and path_ok:
            fp = os.path.join(root, p)
            if not os.path.isfile(fp):
                add("FILE_MISSING", "ERROR", "file not found under root: %s" % p, loc)
            elif verify_hash and sha_ok:
                if _sha256_file(fp) != sha:
                    add("FILE_HASH_MISMATCH", "ERROR",
                        "file hash mismatch for %s" % p, loc)
    return findings


def summarize(findings):
    out = {"error": 0, "warn": 0, "info": 0}
    for f in findings:
        key = f["severity"].lower()
        out[key] = out.get(key, 0) + 1
    return out


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="multimodal-asset-manifest",
        description="Validate multimodal asset manifests: schema, metadata "
                    "completeness, path safety, checksum audit.")
    p.add_argument("manifest", help="path to manifest JSON")
    p.add_argument("--root", default=None,
                   help="directory against which asset paths are audited")
    p.add_argument("--no-hash", dest="no_hash", action="store_true",
                   help="skip on-disk sha256 recomputation")
    p.add_argument("--json", dest="as_json", action="store_true",
                   help="emit findings as JSON")
    a = p.parse_args(argv)

    try:
        with open(a.manifest, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except OSError as e:
        print("error: cannot read manifest: %s" % e, file=sys.stderr)
        sys.exit(2)
    except ValueError as e:
        print("error: manifest is not valid JSON: %s" % e, file=sys.stderr)
        sys.exit(2)

    try:
        findings = validate_manifest(manifest, root=a.root,
                                     verify_hash=not a.no_hash)
    except TypeError as e:
        print("error: %s" % e, file=sys.stderr)
        sys.exit(2)

    s = summarize(findings)
    if a.as_json:
        print(json.dumps({"findings": findings, "summary": s},
                         ensure_ascii=False, indent=2))
    else:
        for f in findings:
            print("[%s] %s %s: %s" % (f["severity"], f["location"],
                                      f["code"], f["message"]))
        print("summary: %d error(s), %d warn(s), %d info(s)"
              % (s["error"], s["warn"], s["info"]))
    sys.exit(1 if s["error"] else 0)


if __name__ == "__main__":
    main()
