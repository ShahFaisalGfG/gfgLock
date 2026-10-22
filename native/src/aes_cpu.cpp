// aes_cpu.cpp - gfgLock file transforms via OpenSSL EVP: the v2 chunked AEAD stream (seal and
// open) and the v1 single-stream decrypt.
//
// These functions only turn one file into another. The Python caller (gfglock/core/file_ops.py)
// builds the v2 header and metadata, derives the file key, picks a fresh output path, validates
// the decrypted name, moves the finished file into place, and deletes the source. Keeping naming
// and deletion in that one shared layer means the native and Python fallback paths can never
// disagree about which file is safe to remove.
//
// v2 layout (owned by gfglock/core/format_v2.py; identical to the Python fallback):
//   header | chunk 0 | chunk 1 | ...
//   The plaintext stream metadata + data is cut into chunks of chunk_size bytes. Chunk i is
//   sealed with the nonce nonce_prefix | u32be(i) | u8(1 for the final chunk), the header as AAD,
//   and ends with its 16-byte tag.
// v1 layout (decrypt only):
//   salt(16) | nonce(12) or iv(16) | chunk_size u32 BE | E(original_name + NUL + data) | tag(16, AEAD only)
//
// The cipher runs on the calling thread. Disk reads and writes run on two helper threads (see
// streamBlocks), so the disk never waits for the cipher and the cipher never waits for the disk.

#include "aes_cpu.hpp"
#include "kdf.hpp"

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>

#include <openssl/evp.h>

#include <algorithm>
#include <array>
#include <bit>
#include <condition_variable>
#include <cstdint>
#include <deque>
#include <exception>
#include <filesystem>
#include <functional>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <thread>
#include <utility>
#include <vector>

