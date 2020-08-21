#!/usr/bin/env python2
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

import re
import os
import ConfigParser
import ast
from datetime import datetime
from re import MULTILINE
import xmlrpclib
from gitlab_api import Connection, Issues, Notes, Milestones

"""
What
=====

 This script migrates issues from trac to gitlab.

License
========

 License: http://www.wtfpl.net/

Requirements
==============

 * Python 2, xmlrpclib, requests
 * Trac with xmlrpc plugin enabled
 * GitLab

"""

default_config = {
    'ssl_verify': 'no',
    'migrate' : 'true',
    'overwrite' : 'true',
    'exclude_authors' : 'trac',
}

# 6-digit hex notation with leading '#' sign (e.g. #FFAABB) or one of the CSS color names (https://developer.mozilla.org/en-US/docs/Web/CSS/color_value#Color_keywords)
labelcolor = {
  'component' : 'navy',
  'platform' : 'teal',
  'priority' : 'red',
  'type' : 'purple',
  'keyword' : 'silver',
  'vendor' : 'yellow'
}

config = ConfigParser.ConfigParser(default_config)
config.read('migrate.cfg')

trac_url = config.get('source', 'url')
trac_path = None
if config.has_option('source', 'path') :
    trac_path = config.get('source', 'path')
dest_project_name = config.get('target', 'project_name')

gitlab_url = config.get('target', 'url')
gitlab_access_token = config.get('target', 'access_token')
gitlab_user_ids_map = ast.literal_eval(config.get('target', 'user_ids'))
gitlab_impers_tokens_map = ast.literal_eval(config.get('target', 'impers_tokens'))
dest_ssl_verify = config.getboolean('target', 'ssl_verify')
overwrite = config.getboolean('target', 'overwrite')

users_map = ast.literal_eval(config.get('target', 'usernames'))
must_convert_issues = config.getboolean('issues', 'migrate')
only_issues = None
if config.has_option('issues', 'only_issues'):
    only_issues = ast.literal_eval(config.get('issues', 'only_issues'))
blacklist_issues = None
if config.has_option('issues', 'blacklist_issues'):
    blacklist_issues = ast.literal_eval(config.get('issues', 'blacklist_issues'))
filter_issues = 'max=0&order=id'
if config.has_option('issues', 'filter_issues') :
    filter_issues = config.get('issues', 'filter_issues')
must_convert_wiki = config.getboolean('wiki', 'migrate')
migrate_keywords = config.getboolean('issues', 'migrate_keywords')
migrate_milestones = config.getboolean('issues', 'migrate_milestones')
add_label = None
if config.has_option('issues', 'add_label'):
    add_label = config.get('issues', 'add_label')

svngit_mapfile = None
if config.has_option('source', 'svngitmap') :
    svngit_mapfile = config.get('source', 'svngitmap')
svngit_map = None

#pattern_changeset = r'(?sm)In \[changeset:"([^"/]+?)(?:/[^"]+)?"\]:\n\{\{\{(\n#![^\n]+)?\n(.*?)\n\}\}\}'
pattern_changeset = r'(?sm)In \[changeset:"[0-9]+" ([0-9]+)\]:\n\{\{\{(\n#![^\n]+)?\n(.*?)\n\}\}\}'
matcher_changeset = re.compile(pattern_changeset)

pattern_changeset2 = r'\[changeset:([a-zA-Z0-9]+)\]'
matcher_changeset2 = re.compile(pattern_changeset2)

pattern_svnrev1 = r'(?:\bchangeset *)?\[([0-9]+)\]'
matcher_svnrev1 = re.compile(pattern_svnrev1)

pattern_svnrev2 = r'\b(?:changeset *)?r([0-9]+)\b'
matcher_svnrev2 = re.compile(pattern_svnrev2)


def format_changeset_comment(m):
    if svngit_map is not None and m.group(1) in svngit_map :
        r = 'In ' + svngit_map[m.group(1)][0][:10]
    else :
        if svngit_map is not None :
            print '  WARNING: svn revision', m.group(1), 'not given in svn to git mapping'
        r = 'In changeset ' + m.group(1)
    r += ':\n> ' + m.group(3).replace('\n', '\n> ')
    return r


def handle_svnrev_reference(m) :
    assert svngit_map is not None
    if m.group(1) in svngit_map :
        return svngit_map[m.group(1)][0][:10]
    else :
        #print '  WARNING: svn revision', m.group(1), 'not given in svn to git mapping'
        return m.group(0)


