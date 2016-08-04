#!/usr/bin/python
#title           :sat_export.py
#description     :Exports Satellite 6 Content for disconnected environments
#URL             :https://github.com/ggatward/sat6_scripts
#author          :Geoff Gatward <ggatward@redhat.com>
#notes           :This script is NOT SUPPORTED by Red Hat Global Support Services.
#license         :GPLv3
#==============================================================================
"""
Exports Satellite 6 yum content.
"""

import sys, argparse, datetime, os, shutil, pickle
import fnmatch, subprocess, tarfile
import simplejson as json
from glob import glob
import helpers

try:
    import yaml
except ImportError:
    print "Please install the PyYAML module."
    sys.exit(-1)

# Get details about Content Views and versions
def get_cv(org_id):
    """
    Get the version of the Content Views
    There should only ever be ONE version of the Default Org View.
    It Should be v1.0 with id=1, but we're verifying here just in case.
    """

    # Query API to get all content views for our org
    cvs = helpers.get_json(
        helpers.KATELLO_API + "organizations/" + str(org_id) + "/content_views/")
    for cv_result in cvs['results']:
        if cv_result['name'] == "Default Organization View":
            msg = "CV Name: " + cv_result['name']
            helpers.log_msg(msg, 'DEBUG')

            # Find the current version of the view in the env we are coming from
            for ver in cv_result['versions']:
                msg = "  Env ID:     " + str(ver['environment_ids'])
                helpers.log_msg(msg, 'DEBUG')
                msg = "  Version:    " + str(ver['version'])
                helpers.log_msg(msg, 'DEBUG')
                msg = "  Version ID: " + str(ver['id'])
                helpers.log_msg(msg, 'DEBUG')

        # There will only ever be one DOV
        return cv_result['id']


# Promote a content view version
def export_cv(dov_ver, last_export, export_type):
    """
    Export Content View
    Takes the content view version and a start time (API 'since' value)
    """
    if export_type == 'full':
        msg = "Exporting complete DOV version " + str(dov_ver)
    else:
        msg = "Exporting DOV version " + str(dov_ver) + " from start date " + last_export
    helpers.log_msg(msg, 'INFO')

    try:
        if export_type == 'full':
            task_id = helpers.post_json(
                helpers.KATELLO_API + "content_view_versions/" + str(dov_ver) + "/export", \
                    json.dumps(
                        {
                        }
                    ))["id"]
        else:
            task_id = helpers.post_json(
                helpers.KATELLO_API + "content_view_versions/" + str(dov_ver) + "/export/", \
                    json.dumps(
                        {
                            "since": last_export,
                        }
                    ))["id"]
    except: # pylint: disable-msg=W0702
        msg = "Unable to start export - Conflicting Sync or Export already in progress"
        helpers.log_msg(msg, 'ERROR')
        sys.exit(-1)

    # Trap some other error conditions
    if "Required lock is already taken" in str(task_id):
        msg = "Unable to start export - Sync in progress"
        helpers.log_msg(msg, 'ERROR')
        sys.exit(-1)

    msg = "Export started, task_id = " + str(task_id)
    helpers.log_msg(msg, 'DEBUG')

    return str(task_id)


def export_repo(repo_id, last_export, export_type):
    """
    Export individual repository
    Takes the repository id and a start time (API 'since' value)
    """
    if export_type == 'full':
        msg = "Exporting repository id " + str(repo_id)
    else:
        msg = "Exporting repository id " + str(repo_id) + " from start date " + last_export
    helpers.log_msg(msg, 'INFO')

    try:
        if export_type == 'full':
            task_id = helpers.post_json(
                helpers.KATELLO_API + "repositories/" + str(repo_id) + "/export", \
                    json.dumps(
                        {
                        }
                    ))["id"]
        else:
            task_id = helpers.post_json(
                helpers.KATELLO_API + "repositories/" + str(repo_id) + "/export/", \
                    json.dumps(
                        {
                            "since": last_export,
                        }
                    ))["id"]
    except: # pylint: disable-msg=W0702
        msg = "Unable to start export - Conflicting Sync or Export already in progress"
        helpers.log_msg(msg, 'ERROR')
        sys.exit(-1)

    # Trap some other error conditions
    if "Required lock is already taken" in str(task_id):
        msg = "Unable to start export - Sync in progress"
        helpers.log_msg(msg, 'ERROR')
        sys.exit(-1)

    msg = "Export started, task_id = " + str(task_id)
    helpers.log_msg(msg, 'DEBUG')

    return str(task_id)


