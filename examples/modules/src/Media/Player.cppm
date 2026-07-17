export module golemcpp.examples.modules.hello_modules.Media.Player;

export import std;

export namespace golemcpp::examples::modules::hello_modules::Media
{
	class Player
	{
	public:
		Player() = default;

		void play(const std::string& name) const;

	private:
	};
}