namespace fs = std::filesystem;
namespace gfglock {

namespace {
constexpr size_t   SALT_SIZE          = 16;
constexpr size_t   NONCE_SIZE         = 12;
constexpr size_t   IV_SIZE            = 16;
constexpr size_t   TAG_SIZE           = 16;
constexpr size_t   CHUNK_FIELD_SIZE   = 4;
constexpr size_t   KEY_SIZE           = 32;
constexpr size_t   NONCE_PREFIX_SIZE  = 7;
constexpr size_t   MIN_CHUNK_SIZE     = size_t{1} << 16;
constexpr size_t   MAX_CHUNK_SIZE     = size_t{1} << 24;
constexpr uint64_t MAX_CHUNKS         = uint64_t{1} << 32;  // the chunk counter is a u32
// The v2 header is 60 bytes; the cap only keeps its length (the AAD) within an int.
constexpr size_t   MAX_HEADER_SIZE    = 4096;
constexpr size_t   METADATA_OVERHEAD  = 2 + 8;  // name_len u16 + mtime_ns i64
constexpr size_t   MAX_NAME_BYTES     = 1024;
constexpr size_t   V1_MAX_NAME_BYTES  = 4096;
// The read size used when the caller passes 0 ("Automatic"): 4 MB measured fastest on a typical
// desktop, but the best size depends on the disk and CPU cache, so callers can pick another.
// Each file in flight holds up to PIPELINE_DEPTH blocks; a v2 block has an input and an output
// buffer, so at the 64 MB cap one file holds about 512 MB.
constexpr size_t   DEFAULT_BLOCK_SIZE = 4  * 1024 * 1024;
constexpr size_t   MIN_BLOCK_SIZE     = 64 * 1024;
constexpr size_t   MAX_BLOCK_SIZE     = 64 * 1024 * 1024;
constexpr uint64_t PIPELINE_DEPTH     = 4;
constexpr uint64_t PROGRESS_INTERVAL  = 100 * 1024 * 1024;
constexpr DWORD    MAX_SYSCALL_BYTES  = 1u << 30;
constexpr int      KDF_ITERATIONS     = 200000;
static_assert(NONCE_PREFIX_SIZE + 4 + 1 == NONCE_SIZE, "a v2 nonce is prefix | u32 counter | u8 last flag");

// The messages Python matches or shows; py_cipher.py returns the same ones for the same failures.
constexpr const char* STOPPED      = "stopped";
constexpr const char* TRUNCATED    = "the file is truncated or corrupted";
constexpr const char* CORRUPTED    = "the file is corrupted";
constexpr const char* AUTH_FAILED  = "wrong password or the file was modified (authentication failed)";
constexpr const char* SIZE_CHANGED = "the source file changed size while it was being read";
constexpr const char* V1_BAD_NAME  = "wrong password or the file is corrupted";
// Inputs are opened read-share only, so a file another program holds open for writing fails.
constexpr const char* IN_USE       = "the file is open in another program";

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

void throwIfStopped(const CancelFlag* cancel) {
    if (cancel && cancel->load(std::memory_order_relaxed)) throw std::runtime_error(STOPPED);
}

// The read size for a block_size argument: 0 picks the default, others are clamped to the range.
size_t readSize(size_t requested) {
    return std::clamp(requested ? requested : DEFAULT_BLOCK_SIZE, MIN_BLOCK_SIZE, MAX_BLOCK_SIZE);
}

// Whole chunks per block for a block_size argument; a chunk larger than the read size makes one.
size_t chunksPerBlock(size_t block_size, size_t chunk_size) {
    return std::max<size_t>(1, readSize(block_size) / chunk_size);
}

// Throws std::invalid_argument unless spec has the sizes a v2 stream needs.
void checkStream(const StreamSpec& spec) {
    if (spec.algorithm == Algorithm::Cfb)
        throw std::invalid_argument("CFB only decrypts v1 files; v2 files use gcm or chacha");
    if (spec.header.empty() || spec.header.size() > MAX_HEADER_SIZE)
        throw std::invalid_argument("header must be 1 to 4096 bytes");
    if (spec.key.size() != KEY_SIZE)
        throw std::invalid_argument("key must be 32 bytes");
    if (spec.nonce_prefix.size() != NONCE_PREFIX_SIZE)
        throw std::invalid_argument("nonce_prefix must be 7 bytes");
    if (!std::has_single_bit(spec.chunk_size) || spec.chunk_size < MIN_CHUNK_SIZE || spec.chunk_size > MAX_CHUNK_SIZE)
        throw std::invalid_argument("chunk_size must be a power of two from 65536 to 16777216");
}

// Length of the v2 metadata block (name_len u16 BE, name, mtime_ns i64) at the start of
// `plain`, or 0 when `plain` doesn't start with a valid one.
size_t metadataSize(std::span<const uint8_t> plain) {
    if (plain.size() < 2) return 0;
    const size_t name_len = static_cast<size_t>(plain[0]) << 8 | plain[1];
    const size_t size = METADATA_OVERHEAD + name_len;
    return name_len >= 1 && name_len <= MAX_NAME_BYTES && plain.size() >= size ? size : 0;
}

struct EvpCtx {
    EVP_CIPHER_CTX* p = EVP_CIPHER_CTX_new();
    EvpCtx() { if (!p) throw std::runtime_error("EVP_CIPHER_CTX_new failed"); }
    EvpCtx(const EvpCtx&) = delete;
    EvpCtx& operator=(const EvpCtx&) = delete;
    ~EvpCtx() { EVP_CIPHER_CTX_free(p); }
    EVP_CIPHER_CTX* get() const { return p; }
};

// Selects the cipher, sets the nonce length for AEAD ciphers, and loads the key (and the IV,
// unless it is null and set later).
void initCipher(EVP_CIPHER_CTX* ctx, const CipherSpec& spec, const uint8_t* key, const uint8_t* iv, bool encrypt) {
    auto init = encrypt ? EVP_EncryptInit_ex : EVP_DecryptInit_ex;
    if (init(ctx, spec.cipher(), nullptr, nullptr, nullptr) != 1
        || (spec.aead && EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_AEAD_SET_IVLEN,
                                             static_cast<int>(spec.iv_size), nullptr) != 1)
        || init(ctx, nullptr, nullptr, key, iv) != 1)
        throw std::runtime_error("cipher initialisation failed");
}

// v1's ciphers are stream modes: every update turns n input bytes into exactly n output bytes,
// so v1 blocks are decrypted in place.
void decryptInPlace(EVP_CIPHER_CTX* ctx, uint8_t* data, size_t n) {
    int out_len = 0;
    if (EVP_DecryptUpdate(ctx, data, &out_len, data, static_cast<int>(n)) != 1
        || static_cast<size_t>(out_len) != n)
        throw std::runtime_error("decryption failed");
}

// Seals or opens the chunks of one v2 stream. The context keeps the file key's schedule; each
// chunk re-initialises it with only its own nonce, then feeds the header as AAD.
class ChunkCipher {
public:
    ChunkCipher(const StreamSpec& spec, bool encrypt) : header_(spec.header) {
        initCipher(ctx_.get(), specFor(spec.algorithm), spec.key.data(), nullptr, encrypt);
        std::copy(spec.nonce_prefix.begin(), spec.nonce_prefix.end(), nonce_.begin());
    }