def check_running_tasks(label, name):
    """
    Check for any currently running Sync or Export tasks
    Exits script if any Synchronize or Export tasks are found in a running state.
    """
    #pylint: disable-msg=R0912,R0914,R0915
    tasks = helpers.get_p_json(
        helpers.FOREMAN_API + "tasks/", \
                json.dumps(
                    {
                        "per_page": "100",
                    }
                ))

    # From the list of tasks, look for any running export or sync jobs.
    # If e have any we exit, as we can't export in this state.
    ok_to_export = True
    for task_result in tasks['results']:
        if task_result['state'] == 'running':
            if task_result['humanized']['action'] == 'Export':
                if task_result['input']['repository']['label'] == label:
                    msg = "Unable to export due to export task in progress"
                    if name == 'DoV':
                        helpers.log_msg(msg, 'ERROR')
                        sys.exit(-1)
                    else:
                        helpers.log_msg(msg, 'WARNING')
                        ok_to_export = False
            if task_result['humanized']['action'] == 'Synchronize':
                if task_result['input']['repository']['label'] == label:
                    msg = "Unable to export due to sync task in progress"
                    if name == 'DoV':
                        helpers.log_msg(msg, 'ERROR')
                        sys.exit(-1)
                    else:
                        helpers.log_msg(msg, 'WARNING')
                        ok_to_export = False
        if task_result['state'] == 'paused':
            if task_result['humanized']['action'] == 'Export':
                if task_result['input']['repository']['label'] == label:
                    msg = "Unable to export due to paused export task - Please resolve this issue."
                    if name == 'DoV':
                        helpers.log_msg(msg, 'ERROR')
                        sys.exit(-1)
                    else:
                        helpers.log_msg(msg, 'WARNING')
                        ok_to_export = False
            if task_result['humanized']['action'] == 'Synchronize':
                if task_result['input']['repository']['label'] == label:
                    msg = "Unable to export due to paused sync task."
                    if name == 'DoV':
                        helpers.log_msg(msg, 'ERROR')
                        sys.exit(-1)
                    else:
                        helpers.log_msg(msg, 'WARNING')
                        ok_to_export = False

    check_incomplete_sync()
    return ok_to_export


def check_incomplete_sync():
    """
    Check for any sync tasks that are in an Incomplete state.
    These are not paused or locked, but are the orange 100% complete ones in the UI
    """
    repo_list = helpers.get_json(
        helpers.KATELLO_API + "/content_view_versions")

    # Extract the list of repo ids, then check the state of each one.
    incomplete_sync = False
    for repo in repo_list['results']:
        for repo_id in repo['repositories']:
            repo_status = helpers.get_json(
                helpers.KATELLO_API + "/repositories/" + str(repo_id['id']))

            if repo_status['content_type'] == 'yum':
                if repo_status['last_sync']['state'] == 'stopped':
                    if repo_status['last_sync']['result'] == 'warning':
                        incomplete_sync = True
                        msg = "Repo ID " + str(repo_id['id']) + " Sync Incomplete"
                        helpers.log_msg(msg, 'DEBUG')

    # If we have detected incomplete sync tasks, ask the user if they want to export anyway.
    # This isn't fatal, but *MAY* lead to inconsistent repositories on the dieconnected sat.
    if incomplete_sync:
        msg = "Incomplete sync jobs detected"
        helpers.log_msg(msg, 'WARNING')
        answer = helpers.query_yes_no("Continue with export?", "no")
        if not answer:
            msg = "Export Aborted"
            helpers.log_msg(msg, 'ERROR')
            sys.exit(-1)
        else:
            msg = "Export continued by user"
            helpers.log_msg(msg, 'INFO')


def check_disk_space(export_type):
    """
    Check the disk usage of the pulp partition
    For a full export we need at least 50% free, as we spool to /var/lib/pulp.
    """
    pulp_used = str(helpers.disk_usage('/var/lib/pulp'))
    if export_type == 'full' and int(float(pulp_used)) > 50:
        msg = "Insufficient space in /var/lib/pulp for a full export. >50% free space is required."
        helpers.log_msg(msg, 'ERROR')
        sys.exit(-1)


def locate(pattern, root=os.curdir):
    """Provides simple 'locate' functionality for file search"""
    # pylint: disable=unused-variable
    for path, dirs, files in os.walk(os.path.abspath(root)):
        for filename in fnmatch.filter(files, pattern):
            yield os.path.join(path, filename)


