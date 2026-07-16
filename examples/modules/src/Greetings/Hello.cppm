export module golemcpp.examples.modules.hello_modules.Greetings.Hello;

import std;

export namespace golemcpp::examples::modules::hello_modules::Greetings
{
    void hello()
    {
        std::println("Hello");
    }
}