    // Encrypts n plaintext bytes into out and appends the tag; returns the bytes written.
    size_t seal(uint64_t index, bool last, const uint8_t* plain, size_t n, uint8_t* out) {
        start(index, last);
        uint8_t rest[EVP_MAX_BLOCK_LENGTH];
        int len = 0, rest_len = 0;
        if (EVP_EncryptUpdate(ctx_.get(), out, &len, plain, static_cast<int>(n)) != 1
            || static_cast<size_t>(len) != n
            || EVP_EncryptFinal_ex(ctx_.get(), rest, &rest_len) != 1 || rest_len != 0
            || EVP_CIPHER_CTX_ctrl(ctx_.get(), EVP_CTRL_AEAD_GET_TAG, static_cast<int>(TAG_SIZE), out + n) != 1)
            throw std::runtime_error("encryption failed");
        return n + TAG_SIZE;
    }

    // Decrypts one chunk (ciphertext then tag, more than TAG_SIZE bytes) into out. Returns false
    // when the tag doesn't verify; out must then be discarded.
    bool open(uint64_t index, bool last, uint8_t* chunk, size_t n, uint8_t* out) {
        const size_t plain = n - TAG_SIZE;
        start(index, last);
        uint8_t rest[EVP_MAX_BLOCK_LENGTH];
        int len = 0;
        if (EVP_DecryptUpdate(ctx_.get(), out, &len, chunk, static_cast<int>(plain)) != 1
            || static_cast<size_t>(len) != plain
            || EVP_CIPHER_CTX_ctrl(ctx_.get(), EVP_CTRL_AEAD_SET_TAG, static_cast<int>(TAG_SIZE), chunk + plain) != 1)
            throw std::runtime_error("decryption failed");
        return EVP_DecryptFinal_ex(ctx_.get(), rest, &len) > 0;
    }

private:
    void start(uint64_t index, bool last) {
        for (size_t i = 0; i < 4; ++i)
            nonce_[NONCE_PREFIX_SIZE + i] = static_cast<uint8_t>(index >> (24 - 8 * i));
        nonce_[NONCE_SIZE - 1] = last ? 1 : 0;
        int len = 0;
        if (EVP_CipherInit_ex(ctx_.get(), nullptr, nullptr, nullptr, nonce_.data(), -1) != 1
            || EVP_CipherUpdate(ctx_.get(), nullptr, &len, header_.data(), static_cast<int>(header_.size())) != 1)
            throw std::runtime_error("cipher initialisation failed");
    }

    EvpCtx ctx_;
    std::span<const uint8_t> header_;
    std::array<uint8_t, NONCE_SIZE> nonce_{};
};

// A Win32 file opened for sequential access, which lets Windows read ahead aggressively. Other
// programs may only read it while it is open, so no one can change a file being read.
class File {
public:
    enum class Mode { Read, Create };