def do_gpg_check(export_dir):
    """
    Find and GPG Check all RPM files
    """
    msg = "Checking GPG integrity of RPMs in " + export_dir
    helpers.log_msg(msg, 'INFO')
    print msg

    badrpms = []
    os.chdir(export_dir)
    for rpm in locate("*.rpm"):
        return_code = subprocess.call("rpm -K " + rpm, shell=True, stdout=open(os.devnull, 'wb'))

        # A non-zero return code indicates a GPG check failure.
        if return_code != 0:
            # For display purposes, strip the first 6 directory elements
            rpmnew = os.path.join(*(rpm.split(os.path.sep)[6:]))
            badrpms.append(rpmnew)

    # If we have any bad ones we need to fail the export.
    if len(badrpms) != 0:
        msg = "The following RPM's failed the GPG check.."
        helpers.log_msg(msg, 'ERROR')
        for badone in badrpms:
            msg = badone
            helpers.log_msg(msg, 'ERROR')
        msg = "------ Export Aborted ------"
        helpers.log_msg(msg, 'ERROR')
        sys.exit(-1)
    else:
        msg = "GPG check completed successfully"
        helpers.log_msg(msg, 'INFO')
        print helpers.GREEN + "GPG Check - Pass" + helpers.ENDC


def create_tar(export_dir, name):
    """
    Create a TAR of the content we have exported
    Creates a single tar, then splits into DVD size chunks and calculates
    sha256sum for each chunk.
    """
    today = datetime.datetime.strftime(datetime.datetime.now(), '%Y-%m-%d')
    msg = "Creating TAR files..."
    helpers.log_msg(msg, 'INFO')
    print msg

    os.chdir(export_dir)
    full_tarfile = helpers.EXPORTDIR + '/sat6_export_' + today + '_' + name
    short_tarfile = 'sat6_export_' + today + '_' + name
    with tarfile.open(full_tarfile, 'w') as archive:
        archive.add(os.curdir, recursive=True)

    # Get a list of all the RPM content we are exporting
    result = [y for x in os.walk(export_dir) for y in glob(os.path.join(x[0], '*.rpm'))]
    if result:
        f_handle = open(helpers.LOGDIR + '/export_' + today + '_' + name + '.log', 'a+')
        f_handle.write('-------------------\n')
        for rpm in result:
            m_rpm = os.path.join(*(rpm.split(os.path.sep)[6:]))
            f_handle.write(m_rpm + '\n')
        f_handle.close()

    # When we've tar'd up the content we can delete the export dir.
    os.chdir(helpers.EXPORTDIR)
    shutil.rmtree(export_dir)

    # Split the resulting tar into DVD size chunks & remove the original.
    msg = "Splitting TAR file..."
    helpers.log_msg(msg, 'INFO')
    print msg
    os.system("split -d -b 4200M " + full_tarfile + " " + full_tarfile + "_")
    os.remove(full_tarfile)

    # Temporary until pythonic method is done
    msg = "Calculating Checksums..."
    helpers.log_msg(msg, 'INFO')
    print msg
    os.system('sha256sum ' + short_tarfile + '_* > ' + short_tarfile + '.sha256')


def prep_export_tree(org_name):
    """
    Function to combine individual export directories into single export tree
    Export top level contains /content and /custom directories with 'listing'
    files through the tree.
    """
    msg = "Preparing export directory tree..."
    helpers.log_msg(msg, 'INFO')
    print msg
    devnull = open(os.devnull, 'wb')
    os.makedirs(helpers.EXPORTDIR + "/export")
    # Haven't found a nice python way to do this - yet...
    subprocess.call("cp -rp " + helpers.EXPORTDIR + "/" + org_name + "*/" + org_name + \
        "/Library/* " + helpers.EXPORTDIR + "/export", shell=True, stdout=devnull, stderr=devnull)
    # Remove original directores
    os.system("rm -rf " + helpers.EXPORTDIR + "/" + org_name + "*/")

    # We need to re-generate the 'listing' files as we will have overwritten some during the merge
    msg = "Rebuilding listing files..."
    helpers.log_msg(msg, 'INFO')
    print msg
    create_listing_file(helpers.EXPORTDIR + "/export")

    # pylint: disable=unused-variable
    for root, directories, filenames in os.walk(helpers.EXPORTDIR + "/export"):
        for subdir in directories:
            currentdir = os.path.join(root, subdir)
            create_listing_file(currentdir)


def get_immediate_subdirectories(a_dir):
    """ Return a list of subdirectories """
    return [name for name in os.listdir(a_dir) if os.path.isdir(os.path.join(a_dir, name))]


def create_listing_file(directory):
    """
    Function to create the listing file containing the subdirectories
    """
    listing_file = open(directory + "/listing", "w")
    sorted_subdirs = sorted(get_immediate_subdirectories(directory))
    for directory in sorted_subdirs:
        listing_file.write(directory + "\n")
    listing_file.close()


