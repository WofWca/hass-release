from .const import GITHUB_ORGANIZATION_NAME
from threading import Thread
import requests
from .const import TOKEN_FILE
import sys


# GitHub API endpoint address
ENDPOINT = 'https://api.github.com'
# GitHub API response header keys corresponding to GitHub API rate limits.
RATELIMIT_REMAINING_STR = 'x-ratelimit-remaining'
RATELIMIT_STR = 'x-ratelimit-limit'

# Additional headers for API requests.  For each request they're the same
# and contain the authorizations token
headers = None


class ContributorData:
    def __init__(self, name):
        self.name = name
        self.num_contributions = 0


def __process_contributors(repo: dict,
                           contributors_data_dict: dict):
    """
    Calculates the number of contributions made to the repository by each user
    :param repo: The repository to which contributions were made.
    :param contributors_data_dict: An assumingly empty dictionary to which
    the resulting data needs to be output.  Has the following structure:
    {
        <user_login>: <ContributorData class instance>
        ...
    }
    :return:
    """
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
    #
    # If there is a lot of contributors to this  repository, we're gonna
    # have to do several requests.  So we need a do-while loop again.
    next_contributors_page = repo['contributors_url'] + '?anon=true'
    while True:
        contributors_response = requests.get(url=next_contributors_page,
                                             headers=headers)
        contributors = contributors_response.json()
        for contributor in contributors:
            if contributor['type'] == 'User':
                # A non-anonymous contributor entry can only be seen once in
                # one repository, there's no need to check if the user is
                # already in the dictionary.
                # Get the user's name, if he has one.  Else use login.
                # Contributor entry does not contain such data. Accessing
                # user profile.
                user_response = requests.get(url=contributor['url'],
                                             headers=headers)
                user = user_response.json()
                contributor_name = user['name'] or user['login']
                # Initialize contributor's data structure.
                contributor_data = ContributorData(contributor_name)
                contributor_data.num_contributions = contributor[
                    'contributions']
                # Associate the contributor's login with it.
                contributors_data_dict[contributor['login']] = contributor_data
            # If the contributor's data is anonymous (we only know his
            # email, name, and the number of contributions he made).
            else:
                # Gotta find a commit authored by this email's user and extract
                # his login from it.
                # repo['commits_url'] ends with '/commits{/sha}'.  Removing
                # the last 6.
                commits_url = repo['commits_url'][:-6]
                commits_response = requests.get(
                    url=commits_url,
                    params={
                        'author': contributor['email'],
                        'per_page': 1
                    },
                    headers=headers)
                commit = commits_response.json()[0]
                contributor_login = commit['author']['login']
                # We can also get the user's name right from a commit.
                contributor_name = commit['commit']['author']['name']
                # As was said, if the user has committed to the repository
                # using several emails, he may have already been meet in the
                # list either in form of an anonymous or non-anonymous
                # contributor.
                #
                # Check whether the user's already listed.
                contributor_data = contributors_data_dict.get(
                    contributor_login)
                # If he's not
                if contributor_data is None:
                    # Initialize contributor's data structure.
                    contributor_data = ContributorData(contributor_name)
                    contributor_data.num_contributions = contributor[
                        'contributions']
                    # Associate the contributor's login with it.
                    contributors_data_dict[
                        contributor_login] = contributor_data
                # We've found an anonymous contributor entry that belongs to an
                # already listed non-anonymous contributor.
                else:
                    # Incrementing his contributions counter.
                    contributors_data_dict[
                        contributor_login].num_contributions += \
                        contributor['contributions']
        # 'None'  will be returned if there is no next page.
        next_contributors_page = contributors_response.links.get('next')
        # Stop if there is no more pages left.
        if next_contributors_page is None:
            break
    print('Done processing contributors for' + repo['name'] + 'repository')


def generate_credits():
    # Authenticate to GitHub. It is possible to receive required data as an
    # anonymous user.
    try:
        with open(TOKEN_FILE) as token_file:
            token = token_file.readline().strip()
        headers = {
            'Authorization': 'token ' + token
        }
        repos_response = requests.get(
            url=ENDPOINT,
            headers=headers)
        print('Authentication status: ' + repos_response.reason)
        if repos_response.status_code != 200:
            print('Authentication failed, proceeding anonymously')
    except OSError:
        sys.stderr.write('Could not open the .token file')
        print('Retrieving the data anonymously')
    # A dictionary that contains the data we're trying to get.  Has the
    # following structure:
    # {
    #     <repository_name>: {
    #         <user_login>: <ContributorData class instance>
    #         ...
    #     }
    #     ...
    # }
    credits_dict = {}
    # A dictionary holding threads.  Each thread processes one repository.
    repo_threads = {}
    # Now we're gonna request the list of the repositories.  It may be
    # paginated, so we use a loop.
    # Pre-loop initialization.
    next_repos_page_url = ENDPOINT + '/orgs/' + GITHUB_ORGANIZATION_NAME + \
                      '/repos' + '?type=public'
    # A do-while loop.
    while True:
        # Request a repositories list page
        repos_response = requests.get(url=next_repos_page_url, headers=headers)
        print('Rate limit: ' + repos_response.headers[RATELIMIT_REMAINING_STR] +
              '/' + repos_response.headers[RATELIMIT_STR])
        repos = repos_response.json()
        for repo in repos:
            # Create a new entry in the resulting dict for the current repo.
            curr_repo_dict = {}
            credits_dict[repo['name']] = curr_repo_dict
            # Create a new thread, write it to the threads dict and start it.
            curr_thread = Thread(target=__process_contributors,
                                 args=(repo, curr_repo_dict))
            repo_threads[repo['name']] = curr_thread
            curr_thread.start()
        # 'None'  will be returned if there is no next page.
        next_repos_page_url = repos_response.links.get('next')
        # Stop if there is no more pages left.
        if next_repos_page_url is None:
            break
    for repo_thread in repo_threads:
        repo_thread.join()
    1+1
