# -*- coding: utf-8 -*-
'''
Copyright © 2013
    Stefan Vigerske <svigerske@gams.com>
This is a modified/extended version of trac-to-gitlab from https://github.com/moimael/trac-to-gitlab.
It has been adapted to fit the needs of a specific Trac to GitLab conversion.

Copyright © 2013 
    Eric van der Vlist <vdv@dyomedea.com>
    Jens Neuhalfen <http://www.neuhalfen.name/>
See license information at the bottom of this file
'''

#import json
import requests
import datetime
import hashlib
import time


# See http://code.activestate.com/recipes/52308-the-simple-but-handy-collector-of-a-bunch-of-named/?in=user-97991
class Bunch(object):

    def __init__(self, **kwds):
        self.__dict__.update(kwds)

    @staticmethod
    def create(dictionary):
        if not dictionary:
            return None
        bunch = Bunch()
        bunch.__dict__ = dictionary
        return bunch


class Issues(Bunch):
    pass


class Notes(Bunch):
    pass


class Milestones(Bunch):
    pass


class Wikis(Bunch):
    pass


class Connection(object):
    """
    Connection to the gitlab API
    """

    def __init__(self, url, access_token, ssl_verify, impers_tokens):
        """

        :param url: "https://gitlab.example.com/api/v4"
        :param access_token: "secretsecretsecret"
        """
        self.url = url
        self.access_token = access_token
        self.verify = ssl_verify
        self.impers_tokens = impers_tokens  #TODO would be nice to delete these tokens when finished
        self.user_ids = dict()  # username to user_id mapping
        self.uploaded_files = dict() # md5-hash to upload-file response (dict)
        self.addedlabels = set() # labels that were added already

    def _request_headers(self, keywords) :
        headers = dict()
        if 'token' in keywords :
            headers['PRIVATE-TOKEN'] = keywords['token']
        else :
            headers['PRIVATE-TOKEN'] = self.access_token
        return headers

    def _complete_url(self, url_postfix, keywords):
        """
        :param url_postfix:  "/projects/:id/issues"
        :param keywords:  map, e.g. { "id" : 5 }
        :return:  self.url + "/projects/5/issues"
        """

        # substitute ":key" by values
        result = url_postfix
        for key, value in keywords.items():
            result = result.replace(":" + str(key), str(value))

        return self.url + result

    def get(self, url_postfix, **keywords):
        return self._get(url_postfix, keywords)

    def _get(self, url_postfix, keywords):
        """
        :param url_postfix: e.g. "/projects/:id/issues"
        :param keywords:  map, e.g. { "id" : 5 }
        :return: json of GET
        """
        completed_url = self._complete_url(url_postfix, keywords)
        while True :
            r = requests.get(completed_url, verify = self.verify, headers = self._request_headers(keywords))
            if r.status_code < 500 :
                break
            time.sleep(2)
        if r.status_code >= 400 : print(r.text)
        r.raise_for_status()
        j = r.json() if r.status_code >= 200 and r.status_code < 300 else None

        # handle paginated return
        if keywords.get('paginate', True) and 'X-Total-Pages' in r.headers and r.headers['X-Total-Pages'] != '1':
            totalpages = int(r.headers['X-Total-Pages'])
            for page in range(2, totalpages + 1) :
                while True :
                    r = requests.get(completed_url, verify = self.verify, headers = self._request_headers(keywords), params = {'page' : page})
                    if r.status_code < 500 :
                        break
                    time.sleep(2)
                r.raise_for_status()
                assert r.status_code < 300
                j = j + r.json()

        return j

    def put(self, url_postfix, data, **keywords):
        completed_url = self._complete_url(url_postfix, keywords)
        while True :
            r = requests.put(completed_url, data = data, verify = self.verify, headers = self._request_headers(keywords))
            if r.status_code < 500 :
                break
            time.sleep(2)
        if r.status_code >= 400 : print(r.text)
        r.raise_for_status()
        j = r.json() if r.status_code >= 200 and r.status_code < 300 else None
        return j

    def post(self, url_postfix, data, **keywords):
        completed_url = self._complete_url(url_postfix, keywords)
        files = keywords['files'] if 'files' in keywords else None
        while True :
            r = requests.post(completed_url, data = data, verify = self.verify, headers = self._request_headers(keywords), files = files)
            if r.status_code < 500 :
                break
            time.sleep(2)
        if r.status_code >= 400 : print(r.text)
        r.raise_for_status()
        j = r.json() if r.status_code >= 200 and r.status_code < 300 else None
        return j

    def delete(self, url_postfix, **keywords) :
        completed_url = self._complete_url(url_postfix, keywords)
        while True :
            r = requests.delete(completed_url, verify = self.verify, headers = self._request_headers(keywords))
            if r.status_code < 500 :
                break
            time.sleep(2)
        if r.status_code >= 400 : print(r.text)
        r.raise_for_status()

    def milestone_by_name(self, project_id, milestone_name):
        milestones = self.get("/projects/:project_id/milestones", project_id = project_id)
        for milestone in milestones:
            if milestone['title'] == milestone_name:
                return milestone
        raise BaseException('Milestone %s not known' % milestone)

    def get_group_id(self, grouppath):
        groups = self.get("/groups")
        for group in groups:
            if group['path'] == grouppath:
                return group["id"]
        raise BaseException('Group with path %s not known' % grouppath)

    def get_user_id(self, username, create = False):
        if username in self.user_ids :
            return self.user_ids[username]
        users = self.get("/users")
        for user in users:
            if user['username'] == username:
                self.user_ids[username] = user["id"]
                return user["id"]
        raise BaseException("id not found for user %s" % username)
        if create :
            print 'Creating user', username
            userdata = {
                'email' : username + '@gams.com',
                'password' : 'secretsecret', #TODO put something useful here
                'username' : username,
                'name' : username,
                'skip_confirmation' : True,
                'admin' : True
            }
            r = self.post("/users", userdata);
            self.user_ids[username] = r['id']

            # add user to group 'devel'
            groupadddata = {
                'user_id' :  r['id'],
                'access_level' : 30  # developer access
            }
            self.post("/groups/:group_id/members", groupadddata, group_id = self.get_group_id('devel'))

            return r['id'];

    def get_user_imperstoken(self, userid) :
        if userid in self.impers_tokens :
            return self.impers_tokens[userid];
        raise BaseException("impers_token not found for %s" % userid)
