class ConditionExpression:
    @staticmethod
    def clean(expression):
        expression = expression.lower()
        expression = expression.replace(' ', '')
        return expression

    @staticmethod
    def parse_conditions(expression):
        expression = ConditionExpression.clean(expression)
        if expression and expression[0] == '?':
            return expression[1:].split('+')
        return []

    @staticmethod
    def parse_members(expression):
        expression = ConditionExpression.clean(expression)
        if expression:
            return expression.split('+')
        return []

    @staticmethod
    def remove_modifiers(expression):
        return expression.replace('!', '')

    @staticmethod
    def has_negation(expression):
        expression = ConditionExpression.clean(expression)
        if expression:
            return expression[0] == '!'
        return False
