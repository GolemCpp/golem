#pragma once

#if defined(_WIN32) || defined(__CYGWIN__)
#define MYFIGURES_HELPER_EXPORT __declspec(dllexport)
#define MYFIGURES_HELPER_IMPORT __declspec(dllimport)
#define MYFIGURES_HELPER_LOCAL
#elif defined(__GNUC__) && __GNUC__ >= 4 || defined(__clang__)
#define MYFIGURES_HELPER_EXPORT __attribute__((visibility("default")))
#define MYFIGURES_HELPER_IMPORT __attribute__((visibility("default")))
#define MYFIGURES_HELPER_LOCAL __attribute__((visibility("hidden")))
#else
#define MYFIGURES_HELPER_EXPORT
#define MYFIGURES_HELPER_IMPORT
#define MYFIGURES_HELPER_LOCAL
#endif

#if defined(MYFIGURES_API_EXPORT)
// Building the shared library
#define MYFIGURES_API MYFIGURES_HELPER_EXPORT
#define MYFIGURES_LOCAL MYFIGURES_HELPER_LOCAL
#elif defined(MYFIGURES_API_IMPORT)
// Consuming the shared library
#define MYFIGURES_API MYFIGURES_HELPER_IMPORT
#define MYFIGURES_LOCAL MYFIGURES_HELPER_LOCAL
#else
// Static library
#define MYFIGURES_API
#define MYFIGURES_LOCAL
#endif