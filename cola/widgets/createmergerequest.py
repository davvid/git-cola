from .. import gitcmds
from .. import utils
from ..i18n import N_
from ..interaction import Interaction

try:
    import gitlab
except ImportError:
    gitlab = None


def create_merge_request(context):
    """Launch a dialog for creating Merge/Pull Requests"""
    # {'origin': 'gitlab'}
    forge_remotes = gitcmds.forge_remotes(context)
    if not forge_remotes:
        Interaction.information(
            N_('Cannot Create Merge Requests'),
            N_(
                'No remotes are associated with a forge.\n\n'
                'Use "File > Edit Remotes..." to associate forges with remotes.'
            ),
        )
        return

    # {'gitlab': Forge(....)}
    forge_details = gitcmds.get_forge_details(context, set(forge_remotes.values()))
    if not forge_details:
        Interaction.information(
            N_('Cannot Create Merge Requests'),
            N_(
                'The forge has not been setup.\n\n'
                'Use "File > Edit Forges..." to configure forges.\n'
            ),
        )

    forge_remote = get_remote_for_merge_request(context, forge_remotes)
    if not forge_remote:
        return

    forge_urls = {
        remote: gitcmds.remote_url(context, remote) for remote in forge_remotes
    }
    forge_paths = {
        remote: utils.get_path_from_url(url) for remote, url in forge_urls.items()
    }
    forge_hostnames = {
        remote: utils.get_hostname_from_url(url) for remote, url in forge_urls.items()
    }

    print('#', forge_remote)
    print(forge_remotes)
    print(forge_urls)
    print(forge_paths)

    print('')
    forge_name = forge_remotes[forge_remote]
    forge = forge_details[forge_name]
    gitlab_api = gitlab.Gitlab(url=forge.url, private_token=forge.token)

    project = gitlab_api.projects.get(forge_paths[forge_remote])
    print('####', project.path_with_namespace)
    project.pprint()
    if hasattr(project, 'forked_from_project'):
        print(project.forked_from_project)
    print('')

    for remote, path in forge_paths.items():
        if remote == forge_remote:
            continue
        project = gitlab_api.projects.get(forge_paths[remote])
        print('####', project.path_with_namespace)
        project.pprint()
        if hasattr(project, 'forked_from_project'):
            print(project.forked_from_project)
        print('')

    # forge = forge_details['gitlab']
    # for project in gitlab_api.projects.list(owned=True, iterator=True):
    #     print(project.path_with_namespace)


def get_remote_for_merge_request(context, forge_details):
    """Return the default remote for merge requests"""
    if len(forge_details) == 1:
        return list(forge_details)[0]
    default_remote = gitcmds.get_default_remote(context)
    if default_remote and default_remote in forge_details:
        return default_remote
    if 'origin' in forge_details:
        return 'origin'
    if forge_details:
        return list(forge_details)[0]
    return None
