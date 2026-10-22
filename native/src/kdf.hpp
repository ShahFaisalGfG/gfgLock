#pragma once
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace gfglock {

/// Key bytes that are wiped from memory when they go out of scope. Move-only, so no copy is
/// left behind unwiped.
struct SecureKey {
    explicit SecureKey(size_t size) : bytes(size) {}
    SecureKey(SecureKey&&) noexcept = default;
    SecureKey(const SecureKey&) = delete;
    SecureKey& operator=(const SecureKey&) = delete;
    SecureKey& operator=(SecureKey&&) = delete;
    ~SecureKey();

    std::vector<uint8_t> bytes;
};

/// Derive a key from a password using PBKDF2-HMAC-SHA256 (OpenSSL EVP). Throws
/// std::invalid_argument for fewer than one iteration or a key length outside 1..1024 bytes.
SecureKey pbkdf2Sha256(
    const std::string& password,
    const std::vector<uint8_t>& salt,
    int iterations,
    int dklen
);

} // namespace gfglock
