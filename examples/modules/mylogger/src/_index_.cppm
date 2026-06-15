module;

#include <mylogger/MyLogger.h>

export module golemcpp.examples.modules.mylogger;

// import std; // TODO: CRC mistmatch needs to be solved

export namespace golemcpp::examples::modules::mylogger
{
	using ::MyLogger;
}