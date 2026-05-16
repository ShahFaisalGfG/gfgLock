#pragma once
#include <functional>
#include <string>
#include <utility>

namespace gfglock {

using ProgressFn = std::function<void(double)>;

/// Encrypt a file using AES-256-GCM. C++ owns the full I/O loop; GIL released.
std::pair<bool, std::string> encryptGcm(
    const std::string& input_path,
    const std::string& password,
    bool encrypt_name,
    int chunk_size,
    const ProgressFn& progress
);

/// Decrypt a .gfglock file using AES-256-GCM.
std::pair<bool, std::string> decryptGcm(
    const std::string& input_path,
    const std::string& password,
    const ProgressFn& progress
);

/// Encrypt a file using AES-256-CFB.
std::pair<bool, std::string> encryptCfb(
    const std::string& input_path,
    const std::string& password,
    bool encrypt_name,
    int chunk_size,
    const ProgressFn& progress
);

/// Decrypt a .gfglck file using AES-256-CFB.
std::pair<bool, std::string> decryptCfb(
    const std::string& input_path,
    const std::string& password,
    const ProgressFn& progress
);

/// Encrypt a file using ChaCha20-Poly1305.
std::pair<bool, std::string> encryptChacha(
    const std::string& input_path,
    const std::string& password,
    bool encrypt_name,
    int chunk_size,
    const ProgressFn& progress
);

/// Decrypt a .gfgcha file using ChaCha20-Poly1305.
std::pair<bool, std::string> decryptChacha(
    const std::string& input_path,
    const std::string& password,
    const ProgressFn& progress
);

} // namespace gfglock
