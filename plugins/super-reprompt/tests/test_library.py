# -*- coding: utf-8 -*-
"""validate_library.py: the documentation library's manifest must be true, legal and free of personal paths."""
import hashlib
import os
import unittest

from _t import TmpCase

HEADER = "file,url,date,sha256,licence,vault_note"


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Library(TmpCase):
    def setUp(self):
        TmpCase.setUp(self)
        self.lib = os.path.join(self.tmp, "library")
        self.dom = os.path.join(self.lib, "finance")
        os.makedirs(self.dom)

    def write_file(self, name, data=b"hello world\n"):
        p = os.path.join(self.dom, name)
        with open(p, "wb") as f:
            f.write(data)
        return sha(data)

    def write_manifest(self, rows, header=HEADER, domain=None):
        p = os.path.join(domain or self.dom, "manifest.csv")
        with open(p, "w", encoding="utf-8") as f:
            f.write(header + "\n")
            for r in rows:
                f.write(r + "\n")
        return p

    def run_lib(self, args=None):
        return self.run_script("validate_library.py", list(args) if args else [self.lib])

    def row(self, name="paper.pdf", digest=None, url="https://example.org/paper.pdf", date="2026-01-15",
            licence="open-access", note="fiche-allocation-actifs"):
        return ",".join([name, url, date, digest or "0" * 64, licence, note])

    # ---------------------------------------------------------------- happy path
    def test_valid_manifest_passes(self):
        d = self.write_file("paper.pdf")
        self.write_manifest([self.row(digest=d)])
        code, out, err = self.run_lib()
        self.assertEqual(code, 0, out + err)
        self.assertIn("1 entr", out.lower() + " 1 entries")

    def test_link_only_row_has_no_file(self):
        self.write_manifest([",".join(["", "https://example.org/book", "2026-02-01", "", "link-only", "fiche-x"])])
        code, out, err = self.run_lib()
        self.assertEqual(code, 0, out + err)

    def test_missing_manifest_is_an_error_not_a_silent_pass(self):
        self.write_file("paper.pdf")
        code, out, err = self.run_lib()
        self.assertEqual(code, 2)
        self.assertIn("manifest.csv", out + err)

    def test_empty_library_passes(self):
        os.rmdir(self.dom)
        code, out, err = self.run_lib()
        self.assertEqual(code, 0, out + err)

    # ---------------------------------------------------------------- truthfulness
    def test_wrong_sha256_fails(self):
        self.write_file("paper.pdf")
        self.write_manifest([self.row(digest="a" * 64)])
        code, out, err = self.run_lib()
        self.assertEqual(code, 2)
        self.assertIn("sha256", (out + err).lower())

    def test_declared_file_that_does_not_exist_fails(self):
        self.write_manifest([self.row(digest="a" * 64)])
        code, out, err = self.run_lib()
        self.assertEqual(code, 2)
        self.assertIn("paper.pdf", out + err)

    def test_file_present_but_absent_from_the_manifest_fails(self):
        d = self.write_file("paper.pdf")
        self.write_file("orphan.pdf", b"other\n")
        self.write_manifest([self.row(digest=d)])
        code, out, err = self.run_lib()
        self.assertEqual(code, 2)
        self.assertIn("orphan.pdf", out + err)

    def test_sha256_must_be_64_hex(self):
        d = self.write_file("paper.pdf")
        self.write_manifest([self.row(digest=d[:40])])
        code, out, err = self.run_lib()
        self.assertEqual(code, 2)

    # ---------------------------------------------------------------- legality and provenance
    def test_unknown_licence_fails(self):
        d = self.write_file("paper.pdf")
        self.write_manifest([self.row(digest=d, licence="probablement-ok")])
        code, out, err = self.run_lib()
        self.assertEqual(code, 2)
        self.assertIn("licence", (out + err).lower())

    def test_link_only_licence_with_a_copied_file_fails(self):
        d = self.write_file("paper.pdf")
        self.write_manifest([self.row(digest=d, licence="link-only")])
        code, out, err = self.run_lib()
        self.assertEqual(code, 2)

    def test_non_http_url_fails(self):
        d = self.write_file("paper.pdf")
        self.write_manifest([self.row(digest=d, url="file:///etc/passwd")])
        code, out, err = self.run_lib()
        self.assertEqual(code, 2)
        self.assertIn("url", (out + err).lower())

    def test_missing_vault_note_fails(self):
        d = self.write_file("paper.pdf")
        self.write_manifest([self.row(digest=d, note="")])
        code, out, err = self.run_lib()
        self.assertEqual(code, 2)

    def test_bad_date_fails(self):
        d = self.write_file("paper.pdf")
        self.write_manifest([self.row(digest=d, date="15/01/2026")])
        code, out, err = self.run_lib()
        self.assertEqual(code, 2)
        self.assertIn("date", (out + err).lower())

    def test_future_date_fails(self):
        d = self.write_file("paper.pdf")
        self.write_manifest([self.row(digest=d, date="2099-01-01")])
        code, out, err = self.run_lib()
        self.assertEqual(code, 2)

    def test_a_month_only_date_is_accepted(self):
        # a report or a paper is often dated by month; a true month beats an invented day
        d = self.write_file("paper.pdf")
        self.write_manifest([self.row(digest=d, date="2024-12")])
        code, out, err = self.run_lib()
        self.assertEqual(code, 0, out + err)

    def test_a_future_month_still_fails(self):
        d = self.write_file("paper.pdf")
        self.write_manifest([self.row(digest=d, date="2099-01")])
        code, out, err = self.run_lib()
        self.assertEqual(code, 2)

    def test_a_year_alone_is_not_a_date(self):
        d = self.write_file("paper.pdf")
        self.write_manifest([self.row(digest=d, date="2024")])
        code, out, err = self.run_lib()
        self.assertEqual(code, 2)

    # ---------------------------------------------------------------- the link back to the notes
    def test_vault_note_must_exist_when_notes_are_given(self):
        notes = os.path.join(self.tmp, "notes")
        os.makedirs(notes)
        d = self.write_file("paper.pdf")
        self.write_manifest([self.row(digest=d, note="fiche-qui-nexiste-pas")])
        code, out, err = self.run_lib([self.lib, "--notes", notes])
        self.assertEqual(code, 2)
        self.assertIn("fiche-qui-nexiste-pas", out + err)

    def test_vault_note_found_under_a_subfolder_passes(self):
        notes = os.path.join(self.tmp, "notes", "finance", "analyses")
        os.makedirs(notes)
        with open(os.path.join(notes, "fiche-allocation-actifs.md"), "w", encoding="utf-8") as f:
            f.write("# note\n")
        d = self.write_file("paper.pdf")
        self.write_manifest([self.row(digest=d)])
        code, out, err = self.run_lib([self.lib, "--notes", os.path.join(self.tmp, "notes")])
        self.assertEqual(code, 0, out + err)

    def test_notes_folder_that_does_not_exist_is_an_error(self):
        d = self.write_file("paper.pdf")
        self.write_manifest([self.row(digest=d)])
        code, out, err = self.run_lib([self.lib, "--notes", os.path.join(self.tmp, "nope")])
        self.assertEqual(code, 2)

    # ---------------------------------------------------------------- no personal paths, no secrets
    def test_absolute_windows_path_fails(self):
        self.write_file("paper.pdf")
        self.write_manifest([self.row(name="C:/Users/someone/paper.pdf")])
        code, out, err = self.run_lib()
        self.assertEqual(code, 2)
        self.assertIn("path", (out + err).lower())

    def test_absolute_posix_path_fails(self):
        self.write_file("paper.pdf")
        self.write_manifest([self.row(name="/home/someone/paper.pdf")])
        code, out, err = self.run_lib()
        self.assertEqual(code, 2)

    def test_home_shortcut_path_fails(self):
        self.write_file("paper.pdf")
        self.write_manifest([self.row(name="~/paper.pdf")])
        code, out, err = self.run_lib()
        self.assertEqual(code, 2)

    def test_parent_traversal_fails(self):
        self.write_file("paper.pdf")
        self.write_manifest([self.row(name="../paper.pdf")])
        code, out, err = self.run_lib()
        self.assertEqual(code, 2)

    def test_user_home_segment_in_the_note_fails(self):
        d = self.write_file("paper.pdf")
        self.write_manifest([self.row(digest=d, note="C:/Users/someone/vault/fiche.md")])
        code, out, err = self.run_lib()
        self.assertEqual(code, 2)

    def test_a_secret_in_the_manifest_fails(self):
        d = self.write_file("paper.pdf")
        self.write_manifest([self.row(digest=d, url="https://example.org/x?key=sk-ant-abcdefghijklmnop")])
        code, out, err = self.run_lib()
        self.assertEqual(code, 2)
        self.assertIn("secret", (out + err).lower())

    # ---------------------------------------------------------------- shape of the manifest
    def test_wrong_header_fails(self):
        d = self.write_file("paper.pdf")
        self.write_manifest([self.row(digest=d)], header="file,url,sha256")
        code, out, err = self.run_lib()
        self.assertEqual(code, 2)
        self.assertIn("header", (out + err).lower())

    def test_row_with_too_many_fields_fails(self):
        d = self.write_file("paper.pdf")
        self.write_manifest([self.row(digest=d) + ",extra"])
        code, out, err = self.run_lib()
        self.assertEqual(code, 2)

    def test_duplicate_file_rows_fail(self):
        d = self.write_file("paper.pdf")
        self.write_manifest([self.row(digest=d), self.row(digest=d)])
        code, out, err = self.run_lib()
        self.assertEqual(code, 2)
        self.assertIn("twice", (out + err).lower())

    # ---------------------------------------------------------------- caps
    def test_file_count_cap_is_enforced(self):
        rows = []
        for i in range(3):
            d = self.write_file("p%d.pdf" % i, b"data %d\n" % i)
            rows.append(self.row(name="p%d.pdf" % i, digest=d))
        self.write_manifest(rows)
        code, out, err = self.run_lib([self.lib, "--max-files", "2"])
        self.assertEqual(code, 2)
        self.assertIn("2", out + err)

    def test_total_size_cap_is_enforced(self):
        d = self.write_file("big.pdf", b"x" * 5000)
        self.write_manifest([self.row(name="big.pdf", digest=d)])
        code, out, err = self.run_lib([self.lib, "--max-bytes", "1000"])
        self.assertEqual(code, 2)

    def test_defaults_are_the_agreed_caps(self):
        d = self.write_file("paper.pdf")
        self.write_manifest([self.row(digest=d)])
        code, out, err = self.run_lib()
        self.assertEqual(code, 0, out + err)
        self.assertIn("40", out)            # 40 files
        self.assertIn("500", out)           # 500 MB

    # ---------------------------------------------------------------- several domains
    def test_every_domain_is_validated(self):
        d = self.write_file("paper.pdf")
        self.write_manifest([self.row(digest=d)])
        other = os.path.join(self.lib, "crypto")
        os.makedirs(other)
        with open(os.path.join(other, "note.txt"), "wb") as f:
            f.write(b"unlisted\n")
        self.write_manifest([], domain=other)
        code, out, err = self.run_lib()
        self.assertEqual(code, 2)
        self.assertIn("note.txt", out + err)

    def test_manifest_itself_is_not_treated_as_an_orphan(self):
        d = self.write_file("paper.pdf")
        self.write_manifest([self.row(digest=d)])
        code, out, err = self.run_lib()
        self.assertEqual(code, 0, out + err)


if __name__ == "__main__":
    unittest.main()
