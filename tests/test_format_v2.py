"""Tests for gfglock.core.format_v2: the v2 header, metadata, sizes, and the run key ring."""

import dataclasses
import struct
import threading

import pytest

from gfglock.core import format_v2
from gfglock.core.format_v2 import FormatError, Header, KdfParams, KeyRing

FAST_KDF = KdfParams(memory_kib=64, iterations=1, lanes=1)
_BASE = Header(algorithm="gcm", kdf=FAST_KDF, kdf_salt=b"k" * 16, file_salt=b"f" * 16, nonce_prefix=b"n" * 7)


def _header(**changes) -> Header:
    return dataclasses.replace(_BASE, **changes)


def _patched(raw: bytes, offset: int, value: bytes) -> bytes:
    return raw[:offset] + value + raw[offset + len(value):]


class TestHeader:
    def test_pack_parse_roundtrip(self):
        header = _header(algorithm="chacha", chunk_log2=18)
        raw = header.pack()
        assert len(raw) == format_v2.HEADER_SIZE == 60
        assert format_v2.parse_header(raw) == header

    def test_layout_starts_with_magic_and_version(self):
        raw = _header().pack()
        assert raw[:8] == b"GFGLOCK\x02"
        assert format_v2.has_magic(raw)

    def test_magic_alone_marks_v2_and_later(self):
        assert format_v2.has_magic(b"GFGLOCK\x03" + b"\x00" * 52)
        assert not format_v2.has_magic(b"\x00" * 60)
        assert not format_v2.has_magic(b"GFGLOC")

    @pytest.mark.parametrize("raw", [b"GFGLOCK\x03", b"GFGLOCK\x09" + b"\x00" * 100])
    def test_a_later_version_says_so(self, raw):
        with pytest.raises(FormatError, match="newer gfgLock version"):
            format_v2.parse_header(raw)

    @pytest.mark.parametrize("offset, value, message", [
        (7, b"\x01", "not a gfgLock v2 file"),
        (8, b"\x09", "encryption method"),
        (9, b"\x02", "newer gfgLock"),
        (20, b"\x01", "newer gfgLock"),
        (19, b"\x0f", "chunk size"),
        (19, b"\x19", "chunk size"),
        (18, b"\x00", "lanes"),
        (18, b"\x11", "lanes"),
    ])
    def test_rejects_fields_out_of_range(self, offset, value, message):
        raw = _patched(_header().pack(), offset, value)
        with pytest.raises(FormatError, match=message):
            format_v2.parse_header(raw)

    def test_rejects_kdf_costs_out_of_range(self):
        raw = _header().pack()
        with pytest.raises(FormatError, match="iterations"):
            format_v2.parse_header(_patched(raw, 14, struct.pack(">I", 11)))
        with pytest.raises(FormatError, match="memory"):
            format_v2.parse_header(_patched(raw, 10, struct.pack(">I", 1024 * 1024 + 1)))
        with pytest.raises(FormatError, match="memory"):
            format_v2.parse_header(_patched(raw, 10, struct.pack(">I", 7)))

    def test_rejects_short_input(self):
        with pytest.raises(FormatError, match="too small"):
            format_v2.parse_header(_header().pack()[:-1])


class TestChunks:
    def test_nonce_layout(self):
        nonce = format_v2.chunk_nonce(b"p" * 7, 258, last=True)
        assert nonce == b"p" * 7 + b"\x00\x00\x01\x02\x01"
        assert format_v2.chunk_nonce(b"p" * 7, 0, last=False)[-1] == 0

    @pytest.mark.parametrize("plaintext, chunks", [(10, 1), (1 << 20, 1), ((1 << 20) + 1, 2), (3 << 20, 3)])
    def test_chunk_count(self, plaintext, chunks):
        assert format_v2.chunk_count(plaintext) == chunks

    def test_encrypted_size(self):
        name = "résumé.pdf"
        plaintext = 2 + len(name.encode("utf-8")) + 8 + 5_000_000
        assert format_v2.encrypted_size(5_000_000, name) == 60 + plaintext + 5 * 16
        assert format_v2.encrypted_size(0, "a") == 60 + 11 + 16

    def test_encrypted_size_refuses_counter_overflow(self):
        with pytest.raises(FormatError, match="too large"):
            format_v2.encrypted_size(2**32 << 16, "a", chunk_log2=16)


