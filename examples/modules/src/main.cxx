#include <cstdlib>

import std;

import Greetings;
import Media;
import Figures;

int main()
{
	std::println("=> Greetings");
	Greetings::hello();

	std::println("=> Player");
	auto player = Player("Test");
	std::println("Player: {}", player.getName());

	std::println("=> Figures");
    auto r = Rectangle { {1,8}, {11,3} };
	std::println("Upper Left: ({}, {})", r.ul.x, r.ul.y);
	std::println("Lower Right: ({}, {})", r.lr.x, r.lr.y);
    std::println("Rectangle Area: {}", r.area());
    std::println("Rectangle Width: {}", r.width());

	return EXIT_SUCCESS;
}