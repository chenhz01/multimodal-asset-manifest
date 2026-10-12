# -*- coding: utf-8 -*-
"""self_test for multimodal-asset-manifest — R14, inherits 4-defence template v2."""
import atexit
import contextlib
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", newline="\n")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import multimodal_asset_manifest as m  # noqa: E402

_TMP = tempfile.mkdtemp(prefix="mmam_selftest_")
atexit.register(shutil.rmtree, _TMP, ignore_errors=True)

# on-disk fixture files for the existence/hash audit
FILES = os.path.join(_TMP, "files")
os.makedirs(os.path.join(FILES, "images"), exist_ok=True)
CONTENT_A = b"asset-bytes-a"
CONTENT_B = b"different-bytes"
SHA_A = hashlib.sha256(CONTENT_A).hexdigest()
with open(os.path.join(FILES, "images", "a.png"), "wb") as f:
    f.write(CONTENT_A)
with open(os.path.join(FILES, "images", "b.png"), "wb") as f:
    f.write(CONTENT_B)


def wf(name, content):
    p = os.path.join(_TMP, name)
    with open(p, "w", encoding="utf-8", newline="") as f:  # Defence 3
        f.write(content)
    return p


def run_cli(argv):
    buf_out, buf_err = io.StringIO(), io.StringIO()
    code = 0
    try:
        with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
            m.main(argv)
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    except Exception as e:  # noqa: BLE001
        code = 1
        buf_err.write(repr(e))
    return code, buf_out.getvalue(), buf_err.getvalue()


def asset(**kw):
    a = {"id": "img-001", "path": "images/a.png", "type": "image", "format": "png",
         "width": 100, "height": 100, "license": "CC0", "sha256": SHA_A}
    a.update(kw)
    return {k: v for k, v in a.items() if v is not None}


def manifest(assets=None, **top):
    d = {"schema_version": "1.0",
         "assets": assets if assets is not None else [asset()]}
    d.update(top)
    return d

MANIFEST_OK = wf("b_ok.json", json.dumps(manifest()))
MANIFEST_BAD = wf("b_bad.json", json.dumps({"schema_version": "1.0", "assets": [{"id": "x"}]}))
MANIFEST_MALFORMED = wf("b_malformed.json", "{oops")
MANIFEST_LIST = wf("b_list.json", json.dumps([1, 2]))

# ---- [A] functional: (name, manifest, checks, no_errors, kwargs) ----
A_CASES = [
    ("valid_manifest_clean", manifest(), [], True, {}),
    ("valid_with_disk_audit", manifest(), [], True, {"root": FILES}),
    ("missing_schema_version", {"assets": [asset()]}, [("MISSING_SCHEMA_VERSION", "")], False, {}),
    ("assets_missing", {"schema_version": "1.0"}, [("ASSETS_NOT_LIST", "")], False, {}),
    ("assets_not_list", manifest(assets={"id": "x"}), [("ASSETS_NOT_LIST", "")], False, {}),
    ("asset_not_object", manifest([42]), [("ASSET_NOT_OBJECT", "")], False, {}),
    ("id_missing", manifest([asset(id=None)]), [("ASSET_ID_INVALID", "")], False, {}),
    ("id_empty", manifest([asset(id="  ")]), [("ASSET_ID_INVALID", "")], False, {}),
    ("id_duplicate", manifest([asset(), asset(id="img-001", path="images/b.png")]),
     [("ASSET_ID_DUP", "img-001")], False, {}),
    ("path_missing", manifest([asset(path=None)]), [("ASSET_PATH_INVALID", "")], False, {}),
    ("path_absolute", manifest([asset(path="/etc/passwd")]), [("ASSET_PATH_ABSOLUTE", "")], False, {}),
    ("path_windows_absolute", manifest([asset(path="C:/tmp/x.png")]), [("ASSET_PATH_ABSOLUTE", "")], False, {}),
    ("path_traversal", manifest([asset(path="../secret.png")]), [("ASSET_PATH_TRAVERSAL", "")], False, {}),
    ("type_invalid", manifest([asset(type="movie")]), [("ASSET_TYPE_INVALID", "")], False, {}),
    ("license_missing", manifest([asset(license=None)]), [("ASSET_LICENSE_MISSING", "")], False, {}),
    ("license_unknown_warn", manifest([asset(license="unknown")]), [("ASSET_LICENSE_UNKNOWN", "")], False, {}),
    ("sha_missing_warn", manifest([asset(sha256=None)]), [("ASSET_SHA_MISSING", "")], False, {}),
    ("sha_uppercase", manifest([asset(sha256=SHA_A.upper())]), [("ASSET_SHA_MALFORMED", "")], False, {}),
    ("sha_short", manifest([asset(sha256="abcd")]), [("ASSET_SHA_MALFORMED", "")], False, {}),
    ("image_missing_width", manifest([asset(width=None)]), [("ASSET_FIELD_MISSING", "width")], False, {}),
    ("image_bool_width", manifest([asset(width=True)]), [("ASSET_FIELD_MISSING", "width")], False, {}),
    ("audio_missing_duration", manifest([asset(type="audio", width=None, height=None, format=None,
                                               duration_seconds=None)]),
     [("ASSET_FIELD_MISSING", "duration_seconds")], False, {}),
    ("video_missing_fps", manifest([asset(type="video", format=None, duration_seconds=10, fps=None)]),
     [("ASSET_FIELD_MISSING", "fps")], False, {}),
    ("video_fps_zero", manifest([asset(type="video", format=None, duration_seconds=10, fps=0)]),
     [("ASSET_FIELD_MISSING", "fps")], False, {}),
    ("duration_negative", manifest([asset(type="audio", width=None, height=None, format=None,
                                          duration_seconds=-1)]),
     [("ASSET_FIELD_MISSING", "duration_seconds")], False, {}),
    ("file_missing", manifest([asset(path="images/gone.png")]), [("FILE_MISSING", "")], False, {"root": FILES}),
    ("file_hash_mismatch", manifest([asset(path="images/b.png")]), [("FILE_HASH_MISMATCH", "")], False,
     {"root": FILES}),
]


