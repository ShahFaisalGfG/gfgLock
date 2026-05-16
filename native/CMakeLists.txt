cmake_minimum_required(VERSION 3.25)
project(gfglock_native VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT WIN32)
    message(FATAL_ERROR "gfglock_native is a Windows-only target")
endif()

# ── Dependencies ──────────────────────────────────────────────────────────────

set(PYBIND11_FINDPYTHON ON)
find_package(pybind11 CONFIG REQUIRED)
find_package(OpenSSL REQUIRED)

# ── Sources ───────────────────────────────────────────────────────────────────

set(_SOURCES
    src/bindings.cpp
    src/kdf.cpp
    src/aes_cpu.cpp
)

# ── Module target ─────────────────────────────────────────────────────────────

pybind11_add_module(gfglock_native ${_SOURCES})

target_link_libraries(gfglock_native PRIVATE OpenSSL::Crypto)

# ── Output location ───────────────────────────────────────────────────────────
# Place the .pyd directly into gfglock/core/ for immediate Python import.
# POST_BUILD copy is the reliable path for VS multi-config generators, which
# append the config name regardless of per-target output directory properties.

set(_OUT_DIR "${PROJECT_SOURCE_DIR}/../gfglock/core")

foreach(_CONFIG Debug Release RelWithDebInfo MinSizeRel)
    set_target_properties(gfglock_native PROPERTIES
        "LIBRARY_OUTPUT_DIRECTORY_${_CONFIG}" "${_OUT_DIR}"
        "RUNTIME_OUTPUT_DIRECTORY_${_CONFIG}" "${_OUT_DIR}"
    )
endforeach()
set_target_properties(gfglock_native PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY "${_OUT_DIR}"
    RUNTIME_OUTPUT_DIRECTORY "${_OUT_DIR}"
)

add_custom_command(TARGET gfglock_native POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        "$<TARGET_FILE:gfglock_native>"
        "${_OUT_DIR}/$<TARGET_FILE_NAME:gfglock_native>"
)
