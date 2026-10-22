// kdf.cpp - PBKDF2-HMAC-SHA256 key derivation via OpenSSL EVP

#include "kdf.hpp"
#include <openssl/crypto.h>
#include <openssl/evp.h>
#include <limits>
#include <stdexcept>

namespace gfglock {

namespace {
constexpr int MAX_KEY_SIZE = 1024;
constexpr size_t MAX_INPUT_SIZE = static_cast<size_t>(std::numeric_limits<int>::max());
}

SecureKey::~SecureKey()
{
    if (!bytes.empty()) OPENSSL_cleanse(bytes.data(), bytes.size());
}

SecureKey pbkdf2Sha256(
    const std::string& password,
    const std::vector<uint8_t>& salt,
    int iterations,
    int dklen)
{
    if (iterations < 1 || dklen < 1 || dklen > MAX_KEY_SIZE)
        throw std::invalid_argument("PBKDF2 needs at least one iteration and a key of 1 to 1024 bytes");
    if (password.size() > MAX_INPUT_SIZE || salt.size() > MAX_INPUT_SIZE)
        throw std::invalid_argument("the PBKDF2 password or salt is too long");
    SecureKey key(static_cast<size_t>(dklen));
    int rc = PKCS5_PBKDF2_HMAC(
        password.c_str(), static_cast<int>(password.size()),
        salt.data(),      static_cast<int>(salt.size()),
        iterations,
        EVP_sha256(),
        dklen, key.bytes.data());
    if (rc != 1)
        throw std::runtime_error("PBKDF2-HMAC-SHA256 failed");
    return key;
}

} // namespace gfglock
