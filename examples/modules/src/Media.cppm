export module Media;

import std;

export class Player
{
public:
	Player(const std::string& name);

	void sayHello() const;

	std::string getName() const;

private:
	std::string m_name;
};