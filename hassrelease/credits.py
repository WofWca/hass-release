from .const import GITHUB_ORGANIZATION_NAME
from threading import Thread
import requests
from .const import TOKEN_FILE
import sys
from queue import Queue

# GitHub API endpoint address
ENDPOINT = 'https://api.github.com'
# GitHub API response header keys corresponding to GitHub API rate limits.
RATELIMIT_REMAINING_STR = 'x-ratelimit-remaining'
RATELIMIT_STR = 'x-ratelimit-limit'

# Additional headers for API requests.  For each request they're the same
# and contain the authorizations token. The token will be
# added later. It may not be added, the program will still proceed.
headers = None


class ContributorData:
    def __init__(self, login=None, name=None, num_contributions=0):
        self.login = login
        self.name = name
        self.num_contributions = num_contributions


def assign_contributor_name(
        contributor_record: ContributorData, contributor_profile_url: str):
    """
    Obtains a contributor's name from GitHub and writes it to an existing local
    contributor record.
    :param contributor_record: Whose name needs to be known.
    :param contributor_profile_url: Where to get the name from.
    :return:
    """
    user_response = requests.get(url=contributor_profile_url,
                                 headers=headers)
    user = user_response.json()
    # If the user has not specified the name, use his login
    contributor_record.name = user['name'] or user['login']


def resolve_anon_and_push_to_queue(repo: dict,
                                   contributor: dict,
                                   queue: Queue,
                                   ):
    """
    Resolves an anonymous contributor entry to a ContributorData class instance
    and pushes it to a specified queue by accessing GitHub API.
    :param contributor: The anonymous contributor that needs to be resolved
    :param queue: The queue where resolved users need to be put.
    :param repo: The repo to which the contributor contributed.
    :return:
    """
    # We can find a commit authored by this email's user and
    # extract his login from it, if it is there.  Otherwise this
    # email is not linked to any GitHub account.  There's also
    # an option to find an account by the user name (not login).
    # But names are not unique.

    # repo['commits_url'] ends with '/commits{/sha}'.  Removing
    # the last 6.
    commits_url = repo['commits_url'][:-6]
    # Remember, we only need one commit.
    commits_response = requests.get(
        url=commits_url,
        params={
            'author': contributor['email'],
            'per_page': 1
        },
        headers=headers)
    commit = commits_response.json()[0]
    # Check whether the email is linked to a GitHub profile.
    if commit['author'] is not None:
        contributor_login = commit['author']['login']
        # We can also get the user's name right from a commit.
        contributor_name = commit['commit']['author']['name']
        # Add the resolved user to the queue.
        print('put to q')
        queue.put(ContributorData(
            login=contributor_login,
            name=contributor_name,
            num_contributions=contributor['contributions']))
    # This contributor is not linked to any GitHub account.
    # else:


def process_contributors(repo: dict,
                         contributors_data_dict: dict):
    """
    Calculates the number of contributions made to the specified repository by
    each user.
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
    # A dictionary containing threads. Each thread obtains a
    # non-anonymous user's name (not login) by accessing the API.
    non_anon_user_threads = {}
    # A dict that holds threads which are responsible for resolving
    # anonymous entries to ContributorData class instances.
    anon_user_threads = {}
    # A queue that hold ContributorData class instances that were given by
    # GitHub as anonymous contributor entries.
    anon_queue = Queue()
    while True:
        contributors_response = requests.get(url=next_contributors_page,
                                             params={
                                                 'per_page': 100
                                             },
                                             headers=headers)
        contributors = contributors_response.json()
        for contributor in contributors:
            if contributor['type'] == 'User':
                print(contributor['login'] + ': ' + str(contributor[
                    'contributions']))
                # A non-anonymous contributor entry can only be seen once in
                # one repository, there's no need to check if the user is
                # already in the dictionary.

                # Add a new contributor's data structure to the dict.
                contributor_record = ContributorData(
                    login=contributor['login'],
                    num_contributions=contributor['contributions'])
                contributors_data_dict[contributor['login']] = \
                    contributor_record
                # User's name is not provided in contributor data entry.
                # We need to access GitHub user profile. Let's not wait and
                # give this job to another thread. He'll do fine, don't worry.
                user_thread = Thread(target=assign_contributor_name,
                                     args=(
                                         contributor_record,
                                         contributor['url']
                                     )
                                     )
                """assign_contributor_name(contributor_record, contributor['url'])"""
                user_thread.start()
                non_anon_user_threads[contributor['login']] = user_thread
            # If the contributor's data is anonymous (we only know his
            # email, name, and the number of contributions he made).
            else:
                print(contributor['email'] + ': ' + str(contributor[
                    'contributions']))
                # Gonna let another thread get de-anonymize them, and then
                # put to a queue. We'll get back to them later.
                anon_user_thread = Thread(
                    target=resolve_anon_and_push_to_queue,
                    args=(
                         repo,
                         contributor,
                         anon_queue
                     ))
                """resolve_anon_and_push_to_queue(repo, contributor, anon_queue)"""
                anon_user_thread.start()
                anon_user_threads[contributor['email']] = anon_user_thread
        # 'None'  will be returned if there is no next page.
        next_contributors_page_dict = contributors_response.links.get('next')
        # Stop if there is no more pages left.
        if next_contributors_page_dict is None:
            break
        else:
            next_contributors_page = next_contributors_page_dict['url']
        print(repo['name'] + ' thread: ' + str(len(non_anon_user_threads)) +
              'nested threads created')
        print(repo['name'] + ' thread: ' + str(len(contributors_data_dict)) +
              ' contributor entries currently')
    # Initially-anonymous contributors are awaiting in the anon_queue.
    # And threads assigned to them too.
    for anon_user_thread in anon_user_threads.values():
        anon_user_thread.join()
    print(anon_queue.qsize())
    # As was said, if the user has committed to the repository
    # using several emails, he may have already been meet in
    # the list either in form of an anonymous or non-anonymous
    # contributor.
    # Check whether the user's already listed.


    for user_thread in non_anon_user_threads.values():
        user_thread.join()
    print('Done processing contributors for' + repo['name'] + 'repository')


def generate_credits():
    # Authenticate to GitHub. It is possible to receive required data as an
    # anonymous user.
    try:
        with open(TOKEN_FILE) as token_file:
            token = token_file.readline().strip()
        global headers
        headers = {
            'Authorization': 'token ' + token
        }
        repos_response = requests.get(
            url=ENDPOINT,
            params={
                'per_page': 100
            },
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
        repos_response = requests.get(url=next_repos_page_url,
                                      params={
                                          'per_page': 100
                                      },
                                      headers=headers)
        print('Rate limit: ' + repos_response.headers[RATELIMIT_REMAINING_STR] +
              '/' + repos_response.headers[RATELIMIT_STR])
        repos = repos_response.json()
        for repo in repos:
            # Create a new entry in the resulting dict for the current repo.
            curr_repo_dict = {}
            credits_dict[repo['name']] = curr_repo_dict
            # Create a new thread, write it to the threads dict and start it.
            curr_thread = Thread(target=process_contributors,
                                 args=(repo, curr_repo_dict))


            """
            curr_thread.start()
            """
            process_contributors(repo, curr_repo_dict)
            #
            #
            #

            repo_threads[repo['name']] = curr_thread


        # 'None'  will be returned if there is no next page.
        next_repos_page_dict = repos_response.links.get('next')
        # Stop if there is no more pages left.
        if next_repos_page_dict is None:
            break
        else:
            next_repos_page_url = next_repos_page_dict['url']
    for repo_thread in repo_threads.values():
        repo_thread.join()
    1+1
