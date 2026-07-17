import std;

import golemcpp.examples.modules.hello_modules;
using namespace golemcpp::examples::modules::hello_modules;

import golemcpp.examples.modules.myfigures;
using namespace golemcpp::examples::modules::myfigures;

import golemcpp.examples.modules.mylogger;
using namespace golemcpp::examples::modules::mylogger;

int main()
{
    std::println("=> mylogger/MyLogger");
    MyLogger::info("This is an info message");

    // MSVC 14.51.36231 returns "Caller: mylogger" instead of "Caller: consumer"
    // Likely to be a bug
    std::println("Caller: {}", MyLogger::getCaller());

    std::println("=> myfigures/Figures");
    auto rectangle = Figures::Rectangle{{1, 8}, {11, 3}};
    std::println("Rectangle Area: {}", rectangle.area());
    std::println("Rectangle Width: {}", rectangle.width());

    std::println("=> hello_modules/Greetings");
    Greetings::hello();

    std::println("=> hello_modules/Media");
    auto player = Media::Player();
    player.play("Test");

    return 0;
}