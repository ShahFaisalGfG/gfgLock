// aes_cpu.cpp - AES-256-GCM / AES-256-CFB / ChaCha20-Poly1305 file transforms via OpenSSL EVP.
//
// These functions only turn one file into another. The Python caller (gfglock/core/file_ops.py)
// picks a fresh output path, validates the decrypted file name, moves the finished file into
// place, and deletes the source. Keeping naming and deletion in that one shared layer means the
// native and Python fallback paths can never disagree about which file is safe to remove.
//
// File layout (identical to the Python fallback):
//   salt(16) | nonce(12) or iv(16) | chunk_size u32 BE | E(original_name + NUL + data) | tag(16, AEAD only)
//
// The data is one cipher stream, so the cipher itself runs on one thread. Disk reads and writes
// run on two helper threads (see streamBlocks), so the disk never waits for the cipher and the
// cipher never waits for the disk.

#include "aes_cpu.hpp"
#include "kdf.hpp"

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>

#include <openssl/crypto.h>
#include <openssl/evp.h>
#include <openssl/rand.h>

#include <algorithm>
#include <condition_variable>
#include <cstdint>
#include <deque>
#include <exception>
#include <filesystem>
#include <functional>
#include <limits>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <thread>
#include <utility>
#include <vector>

namespace fs = std::filesystem;
namespace gfglock {

namespace {
constexpr size_t SALT_SIZE         = 16;
constexpr size_t NONCE_SIZE        = 12;
constexpr size_t IV_SIZE           = 16;
constexpr size_t TAG_SIZE          = 16;
constexpr size_t CHUNK_FIELD_SIZE  = 4;
// The read size used when the caller passes 0 ("Automatic"): 4 MB measured fastest on a typical
// desktop, but the best size depends on the disk and CPU cache, so callers can pick another.
// Each file in flight holds PIPELINE_DEPTH blocks; the cap keeps that under 256 MB.
constexpr size_t DEFAULT_BLOCK_SIZE = 4   * 1024 * 1024;
constexpr size_t MAX_BLOCK_SIZE     = 64  * 1024 * 1024;
constexpr size_t PIPELINE_DEPTH    = 4;
constexpr size_t PROGRESS_INTERVAL = 100  * 1024 * 1024;
constexpr size_t MAX_NAME_BYTES    = 4096;
constexpr size_t MIN_BLOCK_SIZE    = 64   * 1024;
constexpr DWORD  MAX_SYSCALL_BYTES = 1u << 30;
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

// GCM, CFB and ChaCha20-Poly1305 are stream modes: every update turns n input bytes into exactly
// n output bytes, so blocks are transformed in place.
void cipherInPlace(EVP_CIPHER_CTX* ctx, bool encrypt, uint8_t* data, size_t n) {
    int out_len = 0;
    const int ok = encrypt
        ? EVP_EncryptUpdate(ctx, data, &out_len, data, static_cast<int>(n))
        : EVP_DecryptUpdate(ctx, data, &out_len, data, static_cast<int>(n));
    if (ok != 1 || static_cast<size_t>(out_len) != n)
        throw std::runtime_error(encrypt ? "encryption failed" : "decryption failed");
}

// A Win32 file opened for sequential access, which lets Windows read ahead aggressively.
class File {
public:
    enum class Mode { Read, Create };

    File(const fs::path& path, Mode mode, const char* open_error) {
        const bool read = mode == Mode::Read;
        handle_ = CreateFileW(path.c_str(), read ? GENERIC_READ : GENERIC_WRITE,
                              read ? FILE_SHARE_READ | FILE_SHARE_WRITE : FILE_SHARE_READ, nullptr,
                              read ? OPEN_EXISTING : CREATE_ALWAYS,
                              FILE_ATTRIBUTE_NORMAL | FILE_FLAG_SEQUENTIAL_SCAN, nullptr);
        if (handle_ == INVALID_HANDLE_VALUE) throw std::runtime_error(open_error);
    }
    File(const File&) = delete;
    File& operator=(const File&) = delete;
    ~File() { if (handle_ != INVALID_HANDLE_VALUE) CloseHandle(handle_); }

