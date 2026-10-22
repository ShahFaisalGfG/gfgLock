// bindings.cpp - pybind11 module: exposes the native file transforms to Python.
// The GIL is released for the whole file operation and re-acquired only for progress callbacks.

#include <pybind11/pybind11.h>

#include <openssl/crypto.h>
#include <openssl/opensslv.h>

#include <memory>
#include <span>
#include <stdexcept>
#include <string_view>
#include <vector>

#include "aes_cpu.hpp"
#include "kdf.hpp"

namespace py = pybind11;
using namespace gfglock;

namespace {

// Bumped whenever the Python-facing API changes; native_bridge falls back to the pure-Python
// path when an older module is found on disk.
// 4: both transforms take a read size (block_size) and stream through reader/writer threads.
//    (3 was an unreleased build without the read size.)
// 5: v2 files: seal_file and open_file seal a chunked AEAD stream with a key and header the
//    caller derives; v1 encrypt_file is gone and decrypt_file became decrypt_file_v1; every
//    transform takes a CancelToken; openssl_version and openssl_build_version report OpenSSL.
constexpr int API_VERSION = 5;

// Lets Python stop a running transform from another thread or from its progress callback. The
// flag is shared, so a call keeps it alive even if the token object is released meanwhile.
class CancelToken {
public:
    void cancel() { flag_->store(true); }
    bool cancelled() const { return flag_->load(); }
    std::shared_ptr<CancelFlag> flag() const { return flag_; }

private:
    std::shared_ptr<CancelFlag> flag_ = std::make_shared<CancelFlag>(false);
};

std::shared_ptr<CancelFlag> flagOf(const CancelToken* token) {
    return token ? token->flag() : nullptr;
}

// Wrap a Python callable so C++ can invoke it with the GIL held.
ProgressFn wrapCallback(py::object cb) {
    if (cb.is_none()) return {};
    return [cb](uint64_t bytes) {
        py::gil_scoped_acquire acquire;
        cb(bytes);
    };
}

// Run a file-level function with the GIL released; progress callbacks re-acquire it.
template<typename Fn>
auto withGilReleased(Fn&& fn) {
    py::gil_scoped_release release;
    return fn();
}

Algorithm parseAlgorithm(const std::string& name) {
    if (name == "gcm") return Algorithm::Gcm;
    if (name == "cfb") return Algorithm::Cfb;
    if (name == "chacha") return Algorithm::Chacha;
    throw std::invalid_argument("unknown algorithm '" + name + "'");
}

// The bytes of a Python bytes object, read in place. Bytes are immutable and the call's
// arguments keep them alive, so the view stays valid while the GIL is released.
std::span<const uint8_t> view(const py::bytes& data) {
    const auto text = static_cast<std::string_view>(data);
    return {reinterpret_cast<const uint8_t*>(text.data()), text.size()};
}

StreamSpec streamSpec(const std::string& algorithm, const py::bytes& header, const py::bytes& key,
                      const py::bytes& nonce_prefix, size_t chunk_size) {
    return {parseAlgorithm(algorithm), view(header), view(key), view(nonce_prefix), chunk_size};
}

py::tuple decryptTuple(const DecryptResult& result) {
    return py::make_tuple(result.ok, result.message, py::bytes(result.stored));
}

} // anonymous namespace

