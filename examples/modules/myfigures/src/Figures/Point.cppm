module;

#include "../api.h"

export module golemcpp.examples.modules.myfigures.Figures:Point;

export namespace golemcpp::examples::modules::myfigures::Figures
{
    struct MYFIGURES_API Point
    {
        int x, y;
    };
}