    File(const fs::path& path, Mode mode, const char* open_error) {
        const bool read = mode == Mode::Read;
        handle_ = CreateFileW(path.c_str(), read ? GENERIC_READ : GENERIC_WRITE, FILE_SHARE_READ, nullptr,
                              read ? OPEN_EXISTING : CREATE_ALWAYS,
                              FILE_ATTRIBUTE_NORMAL | FILE_FLAG_SEQUENTIAL_SCAN, nullptr);
        if (handle_ == INVALID_HANDLE_VALUE)
            throw std::runtime_error(GetLastError() == ERROR_SHARING_VIOLATION ? IN_USE : open_error);
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
        if (read(dst, n) != n) throw std::runtime_error(TRUNCATED);
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

// One block in flight. The reader fills `in`; the transform leaves the bytes to write in
// `result`, inside `in` when it works in place, else inside `out`.
struct Block {
    Block(size_t in_capacity, size_t out_capacity)
        : in(std::make_unique_for_overwrite<uint8_t[]>(in_capacity)),
          out(out_capacity ? std::make_unique_for_overwrite<uint8_t[]>(out_capacity) : nullptr) {}
    std::unique_ptr<uint8_t[]> in;
    std::unique_ptr<uint8_t[]> out;
    uint64_t index = 0;  // block i holds stream bytes [i * in_size, (i + 1) * in_size)
    size_t size = 0;     // bytes in `in`, the first block's prefix included
    size_t read = 0;     // bytes of `size` that came from the file
    std::span<const uint8_t> result;
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

// How streamBlocks cuts its input: `limit` file bytes in blocks of `in_size` bytes, the first
// block starting with `prefix` (at most in_size bytes). `out_size` is each block's output
// buffer, 0 when the transform works in place. `counted` input bytes read outside the stream
// (headers and tags) are added to the progress.
struct StreamPlan {
    uint64_t limit;
    size_t in_size;
    size_t out_size;
    std::span<const uint8_t> prefix;
    uint64_t counted;
};

// Read plan.limit bytes from `in` in blocks, pass each block through `transform` on the calling
// thread, and append each block's result to `out`. Reading and writing run on their own threads
// with a few blocks in flight, so all three stages work at once. The cancel flag is checked
// before every read and every transform. Returns the number of file bytes read.
template<typename Transform>
uint64_t streamBlocks(File& in, File& out, const StreamPlan& plan, Transform&& transform,
                      const CancelFlag* cancel, const ProgressFn& progress) {
    const uint64_t blocks = (plan.prefix.size() + plan.limit + plan.in_size - 1) / plan.in_size;
    const uint64_t depth = std::clamp<uint64_t>(blocks, 1, PIPELINE_DEPTH);
    Channel free_blocks, read_blocks, done_blocks;
    for (uint64_t i = 0; i < depth; ++i) free_blocks.push(std::make_unique<Block>(plan.in_size, plan.out_size));

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
            uint64_t remaining = plan.limit;
            for (uint64_t index = 0; index == 0 || remaining > 0; ++index) {
                BlockPtr block = free_blocks.pop();
                if (!block) break;
                throwIfStopped(cancel);
                const size_t prefix = index == 0 ? plan.prefix.size() : 0;
                std::copy_n(plan.prefix.data(), prefix, block->in.get());
                const size_t want = static_cast<size_t>(std::min<uint64_t>(remaining, plan.in_size - prefix));
                block->index = index;
                block->read = in.read(block->in.get() + prefix, want);
                block->size = prefix + block->read;
                remaining -= block->read;
                total_read += block->read;
                const bool at_end = block->read < want;
                if (block->size > 0) read_blocks.push(std::move(block));
                if (at_end) break;
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
                out.write(block->result.data(), block->result.size());
                free_blocks.push(std::move(block));
            }
        } catch (...) {
            write_error = std::current_exception();
            abortAll();
        }
    });

    uint64_t progress_batch = plan.counted;
    while (BlockPtr block = read_blocks.pop()) {
        throwIfStopped(cancel);
        transform(*block);
        progress_batch += block->read;
        done_blocks.push(std::move(block));
        if (progress && progress_batch >= PROGRESS_INTERVAL) {
            progress(progress_batch);
            progress_batch = 0;
        }
    }
    done_blocks.close();
    joiner.reader.join();
    joiner.writer.join();
    joiner.finished = true;
    if (read_error) std::rethrow_exception(read_error);
    if (write_error) std::rethrow_exception(write_error);
    if (progress && progress_batch > 0) progress(progress_batch);
    return total_read;
}

} // anonymous namespace

