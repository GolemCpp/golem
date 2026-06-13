module golemcpp.examples.modules.myfigures.Figures;

import :Rectangle;

namespace golemcpp::examples::modules::myfigures::Figures
{
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
}