def trac2markdown(text, base_path, multilines = True) :
    text = matcher_changeset.sub(format_changeset_comment, text)
    text = matcher_changeset2.sub(r'\1', text)

    text = re.sub('\r\n', '\n', text)
    text = re.sub(r'{{{(.*?)}}}', r'`\1`', text)
    text = re.sub(r'(?sm){{{(\n?#![^\n]+)?\n(.*?)\n}}}', r'```\n\2\n```', text)

    text = text.replace('[[TOC]]', '')
    text = text.replace('[[BR]]', '\n')
    text = text.replace('[[br]]', '\n')

    if svngit_map is not None :
        text = matcher_svnrev1.sub(handle_svnrev_reference, text)
        text = matcher_svnrev2.sub(handle_svnrev_reference, text)

    if multilines:
        text = re.sub(r'^\S[^\n]+([^=-_|])\n([^\s`*0-9#=->-_|])', r'\1 \2', text)

    text = re.sub(r'(?m)^======\s+(.*?)\s+======$', r'\n###### \1', text)
    text = re.sub(r'(?m)^=====\s+(.*?)\s+=====$', r'\n##### \1', text)
    text = re.sub(r'(?m)^====\s+(.*?)\s+====$', r'\n#### \1', text)
    text = re.sub(r'(?m)^===\s+(.*?)\s+===$', r'\n### \1', text)
    text = re.sub(r'(?m)^==\s+(.*?)\s+==$', r'\n## \1', text)
    text = re.sub(r'(?m)^=\s+(.*?)\s+=$', r'\n# \1', text)
    text = re.sub(r'^             * ', r'****', text)
    text = re.sub(r'^         * ', r'***', text)
    text = re.sub(r'^     * ', r'**', text)
    text = re.sub(r'^ * ', r'*', text)
    text = re.sub(r'^ \d+. ', r'1.', text)

    a = []
    is_table = False
    for line in text.split('\n'):
        if not line.startswith('    '):
            line = re.sub(r'\[\[(https?://[^\s\[\]\|]+)\s*[\s\|]\s*([^\[\]]+)\]\]', r'[\2](\1)', line)
            line = re.sub(r'\[(https?://[^\s\[\]\|]+)\s*[\s\|]\s*([^\[\]]+)\]', r'[\2](\1)', line)
            line = re.sub(r'\[wiki:([^\s\[\]]+)\s([^\[\]]+)\]', r'[\2](%s/\1)' % os.path.relpath('/wikis/', base_path), line)
            line = re.sub(r'\[/wiki/([^\s\[\]]+)\s([^\[\]]+)\]', r'[\2](%s/\1)' % os.path.relpath('/wikis/', base_path), line)
            line = re.sub(r'\[source:([^\s\[\]]+)\s([^\[\]]+)\]', r'[\2](%s/\1)' % os.path.relpath('/tree/master/', base_path), line)
            line = re.sub(r'source:([\S]+)', r'[\1](%s/\1)' % os.path.relpath('/tree/master/', base_path), line)
            line = re.sub(r'\!(([A-Z][a-z0-9]+){2,})', r'\1', line)
            line = re.sub(r'\[\[Image\(source:([^(]+)\)\]\]', r'![](%s/\1)' % os.path.relpath('/tree/master/', base_path), line)
            line = re.sub(r'\[\[Image\(([^(]+)\)\]\]', r'![](\1)', line)
            line = re.sub(r'\'\'\'(.*?)\'\'\'', r'*\1*', line)
            line = re.sub(r'\'\'(.*?)\'\'', r'_\1_', line)
            if line.startswith('||'):
                if not is_table:
                    sep = re.sub(r'[^|]', r'-', line)
                    line = line + '\n' + sep
                    is_table = True
                line = re.sub(r'\|\|', r'|', line)
            else:
                is_table = False
        else:
            is_table = False
        a.append(line)
    text = '\n'.join(a)
    return text


def convert_xmlrpc_datetime(dt):
    # datetime.strptime(str(dt), "%Y%m%dT%X").isoformat() + "Z"
    return datetime.strptime(str(dt), "%Y%m%dT%H:%M:%S")


def get_dest_project_id(dest, dest_project_name):
    dest_project = dest.project_by_name(dest_project_name)
    if not dest_project:
        raise ValueError("Project '%s' not found" % dest_project_name)
    return dest_project["id"]


