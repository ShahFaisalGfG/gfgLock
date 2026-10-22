#pragma once
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <span>
#include <string>
#include <utility>

namespace gfglock {

/// Receives the number of input-file bytes read since the previous call.
using ProgressFn = std::function<void(uint64_t)>;

/// Set from any thread to stop a running call; checked at least once per block.
using CancelFlag = std::atomic<bool>;

/// Cipher behind each encrypted file type: .gfglock (GCM), .gfglck (CFB, v1 only), .gfgcha (ChaCha).
enum class Algorithm { Gcm, Cfb, Chacha };

/// Everything a v2 chunk stream needs from its header (see gfglock/core/format_v2.py). The spans
/// are read in place and must stay valid for the whole call.
struct StreamSpec {
    Algorithm algorithm;                     // Gcm or Chacha
    std::span<const uint8_t> header;         // written first and authenticated with every chunk
    std::span<const uint8_t> key;            // the file key, 32 bytes
    std::span<const uint8_t> nonce_prefix;   // 7 bytes; chunk i uses prefix | u32be(i) | u8(last)
    size_t chunk_size;                       // plaintext bytes per chunk, a power of two, 2^16..2^24
};

/// Outcome of a decrypting call. On success `stored` holds the untrusted bytes the file keeps
/// ahead of the data: the v2 metadata block, or the v1 original name. The caller validates them.
struct DecryptResult {
    bool ok = false;
    std::string message;
    std::string stored;
};

/// Seal input_path into output_path (both UTF-8) as a v2 file: `header` verbatim, then
/// `metadata` + the file data in AEAD chunks. The source is opened read-share only and must keep
/// the size it had when opened. `block_size` is the read size in bytes, 0 for the default.
/// Throws std::invalid_argument when `spec` or `metadata` is outside the v2 limits; every other
/// failure, "stopped" included, is returned as (false, message). Never deletes or renames anything.
std::pair<bool, std::string> sealFile(
    const StreamSpec& spec,
    const std::string& input_path,
    const std::string& output_path,
    std::span<const uint8_t> metadata,
    size_t block_size,
    const CancelFlag* cancel,
    const ProgressFn& progress
);

/// Open the v2 file input_path into output_path (data only). Each chunk's plaintext is written
/// only after its tag verifies; the metadata block is returned in `stored`, not written. Throws
/// std::invalid_argument when `spec` is outside the v2 limits. On any failure the caller must
/// discard output_path.
DecryptResult openFile(
    const StreamSpec& spec,
    const std::string& input_path,
    const std::string& output_path,
    size_t block_size,
    const CancelFlag* cancel,
    const ProgressFn& progress
);

/// Decrypt a v1 file (one cipher stream, PBKDF2 key) into output_path (data only); `stored` gets
/// the original name. For AEAD ciphers success is only reported after the tag verifies; on any
/// failure the caller must discard output_path.
DecryptResult decryptFileV1(
    Algorithm algorithm,
    const std::string& input_path,
    const std::string& output_path,
    const std::string& password,
    size_t block_size,
    const CancelFlag* cancel,
    const ProgressFn& progress
);

} // namespace gfglock