def read_pickle(name):
    """
    Function to read the last export dates from an existing pickle
    """
    if not os.path.exists('var/exports_' + name + '.pkl'):
        if not os.path.exists('var'):
            os.makedirs('var')
        export_times = {}
        return export_times

    # Read in the export time pickle
    export_times = pickle.load(open('var/exports_' + name + '.pkl', 'rb'))
    return export_times


def main():
    """
    Main Routine
    """
    #pylint: disable-msg=R0912,R0914,R0915

    if helpers.DISCONNECTED:
        msg = "Export cannot be run on the disconnected Satellite host"
        helpers.log_msg(msg, 'ERROR')
        sys.exit(-1)

    # Who is running this script?
    runuser = helpers.who_is_running()

    # Log the fact we are starting
    msg = "------------- Content export started by " + runuser + " ----------------"
    helpers.log_msg(msg, 'INFO')

    # Check for sane input
    parser = argparse.ArgumentParser(description='Performs Export of Default Content View.')
    group = parser.add_mutually_exclusive_group()
    # pylint: disable=bad-continuation
    parser.add_argument('-o', '--org', help='Organization', required=True)
    parser.add_argument('-e', '--env', help='Environment config file', required=False)
    group.add_argument('-a', '--all', help='Export ALL content', required=False,
        action="store_true")
    group.add_argument('-i', '--incr', help='Incremental Export of content since last run',
        required=False, action="store_true")
    group.add_argument('-s', '--since', help='Export content since YYYY-MM-DD HH:MM:SS',
        required=False, type=helpers.valid_date)
    parser.add_argument('-l', '--last', help='Display time of last export', required=False,
        action="store_true")
    args = parser.parse_args()

    # Set our script variables from the input args
    org_name = args.org
    since = args.since

    # Record where we are running from
    script_dir = str(os.getcwd())

    # Get the org_id (Validates our connection to the API)
    org_id = helpers.get_org_id(org_name)
    exported_repos = []
    # If a specific environment is requested, find and read that config file
    if args.env:
        if not os.path.exists('config/' + args.env + '.yml'):
            print "ERROR: Config file 'config/" + args.env + ".yml' not found."
            sys.exit(-1)
        cfg = yaml.safe_load(open("config/" + args.env + ".yml", 'r'))
        ename = args.env
        erepos = cfg["env"]["repos"]
        msg = "Specific environment export called for " + ename + ". Configured repos:"
        helpers.log_msg(msg, 'DEBUG')
        for repo in erepos:
            msg = "  - " + repo
            helpers.log_msg(msg, 'DEBUG')

    else:
        ename = 'DoV'
        label = 'DoV'
        msg = "DoV export called"
        helpers.log_msg(msg, 'DEBUG')

    # Get the current time - this will be the 'last export' time if the export is OK
    start_time = datetime.datetime.strftime(datetime.datetime.now(), '%Y-%m-%d %H:%M:%S')
    print "START: " + start_time + " (" + ename + " export)"

    # Read the last export date pickle for our selected repo group.
    export_times = read_pickle(ename)
    export_type = 'incr'

    if args.all:
        print "Performing full content export for " + ename
        export_type = 'full'
        since = False
    else:
        if not since:
            since = False
            if args.last:
                if export_times:
                    print "Last successful export for " + ename + ":"
                    for time in export_times:
                        print str(time) + '\t' + str(export_times[time])
                else:
                    print "Export has never been performed for " + ename
                sys.exit(-1)
            if not export_times:
                print "No prior export recorded for " + ename + ", performing full content export"
                export_type = 'full'
        else:
            # TODO: Re-populate export_times dictionary so each repo has 'since' date
            since = True
            since_export = str(since)

            # We have our timestamp so we can kick of an incremental export
            print "Incremental export of content for " + ename + " synchronised after " \
            + str(since)

    # Check the available space in /var/lib/pulp
    check_disk_space(export_type)

    # TODO: Remove any previous exported content
