module;

#include "../api.h"

export module golemcpp.examples.modules.myfigures.Figures:Rectangle;

import :Point;

export namespace golemcpp::examples::modules::myfigures::Figures
{
	struct MYFIGURES_API Rectangle // Make this struct visible to importers
	{
		Point ul, lr;

		int area() const;
		int width() const;
		int height() const;
	};
}