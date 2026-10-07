// bindings.cpp - pybind11 module: exposes the native file transforms to Python.
// The GIL is released for the whole file operation and re-acquired only for progress callbacks.

#include <pybind11/functional.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <stdexcept>

#include "aes_cpu.hpp"
#include "kdf.hpp"

namespace py = pybind11;
using namespace gfglock;

namespace {

// Bumped whenever the Python-facing API changes; native_bridge falls back to the pure-Python
// path when an older module is found on disk. 4: both transforms take a read size (block_size)
// and stream through reader/writer threads. (3 was an unreleased build without the read size.)
constexpr int API_VERSION = 4;

// Wrap a Python callable so C++ can invoke it with the GIL held.
ProgressFn wrapCallback(py::object cb) {
    if (cb.is_none()) return {};
    return [cb](double bytes) {
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
    throw std::invalid_argument("unknown algorithm '" + name + "' (expected gcm, cfb, or chacha)");
}

} // anonymous namespace

PYBIND11_MODULE(gfglock_native, m) {
    m.doc() = "gfgLock native C++20 acceleration module (OpenSSL)";
    m.attr("API_VERSION") = API_VERSION;

    m.def("pbkdf2_sha256",
        [](const std::string& password, py::bytes salt_py, int iterations, int dklen) -> py::bytes {
            auto sv = py::cast<std::string>(salt_py);
            std::vector<uint8_t> salt(sv.begin(), sv.end());
            auto key = withGilReleased([&] {
                return pbkdf2Sha256(password, salt, iterations, dklen);
            });
            return py::bytes(reinterpret_cast<const char*>(key.data()), key.size());
        },
        py::arg("password"), py::arg("salt"), py::arg("iterations"), py::arg("dklen"),
        "Derive a key with PBKDF2-HMAC-SHA256 (OpenSSL EVP).");

    m.def("encrypt_file",
        [](const std::string& algorithm, const std::string& input_path, const std::string& output_path,
           const std::string& original_name, const std::string& password, size_t block_size, py::object cb) {
            const Algorithm algo = parseAlgorithm(algorithm);
            auto progress = wrapCallback(cb);
            return withGilReleased([&] {
                return encryptFile(algo, input_path, output_path, original_name, password, block_size, progress);
            });
        },
        py::arg("algorithm"), py::arg("input_path"), py::arg("output_path"), py::arg("original_name"),
        py::arg("password"), py::arg("block_size") = 0, py::arg("callback") = py::none(),
        "Encrypt input_path into output_path. Returns (ok, error). Never deletes or renames files.");

    m.def("decrypt_file",
        [](const std::string& algorithm, const std::string& input_path, const std::string& output_path,
           const std::string& password, size_t block_size, py::object cb) {
            const Algorithm algo = parseAlgorithm(algorithm);
            auto progress = wrapCallback(cb);
            DecryptResult result = withGilReleased([&] {
                return decryptFile(algo, input_path, output_path, password, block_size, progress);
            });
            return py::make_tuple(result.ok, result.message, py::bytes(result.original_name));
        },
        py::arg("algorithm"), py::arg("input_path"), py::arg("output_path"),
        py::arg("password"), py::arg("block_size") = 0, py::arg("callback") = py::none(),
        "Decrypt input_path into output_path. Returns (ok, error, original_name_bytes); the name is "
        "untrusted and must be validated. Never deletes or renames files.");
}
