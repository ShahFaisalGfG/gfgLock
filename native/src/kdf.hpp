#pragma once
#include <cstdint>
#include <string>
#include <vector>

namespace gfglock {

/// Derive a 256-bit key from a password using PBKDF2-HMAC-SHA256 (OpenSSL EVP).
std::vector<uint8_t> pbkdf2Sha256(
    const std::string& password,
    const std::vector<uint8_t>& salt,
    int iterations,
    int dklen
);

} // namespace gfglock