def get_dest_milestone_id(dest, dest_project_id, milestone_name):
    dest_milestone_id = dest.milestone_by_name(dest_project_id, milestone_name)
    if not dest_milestone_id:
        raise ValueError("Milestone '%s' of project '%s' not found" % (milestone_name, dest_project_name))
    return dest_milestone_id["id"]


def convert_issues(source, dest, dest_project_id, only_issues = None, blacklist_issues = None):
    if overwrite:
        # (soft)delete existing issues
        # unfortunately, newly added issues do not start with 1
        dest.clear_issues(dest_project_id)

    milestone_map_id = {}

    if migrate_milestones:
        for milestone_name in source.ticket.milestone.getAll():
            milestone = source.ticket.milestone.get(milestone_name)
            print(milestone)
            new_milestone = Milestones(
                description = trac2markdown(milestone['description'], '/milestones/', False),
                title = milestone['name'],
                state = 'active' if str(milestone['completed']) == '0'  else 'closed'
            )
            if milestone['due']:
                new_milestone.due_date = convert_xmlrpc_datetime(milestone['due'])
            new_milestone = dest.create_milestone(dest_project_id, new_milestone)
            milestone_map_id[milestone_name] = new_milestone.id

    get_all_tickets = xmlrpclib.MultiCall(source)

    for ticket in source.ticket.query(filter_issues):
        get_all_tickets.ticket.get(ticket)

    for src_ticket in get_all_tickets():
        #src_ticket is [id, time_created, time_changed, attributes]
        src_ticket_id = src_ticket[0]
        if only_issues and src_ticket_id not in only_issues:
            print("SKIP unwanted ticket #%s" % src_ticket_id)
            continue
        if blacklist_issues and src_ticket_id in blacklist_issues:
            print("SKIP blacklisted ticket #%s" % src_ticket_id)
            continue

        src_ticket_data = src_ticket[3]
        # src_ticket_data.keys(): ['status', 'changetime', 'description', 'reporter', 'cc', 'type', 'milestone', '_ts',
        # 'component', 'owner', 'summary', 'platform', 'version', 'time', 'keywords', 'resolution']

        changelog = source.ticket.changeLog(src_ticket_id)

        print(("Migrate ticket #%s (%d changes): %s" % (src_ticket_id, len(changelog), src_ticket_data['summary'][:30])).encode("ascii", "replace"));

        # get original component, owner
        # src_ticket_data['component'] is the component after all changes, but for creating the issue we want the component
        # that was set when the issue was created; we should get this from the first changelog entry that changed a component
        # ... and similar for other attributes
        component = None
        owner = None
        platform = None
        version = None
        tickettype = None
        description = None
        summary = None
        priority = None
        keywords = None
        status = None
        for change in changelog :
            #change is tuple (time, author, field, oldvalue, newvalue, permanent)
            if component is None and change[2] == 'component' :
                component = change[3]
                continue
            if owner is None and change[2] == 'owner' :
                owner = change[3]
                continue
            if platform is None and change[2] == 'platform' :
                platform = change[3]
                continue
            if version is None and change[2] == 'version' :
                version = change[3]
                continue
            if tickettype is None and change[2] == 'type' :
                tickettype = change[3]
                continue
            if description is None and change[2] == 'description' :
                description = change[3]
                continue
            if summary is None and change[2] == 'summary' :
                summary = change[3]
                continue
            if priority is None and change[2] == 'priority' :
                priority = change[3]
                continue
            if keywords is None and change[2] == 'keywords' :
                keywords = change[3]
                continue
            if status is None and change[2] == 'status' :
                status = change[3]
                continue

        # if no change changed a certain attribute, then that attribute is given by ticket data
        if component is None :
            component = src_ticket_data['component']
        if owner is None :
            owner = src_ticket_data['owner']
        if platform is None :
            platform = src_ticket_data.get('platform')
        if version is None :
            version = src_ticket_data.get('version')
        if tickettype is None :
            tickettype = src_ticket_data['type']
        if description is None :
            description = src_ticket_data['description']
        if summary is None :
            summary = src_ticket_data['summary']
        if priority is None :
            priority = src_ticket_data.get('priority', 'normal')
        if keywords is None :
            keywords = src_ticket_data['keywords']
        if status is None :
            status = src_ticket_data['status']

        #reporter_id = dest.get_user_id(users_map[src_ticket_data['reporter']], True)
        reporter_id = gitlab_user_ids_map[users_map[src_ticket_data['reporter']]]

        labels = []
        if add_label:
            labels.append(add_label)
        labels.append(component)
        dest.ensure_label(dest_project_id, component, labelcolor['component'])
        if platform is not None and platform != 'All platforms' and platform != '' :
            labels.append(platform)
            dest.ensure_label(dest_project_id, platform, labelcolor['platform'])
        if priority != 'normal' :
            labels.append(priority)
            dest.ensure_label(dest_project_id, priority, labelcolor['priority'])
        labels.append(tickettype)
        dest.ensure_label(dest_project_id, tickettype, labelcolor['type'])
        if keywords != '' and migrate_keywords:
            for keyword in keywords.split(','):
                labels.append(keyword.strip())
                dest.ensure_label(dest_project_id, keyword.strip(), labelcolor['keyword'])

        description_add = ''
        if version is not None and version != 'trunk' :
            description_add += '\n\nVersion: ' + version

        # process descriptions that are links to "AB master pages" in wiki
        # this is very GAMS specific, so commented out
        #ab = re.search(r'\[/wiki/(AB[0-9]{5}) AB[0-9]{5}\]', description)
        ab = None
        if ab is not None :
            pagename = ab.group(1)
            print '  get wiki page', pagename
            page = source.wiki.getPage(pagename)
            page = page.replace("{{{\n#!html\n", "")
            page = page.replace("}}}", "")
            page = re.sub(r'&nbsp([^;])', r'&nbsp;\1', re.sub(r'&nbsp([^;])', r'&nbsp;\1', page))  # fixup &nbsp (missing semicolon)
            page = re.sub(r'~~~*', '', page)   # replace lines '~~~~~...'  FIXME
            page = re.sub(r'---*', '', page)   # replace lines '-----...'  FIXME

            pattern_changeset2 = r'\[changeset:([a-zA-Z0-9]+)\]'
            attachment_re = re.compile(r'\[ ATTACHMENT REMOVED : <a href="/source/attachment/wiki/([^"]*)">([^<]*)</a> ]')
            #for m in attachment_re.finditer(page) :
            #    print m.group(0), m.group(1)

            def handle_wiki_attachment(m):
                # ensure file name will be in ascii (otherwise gitlab complain), e.g., #2504
                origname = m.group(2)
                name = origname.encode("ascii", "replace")

                try :
                    file = source.wiki.getAttachment(m.group(1)).data
                except xmlrpclib.Fault :
                    if trac_path is None :
                        raise BaseException('Attachment', name, 'of page', pagename, 'for ticket', src_ticket_id, 'not found and no diskpath to trac specified')
                    diskfile = os.path.join(trac_path, 'attachments', 'wiki', pagename, name)
                    if os.path.exists(diskfile) :
                        file = open(diskfile, 'rb').read()
                    else :
                        raise BaseException('Attachment', name, 'of page', pagename, 'for ticket', src_ticket_id, 'not found')
                r = dest.upload_file(dest_project_id, reporter_id, name, file)

                rstr = '[ ATTACHMENT REMOVED : <a href="%s">%s</a>' % (r['url'], name)
                if origname != name :
                    rstr += ' (filename changed during trac to gitlab conversion; original filename: ' + origname + ')'
                rstr += ' ]'
                return rstr

            page = attachment_re.sub(handle_wiki_attachment, page)

            description = page.strip()
        else :
            description = trac2markdown(description, '/issues/', False) + description_add

        assert description.find('/wikis/') < 0

        # collect all parameters
        new_issue_data = Issues(
            title = summary,
            description = description,
            labels = ",".join(labels),
            reporter = reporter_id,
            created_at = str(convert_xmlrpc_datetime(src_ticket[1]))
        )
        if owner != '' :
            new_issue_data.assignee = gitlab_user_ids_map[users_map[owner]]

        if 'milestone' in src_ticket_data:
            milestone = src_ticket_data['milestone']
            if milestone and milestone in milestone_map_id:
                new_issue_data.milestone = milestone_map_id[milestone]
            else:
                milestone_map_id[milestone] = get_dest_milestone_id(dest, dest_project_id, milestone)
                new_issue_data.milestone = milestone_map_id[milestone]

        issue = dest.create_issue(dest_project_id, new_issue_data)
        print("  created issue %d with labels %s owner %s component %s" % (issue.id, issue.labels, owner, component))

        # handle status
        if status in ['new', 'assigned', 'analyzed', 'reopened'] : #'vendor' (would need to create label)
            issue.state = 'open'
        elif status in ['closed'] :
            # sometimes a ticket is already closed at creation, e.g., #1, so close issue
            issue.state = 'closed'
            # workaround #3 dest.update_issue_property(dest_project_id, issue, new_issue_data.reporter, new_issue_data.created_at, 'state')  #TODO
        else :
            raise("  unknown ticket status: " + status)

        attachment = None
        newowner = None
        for change in changelog:
            #change is tuple (time, author, field, oldvalue, newvalue, permanent)
            change_time = str(convert_xmlrpc_datetime(change[0]))
            change_type = change[2]
            print(("  %s by %s (%s -> %s)" % (change_type, change[1], change[3][:40].replace("\n", " "), change[4][:40].replace("\n", " "))).encode("ascii", "replace"))
            assert attachment is None or change_type == "comment", "an attachment must be followed by a comment"
            #author = dest.get_user_id(users_map[change[1]], True)
            author = gitlab_user_ids_map[users_map[change[1]]]
            if change_type == "attachment":
                # The attachment will be described in the next change!
                attachment = change
            elif change_type == "comment":
                # change[3] is here either x or y.x, where x is the number of this comment and y is the number of the comment that is replied to
                desc = change[4].strip();
                if desc == '' and attachment is None :
                    # empty description and not description of attachment
                    continue
                note = Notes(
                    note = trac2markdown(desc, '/issues/', False)
                )
                if attachment is not None :
                    note.attachment_name = attachment[4]  # name of attachment
                    note.attachment = source.ticket.getAttachment(src_ticket_id, attachment[4].encode('utf8')).data
                    attachment = None
                note.created_at = change_time
                note.author = author
                dest.comment_issue(dest_project_id, issue, note)
            elif change_type.startswith("_comment") :
                # this is an old version of a comment, which has been edited later (given in previous change),
                # we will forget about these old versions and only keep the latest one
                pass
            elif change_type == "status" :
                if change[3] == 'vendor' :
                    # remove label 'vendor'
                    issue.labels.remove('vendor')
                    # workaround #3 dest.update_issue_property(dest_project_id, issue, author, change_time, 'labels')

                # we map here the various statii we have in trac to just 2 statii in gitlab (open or close), so loose some information
                if change[4] in ['new', 'assigned', 'analyzed', 'vendor', 'reopened'] :
                    newstate = 'open'
                elif change[4] in ['closed'] :
                    newstate = 'closed'
                else :
                    raise("  unknown ticket status: " + change[4])

                if issue.state != newstate :
                    issue.state = newstate
                    # workaround #3 dest.update_issue_property(dest_project_id, issue, author, change_time, 'state')

                if change[4] == 'vendor' :
                    # add label 'vendor'
                    issue.labels.append('vendor')
                    dest.ensure_label(dest_project_id, 'vendor', labelcolor['vendor'])
                    # workaround #3 dest.update_issue_property(dest_project_id, issue, author, change_time, 'labels')

                # workaround #3
                dest.comment_issue(dest_project_id, issue, Notes(note = 'Changing status from ' + change[3] + ' to ' + change[4] + '.', created_at = change_time, author = author))
            elif change_type == "resolution" :
                if change[3] != '' :
                    desc = "Resolution changed from %s to %s" % (change[3], change[4])
                else :
                    desc = "Resolution: " + change[4]
                note = Notes(
                    note = desc,
                    author = author,
                    created_at = change_time
                )
                dest.comment_issue(dest_project_id, issue, note)
            elif change_type == "component" :
                issue.labels.remove(change[3])
                issue.labels.append(change[4])
                dest.ensure_label(dest_project_id, change[4], labelcolor['component'])
                # workaround #3 dest.update_issue_property(dest_project_id, issue, author, change_time, 'labels')
                dest.comment_issue(dest_project_id, issue, Notes(note = 'Changing component from ~' + change[3] + ' to ~' + change[4] + '.', created_at = change_time, author = author))
            elif change_type == "owner" :
                #issue.assignee = dest.get_user_id(users_map[change[4]], True)
                issue.assignee = gitlab_user_ids_map[users_map[change[4]]]
                # workaround #3 dest.update_issue_property(dest_project_id, issue, author, change_time, 'assignee')
                if change[3] != '' :
                    dest.comment_issue(dest_project_id, issue, Notes(note = 'Changing assignee from @' + users_map[change[3]] + ' to @' + users_map[change[4]] + '.', created_at = change_time, author = author))
                else :
                    dest.comment_issue(dest_project_id, issue, Notes(note = 'Set assignee to @' + users_map[change[4]] + '.', created_at = change_time, author = author))
                newowner = change[4]
            elif change_type == "platform" :
                if change[3] != '' and change[3] != 'All platforms' :
                    issue.labels.remove(change[3])
                if change[4] != '' and change[4] != 'All platforms' :
                    issue.labels.append(change[4])
                    dest.ensure_label(dest_project_id, change[4], labelcolor['platform'])
                # workaround #3  dest.update_issue_property(dest_project_id, issue, author, change_time, 'labels')
                if change[3] != '' and change[3] != 'All platforms' : change[3] = '~' + change[3]
                if change[4] != '' and change[4] != 'All platforms' : change[4] = '~' + change[4]
                dest.comment_issue(dest_project_id, issue, Notes(note = 'Changing platform from ' + change[3] + ' to ' + change[4] + '.', created_at = change_time, author = author))
            elif change_type == "version" :
                if change[3] != '' :
                    desc = "Version changed from %s to %s" % (change[3], change[4])
                else :
                    desc = "Version: " + change[4]
                note = Notes(
                    note = "Version: " + desc,
                    author = author,
                    created_at = change_time
                )
                dest.comment_issue(dest_project_id, issue, note)
            elif change_type == "milestone" :
                pass  # we ignore milestones so far
            elif change_type == "cc" :
                pass  # we handle only the final list of CCs (below)
            elif change_type == "type" :
                issue.labels.remove(change[3])
                issue.labels.append(change[4])
                dest.ensure_label(dest_project_id, change[4], labelcolor['type'])
                # workaround #3 dest.update_issue_property(dest_project_id, issue, author, change_time, 'labels')
                if change[3] != '' : change[3] = '~' + change[3]
                if change[4] != '' : change[4] = '~' + change[4]
                dest.comment_issue(dest_project_id, issue, Notes(note = 'Changing type from ' + change[3] + ' to ' + change[4] + '.', created_at = change_time, author = author))
            elif change_type == "description" :
                issue.description = trac2markdown(change[4], '/issues/', False) + description_add
                dest.update_issue_property(dest_project_id, issue, author, change_time, 'description')
            elif change_type == "summary" :
                issue.title = change[4]
                dest.update_issue_property(dest_project_id, issue, author, change_time, 'title')
            elif change_type == "priority" :
                if change[3] != '' and change[3] != 'normal' :
                    issue.labels.remove(change[3])
                if change[4] != '' and change[4] != 'normal' :
                    issue.labels.append(change[4])
                    dest.ensure_label(dest_project_id, change[4], labelcolor['priority'])
                # workaround #3  dest.update_issue_property(dest_project_id, issue, author, change_time, 'labels')
                if change[3] != '' and change[3] != 'normal' : change[3] = '~' + change[3]
                if change[4] != '' and change[4] != 'normal' : change[4] = '~' + change[4]
                dest.comment_issue(dest_project_id, issue, Notes(note = 'Changing priority from ' + change[3] + ' to ' + change[4] + '.', created_at = change_time, author = author))
            elif change_type == "keywords" :
                if not migrate_keywords : continue
                oldkeywords = change[3].split(',')
                newkeywords = change[4].split(',')
                for keyword in oldkeywords :
                    keyword = keyword.strip()
                    if keyword != '' :
                        issue.labels.remove(keyword)
                for keyword in newkeywords :
                    keyword = keyword.strip()
                    if keyword != '' :
                        issue.labels.append(keyword)
                        dest.ensure_label(dest_project_id, keyword, labelcolor['keyword'])
                # workaround #3 dest.update_issue_property(dest_project_id, issue, author, change_time, 'labels')
                oldkeywords = [ '~' + kw.strip() for kw in oldkeywords ]
                newkeywords = [ '~' + kw.strip() for kw in newkeywords ]
                dest.comment_issue(dest_project_id, issue, Notes(note = 'Changing keywords from ' + ','.join(oldkeywords) + ' to ' + ','.join(newkeywords) + '".', created_at = change_time, author = author))
            else :
                raise BaseException("Unknown change type " + change_type)
        assert attachment is None

        # workaround #3: set final state (if not open), assignee (if changed), and list of labels (if changed)
        if issue.state == 'closed' :
            dest.update_issue_property(dest_project_id, issue, None, None, 'state')
        if newowner is not None and newowner != owner :
            #issue.assignee = dest.get_user_id(users_map[newowner], True)
            issue.assignee = gitlab_user_ids_map[users_map[newowner]]
            dest.update_issue_property(dest_project_id, issue, None, None, 'assignee')
        if issue.labels != new_issue_data.labels :
            dest.update_issue_property(dest_project_id, issue, None, None, 'labels')

        # subscribe persons in cc
        cc = src_ticket_data.get('cc', '').lower()
        for person in cc.split(',') :
            person = person.strip()
            if person == '' : continue
            # shorten e-mail addresses to username as often we have things like someone@gams.com
            atpos = person.find('@')
            if atpos >= 0 :
                person = person[:atpos]
            # if person not in users mapping, then it probably is someone external, whom we cannot subscribe
            if person not in users_map :
                print('  ignore cc ' + person)
                continue
            print('  subscribe ' + users_map[person])
            #person_id = dest.get_user_id(users_map[person], True)
            person_id = gitlab_user_ids_map[users_map[person]]
            dest.subscribe_issue(dest_project_id, issue, person_id)


