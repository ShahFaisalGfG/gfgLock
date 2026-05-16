// bindings.cpp — pybind11 module: exposes all native functions to Python.
// GIL is released before every file I/O operation; re-acquired for callbacks.

#include <pybind11/functional.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "aes_cpu.hpp"
#include "kdf.hpp"

namespace py = pybind11;
using namespace gfglock;

namespace {

// Wrap a Python callable so C++ can invoke it with GIL held.
ProgressFn wrapCallback(py::object cb) {
    if (cb.is_none()) return {};
    return [cb](double bytes) {
        py::gil_scoped_acquire acquire;
        cb(bytes);
    };
}

// Call a file-level function with GIL released, progress callback re-acquires.
template<typename Fn>
auto withGilReleased(Fn&& fn) {
    py::gil_scoped_release release;
    return fn();
}

} // anonymous namespace

PYBIND11_MODULE(gfglock_native, m) {
    m.doc() = "gfgLock native C++20 acceleration module (OpenSSL)";

    // ── KDF ──────────────────────────────────────────────────────────────────

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

    // ── AES-256-GCM ──────────────────────────────────────────────────────────

    m.def("encrypt_gcm",
        [](const std::string& path, const std::string& pw, bool enc_name,
           int chunk_size, py::object cb) {
            auto progress = wrapCallback(cb);
            return withGilReleased([&] { return encryptGcm(path, pw, enc_name, chunk_size, progress); });
        },
        py::arg("path"), py::arg("password"), py::arg("encrypt_name") = false,
        py::arg("chunk_size") = 0, py::arg("callback") = py::none(),
        "Encrypt a file with AES-256-GCM (C++ + OpenSSL, GIL released).");

    m.def("decrypt_gcm",
        [](const std::string& path, const std::string& pw, py::object cb) {
            auto progress = wrapCallback(cb);
            return withGilReleased([&] { return decryptGcm(path, pw, progress); });
        },
        py::arg("path"), py::arg("password"), py::arg("callback") = py::none(),
        "Decrypt a .gfglock file with AES-256-GCM (C++ + OpenSSL, GIL released).");

    // ── AES-256-CFB ──────────────────────────────────────────────────────────

    m.def("encrypt_cfb",
        [](const std::string& path, const std::string& pw, bool enc_name,
           int chunk_size, py::object cb) {
            auto progress = wrapCallback(cb);
            return withGilReleased([&] { return encryptCfb(path, pw, enc_name, chunk_size, progress); });
        },
        py::arg("path"), py::arg("password"), py::arg("encrypt_name") = false,
        py::arg("chunk_size") = 0, py::arg("callback") = py::none(),
        "Encrypt a file with AES-256-CFB (C++ + OpenSSL, GIL released).");

    m.def("decrypt_cfb",
        [](const std::string& path, const std::string& pw, py::object cb) {
            auto progress = wrapCallback(cb);
            return withGilReleased([&] { return decryptCfb(path, pw, progress); });
        },
        py::arg("path"), py::arg("password"), py::arg("callback") = py::none(),
        "Decrypt a .gfglck file with AES-256-CFB (C++ + OpenSSL, GIL released).");

    // ── ChaCha20-Poly1305 ─────────────────────────────────────────────────────

    m.def("encrypt_chacha",
        [](const std::string& path, const std::string& pw, bool enc_name,
           int chunk_size, py::object cb) {
            auto progress = wrapCallback(cb);
            return withGilReleased([&] { return encryptChacha(path, pw, enc_name, chunk_size, progress); });
        },
        py::arg("path"), py::arg("password"), py::arg("encrypt_name") = false,
        py::arg("chunk_size") = 0, py::arg("callback") = py::none(),
        "Encrypt a file with ChaCha20-Poly1305 (C++ + OpenSSL, GIL released).");

    m.def("decrypt_chacha",
        [](const std::string& path, const std::string& pw, py::object cb) {
            auto progress = wrapCallback(cb);
            return withGilReleased([&] { return decryptChacha(path, pw, progress); });
        },
        py::arg("path"), py::arg("password"), py::arg("callback") = py::none(),
        "Decrypt a .gfgcha file with ChaCha20-Poly1305 (C++ + OpenSSL, GIL released).");

}
