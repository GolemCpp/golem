import std;

import golemcpp.examples.modules.hello_modules;
using namespace golemcpp::examples::modules::hello_modules;

import golemcpp.examples.modules.myfigures;
using namespace golemcpp::examples::modules::myfigures;

import golemcpp.examples.modules.mylogger;
using namespace golemcpp::examples::modules::mylogger;

int main()
{
    std::println("=> hello_modules/Greetings");
    Greetings::hello();

    std::println("=> hello_modules/Media");
    auto player = Media::Player();
    player.play("Test");

    std::println("=> myfigures/Figures");
    auto rectangle = Figures::Rectangle { {1,8}, {11,3} };
    std::println("Rectangle Area: {}", rectangle.area());
    std::println("Rectangle Width: {}", rectangle.width());

    std::println("=> mylogger/MyLogger");
    MyLogger::info("This is an info message");
    std::println("Caller: {}", MyLogger::getCaller());

    return 0;
}