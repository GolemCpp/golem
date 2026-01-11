#pragma once

#if defined(_WIN32)
    #if defined(FOO_API_EXPORT)
        #define FOO_API __declspec(dllexport)
    #elif defined(FOO_API_IMPORT)
        #define FOO_API __declspec(dllimport)
    #endif
#endif