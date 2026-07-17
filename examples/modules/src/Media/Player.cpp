module golemcpp.examples.modules.hello_modules.Media.Player;

namespace golemcpp::examples::modules::hello_modules::Media
{
    void Player::play(const std::string &name) const
    {
        std::println("Playing: {}", name);
    }
}