def convert_wiki(source, dest, dest_project_id):
    #if overwrite :
    #    dest.clear_wiki_attachments(dest_project_id)

    exclude_authors = [a.strip() for a in config.get('wiki', 'exclude_authors').split(',')]
    for name in source.wiki.getAllPages():
        info = source.wiki.getPageInfo(name)
        if (info['author'] not in exclude_authors):
            page = source.wiki.getPage(name)
            print("Page %s:%s" % (name, info))
            if (name == 'WikiStart'):
                name = 'home'
            converted = trac2markdown(page, os.path.dirname('/wikis/%s' % name))
            dest.create_wiki(dest_project_id, converted, name, info['author'])
            for attachment in source.wiki.listAttachments(name):
                #    for attachment in source.wiki.listAttachments(name):
                #        print(attachment)
                #        binary_attachment = source.wiki.getAttachment(attachment).data
                #        try:
                #            attachment_path = dest.create_wiki_attachment(dest_project_id, users_map[info['author']], convert_xmlrpc_datetime(info['lastModified']), attachment, binary_attachment)
                #        except KeyError:
                #            attachment_path = dest.create_wiki_attachment(dest_project_id, default_user, convert_xmlrpc_datetime(info['lastModified']), attachment, binary_attachment)
                #        attachment_name = attachment.split('/')[-1]
                #        converted = converted.replace(r'](%s)' % attachment_name, r'](%s)' % os.path.relpath(attachment_path, '/namespace/project/wiki/page'))
                print('skip attachment', attachment);


