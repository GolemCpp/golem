module golemcpp.examples.modules.myfigures.Figures;

import :Rectangle;

import golemcpp.examples.modules.mylogger;
using namespace golemcpp::examples::modules::mylogger;

namespace golemcpp::examples::modules::myfigures::Figures
{
    int Rectangle::area() const
    {
        MyLogger::info("Rectangle::area() called");
        return width() * height();
    }

    int Rectangle::width() const
    {
        MyLogger::info("Rectangle::width() called");
        return lr.x - ul.x;
    }

    int Rectangle::height() const
    {
        MyLogger::info("Rectangle::height() called");
        return ul.y - lr.y;
    }
}