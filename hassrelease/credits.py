from .github import get_session
from .const import GITHUB_ORGANIZATION_NAME


def generate_credits():
    gh = get_session()
    org = gh.organization(GITHUB_ORGANIZATION_NAME)
    for repo in org.repositories(type='public'):
        for contributor in repo.contributors(anon=True):
            print(contributor.login + '\t' + str(contributor.contributions))
        print(repo.ratelimit_remaining)