std::pair<bool, std::string> sealFile(
    const StreamSpec& spec,
    const std::string& input_path,
    const std::string& output_path,
    std::span<const uint8_t> metadata,
    size_t block_size,
    const CancelFlag* cancel,
    const ProgressFn& progress)
{
    checkStream(spec);
    if (metadataSize(metadata) != metadata.size())
        throw std::invalid_argument("metadata must be one v2 metadata block (name length, name, mtime)");
    try {
        throwIfStopped(cancel);
        File fin(utf8Path(input_path), File::Mode::Read, "cannot open the source file");
        const uint64_t data_size = fin.size();
        const size_t chunk = spec.chunk_size;
        const uint64_t plain_size = metadata.size() + data_size;
        const uint64_t chunks = (plain_size + chunk - 1) / chunk;
        if (chunks > MAX_CHUNKS) throw std::runtime_error("the file is too large");

        File fout(utf8Path(output_path), File::Mode::Create, "cannot create the output file");
        fout.write(spec.header.data(), spec.header.size());
        ChunkCipher cipher(spec, true);

        // Blocks hold whole chunks (the metadata fills the start of the first), so block b
        // starts with chunk b * per_block.
        const size_t per_block = chunksPerBlock(block_size, chunk);
        const size_t in_size = static_cast<size_t>(std::min<uint64_t>(per_block * chunk, plain_size));
        const size_t out_size = in_size + (in_size + chunk - 1) / chunk * TAG_SIZE;
        auto sealBlock = [&](Block& block) {
            const uint64_t first = block.index * per_block;
            size_t sealed = 0;
            for (size_t pos = 0; pos < block.size; pos += chunk) {
                const uint64_t index = first + pos / chunk;
                sealed += cipher.seal(index, index == chunks - 1, block.in.get() + pos,
                                      std::min(chunk, block.size - pos), block.out.get() + sealed);
            }
            block.result = {block.out.get(), sealed};
        };

        // The size taken at open is the read limit; one more byte after it means the file grew.
        const StreamPlan plan{data_size, in_size, out_size, metadata, 0};
        const uint64_t total_read = streamBlocks(fin, fout, plan, sealBlock, cancel, progress);
        uint8_t probe = 0;
        if (total_read != data_size || fin.read(&probe, 1) != 0)
            throw std::runtime_error(SIZE_CHANGED);
        fout.close();
        return {true, ""};
    } catch (const std::exception& e) {
        return {false, e.what()};
    }
}

DecryptResult openFile(
    const StreamSpec& spec,
    const std::string& input_path,
    const std::string& output_path,
    size_t block_size,
    const CancelFlag* cancel,
    const ProgressFn& progress)
{
    checkStream(spec);
    try {
        throwIfStopped(cancel);
        File fin(utf8Path(input_path), File::Mode::Read, "cannot open the encrypted file");
        const uint64_t file_size = fin.size();
        const size_t header_size = spec.header.size();
        if (file_size <= header_size) throw std::runtime_error(TRUNCATED);
        // The header is every chunk's AAD, so a stored header that differs could never verify.
        std::vector<uint8_t> stored_header(header_size);
        fin.readExact(stored_header.data(), header_size);
        if (!std::ranges::equal(stored_header, spec.header)) throw std::runtime_error(AUTH_FAILED);

        const size_t chunk = spec.chunk_size;
        const size_t unit = chunk + TAG_SIZE;
        const uint64_t body = file_size - header_size;
        const uint64_t tail = body % unit;
        if (tail != 0 && tail <= TAG_SIZE) throw std::runtime_error(TRUNCATED);
        const uint64_t chunks = body / unit + (tail != 0 ? 1 : 0);
        if (chunks > MAX_CHUNKS) throw std::runtime_error(CORRUPTED);

        File fout(utf8Path(output_path), File::Mode::Create, "cannot create the output file");
        ChunkCipher cipher(spec, false);

        DecryptResult result;
        const size_t per_block = chunksPerBlock(block_size, chunk);
        const size_t in_size = static_cast<size_t>(std::min<uint64_t>(per_block * unit, body));
        auto openBlock = [&](Block& block) {
            const uint64_t first = block.index * per_block;
            size_t opened = 0;
            for (size_t pos = 0; pos < block.size; pos += unit) {
                const size_t n = std::min(unit, block.size - pos);
                if (n <= TAG_SIZE) throw std::runtime_error(TRUNCATED);
                const uint64_t index = first + pos / unit;
                if (!cipher.open(index, index == chunks - 1, block.in.get() + pos, n, block.out.get() + opened))
                    throw std::runtime_error(AUTH_FAILED);
                opened += n - TAG_SIZE;
            }
            // The metadata block must sit inside chunk 0's plaintext; it is returned, not written.
            size_t skip = 0;
            if (block.index == 0) {
                skip = metadataSize({block.out.get(), std::min(opened, chunk)});
                if (skip == 0) throw std::runtime_error(CORRUPTED);
                result.stored.assign(reinterpret_cast<const char*>(block.out.get()), skip);
            }
            block.result = {block.out.get() + skip, opened - skip};
        };

        const StreamPlan plan{body, in_size, in_size, {}, header_size};
        if (streamBlocks(fin, fout, plan, openBlock, cancel, progress) != body)
            throw std::runtime_error(TRUNCATED);
        fout.close();
        result.ok = true;
        return result;
    } catch (const std::exception& e) {
        return {false, e.what(), ""};
    }
}

