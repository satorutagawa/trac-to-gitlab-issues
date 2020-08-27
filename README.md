# trac-to-gitlab-issues

This is based on work by [Stefan Vigerske](https://www.gams.com/~svigerske/svn2git/index.html) in 2018, which in turn is based on [trac-to-gitlab](https://github.com/moimael/trac-to-gitlab). 
It retrieves trac tickets via xmlrpc, then writes to gitlab via API v4.

Copying over of the code repository (svn -> git) is commented out as I did not need it, but it will probably work if you just uncomment it...

The assumption in the previous work was that the user had admin rights to gitlab.
But with some small changes, I was able to get it to work.
While it wasn’t all that hard, I don’t think it's worth wasting anyone else’s time to figure this out, so hence this repo.

## Assumptions
* xmlrpc can be used for trac
* User (non-admin) access to gitlab
* All user accounts are already created on gitlab
* Gitlab Access Token for each users can be retrieved

## How to run
1. cp example/migrate.cfg.example migrate.cfg
2. Edit migrate.cfg
 * Fill in usernames
 ```
 usernames = {
    'trac1': 'git_user1',
    'trac2': 'git_user2'
    }
 ```
 * Fill in user_ids
 ```
user_ids = {
    ‘git_user1’: 47,
    ‘git_user2’: 96
}
```
 * Fill in impers_tokens
 ```
impers_tokens = {
    47: ‘<access token for user1>’,
    96: ‘<access token for user2>'
}
```
 * Any other changes as required
3. python2 migrate.py
 * Took about 4 hours for 1100 tickets
4. Ask gitlab users to delete Access Tokens

## Set-backs caused by not having admin access
1. Getting User ID
    * gitlab_api/Connection.py::get_user_id()
2. Token Impersonation
    * gitlab_api/Connection.py::get_user_imperstoken()

## Getting User ID
get_user_id() assumed that all users could be retrieved via a GET request to /users. While this seems to work for admins, this doesn’t work for normal users (api doc).

### The easy way
 * simply ask each Gitlab user to look up their User ID on their settings page.

### The dumb way
The work around I found to retrieve User ID was the following:
1. Find Project ID (on project web page)
2. Create a dummy issue
3. Assign all necessary gitlab users to the issue
4. GET request for issue info
    ```
    curl --header "Authorization: Bearer <access-token>" "https://gitlab.example.com/api/v4/projects/<project_id>/issues/<issue #>/"
    ```

### Set user_ids in migrate.cfg
Once you know everyone’s User ID, write this on the migrate.cfg.
```
user_ids = {
    ‘git_user1’: 47,
    ‘git_user2’: 96
}
```

## Token Impersonation

### Why Impersonation Tokens are required
This is to keep track of who opened/closed/commented/assigned/etc the Issue. 
The alternative, of course, is simply for you to take credit for all the trac tickets… But I’m assuming you don’t want that...

### How to create Access Tokens
 * https://docs.gitlab.com/ee/user/profile/personal_access_tokens.html
 * This has to done for each gitlab user

### Set impers_tokens in migrate.cfg
```
impers_tokens = {
    47: ‘<access token for user1>’,
    96: ‘<access token for user2>'
}
```