PYBIND11_MODULE(gfglock_native, m) {
    m.doc() = "gfgLock native C++20 acceleration module (OpenSSL)";
    m.attr("API_VERSION") = API_VERSION;

    py::class_<CancelToken>(m, "CancelToken",
        "Stops a running transform; seal_file, open_file and decrypt_file_v1 then return \"stopped\".")
        .def(py::init<>())
        .def("cancel", &CancelToken::cancel, "Ask every call holding this token to stop (thread-safe).")
        .def_property_readonly("cancelled", &CancelToken::cancelled, "True once cancel() was called.");

    m.def("pbkdf2_sha256",
        [](const std::string& password, py::bytes salt_py, int iterations, int dklen) -> py::bytes {
            const auto salt_view = view(salt_py);
            const std::vector<uint8_t> salt(salt_view.begin(), salt_view.end());
            const SecureKey key = withGilReleased([&] {
                return pbkdf2Sha256(password, salt, iterations, dklen);
            });
            return py::bytes(reinterpret_cast<const char*>(key.bytes.data()), key.bytes.size());
        },
        py::arg("password"), py::arg("salt"), py::arg("iterations"), py::arg("dklen"),
        "Derive a key with PBKDF2-HMAC-SHA256 (OpenSSL EVP).");

    m.def("seal_file",
        [](const std::string& algorithm, const std::string& input_path, const std::string& output_path,
           const py::bytes& header, const py::bytes& key, const py::bytes& nonce_prefix, size_t chunk_size,
           const py::bytes& metadata, size_t block_size, const CancelToken* cancel, py::object cb) {
            const StreamSpec spec = streamSpec(algorithm, header, key, nonce_prefix, chunk_size);
            const auto meta = view(metadata);
            const auto flag = flagOf(cancel);
            auto progress = wrapCallback(cb);
            return withGilReleased([&] {
                return sealFile(spec, input_path, output_path, meta, block_size, flag.get(), progress);
            });
        },
        py::arg("algorithm"), py::arg("input_path"), py::arg("output_path"), py::arg("header"),
        py::arg("key"), py::arg("nonce_prefix"), py::arg("chunk_size"), py::arg("metadata"),
        py::arg("block_size") = 0, py::arg("cancel") = py::none(), py::arg("callback") = py::none(),
        "Seal input_path into output_path as a v2 file: header, then metadata + data in AEAD chunks. "
        "Returns (ok, error). Raises ValueError for arguments outside the v2 limits. Never deletes "
        "or renames files.");

    m.def("open_file",
        [](const std::string& algorithm, const std::string& input_path, const std::string& output_path,
           const py::bytes& header, const py::bytes& key, const py::bytes& nonce_prefix, size_t chunk_size,
           size_t block_size, const CancelToken* cancel, py::object cb) {
            const StreamSpec spec = streamSpec(algorithm, header, key, nonce_prefix, chunk_size);
            const auto flag = flagOf(cancel);
            auto progress = wrapCallback(cb);
            const DecryptResult result = withGilReleased([&] {
                return openFile(spec, input_path, output_path, block_size, flag.get(), progress);
            });
            return decryptTuple(result);
        },
        py::arg("algorithm"), py::arg("input_path"), py::arg("output_path"), py::arg("header"),
        py::arg("key"), py::arg("nonce_prefix"), py::arg("chunk_size"),
        py::arg("block_size") = 0, py::arg("cancel") = py::none(), py::arg("callback") = py::none(),
        "Open the v2 file input_path into output_path (data only). Returns (ok, error, metadata); the "
        "metadata is untrusted and must be validated. Never deletes or renames files.");

    m.def("decrypt_file_v1",
        [](const std::string& algorithm, const std::string& input_path, const std::string& output_path,
           const std::string& password, size_t block_size, const CancelToken* cancel, py::object cb) {
            const Algorithm algo = parseAlgorithm(algorithm);
            const auto flag = flagOf(cancel);
            auto progress = wrapCallback(cb);
            const DecryptResult result = withGilReleased([&] {
                return decryptFileV1(algo, input_path, output_path, password, block_size, flag.get(), progress);
            });
            return decryptTuple(result);
        },
        py::arg("algorithm"), py::arg("input_path"), py::arg("output_path"), py::arg("password"),
        py::arg("block_size") = 0, py::arg("cancel") = py::none(), py::arg("callback") = py::none(),
        "Decrypt the v1 file input_path into output_path. Returns (ok, error, original_name_bytes); the "
        "name is untrusted and must be validated. Never deletes or renames files.");

    m.def("openssl_version", [] { return std::string(OpenSSL_version(OPENSSL_VERSION_STRING)); },
        "The version of the OpenSSL library loaded at run time, e.g. \"3.6.5\".");
    m.def("openssl_build_version", [] { return std::string(OPENSSL_VERSION_STR); },
        "The OpenSSL version this module was compiled against.");
}