def _mk_a(name, man, checks, no_errors, kw):
    def t(self):
        fs = m.validate_manifest(man, **kw)
        if no_errors:
            self.assertEqual([f for f in fs if f["severity"] == "ERROR"], [], msg=name)
        for code, sub in checks:
            hit = [f for f in fs if f["code"] == code and sub in f["message"]]
            self.assertTrue(hit, msg="%s expects %s (%r)" % (name, code, sub))
    t.__doc__ = "A: %s" % name
    return t


class TestA(unittest.TestCase):
    def test_a25_unknown_severity_is_warn(self):
        fs = m.validate_manifest(manifest([asset(license="unknown")]))
        self.assertEqual(fs[0]["severity"], "WARN")

    def test_a26_sha_missing_severity_is_warn(self):
        fs = m.validate_manifest(manifest([asset(sha256=None)]))
        self.assertEqual(fs[0]["severity"], "WARN")

    def test_a27_hash_match_positive(self):
        fs = m.validate_manifest(manifest(), root=FILES, verify_hash=True)
        self.assertEqual(fs, [])

    def test_a28_audio_video_extra_fields_allowed(self):
        fs = m.validate_manifest(manifest([asset(type="audio", width=None, height=None, format=None,
                                                 duration_seconds=5, sample_rate=44100)]))
        self.assertEqual(fs, [])

    def test_a29_type_error_on_non_dict(self):
        with self.assertRaises(TypeError):
            m.validate_manifest([1, 2])

    def test_a30_type_error_on_none(self):
        with self.assertRaises(TypeError):
            m.validate_manifest(None)


for _i, _c in enumerate(A_CASES):
    _nm, _mn, _ck, _ne = _c[0], _c[1], _c[2], _c[3]
    _kw = _c[4] if len(_c) > 4 else {}
    setattr(TestA, "test_a%02d_%s" % (_i, _nm), _mk_a(_nm, _mn, _ck, _ne, _kw))