#    os.chdir(helpers.EXPORTDIR)
#    shutil.rmtree()


    # Collect a list of enabled repositories. This is needed for:
    # 1. Matching specific repo exports, and
    # 2. Running import sync per repo on the disconnected side
    repolist = helpers.get_p_json(
        helpers.KATELLO_API + "/repositories/", \
                json.dumps(
                        {
                           "organization_id": org_id,
                        }
                ))

    # If we are running a full DoV export we run a different set of API calls...
    if ename == 'DoV':
        if export_type == 'incr' and 'DoV' in export_times:
            last_export = export_times['DoV']
            if since:
                last_export = since_export
            msg = "Exporting DoV (INCR since " + last_export + ")"
        else:
            export_type = 'full'
            last_export = '2000-01-01 12:00:00' # This is a dummy value, never used.
            msg = "Exporting DoV (FULL)"
        helpers.log_msg(msg, 'INFO')
        print msg

        # Check if there are any currently running tasks that will conflict with an export
        check_running_tasks(label, ename)

        # Get the version of the CV (Default Org View) to export
        dov_ver = get_cv(org_id)

        # Now we have a CV ID and a starting date, and no conflicting tasks, we can export
        export_id = export_cv(dov_ver, last_export, export_type)

        # Now we need to wait for the export to complete
        helpers.wait_for_task(export_id, 'export')

        # Check if the export completed OK. If not we exit the script.
        tinfo = helpers.get_task_status(export_id)
        if tinfo['state'] != 'running' and tinfo['result'] == 'success':
            msg = "Content View Export OK"
            helpers.log_msg(msg, 'INFO')
            print helpers.GREEN + msg + helpers.ENDC

            # Update the export timestamp for this repo
            export_times['DoV'] = start_time

            # Generate a list of repositories that were exported
            for repo_result in repolist['results']:
                if repo_result['content_type'] == 'yum':
                    # Add the repo to the successfully exported list
                    exported_repos.append(repo_result['label'])

        else:
            msg = "Content View Export FAILED"
            helpers.log_msg(msg, 'ERROR')
            sys.exit(-1)

    else:
        # Verify that defined repos exist in our DoV
        for repo_result in repolist['results']:
            if repo_result['content_type'] == 'yum':
                # If we have a match, do the export
                if repo_result['label'] in erepos:
                    # Extract the last export time for this repo
                    if export_type == 'incr' and repo_result['label'] in export_times:
                        last_export = export_times[repo_result['label']]
                        if since:
                            last_export = since_export
                        msg = "Exporting " + repo_result['label'] \
                            + " (INCR since " + last_export + ")"
                    else:
                        export_type = 'full'
                        last_export = '2000-01-01 12:00:00' # This is a dummy value, never used.
                        msg = "Exporting " + repo_result['label'] + "(FULL)"
                    helpers.log_msg(msg, 'INFO')
                    print msg

                    # Check if there are any currently running tasks that will conflict
                    ok_to_export = check_running_tasks(repo_result['label'], ename)

                    if ok_to_export:
                        # Trigger export on the repo
                        export_id = export_repo(repo_result['id'], last_export, export_type)

                        # Now we need to wait for the export to complete
                        helpers.wait_for_task(export_id, 'export')

                        # Check if the export completed OK. If not we exit the script.
                        tinfo = helpers.get_task_status(export_id)
                        if tinfo['state'] != 'running' and tinfo['result'] == 'success':
                            msg = "Repository Export OK"
                            helpers.log_msg(msg, 'INFO')
                            print helpers.GREEN + msg + helpers.ENDC

                            # Update the export timestamp for this repo
                            export_times[repo_result['label']] = start_time

                            # Add the repo to the successfully exported list
                            exported_repos.append(repo_result['label'])
                        else:
                            msg = "Export FAILED"
                            helpers.log_msg(msg, 'ERROR')


                else:
                    msg = "Skipping  " + repo_result['label']
                    helpers.log_msg(msg, 'DEBUG')


    # Combine resulting directory structures into a single repo format (top level = /content)
    prep_export_tree(org_name)

    # Now we need to process the on-disk export data.
    # Define the location of our exported data.
    export_dir = helpers.EXPORTDIR + "/export"

    # Write out the list of exported repos. This will be transferred to the disconnected system
    # and used to perform the repo sync tasks during the import.
    pickle.dump(exported_repos, open(export_dir + '/exported_repos.pkl', 'wb'))

    # Run GPG Checks on the exported RPMs
    do_gpg_check(export_dir)

    # Add our exported data to a tarfile
    create_tar(export_dir, ename)

    # We're done. Write the start timestamp to file for next time
    os.chdir(script_dir)
    pickle.dump(export_times, open('var/exports_' + ename + '.pkl', "wb"))

    # And we're done!
    print helpers.GREEN + "Export complete.\n" + helpers.ENDC
    print 'Please transfer the contents of ' + helpers.EXPORTDIR + \
        'to your disconnected Satellite system content import location.\n' \
        'Once transferred, please run ' + helpers.BOLD + ' sat_import' \
        + helpers.ENDC + ' to extract it.'


if __name__ == "__main__":
    main()

