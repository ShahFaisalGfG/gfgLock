// aes_cpu.cpp - AES-256-GCM / AES-256-CFB / ChaCha20-Poly1305 file transforms via OpenSSL EVP.
//
// These functions only turn one file into another. The Python caller (gfglock/core/file_ops.py)
// picks a fresh output path, validates the decrypted file name, moves the finished file into
// place, and deletes the source. Keeping naming and deletion in that one shared layer means the
// native and Python fallback paths can never disagree about which file is safe to remove.
//
// File layout (identical to the Python fallback):
//   salt(16) | nonce(12) or iv(16) | chunk_size u32 BE | E(original_name + NUL + data) | tag(16, AEAD only)

#include "aes_cpu.hpp"
#include "kdf.hpp"

#include <openssl/crypto.h>
#include <openssl/evp.h>
#include <openssl/rand.h>

#include <algorithm>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <vector>

namespace fs = std::filesystem;
namespace gfglock {

namespace {
constexpr size_t SALT_SIZE         = 16;
constexpr size_t NONCE_SIZE        = 12;
constexpr size_t IV_SIZE           = 16;
constexpr size_t TAG_SIZE          = 16;
constexpr size_t CHUNK_FIELD_SIZE  = 4;
constexpr size_t BUFFER_SIZE       = 512  * 1024;
// A user-chosen chunk size only sets the I/O buffer; capping it keeps a huge setting from
// allocating gigabytes per worker thread.
constexpr size_t MAX_IO_BUFFER     = 64   * 1024 * 1024;
constexpr size_t SMALL_THRESHOLD   = 10   * 1024 * 1024;
constexpr size_t PROGRESS_INTERVAL = 100  * 1024 * 1024;
constexpr size_t MAX_NAME_BYTES    = 4096;
constexpr int    KDF_ITERATIONS    = 200000;
constexpr int    KEY_SIZE          = 32;

struct CipherSpec {
    const EVP_CIPHER* (*cipher)();
    size_t iv_size;
    bool aead;
};

CipherSpec specFor(Algorithm algorithm) {
    switch (algorithm) {
    case Algorithm::Gcm:    return {EVP_aes_256_gcm, NONCE_SIZE, true};
    case Algorithm::Cfb:    return {EVP_aes_256_cfb128, IV_SIZE, false};
    case Algorithm::Chacha: return {EVP_chacha20_poly1305, NONCE_SIZE, true};
    }
    throw std::invalid_argument("unknown algorithm");
}

// Python hands paths over as UTF-8; MSVC would read a plain std::string as the ANSI code
// page, which breaks any non-ASCII file name.
fs::path utf8Path(const std::string& s) {
    return fs::path(std::u8string(reinterpret_cast<const char8_t*>(s.data()), s.size()));
}

std::vector<uint8_t> randBytes(size_t n) {
    std::vector<uint8_t> buf(n);
    if (RAND_bytes(buf.data(), static_cast<int>(n)) != 1)
        throw std::runtime_error("random number generator failed");
    return buf;
}

void packBE32(uint32_t v, uint8_t* out) {
    out[0] = (v >> 24) & 0xFF; out[1] = (v >> 16) & 0xFF;
    out[2] = (v >>  8) & 0xFF; out[3] = (v      ) & 0xFF;
}

// Key bytes are wiped from memory as soon as the key goes out of scope.
struct SecureKey {
    std::vector<uint8_t> bytes;
    ~SecureKey() { if (!bytes.empty()) OPENSSL_cleanse(bytes.data(), bytes.size()); }
};

struct EvpCtx {
    EVP_CIPHER_CTX* p = EVP_CIPHER_CTX_new();
    EvpCtx() { if (!p) throw std::runtime_error("EVP_CIPHER_CTX_new failed"); }
    EvpCtx(const EvpCtx&) = delete;
    EvpCtx& operator=(const EvpCtx&) = delete;
    ~EvpCtx() { EVP_CIPHER_CTX_free(p); }
    EVP_CIPHER_CTX* get() const { return p; }
};

void initCipher(EVP_CIPHER_CTX* ctx, const CipherSpec& spec, const uint8_t* key, const uint8_t* iv, bool encrypt) {
    auto init = encrypt ? EVP_EncryptInit_ex : EVP_DecryptInit_ex;
    if (init(ctx, spec.cipher(), nullptr, nullptr, nullptr) != 1
        || (spec.aead && EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_AEAD_SET_IVLEN,
                                             static_cast<int>(spec.iv_size), nullptr) != 1)
        || init(ctx, nullptr, nullptr, key, iv) != 1)
        throw std::runtime_error("cipher initialisation failed");
}

void writeAll(std::ofstream& out, const void* data, size_t n) {
    if (n == 0) return;
    out.write(static_cast<const char*>(data), static_cast<std::streamsize>(n));
    if (!out) throw std::runtime_error("could not write the output file (disk full or no access?)");
}

size_t readSome(std::ifstream& in, std::vector<uint8_t>& buf, size_t max_bytes) {
    in.read(reinterpret_cast<char*>(buf.data()),
            static_cast<std::streamsize>(std::min(max_bytes, buf.size())));
    if (in.bad()) throw std::runtime_error("could not read the source file");
    return static_cast<size_t>(in.gcount());
}

void readExact(std::ifstream& in, uint8_t* dst, size_t n) {
    in.read(reinterpret_cast<char*>(dst), static_cast<std::streamsize>(n));
    if (static_cast<size_t>(in.gcount()) != n)
        throw std::runtime_error("the file is truncated or corrupted");
}

void fireProgress(const ProgressFn& cb, size_t& batch, size_t n) {
    batch += n;
    if (cb && batch >= PROGRESS_INTERVAL) { cb(static_cast<double>(batch)); batch = 0; }
}

void closeOrThrow(std::ofstream& out) {
    out.close();
    if (out.fail()) throw std::runtime_error("could not finish writing the output file");
}

} // anonymous namespace

