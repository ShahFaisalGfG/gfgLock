// kdf.cpp — PBKDF2-HMAC-SHA256 key derivation via OpenSSL EVP

#include "kdf.hpp"
#include <openssl/evp.h>
#include <stdexcept>

namespace gfglock {

std::vector<uint8_t> pbkdf2Sha256(
    const std::string& password,
    const std::vector<uint8_t>& salt,
    int iterations,
    int dklen)
{
    std::vector<uint8_t> key(static_cast<size_t>(dklen));
    int rc = PKCS5_PBKDF2_HMAC(
        password.c_str(), static_cast<int>(password.size()),
        salt.data(),      static_cast<int>(salt.size()),
        iterations,
        EVP_sha256(),
        dklen, key.data());
    if (rc != 1)
        throw std::runtime_error("PBKDF2-HMAC-SHA256 failed");
    return key;
}

} // namespace gfglock
