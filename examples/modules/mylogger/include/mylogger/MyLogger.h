#pragma once

#include "api.h"

#include <string>

class MYLOGGER_API MyLogger
{
public:
    MyLogger() = default;

	static std::string getCaller()
	{
		return MYLOGGER_CALLER;
	}

	static void info(const std::string& message);
};