std::pair<bool, std::string> encryptFile(
    Algorithm algorithm,
    const std::string& input_path,
    const std::string& output_path,
    const std::string& original_name,
    const std::string& password,
    int chunk_size,
    const ProgressFn& progress)
{
    try {
        const CipherSpec spec = specFor(algorithm);
        const fs::path in_path = utf8Path(input_path);
        std::ifstream fin(in_path, std::ios::binary);
        if (!fin) throw std::runtime_error("cannot open the source file");
        const uintmax_t file_size = fs::file_size(in_path);
        if (file_size < SMALL_THRESHOLD || chunk_size < 0) chunk_size = 0;

        std::ofstream fout(utf8Path(output_path), std::ios::binary | std::ios::trunc);
        if (!fout) throw std::runtime_error("cannot create the output file");

        const auto salt = randBytes(SALT_SIZE);
        const auto iv   = randBytes(spec.iv_size);
        SecureKey key{pbkdf2Sha256(password, salt, KDF_ITERATIONS, KEY_SIZE)};
        EvpCtx ctx;
        initCipher(ctx.get(), spec, key.bytes.data(), iv.data(), true);

        uint8_t cs_field[CHUNK_FIELD_SIZE];
        packBE32(static_cast<uint32_t>(chunk_size), cs_field);
        writeAll(fout, salt.data(), salt.size());
        writeAll(fout, iv.data(), iv.size());
        writeAll(fout, cs_field, CHUNK_FIELD_SIZE);

        std::vector<uint8_t> name_meta(original_name.begin(), original_name.end());
        name_meta.push_back(0);
        std::vector<uint8_t> enc_meta(name_meta.size() + EVP_MAX_BLOCK_LENGTH);
        int out_len = 0;
        if (EVP_EncryptUpdate(ctx.get(), enc_meta.data(), &out_len,
                              name_meta.data(), static_cast<int>(name_meta.size())) != 1)
            throw std::runtime_error("encryption failed");
        writeAll(fout, enc_meta.data(), static_cast<size_t>(out_len));
        if (progress) progress(static_cast<double>(name_meta.size()));

        const size_t io_size = chunk_size > 0
            ? std::clamp(static_cast<size_t>(chunk_size), BUFFER_SIZE, MAX_IO_BUFFER) : BUFFER_SIZE;
        std::vector<uint8_t> read_buf(io_size);
        std::vector<uint8_t> write_buf(io_size + EVP_MAX_BLOCK_LENGTH);
        size_t progress_batch = 0;
        uintmax_t total_read = 0;

        while (true) {
            const size_t n = readSome(fin, read_buf, io_size);
            if (n == 0) break;
            total_read += n;
            if (EVP_EncryptUpdate(ctx.get(), write_buf.data(), &out_len,
                                  read_buf.data(), static_cast<int>(n)) != 1)
                throw std::runtime_error("encryption failed");
            writeAll(fout, write_buf.data(), static_cast<size_t>(out_len));
            fireProgress(progress, progress_batch, n);
        }
        if (progress && progress_batch > 0) progress(static_cast<double>(progress_batch));
        if (total_read != file_size)
            throw std::runtime_error("the source file changed size while it was being read");

        if (EVP_EncryptFinal_ex(ctx.get(), write_buf.data(), &out_len) != 1)
            throw std::runtime_error("encryption failed");
        writeAll(fout, write_buf.data(), static_cast<size_t>(out_len));

        if (spec.aead) {
            uint8_t tag[TAG_SIZE];
            if (EVP_CIPHER_CTX_ctrl(ctx.get(), EVP_CTRL_AEAD_GET_TAG, static_cast<int>(TAG_SIZE), tag) != 1)
                throw std::runtime_error("could not compute the authentication tag");
            writeAll(fout, tag, TAG_SIZE);
        }
        closeOrThrow(fout);
        return {true, ""};
    } catch (const std::exception& e) {
        return {false, e.what()};
    }
}