DecryptResult decryptFileV1(
    Algorithm algorithm,
    const std::string& input_path,
    const std::string& output_path,
    const std::string& password,
    size_t block_size,
    const CancelFlag* cancel,
    const ProgressFn& progress)
{
    try {
        throwIfStopped(cancel);
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

        const SecureKey key = pbkdf2Sha256(password, salt, KDF_ITERATIONS, static_cast<int>(KEY_SIZE));
        EvpCtx ctx;
        initCipher(ctx.get(), spec, key.bytes.data(), iv.data(), false);

        File fout(utf8Path(output_path), File::Mode::Create, "cannot create the output file");

        DecryptResult result;
        bool got_name = false;
        // The stream starts with the original file name and a NUL; everything after it is data.
        auto decryptBlock = [&](Block& block) {
            uint8_t* data = block.in.get();
            decryptInPlace(ctx.get(), data, block.size);
            size_t skip = 0;
            if (!got_name) {
                const uint8_t* end = data + block.size;
                const uint8_t* nul = std::find(static_cast<const uint8_t*>(data), end, uint8_t{0});
                result.stored.append(reinterpret_cast<const char*>(data), static_cast<size_t>(nul - data));
                if (result.stored.size() > V1_MAX_NAME_BYTES) throw std::runtime_error(V1_BAD_NAME);
                got_name = nul != end;
                skip = got_name ? static_cast<size_t>(nul - data) + 1 : block.size;
            }
            block.result = {data + skip, block.size - skip};
        };

        const uint64_t data_size = total_size - header_size - tag_size;
        const size_t in_size = static_cast<size_t>(std::min<uint64_t>(data_size, readSize(block_size)));
        const StreamPlan plan{data_size, in_size, 0, {}, header_size + tag_size};
        if (streamBlocks(fin, fout, plan, decryptBlock, cancel, progress) != data_size)
            throw std::runtime_error(TRUNCATED);

        // All three ciphers are stream modes, so finalising never yields more plaintext.
        uint8_t final_block[EVP_MAX_BLOCK_LENGTH];
        int out_len = 0;
        if (spec.aead) {
            uint8_t tag[TAG_SIZE];
            fin.readExact(tag, TAG_SIZE);
            if (EVP_CIPHER_CTX_ctrl(ctx.get(), EVP_CTRL_AEAD_SET_TAG, static_cast<int>(TAG_SIZE), tag) != 1)
                throw std::runtime_error("decryption failed");
            if (EVP_DecryptFinal_ex(ctx.get(), final_block, &out_len) <= 0)
                return {false, AUTH_FAILED, ""};
        } else if (EVP_DecryptFinal_ex(ctx.get(), final_block, &out_len) != 1) {
            throw std::runtime_error("decryption failed");
        }
        if (!got_name) throw std::runtime_error(V1_BAD_NAME);
        fout.close();
        result.ok = true;
        return result;
    } catch (const std::exception& e) {
        return {false, e.what(), ""};
    }
}

} // namespace gfglock