    uint64_t size() const {
        LARGE_INTEGER size{};
        if (!GetFileSizeEx(handle_, &size)) throw std::runtime_error("could not read the file size");
        return static_cast<uint64_t>(size.QuadPart);
    }

    // Read up to n bytes; returns fewer only at the end of the file.
    size_t read(uint8_t* dst, size_t n) {
        size_t total = 0;
        while (total < n) {
            DWORD got = 0;
            const DWORD want = static_cast<DWORD>(std::min<size_t>(n - total, MAX_SYSCALL_BYTES));
            if (!ReadFile(handle_, dst + total, want, &got, nullptr))
                throw std::runtime_error("could not read the source file");
            if (got == 0) break;
            total += got;
        }
        return total;
    }

    void readExact(uint8_t* dst, size_t n) {
        if (read(dst, n) != n) throw std::runtime_error("the file is truncated or corrupted");
    }

    void write(const uint8_t* src, size_t n) {
        while (n > 0) {
            DWORD put = 0;
            const DWORD want = static_cast<DWORD>(std::min<size_t>(n, MAX_SYSCALL_BYTES));
            if (!WriteFile(handle_, src, want, &put, nullptr) || put == 0)
                throw std::runtime_error("could not write the output file (disk full or no access?)");
            src += put;
            n -= put;
        }
    }

