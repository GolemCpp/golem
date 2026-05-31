export module Figures:Rectangle; // Defines the module partition Rectangle

import :Point;

export struct Rectangle // Make this struct visible to importers
{
    Point ul, lr;

	int area() const;
	int width() const;
	int height() const;
};
