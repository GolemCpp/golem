module Media;

Player::Player(const std::string& name)
	: m_name(name)
{ }

void Player::sayHello() const
{
	std::cout << "Hello there! I am " << m_name;
}

std::string Player::getName() const
{
	return m_name;
}