    void close() {
        const HANDLE handle = std::exchange(handle_, INVALID_HANDLE_VALUE);
        if (!CloseHandle(handle)) throw std::runtime_error("could not finish writing the output file");
    }

private:
    HANDLE handle_ = INVALID_HANDLE_VALUE;
};

struct Block {
    explicit Block(size_t capacity) : data(capacity) {}
    std::vector<uint8_t> data;
    size_t offset = 0;  // first byte to write; decryption skips the stored file name
    size_t size = 0;    // bytes to write, starting at offset
};
using BlockPtr = std::unique_ptr<Block>;

// A blocking queue handing blocks from one pipeline stage to the next.
class Channel {
public:
    void push(BlockPtr block) {
        { std::lock_guard lock(mutex_); queue_.push_back(std::move(block)); }
        ready_.notify_one();
    }
    // Waits for the next block; nullptr once the channel is closed and drained, or aborted.
    BlockPtr pop() {
        std::unique_lock lock(mutex_);
        ready_.wait(lock, [&] { return aborted_ || closed_ || !queue_.empty(); });
        if (aborted_ || queue_.empty()) return nullptr;
        BlockPtr block = std::move(queue_.front());
        queue_.pop_front();
        return block;
    }
    void close() { { std::lock_guard lock(mutex_); closed_ = true; } ready_.notify_all(); }
    void abort() { { std::lock_guard lock(mutex_); aborted_ = true; } ready_.notify_all(); }

private:
    std::mutex mutex_;
    std::condition_variable ready_;
    std::deque<BlockPtr> queue_;
    bool closed_ = false;
    bool aborted_ = false;
};

// Read up to `limit` bytes from `in` in blocks of `requested_size` bytes (0 for the default), pass
// each block through `transform` on the calling thread, and append the result to `out`. Reading
// and writing run on their own threads with a few blocks in flight, so all three stages work at
// once. `expected` (the likely byte count) keeps small files from allocating full-size blocks.
// Returns the number of bytes read.
template<typename Transform>
uint64_t streamBlocks(File& in, uint64_t limit, uint64_t expected, File& out, size_t requested_size,
                      Transform&& transform, const ProgressFn& progress) {
    const size_t wanted = std::clamp(requested_size ? requested_size : DEFAULT_BLOCK_SIZE, MIN_BLOCK_SIZE, MAX_BLOCK_SIZE);
    const size_t block_size = static_cast<size_t>(std::clamp<uint64_t>(expected, MIN_BLOCK_SIZE, wanted));
    Channel free_blocks, read_blocks, done_blocks;
    for (size_t i = 0; i < PIPELINE_DEPTH; ++i) free_blocks.push(std::make_unique<Block>(block_size));

    std::exception_ptr read_error, write_error;
    uint64_t total_read = 0;
    auto abortAll = [&] { free_blocks.abort(); read_blocks.abort(); done_blocks.abort(); };

    // Whatever happens on this thread, both helpers must stop before the buffers and files go
    // away. The joiner exists before either thread starts, so even a failed thread start (which
    // throws) can't leave the other thread running unjoined.
    struct Joiner {
        std::function<void()> abort;
        std::thread reader;
        std::thread writer;
        bool finished = false;
        ~Joiner() {
            if (!finished) abort();
            if (reader.joinable()) reader.join();
            if (writer.joinable()) writer.join();
        }
    } joiner{abortAll};

    joiner.reader = std::thread([&] {
        try {
            uint64_t remaining = limit;
            while (remaining > 0) {
                BlockPtr block = free_blocks.pop();
                if (!block) break;
                const size_t want = static_cast<size_t>(std::min<uint64_t>(remaining, block_size));
                block->offset = 0;
                block->size = in.read(block->data.data(), want);
                if (block->size == 0) break;
                remaining -= block->size;
                total_read += block->size;
                read_blocks.push(std::move(block));
            }
        } catch (...) {
            read_error = std::current_exception();
            abortAll();
        }
        read_blocks.close();
    });
    joiner.writer = std::thread([&] {
        try {
            while (BlockPtr block = done_blocks.pop()) {
                out.write(block->data.data() + block->offset, block->size);
                free_blocks.push(std::move(block));
            }
        } catch (...) {
            write_error = std::current_exception();
            abortAll();
        }
    });

    size_t progress_batch = 0;
    while (BlockPtr block = read_blocks.pop()) {
        const size_t n = block->size;
        transform(*block);
        done_blocks.push(std::move(block));
        progress_batch += n;
        if (progress && progress_batch >= PROGRESS_INTERVAL) {
            progress(static_cast<double>(progress_batch));
            progress_batch = 0;
        }
    }
    done_blocks.close();
    joiner.reader.join();
    joiner.writer.join();
    joiner.finished = true;
    if (read_error) std::rethrow_exception(read_error);
    if (write_error) std::rethrow_exception(write_error);
    if (progress && progress_batch > 0) progress(static_cast<double>(progress_batch));
    return total_read;
}

} // anonymous namespace

std::pair<bool, std::string> encryptFile(
    Algorithm algorithm,
    const std::string& input_path,
    const std::string& output_path,
    const std::string& original_name,
    const std::string& password,
    size_t block_size,
    const ProgressFn& progress)
{
    try {
        const CipherSpec spec = specFor(algorithm);
        File fin(utf8Path(input_path), File::Mode::Read, "cannot open the source file");
        const uint64_t file_size = fin.size();

        File fout(utf8Path(output_path), File::Mode::Create, "cannot create the output file");

        const auto salt = randBytes(SALT_SIZE);
        const auto iv   = randBytes(spec.iv_size);
        SecureKey key{pbkdf2Sha256(password, salt, KDF_ITERATIONS, KEY_SIZE)};
        EvpCtx ctx;
        initCipher(ctx.get(), spec, key.bytes.data(), iv.data(), true);

        // The chunk field is informational; 0 says the data is one stream, which it always is.
        const uint8_t cs_field[CHUNK_FIELD_SIZE] = {0, 0, 0, 0};
        fout.write(salt.data(), salt.size());
        fout.write(iv.data(), iv.size());
        fout.write(cs_field, CHUNK_FIELD_SIZE);

        std::vector<uint8_t> name_meta(original_name.begin(), original_name.end());
        name_meta.push_back(0);
        cipherInPlace(ctx.get(), true, name_meta.data(), name_meta.size());
        fout.write(name_meta.data(), name_meta.size());
        if (progress) progress(static_cast<double>(name_meta.size()));

        // Read to the end rather than to file_size, so a file that grows meanwhile is noticed.
        const uint64_t total_read = streamBlocks(fin, std::numeric_limits<uint64_t>::max(), file_size, fout, block_size,
            [&](Block& block) { cipherInPlace(ctx.get(), true, block.data.data(), block.size); },
            progress);
        if (total_read != file_size)
            throw std::runtime_error("the source file changed size while it was being read");

        uint8_t final_block[EVP_MAX_BLOCK_LENGTH];
        int out_len = 0;
        if (EVP_EncryptFinal_ex(ctx.get(), final_block, &out_len) != 1)
            throw std::runtime_error("encryption failed");
        fout.write(final_block, static_cast<size_t>(out_len));

        if (spec.aead) {
            uint8_t tag[TAG_SIZE];
            if (EVP_CIPHER_CTX_ctrl(ctx.get(), EVP_CTRL_AEAD_GET_TAG, static_cast<int>(TAG_SIZE), tag) != 1)
                throw std::runtime_error("could not compute the authentication tag");
            fout.write(tag, TAG_SIZE);
        }
        fout.close();
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
    size_t block_size,
    const ProgressFn& progress)
{
    try {
        const CipherSpec spec = specFor(algorithm);
        File fin(utf8Path(input_path), File::Mode::Read, "cannot open the encrypted file");

        const uint64_t total_size = fin.size();
        const size_t header_size = SALT_SIZE + spec.iv_size + CHUNK_FIELD_SIZE;
        const size_t tag_size = spec.aead ? TAG_SIZE : 0;
        if (total_size < header_size + tag_size + 1)
            throw std::runtime_error("the file is too small to be a valid encrypted file");

        std::vector<uint8_t> salt(SALT_SIZE), iv(spec.iv_size), chunk_field(CHUNK_FIELD_SIZE);
        fin.readExact(salt.data(), salt.size());
        fin.readExact(iv.data(), iv.size());
        fin.readExact(chunk_field.data(), chunk_field.size());  // informational only

        SecureKey key{pbkdf2Sha256(password, salt, KDF_ITERATIONS, KEY_SIZE)};
        EvpCtx ctx;
        initCipher(ctx.get(), spec, key.bytes.data(), iv.data(), false);

        File fout(utf8Path(output_path), File::Mode::Create, "cannot create the output file");

        DecryptResult result;
        bool got_name = false;
        // The stream starts with the original file name and a NUL; everything after it is data.
        auto decryptBlock = [&](Block& block) {
            uint8_t* data = block.data.data();
            cipherInPlace(ctx.get(), false, data, block.size);
            if (got_name) return;
            const uint8_t* end = data + block.size;
            const uint8_t* nul = std::find(static_cast<const uint8_t*>(data), end, static_cast<uint8_t>(0));
            result.original_name.append(reinterpret_cast<const char*>(data), static_cast<size_t>(nul - data));
            if (result.original_name.size() > MAX_NAME_BYTES)
                throw std::runtime_error("wrong password or the file is corrupted");
            got_name = nul != end;
            block.offset = got_name ? static_cast<size_t>(nul - data) + 1 : block.size;
            block.size -= block.offset;
        };

        const uint64_t data_size = total_size - header_size - tag_size;
        if (streamBlocks(fin, data_size, data_size, fout, block_size, decryptBlock, progress) != data_size)
            throw std::runtime_error("the file is truncated or corrupted");

        // All three ciphers are stream modes, so finalising never yields more plaintext.
        uint8_t final_block[EVP_MAX_BLOCK_LENGTH];
        int out_len = 0;
        if (spec.aead) {
            uint8_t tag[TAG_SIZE];
            fin.readExact(tag, TAG_SIZE);
            if (EVP_CIPHER_CTX_ctrl(ctx.get(), EVP_CTRL_AEAD_SET_TAG, static_cast<int>(TAG_SIZE), tag) != 1)
                throw std::runtime_error("decryption failed");
            if (EVP_DecryptFinal_ex(ctx.get(), final_block, &out_len) <= 0)
                return {false, "wrong password or the file was modified (authentication failed)", ""};
        } else if (EVP_DecryptFinal_ex(ctx.get(), final_block, &out_len) != 1) {
            throw std::runtime_error("decryption failed");
        }
        if (!got_name) throw std::runtime_error("wrong password or the file is corrupted");
        fout.close();
        result.ok = true;
        return result;
    } catch (const std::exception& e) {
        return {false, e.what(), ""};
    }
}

} // namespace gfglock
