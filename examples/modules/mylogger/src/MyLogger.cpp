#include "MyLogger.h"

#include <print>
#include <string>

void MyLogger::info(const std::string& message)
{
	std::println("[INFO] {}", message);
}