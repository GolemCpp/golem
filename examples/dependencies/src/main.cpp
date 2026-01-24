#include <iostream>

#include <nlohmann/json.hpp>

struct vector3d
{
	int x { };
	int y { };
	int z { };

	NLOHMANN_DEFINE_TYPE_INTRUSIVE(vector3d, x, y, z);
};

int main()
{
	vector3d vec { 1, 2, 3 };

	std::cout << nlohmann::json(vec).dump(4) << std::endl;

	return 0;
}