class TestMetadata:
    def test_roundtrip(self):
        block = format_v2.pack_metadata("notes ü.txt", 1_700_000_000_123_456_789)
        assert format_v2.metadata_size(block + b"data") == len(block)
        assert format_v2.unpack_metadata(block) == ("notes ü.txt".encode("utf-8"), 1_700_000_000_123_456_789)

    def test_negative_mtime(self):
        block = format_v2.pack_metadata("old.txt", -5)
        assert format_v2.unpack_metadata(block)[1] == -5

    @pytest.mark.parametrize("mtime_ns, stored", [(-11644473599999999900, -(2**63)), (2**64, 2**63 - 1)])
    def test_times_outside_64_bits_are_clamped(self, mtime_ns, stored):
        """NTFS can hold times from 1601 that don't fit in nanoseconds since 1970 as an i64."""
        assert format_v2.unpack_metadata(format_v2.pack_metadata("a.txt", mtime_ns))[1] == stored

    @pytest.mark.parametrize("name", ["", "a" * 1025])
    def test_name_limits(self, name):
        with pytest.raises(FormatError):
            format_v2.pack_metadata(name, 0)

    @pytest.mark.parametrize("block", [b"", b"\x00", b"\x00\x00" + b"\x00" * 8, b"\x00\x05abc", b"\x04\x01" + b"a" * 2000])
    def test_rejects_malformed_blocks(self, block):
        with pytest.raises(FormatError):
            format_v2.metadata_size(block)


class TestKeyRing:
    def test_one_run_shares_the_kdf_salt_but_not_file_salts(self):
        ring = KeyRing("pw", FAST_KDF)
        (first, key1), (second, key2) = ring.new_header("gcm"), ring.new_header("gcm")
        assert first.kdf_salt == second.kdf_salt
        assert first.file_salt != second.file_salt and first.nonce_prefix != second.nonce_prefix
        assert key1 != key2 and len(key1) == 32

    def test_another_ring_opens_the_file(self):
        header, key = KeyRing("pw", FAST_KDF).new_header("chacha")
        reader = KeyRing("pw")
        assert reader.file_key(format_v2.parse_header(header.pack())) == key
        assert KeyRing("other", FAST_KDF).file_key(header) != key

    def test_algorithms_get_separate_keys(self):
        ring = KeyRing("pw", FAST_KDF)
        header, _ = ring.new_header("gcm")
        assert ring.file_key(header) != ring.file_key(_header(algorithm="chacha", kdf_salt=header.kdf_salt,
                                                               file_salt=header.file_salt))

    def test_password_is_nfc_normalized(self):
        header, key = KeyRing("café", FAST_KDF).new_header("gcm")
        assert KeyRing("café").file_key(header) == key

    def test_unusable_password(self):
        with pytest.raises(ValueError, match="can't be used"):
            KeyRing("bad\ud800")

    def test_unknown_algorithm(self):
        with pytest.raises(ValueError):
            KeyRing("pw", FAST_KDF).new_header("cfb")

    def test_costs_a_reader_would_refuse_are_refused(self):
        with pytest.raises(FormatError, match="iterations"):
            KeyRing("pw", KdfParams(memory_kib=64, iterations=11, lanes=1))

    def test_master_key_is_derived_once_across_threads(self, monkeypatch):
        calls = []
        argon2id = format_v2.Argon2id

        def counting(**kwargs):
            calls.append(1)
            return argon2id(**kwargs)

        monkeypatch.setattr(format_v2, "Argon2id", counting)
        ring = KeyRing("pw", FAST_KDF)
        header, key = ring.new_header("gcm")
        reader = KeyRing("pw")
        keys = []
        threads = [threading.Thread(target=lambda: keys.append(reader.file_key(header))) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert keys == [key] * 8
        assert len(calls) == 2  # one for the writer's run, one for the reader


class TestMemoryBudget:
    """Argon2id derivations of different runs share one memory budget."""

    def test_a_derivation_waits_while_the_budget_is_full(self):
        budget = format_v2._MemoryBudget(100)
        entered = threading.Event()

        def second():
            with budget.hold(64):
                entered.set()

        with budget.hold(64):
            thread = threading.Thread(target=second)
            thread.start()
            assert not entered.wait(0.2)  # 64 + 64 KiB doesn't fit in 100
        assert entered.wait(5)
        thread.join(5)

    def test_derivations_that_fit_run_together(self):
        budget = format_v2._MemoryBudget(128)
        entered = threading.Event()

        def second():
            with budget.hold(64):
                entered.set()

        with budget.hold(64):
            thread = threading.Thread(target=second)
            thread.start()
            assert entered.wait(5)  # entered while the first still holds its share
        thread.join(5)

    def test_one_larger_than_the_budget_runs_alone(self):
        budget = format_v2._MemoryBudget(100)
        with budget.hold(500):
            pass  # an idle budget never blocks, whatever the size
