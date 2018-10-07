from .github import get_session
from .const import GITHUB_ORGANIZATION_NAME
from threading import Thread
from collections import defaultdict
from github3 import structs


def __process_contributors(repository: structs.GitHubIterator,
                           num_contributions_dict: defaultdict):
    """
    Calculates the number of contributions made to the repository by each user
    :param repository: The repository to which contributions were made.
    :param num_contributions_dict: An assumingly empty dictionary to which
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
        # If the contributor's data is not anonymous (we know his login)
        if contributor.type == 'User':
            num_contributions_dict[contributor.login] +=\
                contributor.contributions
        # If the contributor's data is anonymous (we only know his email and
        # his name.
        else:
            # Gotta count commits authored by this email's user and get the
            # user data by that commit.
            repository.




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
    #         <user_login>: <number_of_contributions_by_this_user_to_this_repo>
    #         ...
    #     }
    #     ...
    # }
    credits_dict = {}
    for repo in repos:
        # The dictionary associated to the current repo. Associates users
        # with the number of contributions they made to this repo.
        curr_repo_num_contributions_dict = defaultdict(int)
        credits_dict[repo.name] = curr_repo_num_contributions_dict
        repo_threads[repo.name] = Thread(
            target=__process_contributors,
            args=(repo, curr_repo_num_contributions_dict)
        )
        repo_threads[repo.name].start()
    for repo_thread in repo_threads:
        repo_thread.join()
