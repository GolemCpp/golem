from golemcpp.golem.condition_expression import ConditionExpression


def test_clean_normalizes_case_and_whitespace():
    assert ConditionExpression.clean(' Foo + Bar ') == 'foo+bar'


def test_parse_conditions_returns_conditions_when_prefixed_with_question_mark():
    assert ConditionExpression.parse_conditions('? Foo + Bar ') == ['foo', 'bar']


def test_parse_conditions_returns_empty_list_without_question_mark():
    assert ConditionExpression.parse_conditions(' Foo + Bar ') == []


def test_parse_members_returns_normalized_members():
    assert ConditionExpression.parse_members(' Foo + Bar ') == ['foo', 'bar']


def test_parse_members_returns_empty_list_for_empty_expression():
    assert ConditionExpression.parse_members('') == []


def test_remove_modifiers_removes_negation_markers():
    assert ConditionExpression.remove_modifiers('!foo+!bar') == 'foo+bar'


def test_has_negation_detects_negated_expression():
    assert ConditionExpression.has_negation(' !Foo ') is True


def test_has_negation_returns_false_for_empty_expression():
    assert ConditionExpression.has_negation('') is False