if __name__ == "__main__":
    dest = Connection(gitlab_url, gitlab_access_token, dest_ssl_verify, gitlab_impers_tokens_map)

    source = xmlrpclib.ServerProxy(trac_url)
    dest_project_id = get_dest_project_id(dest, dest_project_name)

#    if svngit_mapfile is not None :
#        svngit_map = dict()
#        for line in open(svngit_mapfile, 'r') :
#            l = line.split()
#            assert len(l) >= 2, line
#            githash = l[0]
#            svnrev = l[1]
#            svnbranch = l[2][1:] if len(l) > 2 else 'trunk'
#            #print l[1], l[0]
#            # if already have a svn revision entry from branch trunk, then ignore others
#            if svnrev in svngit_map and svngit_map[svnrev][1] == 'trunk' :
#                continue
#            svngit_map[svnrev] = [githash, svnbranch]

    if must_convert_issues:
        convert_issues(source, dest, dest_project_id, only_issues = only_issues, blacklist_issues = blacklist_issues)

    if must_convert_wiki:
        convert_wiki(source, dest, dest_project_id)

'''
This file is part of <https://gitlab.dyomedea.com/vdv/trac-to-gitlab>.

This sotfware is free software: you can redistribute it and/or modify
it under the terms of the GNU Lesser General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This sotfware is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Lesser General Public License for more details.

You should have received a copy of the GNU Lesser General Public License
along with this library. If not, see <http://www.gnu.org/licenses/>.
'''
