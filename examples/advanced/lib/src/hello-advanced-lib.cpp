#include "hello-advanced-lib.h"

#include <iostream>

#define STRINGIFY_IMPL(x) #x
#define STRINGIFY(x) STRINGIFY_IMPL(x)

void hello_advanced_lib::print()
{
	std::cout << "Variant is: " << STRINGIFY(ADVANCED_LIB_VARIANT) << std::endl;
	std::cout << "Message is: " << STRINGIFY(ADVANCED_LIB_MESSAGE) << std::endl;
}