#        data = {
#            'user_id' : userid,
#            'name' : 'trac2gitlab',
#            'expires_at' : datetime.date.today() + datetime.timedelta(days = 1),
#            'scopes[]' : 'api'
#            }
#        r = self.post('/users/:user_id/impersonation_tokens', data, user_id = userid)
#        self.impers_tokens[userid] = r['token'];
#        return r['token']

    def project_by_name(self, project_name):
        projects = self.get("/projects")
        for project in projects:
            if project['path_with_namespace'] == project_name:
                return project

    def clear_issues(self, dest_project_id) :
        # NOTE getting all pages in get doesn't work well here yet, cf https://gitlab.com/gitlab-org/gitlab-ce/issues/40407
        # -> delete issues for each first page and retrieve again
        while True :
            issues = self.get("/projects/:id/issues?scope=all", id = dest_project_id, paginate = False)
            if len(issues) == 0 : break
            for issue in issues :
                print 'delete issue', issue['id'], 'iid', issue['iid']
                self.delete("/projects/:id/issues/:issue_iid", id = dest_project_id, issue_iid = issue['iid'])

    def create_issue(self, dest_project_id, new_issue):
        if hasattr(new_issue, 'milestone'):
            new_issue.milestone_id = new_issue.milestone
        if hasattr(new_issue, 'assignee') and new_issue.assignee is not None:
            print(new_issue.assignee)
            new_issue.assignee_id = new_issue.assignee
            new_issue.assignee_ids = [new_issue.assignee]
        assert(hasattr(new_issue, 'reporter'))
        assert(new_issue.reporter is not None)
        token = self.get_user_imperstoken(new_issue.reporter)
        issue = self.post("/projects/:id/issues", new_issue.__dict__, id = dest_project_id, token = token)
        return Issues.create(issue)

    def create_milestone(self, dest_project_id, new_milestone):
        if hasattr(new_milestone, 'due_date'):
            new_milestone.due_date = new_milestone.due_date.isoformat()
        existing = Milestones.create(self.milestone_by_name(dest_project_id, new_milestone.title))
        if existing:
            new_milestone.id = existing.id
            return Milestones.create(self.put("/projects/:id/milestones/:milestone_id", new_milestone.__dict__, id = dest_project_id, milestone_id = existing.id))
        else:
            return Milestones.create(self.post("/projects/:id/milestones", new_milestone.__dict__, id = dest_project_id))

    def create_wiki(self, dest_project_id, content, title, author):
        token = self.get_user_imperstoken(author)
        new_wiki_data = {
            "id" : dest_project_id,
            "content" : content,
            "title" : title
        }
        self.post("/projects/:project_id/wikis", new_wiki_data, project_id = dest_project_id, token = token)

    def comment_issue(self, project_id, issue, note):
        assert(hasattr(note, 'author'))
        assert(note.author is not None)
        token = self.get_user_imperstoken(note.author)

        # upload attachement, if there is one
        if hasattr(note, 'attachment_name') :
            # ensure file name will be in ascii (otherwise gitlab complain)
            origname = note.attachment_name
            note.attachment_name = note.attachment_name.encode("ascii", "replace")

            r = self.upload_file(project_id, note.author, note.attachment_name, note.attachment)
            note.note = "Attachment added: " + r['markdown'] + '\n\n' + note.note

            if origname != note.attachment_name :
                note.note += '\nFilename changed during trac to gitlab conversion. Original filename: ' + origname

        new_note_data = {
            "body" : note.note if note.note != '' else ' ',
            "created_at" : note.created_at
        }
        self.post("/projects/:project_id/issues/:issue_iid/notes", new_note_data, project_id = project_id, issue_iid = issue.iid, token = token)

    def subscribe_issue(self, project_id, issue, person) :
        self.post("/projects/:project_id/issues/:issue_iid/subscribe", {}, project_id = project_id, issue_iid = issue.iid, token = self.get_user_imperstoken(person))

    def update_issue_property(self, project_id, issue, author, time, propertyname) :
        if propertyname == 'labels' :
            newvalue = ",".join(issue.labels)
        elif propertyname == 'assignee' :
            propertyname = 'assignee_ids'
            newvalue = [issue.assignee]
        elif propertyname == 'state' :
            propertyname = 'state_event'
            newvalue = 'close' if issue.state == 'closed' else 'reopen'
        else :
            newvalue = issue.__dict__[propertyname]

        data = {propertyname : newvalue}
        if time is not None : # NOTE updated_at seems to be ignored by gitlab (see issue #3)
           data["updated_at"] = time

        if author is not None :
           token = self.get_user_imperstoken(author)
        else :
           token = self.access_token

        self.put("/projects/:project_id/issues/:issue_iid", data, project_id = project_id, issue_iid = issue.iid, token = token)

    def upload_file(self, project_id, author, filename, filedata) :
        token = self.get_user_imperstoken(author)

        h = hashlib.md5(filename + filedata).hexdigest()
        if h in self.uploaded_files :
            print '  use previous upload of file', filename
            return self.uploaded_files[h]

        print '  upload file', filename
        r = self.post("/projects/:project_id/uploads", None, files = {'file' : (filename, filedata)}, project_id = project_id, token = token)
        self.uploaded_files[h] = r;
        return r

    def ensure_label(self, project_id, label, labelcolor) :
        if len(self.addedlabels) == 0 :
            # cannot add already existing labels, so if this is the first call, then get list of existing labels
            r = self.get("/projects/:project_id/labels", project_id = project_id)
            for entry in r :
                self.addedlabels.add(entry['name'])
        if label in self.addedlabels :
            # label already added, no need to do again
            return
        print '  creating label', label, 'with color', labelcolor
        self.post("/projects/:project_id/labels", {'name' : label, 'color' : labelcolor}, project_id = project_id)
        self.addedlabels.add(label)

'''
This file is part of <https://gitlab.dyomedea.com/vdv/trac-to-gitlab>.

This software is free software: you can redistribute it and/or modify
it under the terms of the GNU Lesser General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This software is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Lesser General Public License for more details.

You should have received a copy of the GNU Lesser General Public License
along with this library. If not, see <http://www.gnu.org/licenses/>.
'''
