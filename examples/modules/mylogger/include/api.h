#pragma once

#if defined(_WIN32) || defined(__CYGWIN__)
#define MYLOGGER_HELPER_EXPORT __declspec(dllexport)
#define MYLOGGER_HELPER_IMPORT __declspec(dllimport)
#define MYLOGGER_HELPER_LOCAL
#elif defined(__GNUC__) && __GNUC__ >= 4 || defined(__clang__)
#define MYLOGGER_HELPER_EXPORT __attribute__((visibility("default")))
#define MYLOGGER_HELPER_IMPORT __attribute__((visibility("default")))
#define MYLOGGER_HELPER_LOCAL __attribute__((visibility("hidden")))
#else
#define MYLOGGER_HELPER_EXPORT
#define MYLOGGER_HELPER_IMPORT
#define MYLOGGER_HELPER_LOCAL
#endif

#if defined(MYLOGGER_API_EXPORT)
// Building the shared library
#define MYLOGGER_API MYLOGGER_HELPER_EXPORT
#define MYLOGGER_LOCAL MYLOGGER_HELPER_LOCAL
#elif defined(MYLOGGER_API_IMPORT)
// Consuming the shared library
#define MYLOGGER_API MYLOGGER_HELPER_IMPORT
#define MYLOGGER_LOCAL MYLOGGER_HELPER_LOCAL
#else
// Static library
#define MYLOGGER_API
#define MYLOGGER_LOCAL
#endif