DecryptResult decryptFile(
    Algorithm algorithm,
    const std::string& input_path,
    const std::string& output_path,
    const std::string& password,
    const ProgressFn& progress)
{
    try {
        const CipherSpec spec = specFor(algorithm);
        const fs::path in_path = utf8Path(input_path);
        std::ifstream fin(in_path, std::ios::binary);
        if (!fin) throw std::runtime_error("cannot open the encrypted file");

        const uintmax_t total_size = fs::file_size(in_path);
        const size_t header_size = SALT_SIZE + spec.iv_size + CHUNK_FIELD_SIZE;
        const size_t tag_size = spec.aead ? TAG_SIZE : 0;
        if (total_size < header_size + tag_size + 1)
            throw std::runtime_error("the file is too small to be a valid encrypted file");

        std::vector<uint8_t> salt(SALT_SIZE), iv(spec.iv_size), chunk_field(CHUNK_FIELD_SIZE);
        readExact(fin, salt.data(), salt.size());
        readExact(fin, iv.data(), iv.size());
        readExact(fin, chunk_field.data(), chunk_field.size());  // informational only

        SecureKey key{pbkdf2Sha256(password, salt, KDF_ITERATIONS, KEY_SIZE)};
        EvpCtx ctx;
        initCipher(ctx.get(), spec, key.bytes.data(), iv.data(), false);

        std::ofstream fout(utf8Path(output_path), std::ios::binary | std::ios::trunc);
        if (!fout) throw std::runtime_error("cannot create the output file");

        DecryptResult result;
        bool got_name = false;
        // The stream starts with the original file name and a NUL; everything after it is data.
        auto consume = [&](const uint8_t* data, size_t n) {
            if (got_name) { writeAll(fout, data, n); return; }
            const uint8_t* nul = std::find(data, data + n, static_cast<uint8_t>(0));
            result.original_name.append(reinterpret_cast<const char*>(data), static_cast<size_t>(nul - data));
            if (result.original_name.size() > MAX_NAME_BYTES)
                throw std::runtime_error("wrong password or the file is corrupted");
            if (nul != data + n) {
                got_name = true;
                writeAll(fout, nul + 1, static_cast<size_t>((data + n) - (nul + 1)));
            }
        };

        std::vector<uint8_t> read_buf(BUFFER_SIZE);
        std::vector<uint8_t> dec_buf(BUFFER_SIZE + EVP_MAX_BLOCK_LENGTH);
        uintmax_t remaining = total_size - header_size - tag_size;
        size_t progress_batch = 0;
        int out_len = 0;

        while (remaining > 0) {
            const size_t want = static_cast<size_t>(std::min<uintmax_t>(remaining, BUFFER_SIZE));
            const size_t n = readSome(fin, read_buf, want);
            if (n == 0) throw std::runtime_error("the file is truncated or corrupted");
            remaining -= n;
            if (EVP_DecryptUpdate(ctx.get(), dec_buf.data(), &out_len,
                                  read_buf.data(), static_cast<int>(n)) != 1)
                throw std::runtime_error("decryption failed");
            consume(dec_buf.data(), static_cast<size_t>(out_len));
            fireProgress(progress, progress_batch, n);
        }
        if (progress && progress_batch > 0) progress(static_cast<double>(progress_batch));

        if (spec.aead) {
            uint8_t tag[TAG_SIZE];
            readExact(fin, tag, TAG_SIZE);
            if (EVP_CIPHER_CTX_ctrl(ctx.get(), EVP_CTRL_AEAD_SET_TAG, static_cast<int>(TAG_SIZE), tag) != 1)
                throw std::runtime_error("decryption failed");
            if (EVP_DecryptFinal_ex(ctx.get(), dec_buf.data(), &out_len) <= 0)
                return {false, "wrong password or the file was modified (authentication failed)", ""};
        } else if (EVP_DecryptFinal_ex(ctx.get(), dec_buf.data(), &out_len) != 1) {
            throw std::runtime_error("decryption failed");
        }
        consume(dec_buf.data(), static_cast<size_t>(out_len));
        if (!got_name) throw std::runtime_error("wrong password or the file is corrupted");
        closeOrThrow(fout);
        result.ok = true;
        return result;
    } catch (const std::exception& e) {
        return {false, e.what(), ""};
    }
}

} // namespace gfglock