# ---- [B] CLI contract ----
B_CASES = [
    ("valid_exit0", MANIFEST_OK, ["--root", FILES], 0, "", ""),
    ("invalid_exit1", MANIFEST_BAD, [], 1, "", ""),
    ("json_flag", MANIFEST_OK, ["--json"], 0, '"findings"', ""),
    ("missing_manifest", None, [], 2, "", "cannot read"),
    ("malformed_json", MANIFEST_MALFORMED, [], 2, "", "not valid JSON"),
    ("manifest_is_list", MANIFEST_LIST, [], 2, "", "must be a dict"),
    ("no_hash_skips_mismatch",
     wf("b_nohash.json", json.dumps(manifest([asset(path="images/b.png")]))),
     ["--root", FILES, "--no-hash"], 0, "", ""),
    ("text_output_summary", MANIFEST_OK, [], 0, "summary:", ""),
    ("json_summary_key", MANIFEST_BAD, ["--json"], 1, '"summary"', ""),
    ("warn_only_exit0", wf("b_warn.json", json.dumps(manifest([asset(license="unknown")]))),
     [], 0, "", ""),
    ("root_missing_dir_exit1", MANIFEST_OK, ["--root", os.path.join(_TMP, "no_such_dir")], 1, "", ""),
]


def _mk_b(name, content, extra, code, out_sub="", err_sub=""):
    def t(self):
        path = content if content is not None else os.path.join(_TMP, "absent_%s.json" % name)
        c, out, err = run_cli([path] + extra)
        self.assertEqual(c, code, msg="out=%r err=%r" % (out, err))
        if out_sub:
            self.assertIn(out_sub, out)
        if err_sub:
            self.assertIn(err_sub, err)
    t.__doc__ = "B: %s" % name
    return t


class TestB(unittest.TestCase):
    def test_b11_missing_positional(self):
        c, _out, _err = run_cli([])
        self.assertEqual(c, 2)

    def test_b12_help_exit0(self):
        c, out, _err = run_cli(["--help"])
        self.assertEqual(c, 0)
        self.assertIn("usage:", out)


for _i, (_nm, _ct, _ex, _cd, _os, _es) in enumerate(B_CASES):
    setattr(TestB, "test_b%02d_%s" % (_i, _nm), _mk_b(_nm, _ct, _ex, _cd, _os, _es))

# ---- [C] extreme/edge: (name, fn(self)) ----
C_CASES = [
    ("empty_dict", lambda s: s.assertTrue(
        {"MISSING_SCHEMA_VERSION", "ASSETS_NOT_LIST"} <=
        {f["code"] for f in m.validate_manifest({})})),
    ("empty_assets_clean", lambda s: s.assertEqual(m.validate_manifest(manifest([])), [])),
    ("manifest_none_raises", lambda s: s.assertRaises(TypeError, m.validate_manifest, None)),
    ("manifest_str_raises", lambda s: s.assertRaises(TypeError, m.validate_manifest, "x")),
    ("unicode_id_ok", lambda s: s.assertEqual(
        m.validate_manifest(manifest([asset(id="图像-001")])), [])),
    ("emoji_path_no_crash", lambda s: s.assertIsInstance(
        m.validate_manifest(manifest([asset(path="图片/😀.png")])), list)),
    ("thousand_assets_clean", lambda s: s.assertEqual(
        m.validate_manifest(manifest([asset(id="a%04d" % i, path="p/%d.png" % i)
                                      for i in range(1000)])), [])),
    ("sha_63_chars", lambda s: s.assertTrue(any(
        f["code"] == "ASSET_SHA_MALFORMED"
        for f in m.validate_manifest(manifest([asset(sha256="a" * 63)])))),
     ),
    ("sha_non_hex", lambda s: s.assertTrue(any(
        f["code"] == "ASSET_SHA_MALFORMED"
        for f in m.validate_manifest(manifest([asset(sha256="z" * 64)])))),
     ),
    ("width_float_rejected", lambda s: s.assertTrue(any(
        f["code"] == "ASSET_FIELD_MISSING" and "width" in f["message"]
        for f in m.validate_manifest(manifest([asset(width=100.5)]))))),
    ("width_zero_rejected", lambda s: s.assertTrue(any(
        f["code"] == "ASSET_FIELD_MISSING"
        for f in m.validate_manifest(manifest([asset(width=0)]))))),
    ("height_negative_rejected", lambda s: s.assertTrue(any(
        f["code"] == "ASSET_FIELD_MISSING"
        for f in m.validate_manifest(manifest([asset(height=-5)]))))),
    ("type_uppercase_invalid", lambda s: s.assertTrue(any(
        f["code"] == "ASSET_TYPE_INVALID"
        for f in m.validate_manifest(manifest([asset(type="IMAGE")]))))),
    ("license_numeric_rejected", lambda s: s.assertTrue(any(
        f["code"] == "ASSET_LICENSE_MISSING"
        for f in m.validate_manifest(manifest([asset(license=123)]))))),
    ("path_empty_string", lambda s: s.assertTrue(any(
        f["code"] == "ASSET_PATH_INVALID"
        for f in m.validate_manifest(manifest([asset(path="")]))))),
    ("backslash_traversal", lambda s: s.assertTrue(any(
        f["code"] == "ASSET_PATH_TRAVERSAL"
        for f in m.validate_manifest(manifest([asset(path="..\\..\\x.png")]))))),
    ("extra_fields_allowed", lambda s: s.assertEqual(
        m.validate_manifest(manifest([asset(tags=["hero"], note="ok")])), [])),
    ("schema_version_numeric_ok", lambda s: s.assertEqual(
        [f for f in m.validate_manifest(manifest(schema_version=1))
         if f["code"] == "MISSING_SCHEMA_VERSION"], [])),
    ("null_asset_element", lambda s: s.assertTrue(any(
        f["code"] == "ASSET_NOT_OBJECT"
        for f in m.validate_manifest(manifest([None]))))),
    ("triple_dup_id_two_findings", lambda s: s.assertEqual(
        len([f for f in m.validate_manifest(manifest([
            asset(), asset(id="img-001", path="p1"), asset(id="img-001", path="p2")]))
            if f["code"] == "ASSET_ID_DUP"]), 2)),
    ("audio_bool_duration_rejected", lambda s: s.assertTrue(any(
        f["code"] == "ASSET_FIELD_MISSING" for f in m.validate_manifest(
            manifest([asset(type="audio", width=None, height=None, format=None,
                            duration_seconds=True)]))))),
    ("duration_string_rejected", lambda s: s.assertTrue(any(
        f["code"] == "ASSET_FIELD_MISSING" for f in m.validate_manifest(
            manifest([asset(type="audio", width=None, height=None, format=None,
                            duration_seconds="120")]))))),
    ("huge_path_completes", lambda s: s.assertIsInstance(
        m.validate_manifest(manifest([asset(path="x/" * 2000 + "end.png")])), list)),
    ("cli_json_roundtrip", lambda s: s.assertEqual(
        json.loads(run_cli([MANIFEST_OK, "--json"])[1])["summary"]["error"], 0)),
]


