// aes_cpu.cpp — AES-256-GCM / AES-256-CFB / ChaCha20-Poly1305 via OpenSSL EVP.
// C++ owns the full file I/O loop; Python overhead = one function call per file.

#include "aes_cpu.hpp"
#include "kdf.hpp"

#include <openssl/evp.h>
#include <openssl/rand.h>

#include <array>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <stdexcept>

namespace fs = std::filesystem;
namespace gfglock {

// ── Constants (match Python exactly) ─────────────────────────────────────────

namespace {
constexpr int    SALT_SIZE          = 16;
constexpr int    NONCE_SIZE         = 12;
constexpr int    IV_SIZE            = 16;
constexpr int    TAG_SIZE           = 16;
constexpr size_t BUFFER_SIZE        = 512  * 1024;
constexpr size_t SMALL_THRESHOLD    = 10   * 1024 * 1024;
constexpr size_t PROGRESS_INTERVAL  = 100  * 1024 * 1024;
constexpr int    KDF_ITERATIONS     = 200000;
constexpr int    KEY_SIZE           = 32;

// ── Internal helpers ──────────────────────────────────────────────────────────

std::vector<uint8_t> randBytes(int n) {
    std::vector<uint8_t> buf(n);
    if (RAND_bytes(buf.data(), n) != 1)
        throw std::runtime_error("RAND_bytes failed");
    return buf;
}

void packBE32(uint32_t v, uint8_t* out) {
    out[0] = (v >> 24) & 0xFF; out[1] = (v >> 16) & 0xFF;
    out[2] = (v >>  8) & 0xFF; out[3] = (v      ) & 0xFF;
}

uint32_t unpackBE32(const uint8_t* in) {
    return (static_cast<uint32_t>(in[0]) << 24)
         | (static_cast<uint32_t>(in[1]) << 16)
         | (static_cast<uint32_t>(in[2]) <<  8)
         |  static_cast<uint32_t>(in[3]);
}

std::string buildName(const std::string& src, bool encrypt_name, const std::string& ext) {
    if (encrypt_name) {
        time_t t = time(nullptr);
        struct tm tm_info{};
        localtime_s(&tm_info, &t);
        char ts[16];
        strftime(ts, sizeof(ts), "%Y%m%d%H%M%S", &tm_info);
        auto r = randBytes(4);
        std::ostringstream oss;
        oss << ts << "_";
        for (uint8_t b : r) oss << std::hex << std::setw(2) << std::setfill('0') << int(b);
        oss << ext;
        return oss.str();
    }
    return fs::path(src).stem().string() + ext;
}

void fireProgress(const ProgressFn& cb, size_t& batch, size_t n) {
    batch += n;
    if (cb && batch >= PROGRESS_INTERVAL) { cb(static_cast<double>(batch)); batch = 0; }
}

// RAII wrapper for EVP_CIPHER_CTX
struct EvpCtx {
    EVP_CIPHER_CTX* p = EVP_CIPHER_CTX_new();
    explicit operator bool() const { return p != nullptr; }
    EVP_CIPHER_CTX* get() const { return p; }
    ~EvpCtx() { if (p) EVP_CIPHER_CTX_free(p); }
};

// Read from stream into a fixed buffer; returns bytes read.
size_t readChunk(std::ifstream& fin, std::vector<uint8_t>& buf, size_t max_bytes) {
    fin.read(reinterpret_cast<char*>(buf.data()), static_cast<std::streamsize>(
        std::min(max_bytes, buf.size())));
    return static_cast<size_t>(fin.gcount());
}

// Write decrypted bytes, extracting filename metadata on first encounter.
bool feedDecrypted(
    const uint8_t* data, size_t n,
    bool& got_meta, std::string& meta_buf,
    std::string& original_name, const std::string& dir,
    std::ofstream& fout, std::string& out_path_out)
{
    if (got_meta) {
        fout.write(reinterpret_cast<const char*>(data), static_cast<std::streamsize>(n));
        return true;
    }
    // Scan for the null separator
    for (size_t i = 0; i < n; ++i) {
        if (data[i] == 0) {
            original_name = meta_buf + std::string(reinterpret_cast<const char*>(data), i);
            out_path_out = (fs::path(dir) / original_name).string();
            fout.open(out_path_out, std::ios::binary);
            if (!fout) return false;
            size_t rest = n - i - 1;
            if (rest > 0)
                fout.write(reinterpret_cast<const char*>(data + i + 1),
                           static_cast<std::streamsize>(rest));
            got_meta = true;
            return true;
        }
    }
    meta_buf.append(reinterpret_cast<const char*>(data), n);
    return true;
}

} // anonymous namespace

// ── AES-256-GCM ──────────────────────────────────────────────────────────────

std::pair<bool, std::string> encryptGcm(
    const std::string& input_path,
    const std::string& password,
    bool encrypt_name,
    int chunk_size,
    const ProgressFn& progress)
{
    std::string out_path;
    try {
        if (!fs::exists(input_path))
            return {false, "Critical error: " + input_path + " not found"};
        if (input_path.ends_with(".gfglock"))
            return {false, input_path + " is already encrypted"};

        size_t file_size = fs::file_size(input_path);
        if (file_size < SMALL_THRESHOLD) chunk_size = 0;

        std::string out_name = buildName(input_path, encrypt_name, ".gfglock");
        out_path = (fs::path(input_path).parent_path() / out_name).string();

        auto salt  = randBytes(SALT_SIZE);
        auto nonce = randBytes(NONCE_SIZE);
        auto key   = pbkdf2Sha256(password, salt, KDF_ITERATIONS, KEY_SIZE);

        EvpCtx ctx;
        if (!ctx) throw std::runtime_error("EVP_CIPHER_CTX_new failed");
        if (EVP_EncryptInit_ex(ctx.get(), EVP_aes_256_gcm(), nullptr, nullptr, nullptr) != 1
            || EVP_CIPHER_CTX_ctrl(ctx.get(), EVP_CTRL_GCM_SET_IVLEN, NONCE_SIZE, nullptr) != 1
            || EVP_EncryptInit_ex(ctx.get(), nullptr, nullptr, key.data(), nonce.data()) != 1)
            throw std::runtime_error("GCM init failed");

        std::ifstream fin(input_path, std::ios::binary);
        std::ofstream fout(out_path, std::ios::binary);
        if (!fin || !fout) throw std::runtime_error("Cannot open file(s)");

        fout.write(reinterpret_cast<const char*>(salt.data()),  SALT_SIZE);
        fout.write(reinterpret_cast<const char*>(nonce.data()), NONCE_SIZE);
        uint8_t cs_field[4]; packBE32(static_cast<uint32_t>(chunk_size), cs_field);
        fout.write(reinterpret_cast<const char*>(cs_field), 4);

        // Encrypt embedded filename metadata
        std::string fn = fs::path(input_path).filename().string();
        std::vector<uint8_t> name_meta(fn.begin(), fn.end());
        name_meta.push_back(0);
        std::vector<uint8_t> enc_buf(name_meta.size() + EVP_MAX_BLOCK_LENGTH);
        int out_len = 0;
        if (EVP_EncryptUpdate(ctx.get(), enc_buf.data(), &out_len,
                              name_meta.data(), static_cast<int>(name_meta.size())) != 1)
            throw std::runtime_error("EVP_EncryptUpdate (metadata) failed");
        fout.write(reinterpret_cast<const char*>(enc_buf.data()), out_len);
        if (progress) progress(static_cast<double>(name_meta.size()));

        // Stream-encrypt file data
        size_t io_buf_size = chunk_size > 0
            ? std::max(static_cast<size_t>(chunk_size), BUFFER_SIZE) : BUFFER_SIZE;
        std::vector<uint8_t> read_buf(io_buf_size);
        std::vector<uint8_t> write_buf(io_buf_size + EVP_MAX_BLOCK_LENGTH);
        size_t progress_batch = 0;

        while (true) {
            size_t n = readChunk(fin, read_buf, io_buf_size);
            if (n == 0) break;
            if (EVP_EncryptUpdate(ctx.get(), write_buf.data(), &out_len,
                                  read_buf.data(), static_cast<int>(n)) != 1)
                throw std::runtime_error("EVP_EncryptUpdate (data) failed");
            fout.write(reinterpret_cast<const char*>(write_buf.data()), out_len);
            fireProgress(progress, progress_batch, n);
        }
        if (progress && progress_batch > 0) progress(static_cast<double>(progress_batch));

        if (EVP_EncryptFinal_ex(ctx.get(), write_buf.data(), &out_len) != 1)
            throw std::runtime_error("EVP_EncryptFinal_ex failed");
        fout.write(reinterpret_cast<const char*>(write_buf.data()), out_len);

        uint8_t tag[TAG_SIZE];
        if (EVP_CIPHER_CTX_ctrl(ctx.get(), EVP_CTRL_GCM_GET_TAG, TAG_SIZE, tag) != 1)
            throw std::runtime_error("GCM get tag failed");
        fout.write(reinterpret_cast<const char*>(tag), TAG_SIZE);

        fin.close(); fout.close();
        fs::remove(input_path);
        return {true, "Encrypted: " + input_path + " -> " + out_path};
    } catch (const std::exception& e) {
        try { if (!out_path.empty() && fs::exists(out_path)) fs::remove(out_path); } catch (...) {}
        return {false, "Critical error while encrypting " + input_path + ": " + e.what()};
    }
}

std::pair<bool, std::string> decryptGcm(
    const std::string& input_path,
    const std::string& password,
    const ProgressFn& progress)
{
    std::string out_path;
    try {
        if (!fs::exists(input_path))
            return {false, "Critical error: " + input_path + " not found"};
        if (!input_path.ends_with(".gfglock") && !input_path.ends_with(".gfglck"))
            return {false, input_path + " is already decrypted"};

        size_t total_size = fs::file_size(input_path);
        bool is_gcm = input_path.ends_with(".gfglock");

        std::ifstream fin(input_path, std::ios::binary);
        if (!fin) throw std::runtime_error("Cannot open file");

        uint8_t salt_buf[SALT_SIZE], nonce_buf[NONCE_SIZE], cs_buf[4];
        fin.read(reinterpret_cast<char*>(salt_buf), SALT_SIZE);
        fin.read(reinterpret_cast<char*>(nonce_buf), is_gcm ? NONCE_SIZE : IV_SIZE);
        fin.read(reinterpret_cast<char*>(cs_buf), 4);

        std::vector<uint8_t> salt(salt_buf, salt_buf + SALT_SIZE);
        auto key = pbkdf2Sha256(password, salt, KDF_ITERATIONS, KEY_SIZE);

        int hdr_size = SALT_SIZE + (is_gcm ? NONCE_SIZE : IV_SIZE) + 4;
        size_t data_len = total_size - static_cast<size_t>(hdr_size) - (is_gcm ? TAG_SIZE : 0);

        EvpCtx ctx;
        if (!ctx) throw std::runtime_error("EVP_CIPHER_CTX_new failed");
        if (is_gcm) {
            if (EVP_DecryptInit_ex(ctx.get(), EVP_aes_256_gcm(), nullptr, nullptr, nullptr) != 1
                || EVP_CIPHER_CTX_ctrl(ctx.get(), EVP_CTRL_GCM_SET_IVLEN, NONCE_SIZE, nullptr) != 1
                || EVP_DecryptInit_ex(ctx.get(), nullptr, nullptr, key.data(), nonce_buf) != 1)
                throw std::runtime_error("GCM decrypt init failed");
        } else {
            if (EVP_DecryptInit_ex(ctx.get(), EVP_aes_256_cfb128(), nullptr,
                                   key.data(), nonce_buf) != 1)
                throw std::runtime_error("CFB decrypt init failed");
        }

        std::vector<uint8_t> read_buf(BUFFER_SIZE);
        std::vector<uint8_t> dec_buf(BUFFER_SIZE + EVP_MAX_BLOCK_LENGTH);
        bool got_meta = false;
        std::string meta_buf, original_name;
        std::ofstream fout;
        size_t remaining = data_len, progress_batch = 0;
        int out_len = 0;

        while (remaining > 0) {
            size_t to_read = std::min(remaining, BUFFER_SIZE);
            size_t n = readChunk(fin, read_buf, to_read);
            if (n == 0) break;
            remaining -= n;
            if (EVP_DecryptUpdate(ctx.get(), dec_buf.data(), &out_len,
                                  read_buf.data(), static_cast<int>(n)) != 1)
                throw std::runtime_error("EVP_DecryptUpdate failed");
            if (out_len > 0 && !feedDecrypted(dec_buf.data(), static_cast<size_t>(out_len),
                    got_meta, meta_buf, original_name,
                    fs::path(input_path).parent_path().string(), fout, out_path))
                throw std::runtime_error("Cannot create output file");
            fireProgress(progress, progress_batch, n);
        }
        if (progress && progress_batch > 0) progress(static_cast<double>(progress_batch));

        if (is_gcm) {
            uint8_t tag[TAG_SIZE];
            fin.read(reinterpret_cast<char*>(tag), TAG_SIZE);
            if (EVP_CIPHER_CTX_ctrl(ctx.get(), EVP_CTRL_GCM_SET_TAG, TAG_SIZE, tag) != 1)
                throw std::runtime_error("GCM set tag failed");
            if (EVP_DecryptFinal_ex(ctx.get(), dec_buf.data(), &out_len) <= 0) {
                if (fout.is_open()) fout.close();
                try { if (!out_path.empty() && fs::exists(out_path)) fs::remove(out_path); } catch (...) {}
                return {false, "Critical error while decrypting " + input_path + ": authentication failed"};
            }
        } else {
            if (EVP_DecryptFinal_ex(ctx.get(), dec_buf.data(), &out_len) != 1)
                throw std::runtime_error("CFB finalize failed");
        }
        if (out_len > 0 && fout.is_open())
            fout.write(reinterpret_cast<const char*>(dec_buf.data()), out_len);

        if (!got_meta)
            throw std::runtime_error("metadata not found in decrypted stream");
        if (fout.is_open()) fout.close();
        fin.close();
        fs::remove(input_path);
        return {true, "Decrypted: " + input_path + " -> " + out_path};
    } catch (const std::exception& e) {
        try { if (!out_path.empty() && fs::exists(out_path)) fs::remove(out_path); } catch (...) {}
        return {false, "Critical error while decrypting " + input_path + ": " + e.what()};
    }
}

// ── AES-256-CFB ──────────────────────────────────────────────────────────────

std::pair<bool, std::string> encryptCfb(
    const std::string& input_path,
    const std::string& password,
    bool encrypt_name,
    int chunk_size,
    const ProgressFn& progress)
{
    std::string out_path;
    try {
        if (!fs::exists(input_path))
            return {false, "Critical error: " + input_path + " not found"};
        if (input_path.ends_with(".gfglck"))
            return {false, input_path + " is already encrypted"};

        size_t file_size = fs::file_size(input_path);
        if (file_size < SMALL_THRESHOLD) chunk_size = 0;

        std::string out_name = buildName(input_path, encrypt_name, ".gfglck");
        out_path = (fs::path(input_path).parent_path() / out_name).string();

        auto salt = randBytes(SALT_SIZE);
        auto iv   = randBytes(IV_SIZE);
        auto key  = pbkdf2Sha256(password, salt, KDF_ITERATIONS, KEY_SIZE);

        EvpCtx ctx;
        if (!ctx) throw std::runtime_error("EVP_CIPHER_CTX_new failed");
        if (EVP_EncryptInit_ex(ctx.get(), EVP_aes_256_cfb128(), nullptr,
                               key.data(), iv.data()) != 1)
            throw std::runtime_error("CFB init failed");

        std::ifstream fin(input_path, std::ios::binary);
        std::ofstream fout(out_path, std::ios::binary);
        if (!fin || !fout) throw std::runtime_error("Cannot open file(s)");

        fout.write(reinterpret_cast<const char*>(salt.data()), SALT_SIZE);
        fout.write(reinterpret_cast<const char*>(iv.data()),   IV_SIZE);
        uint8_t cs_field[4]; packBE32(static_cast<uint32_t>(chunk_size), cs_field);
        fout.write(reinterpret_cast<const char*>(cs_field), 4);

        std::string fn = fs::path(input_path).filename().string();
        std::vector<uint8_t> name_meta(fn.begin(), fn.end());
        name_meta.push_back(0);
        std::vector<uint8_t> enc_buf(name_meta.size() + EVP_MAX_BLOCK_LENGTH);
        int out_len = 0;
        if (EVP_EncryptUpdate(ctx.get(), enc_buf.data(), &out_len,
                              name_meta.data(), static_cast<int>(name_meta.size())) != 1)
            throw std::runtime_error("EVP_EncryptUpdate (metadata) failed");
        fout.write(reinterpret_cast<const char*>(enc_buf.data()), out_len);
        if (progress) progress(static_cast<double>(name_meta.size()));

        size_t io_buf_size = chunk_size > 0
            ? std::max(static_cast<size_t>(chunk_size), BUFFER_SIZE) : BUFFER_SIZE;
        std::vector<uint8_t> read_buf(io_buf_size);
        std::vector<uint8_t> write_buf(io_buf_size + EVP_MAX_BLOCK_LENGTH);
        size_t progress_batch = 0;

        while (true) {
            size_t n = readChunk(fin, read_buf, io_buf_size);
            if (n == 0) break;
            if (EVP_EncryptUpdate(ctx.get(), write_buf.data(), &out_len,
                                  read_buf.data(), static_cast<int>(n)) != 1)
                throw std::runtime_error("EVP_EncryptUpdate failed");
            fout.write(reinterpret_cast<const char*>(write_buf.data()), out_len);
            fireProgress(progress, progress_batch, n);
        }
        if (progress && progress_batch > 0) progress(static_cast<double>(progress_batch));

        if (EVP_EncryptFinal_ex(ctx.get(), write_buf.data(), &out_len) != 1)
            throw std::runtime_error("EVP_EncryptFinal_ex failed");
        fout.write(reinterpret_cast<const char*>(write_buf.data()), out_len);

        fin.close(); fout.close();
        fs::remove(input_path);
        return {true, "Encrypted: " + input_path + " -> " + out_path};
    } catch (const std::exception& e) {
        try { if (!out_path.empty() && fs::exists(out_path)) fs::remove(out_path); } catch (...) {}
        return {false, "Critical error while encrypting " + input_path + ": " + e.what()};
    }
}

std::pair<bool, std::string> decryptCfb(
    const std::string& input_path,
    const std::string& password,
    const ProgressFn& progress)
{
    // CFB shares the GCM decrypt path (is_gcm = false selects CFB cipher + no tag)
    return decryptGcm(input_path, password, progress);
}

// ── ChaCha20-Poly1305 ─────────────────────────────────────────────────────────

std::pair<bool, std::string> encryptChacha(
    const std::string& input_path,
    const std::string& password,
    bool encrypt_name,
    int chunk_size,
    const ProgressFn& progress)
{
    std::string out_path;
    try {
        if (!fs::exists(input_path))
            return {false, "Critical error: " + input_path + " not found"};
        if (input_path.ends_with(".gfgcha"))
            return {false, input_path + " is already encrypted"};

        size_t file_size = fs::file_size(input_path);
        if (file_size < SMALL_THRESHOLD) chunk_size = 0;

        std::string out_name = buildName(input_path, encrypt_name, ".gfgcha");
        out_path = (fs::path(input_path).parent_path() / out_name).string();

        auto salt  = randBytes(SALT_SIZE);
        auto nonce = randBytes(NONCE_SIZE);
        auto key   = pbkdf2Sha256(password, salt, KDF_ITERATIONS, KEY_SIZE);

        EvpCtx ctx;
        if (!ctx) throw std::runtime_error("EVP_CIPHER_CTX_new failed");
        if (EVP_EncryptInit_ex(ctx.get(), EVP_chacha20_poly1305(), nullptr, nullptr, nullptr) != 1
            || EVP_CIPHER_CTX_ctrl(ctx.get(), EVP_CTRL_AEAD_SET_IVLEN, NONCE_SIZE, nullptr) != 1
            || EVP_EncryptInit_ex(ctx.get(), nullptr, nullptr, key.data(), nonce.data()) != 1)
            throw std::runtime_error("ChaCha20-Poly1305 init failed");

        std::ifstream fin(input_path, std::ios::binary);
        std::ofstream fout(out_path, std::ios::binary);
        if (!fin || !fout) throw std::runtime_error("Cannot open file(s)");

        fout.write(reinterpret_cast<const char*>(salt.data()),  SALT_SIZE);
        fout.write(reinterpret_cast<const char*>(nonce.data()), NONCE_SIZE);
        uint8_t cs_field[4]; packBE32(static_cast<uint32_t>(chunk_size), cs_field);
        fout.write(reinterpret_cast<const char*>(cs_field), 4);

        std::string fn = fs::path(input_path).filename().string();
        std::vector<uint8_t> name_meta(fn.begin(), fn.end());
        name_meta.push_back(0);
        std::vector<uint8_t> enc_buf(name_meta.size() + EVP_MAX_BLOCK_LENGTH);
        int out_len = 0;
        if (EVP_EncryptUpdate(ctx.get(), enc_buf.data(), &out_len,
                              name_meta.data(), static_cast<int>(name_meta.size())) != 1)
            throw std::runtime_error("EVP_EncryptUpdate (metadata) failed");
        fout.write(reinterpret_cast<const char*>(enc_buf.data()), out_len);
        if (progress) progress(static_cast<double>(name_meta.size()));

        size_t io_buf_size = chunk_size > 0
            ? std::max(static_cast<size_t>(chunk_size), BUFFER_SIZE) : BUFFER_SIZE;
        std::vector<uint8_t> read_buf(io_buf_size);
        std::vector<uint8_t> write_buf(io_buf_size + EVP_MAX_BLOCK_LENGTH);
        size_t progress_batch = 0;

        while (true) {
            size_t n = readChunk(fin, read_buf, io_buf_size);
            if (n == 0) break;
            if (EVP_EncryptUpdate(ctx.get(), write_buf.data(), &out_len,
                                  read_buf.data(), static_cast<int>(n)) != 1)
                throw std::runtime_error("EVP_EncryptUpdate failed");
            fout.write(reinterpret_cast<const char*>(write_buf.data()), out_len);
            fireProgress(progress, progress_batch, n);
        }
        if (progress && progress_batch > 0) progress(static_cast<double>(progress_batch));

        if (EVP_EncryptFinal_ex(ctx.get(), write_buf.data(), &out_len) != 1)
            throw std::runtime_error("EVP_EncryptFinal_ex failed");
        fout.write(reinterpret_cast<const char*>(write_buf.data()), out_len);

        uint8_t tag[TAG_SIZE];
        if (EVP_CIPHER_CTX_ctrl(ctx.get(), EVP_CTRL_AEAD_GET_TAG, TAG_SIZE, tag) != 1)
            throw std::runtime_error("ChaCha20 get tag failed");
        fout.write(reinterpret_cast<const char*>(tag), TAG_SIZE);

        fin.close(); fout.close();
        fs::remove(input_path);
        return {true, "Encrypted: " + input_path + " -> " + out_path};
    } catch (const std::exception& e) {
        try { if (!out_path.empty() && fs::exists(out_path)) fs::remove(out_path); } catch (...) {}
        return {false, "Critical error while encrypting " + input_path + ": " + e.what()};
    }
}

std::pair<bool, std::string> decryptChacha(
    const std::string& input_path,
    const std::string& password,
    const ProgressFn& progress)
{
    std::string out_path;
    try {
        if (!fs::exists(input_path))
            return {false, "Critical error: " + input_path + " not found"};
        if (!input_path.ends_with(".gfgcha"))
            return {false, input_path + " is already decrypted"};

        size_t total_size = fs::file_size(input_path);
        std::ifstream fin(input_path, std::ios::binary);
        if (!fin) throw std::runtime_error("Cannot open file");

        uint8_t salt_buf[SALT_SIZE], nonce_buf[NONCE_SIZE], cs_buf[4];
        fin.read(reinterpret_cast<char*>(salt_buf), SALT_SIZE);
        fin.read(reinterpret_cast<char*>(nonce_buf), NONCE_SIZE);
        fin.read(reinterpret_cast<char*>(cs_buf), 4);

        std::vector<uint8_t> salt(salt_buf, salt_buf + SALT_SIZE);
        auto key = pbkdf2Sha256(password, salt, KDF_ITERATIONS, KEY_SIZE);

        EvpCtx ctx;
        if (!ctx) throw std::runtime_error("EVP_CIPHER_CTX_new failed");
        if (EVP_DecryptInit_ex(ctx.get(), EVP_chacha20_poly1305(), nullptr, nullptr, nullptr) != 1
            || EVP_CIPHER_CTX_ctrl(ctx.get(), EVP_CTRL_AEAD_SET_IVLEN, NONCE_SIZE, nullptr) != 1
            || EVP_DecryptInit_ex(ctx.get(), nullptr, nullptr, key.data(), nonce_buf) != 1)
            throw std::runtime_error("ChaCha20-Poly1305 decrypt init failed");

        size_t data_len = total_size - SALT_SIZE - NONCE_SIZE - 4 - TAG_SIZE;
        std::vector<uint8_t> read_buf(BUFFER_SIZE);
        std::vector<uint8_t> dec_buf(BUFFER_SIZE + EVP_MAX_BLOCK_LENGTH);
        bool got_meta = false;
        std::string meta_buf, original_name;
        std::ofstream fout;
        size_t remaining = data_len, progress_batch = 0;
        int out_len = 0;

        while (remaining > 0) {
            size_t to_read = std::min(remaining, BUFFER_SIZE);
            size_t n = readChunk(fin, read_buf, to_read);
            if (n == 0) break;
            remaining -= n;
            if (EVP_DecryptUpdate(ctx.get(), dec_buf.data(), &out_len,
                                  read_buf.data(), static_cast<int>(n)) != 1)
                throw std::runtime_error("EVP_DecryptUpdate failed");
            if (out_len > 0 && !feedDecrypted(dec_buf.data(), static_cast<size_t>(out_len),
                    got_meta, meta_buf, original_name,
                    fs::path(input_path).parent_path().string(), fout, out_path))
                throw std::runtime_error("Cannot create output file");
            fireProgress(progress, progress_batch, n);
        }
        if (progress && progress_batch > 0) progress(static_cast<double>(progress_batch));

        uint8_t tag[TAG_SIZE];
        fin.read(reinterpret_cast<char*>(tag), TAG_SIZE);
        if (EVP_CIPHER_CTX_ctrl(ctx.get(), EVP_CTRL_AEAD_SET_TAG, TAG_SIZE, tag) != 1)
            throw std::runtime_error("ChaCha20 set tag failed");
        if (EVP_DecryptFinal_ex(ctx.get(), dec_buf.data(), &out_len) <= 0) {
            if (fout.is_open()) fout.close();
            try { if (!out_path.empty() && fs::exists(out_path)) fs::remove(out_path); } catch (...) {}
            return {false, "Critical error while decrypting " + input_path + ": authentication failed"};
        }
        if (out_len > 0 && fout.is_open())
            fout.write(reinterpret_cast<const char*>(dec_buf.data()), out_len);

        if (!got_meta) throw std::runtime_error("metadata not found");
        if (fout.is_open()) fout.close();
        fin.close();
        fs::remove(input_path);
        return {true, "Decrypted: " + input_path + " -> " + out_path};
    } catch (const std::exception& e) {
        try { if (!out_path.empty() && fs::exists(out_path)) fs::remove(out_path); } catch (...) {}
        return {false, "Critical error while decrypting " + input_path + ": " + e.what()};
    }
}

} // namespace gfglock
