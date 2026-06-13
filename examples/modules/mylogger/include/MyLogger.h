#pragma once

#include "api.h"

#include <string>

class MYLOGGER_API MyLogger
{
public:
	MyLogger() = default;

	static void info(const std::string& message);
};