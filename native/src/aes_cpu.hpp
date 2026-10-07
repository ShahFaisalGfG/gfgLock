#pragma once
#include <functional>
#include <string>
#include <utility>

namespace gfglock {

using ProgressFn = std::function<void(double)>;

/// Cipher behind each encrypted file type: .gfglock (GCM), .gfglck (CFB), .gfgcha (ChaCha).
enum class Algorithm { Gcm, Cfb, Chacha };

/// Outcome of decryptFile(): on success `original_name` holds the raw UTF-8 bytes of the
/// name stored inside the file. It is untrusted input and must be validated by the caller.
struct DecryptResult {
    bool ok = false;
    std::string message;
    std::string original_name;
};

/// Encrypt input_path into output_path (both UTF-8). Writes the header, the encrypted
/// `original_name` + NUL + file data, and the tag for AEAD ciphers. `block_size` is the read
/// size in bytes, 0 for the default. Never deletes or renames anything: choosing the output name
/// and removing the source is the caller's job.
std::pair<bool, std::string> encryptFile(
    Algorithm algorithm,
    const std::string& input_path,
    const std::string& output_path,
    const std::string& original_name,
    const std::string& password,
    size_t block_size,
    const ProgressFn& progress
);

/// Decrypt input_path into output_path (plaintext data only). For AEAD ciphers the result is
/// only reported as successful after the tag verifies; on any failure the caller must discard
/// output_path. `block_size` is the read size in bytes, 0 for the default. Never deletes or
/// renames anything.
DecryptResult decryptFile(
    Algorithm algorithm,
    const std::string& input_path,
    const std::string& output_path,
    const std::string& password,
    size_t block_size,
    const ProgressFn& progress
);

} // namespace gfglock
