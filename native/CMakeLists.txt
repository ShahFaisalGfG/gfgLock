cmake_minimum_required(VERSION 3.25)

# The app version in pyproject.toml (`version = "x.y.z"`) is the version of both native targets.
set(_PYPROJECT "${CMAKE_CURRENT_SOURCE_DIR}/../pyproject.toml")
file(STRINGS "${_PYPROJECT}" _VERSION_LINES REGEX "^version = \"[0-9]+\\.[0-9]+\\.[0-9]+\"")
if(NOT _VERSION_LINES)
    message(FATAL_ERROR "No `version = \"x.y.z\"` line found in ${_PYPROJECT}")
endif()
list(GET _VERSION_LINES 0 _VERSION_LINE)
string(REGEX MATCH "[0-9]+\\.[0-9]+\\.[0-9]+" GFGLOCK_VERSION "${_VERSION_LINE}")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${_PYPROJECT}")

project(gfglock_native VERSION ${GFGLOCK_VERSION} LANGUAGES CXX RC)

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
# Keeps CMake's default dynamic CRT (/MD), which Python and the vcpkg OpenSSL DLL also use.

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

# ── Shell extension COM DLL (Windows 11 first-level context menu) ─────────────

# The version resource reads these from a generated header.
file(CONFIGURE OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/generated/gfglock_version.h" CONTENT
"#pragma once
#define GFGLOCK_VERSION_BINARY ${PROJECT_VERSION_MAJOR},${PROJECT_VERSION_MINOR},${PROJECT_VERSION_PATCH},0
#define GFGLOCK_VERSION_TEXT \"${PROJECT_VERSION}\"
")

add_library(gfglock_shell SHARED src/shell_extension.cpp src/gfglock_shell.def src/gfglock_shell.rc)

# Explorer loads this DLL into its own process and no installer ships the VC++ runtime next to
# it, so it links the CRT statically and depends on system DLLs only (CMP0091 is NEW under 3.25).
set_target_properties(gfglock_shell PROPERTIES
    CXX_STANDARD 17
    CXX_STANDARD_REQUIRED ON
    PREFIX ""
    SUFFIX ".dll"
    MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>"
)

target_include_directories(gfglock_shell PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/generated")
target_link_libraries(gfglock_shell PRIVATE ole32 shell32 uuid)

set(_SHELL_OUT_DIR "${PROJECT_SOURCE_DIR}/../build/shell")

foreach(_CONFIG Debug Release RelWithDebInfo MinSizeRel)
    set_target_properties(gfglock_shell PROPERTIES
        "RUNTIME_OUTPUT_DIRECTORY_${_CONFIG}" "${_SHELL_OUT_DIR}"
    )
endforeach()
set_target_properties(gfglock_shell PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${_SHELL_OUT_DIR}"
)

# VS multi-config generators still append the config sub-folder, so copy the
# final DLL to the flat _SHELL_OUT_DIR explicitly (mirrors gfglock_native).
add_custom_command(TARGET gfglock_shell POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        "$<TARGET_FILE:gfglock_shell>"
        "${_SHELL_OUT_DIR}/gfglock_shell.dll"
)