class TestC(unittest.TestCase):
    pass


for _i, (_nm, _fn) in enumerate(C_CASES):
    setattr(TestC, "test_c%02d_%s" % (_i, _nm), _fn)


# ---- Round-2 additions (v0.1.1): extra extreme-edge coverage ----
class TestR2(unittest.TestCase):
    def test_r2_empty_file_hash_ok(self):
        p = os.path.join(FILES, "images", "empty.png")
        with open(p, "wb") as f:
            f.write(b"")
        sha = hashlib.sha256(b"").hexdigest()
        fs = m.validate_manifest(manifest([asset(id="e", path="images/empty.png", sha256=sha)]), root=FILES)
        self.assertEqual(fs, [])

    def test_r2_five_mb_hash_completes(self):
        blob = b"x" * (5 * 1024 * 1024)
        p = os.path.join(FILES, "images", "big.png")
        with open(p, "wb") as f:
            f.write(blob)
        fs = m.validate_manifest(manifest([asset(id="big", path="images/big.png",
                                                 sha256=hashlib.sha256(blob).hexdigest())]), root=FILES)
        self.assertEqual(fs, [])

    def test_r2_parent_ref_still_traversal(self):
        fs = m.validate_manifest(manifest([asset(path="images/../images/a.png")]), root=FILES)
        self.assertTrue(any(f["code"] == "ASSET_PATH_TRAVERSAL" for f in fs))

    def test_r2_type_other_clean(self):
        fs = m.validate_manifest(manifest([asset(type="other", width=None, height=None, format=None)]))
        self.assertEqual([f for f in fs if f["severity"] == "ERROR"], [])

if __name__ == "__main__":
    r = unittest.TextTestRunner(verbosity=0).run(
        unittest.defaultTestLoader.loadTestsFromModule(sys.modules["__main__"]))
    total, fails = r.testsRun, len(r.failures) + len(r.errors)
    print("SUMMARY: PASS %d/%d" % (total - fails, total))  # Defence 4
    sys.exit(0 if fails == 0 else 1)
