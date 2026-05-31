module;

// Global module fragment area
// Put #include directives here 

module Figures;

import :Rectangle;

int Rectangle::area() const
{
	return width() * height();
}

int Rectangle::width() const
{
	return lr.x - ul.x;
}

int Rectangle::height() const
{
	return ul.y - lr.y;
}