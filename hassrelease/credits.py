from .github import get_session
from .const import GITHUB_ORGANIZATION_NAME
from threading import Thread
from collections import defaultdict
from github3 import GitHub
from github3.repos.repo import Repository


class ContributorData:
    def __init__(self, name):
        self.name = name
        self.num_contributions = 0


def __process_contributors(gh: GitHub,
                           repository: Repository,
                           contributors_data_dict: defaultdict):
    """
    Calculates the number of contributions made to the repository by each user
    :param gh: A GitHub session.
    :param repository: The repository to which contributions were made.
    :param contributors_data_dict: An assumingly empty dictionary to which
    the resulting data needs to be output.
    :return:
    """
    contributors = repository.contributors(anon=True)
    # According to https://developer.github.com/v3/repos/#list-contributors,
    # "GitHub identifies contributors by author email address" and "only the
    # first 500 author email addresses in the repository link to GitHub
    # users. The rest will appear as anonymous contributors without
    # associated GitHub user information".
    #
    # This means that we'll have to manually associate anonymous contributor
    # entries with their GitHub accounts by email by searching commits.
    #
    # This also means that if the user has contributed to the repository using
    # several emails, the 'contributions' field of the retrieved
    # non-anonymous user entry may not display the actual number of
    # contributions this user made, and further in the list we may
    # find anonymous entries, which must be also associated with this user.
    for contributor in contributors:
        if contributor.type == 'User':
            # A non-anonymous contributor entry can only be seen once in one
            # repository, there's no need to check if the user is already in
            # the dictionary.
            # Get the user's name, if he has one.  Else use login.
            contributor_name = gh.user(contributor.login).name or \
                               contributor.login
            # Initialize contributor's data structure.
            contributor_data = ContributorData(contributor_name)
            contributor_data.num_contributions = contributor.contributions
            # Associate the contributor's login with it.
            contributors_data_dict[contributor.login] = contributor_data
        # If the contributor's data is anonymous (we only know his email, name,
        # and the number of contributions he made).
        else:
            # Gotta find a commit authored by this email's user and extract
            # his login from it.
            commit = next(repository.commits(author=contributor.email,
                                             number=1))
            contributor_login = commit.author.login
            # We can also get the user's name right from a commit.
            contributor_name = commit.commit.author['name']
            # As was said, if the user has committed to the repository using
            # several emails, he may have already been seen.
            # Obtain the data associated with this login, if there is any.
            contributor_data = contributors_data_dict[contributor_login]
            # If there is none
            if contributor_data is None:
                # Initialize contributor's data structure.
                contributor_data = ContributorData(contributor_name)
                contributor_data.num_contributions = contributor.contributions
                # Associate the contributor's login with it.
                contributors_data_dict[contributor_login] = contributor_data
            # We've found an anonymous contributor entry that belongs to an
            # already listed non-anonymous contributor.
            else:
                # Incrementing his contributions counter.
                contributors_data_dict[contributor_login].num_contributions +=\
                    contributor.contributions


def generate_credits():
    gh = get_session()
    org = gh.organization(GITHUB_ORGANIZATION_NAME)
    # One thread for each repository.
    repo_threads = {}
    repos = org.repositories(type='public')
    """
    for repo in repos:
        for cont in repo.contributors(anon=True):
            print(cont)
    """
    # A dictionary with the following structure:
    # {
    #     <repository_name>: {
    #         <user_login>: <ContributorData instance>
    #         ...
    #     }
    #     ...
    # }
    credits_dict = {}
    for repo in repos:
        # The dictionary associated to the current repo. Associates users
        # with the number of contributions they made to this repo.
        curr_repo_contributors_data_dict = {}
        credits_dict[repo.name] = curr_repo_contributors_data_dict
        repo_threads[repo.name] = Thread(
            target=__process_contributors,
            args=(gh, repo, curr_repo_contributors_data_dict)
        )
        repo_threads[repo.name].start()
    for repo_thread in repo_threads:
        repo_thread.join(100)
    1+1
