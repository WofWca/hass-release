from hassrelease.users import resolve_login


def test_resolve_users_from_github_email():
    users = {}
    assert resolve_login(users, '1000+bla@users.noreply.github.com')
    assert users == {'1000+bla@users.noreply.github.com': 'bla'}
